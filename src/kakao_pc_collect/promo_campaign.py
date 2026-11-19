# [변경사유]: 단톡 홍보 예약 — 전송 순서·시각·보낸 방 기록. 카톡 창은 건드리지 않음
"""홍보 캠페인 파일 해석."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from kakao_pc_collect.config import RoomSpec
from kakao_pc_collect.logging_util import get_logger

log = get_logger(__name__)

# 한 방 안에서 이 순서만 사용. 값이 비어 있는 단계는 만들지 않는다.
# 1~3 공통(이미지·문구는 캠페인, 바로가기는 방), 4~6 은 방에 값이 있을 때만.
STEP_LABELS = ("image", "body", "url", "image2", "body2", "url2")


class PromoCampaignError(ValueError):
    """캠페인 파일·방 id·시각 형식 오류."""


@dataclass(frozen=True)
class PromoStep:
    """말풍선 하나. kind=image 는 파일 경로, kind=text 는 전송 문자열."""

    label: str
    kind: str
    value: str


@dataclass(frozen=True)
class PromoRoom:
    id: str
    url: str
    image2: str
    body2: str
    url2: str
    # [변경사유]: 예약 파일에서 방만 켜고 끈다. 생략은 true.
    enabled: bool = True


@dataclass(frozen=True)
class PromoCampaign:
    path: Path
    campaign_id: str
    # None 이면 명령 실행 시각에 바로 전송
    send_at: datetime | None
    image: str
    body: str
    rooms: tuple[PromoRoom, ...]


@dataclass(frozen=True)
class RoomPlan:
    id: str
    search: str
    steps: tuple[PromoStep, ...]


def sent_path_for(campaign_path: Path) -> Path:
    """캠페인 옆 기록. 성공한 방은 다음 실행에서 다시 보내지 않는다."""
    return campaign_path.with_name(campaign_path.name + ".sent.json")


def _enabled_flag(value: object, *, room_id: str) -> bool:
    """
    방 전송 스위치. 생략하면 true.
    true 일 때만 보내고, false 면 그 방은 건너뛴다.
    [변경사유]: faluse 같은 오타는 문자라서 참으로 읽히지 않게 한다.
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    raise PromoCampaignError(
        f"enabled 는 true 또는 false 여야 합니다: room={room_id} value={value!r}"
    )


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


# [변경사유]: 카톡은 말풍선 맨 앞·맨 뒤의 빈 줄을 지운다. 한글 채움은 빈 줄로 남는다.
KAKAO_EDGE_BREAK = "\u3164"

# body / body2 의 `|` 는 마지막 빈 줄을 파서가 버린다. `|+` 만 그 줄을 남긴다.
_BODY_CLIP = re.compile(
    r"^([ \t]*body2?:[ \t]*)\|([ \t]*(?:#.*)?)[ \t]*\r?$",
    re.MULTILINE,
)


def _preserve_body_block_breaks(raw: str) -> str:
    """
    body·body2 블록의 `|` 를 `|+` 로 읽어 마지막 빈 줄을 유지한다.
    [변경사유]: `|` 는 끝 빈 줄을 파서에 넘기기 전에 잘라 낸다.
    """

    def _keep(match: re.Match[str]) -> str:
        return f"{match.group(1)}|+{match.group(2)}"

    return _BODY_CLIP.sub(_keep, raw)


def _keep_visible_edge_breaks(text: str) -> str:
    """맨 앞·맨 뒤 빈 줄만 카톡이 지우지 못하는 글자로 바꾼다. 가운데 빈 줄은 그대로."""
    if not text:
        return ""
    lines = text.split("\n")
    start = 0
    while start < len(lines) and lines[start].strip() == "":
        lines[start] = KAKAO_EDGE_BREAK
        start += 1
    end = len(lines) - 1
    while end >= start and lines[end].strip() == "":
        lines[end] = KAKAO_EDGE_BREAK
        end -= 1
    return "\n".join(lines)


def _body_text(value: object) -> str:
    """
    홍보 문구. 앞에 둔 빈 줄과 `|+` 의 끝 빈 줄은 줄바꿈으로 남긴다.
    YAML 이 항상 붙이는 끝 개행 1개만 뺀다.
    [변경사유]: strip 은 첫줄·마지막 줄바꿈까지 지웠고, 카톡은 남은 빈 줄도 지운다.
    """
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    return _keep_visible_edge_breaks(text)


def _as_local_datetime(raw: object) -> datetime | None:
    """send_at. YAML 이 datetime/date 로 읽어도, 문자열이면 로컬 시각으로 받는다."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None)
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day)
    text = str(raw).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise PromoCampaignError(
        f"send_at 형식 오류: {text!r} — 예: 2026-11-21 10:00"
    )


def _resolve_media(raw: str, base_dir: Path) -> str:
    """이미지 경로. 상대 경로는 캠페인 파일이 있는 폴더 기준."""
    path = Path(raw)
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


def load_campaign(path: Path) -> PromoCampaign:
    """캠페인 YAML. 이미지·문구는 공통, url 과 2번 세트는 방별."""
    path = path.resolve()
    if not path.is_file():
        raise PromoCampaignError(f"캠페인 파일 없음: {path}")
    # [변경사유]: body/body2 의 `|` 가 마지막 빈 줄을 버리므로 읽기 전에 `|+` 로 맞춘다.
    raw_text = _preserve_body_block_breaks(path.read_text(encoding="utf-8"))
    raw = yaml.safe_load(raw_text) or {}
    if not isinstance(raw, dict):
        raise PromoCampaignError("캠페인 파일은 YAML 객체여야 합니다")
    rooms_raw = raw.get("rooms") or []
    if not isinstance(rooms_raw, list) or not rooms_raw:
        raise PromoCampaignError("rooms 가 비어 있습니다")
    rooms: list[PromoRoom] = []
    seen: set[str] = set()
    for item in rooms_raw:
        if not isinstance(item, dict):
            raise PromoCampaignError("rooms 항목은 id/url 객체여야 합니다")
        room_id = _clean(item.get("id"))
        if not room_id:
            raise PromoCampaignError("rooms.id 가 비어 있습니다")
        if room_id in seen:
            raise PromoCampaignError(f"rooms.id 중복: {room_id}")
        seen.add(room_id)
        rooms.append(
            PromoRoom(
                id=room_id,
                url=_clean(item.get("url")),
                image2=_clean(item.get("image2")),
                body2=_body_text(item.get("body2")),
                url2=_clean(item.get("url2")),
                enabled=_enabled_flag(item.get("enabled"), room_id=room_id),
            )
        )
    campaign_id = _clean(raw.get("id")) or path.stem
    campaign = PromoCampaign(
        path=path,
        campaign_id=campaign_id,
        send_at=_as_local_datetime(raw.get("send_at")),
        image=_clean(raw.get("image")),
        body=_body_text(raw.get("body")),
        rooms=tuple(rooms),
    )
    log.info(
        "promo campaign id=%s send_at=%s rooms=%s image=%s body_chars=%s file=%s",
        campaign.campaign_id,
        campaign.send_at.isoformat(sep=" ") if campaign.send_at else "(immediate)",
        len(campaign.rooms),
        bool(campaign.image),
        len(campaign.body),
        campaign.path.name,
    )
    return campaign


def build_steps(campaign: PromoCampaign, room: PromoRoom) -> tuple[PromoStep, ...]:
    """
    전송 말풍선.
    공통: 이미지 → 홍보문구 → 바로가기.
    방별 추가(값이 있을 때만): 이미지2 → 홍보문구2 → 바로가기2.
    """
    base = campaign.path.parent
    steps: list[PromoStep] = []
    if campaign.image:
        steps.append(PromoStep("image", "image", _resolve_media(campaign.image, base)))
    if campaign.body:
        steps.append(PromoStep("body", "text", campaign.body))
    if room.url:
        steps.append(PromoStep("url", "text", room.url))
    if room.image2:
        steps.append(PromoStep("image2", "image", _resolve_media(room.image2, base)))
    if room.body2:
        steps.append(PromoStep("body2", "text", room.body2))
    if room.url2:
        steps.append(PromoStep("url2", "text", room.url2))
    return tuple(steps)


def build_plans(
    campaign: PromoCampaign,
    room_specs: list[RoomSpec],
    *,
    only_ids: set[str] | None = None,
) -> list[RoomPlan]:
    """rooms.yaml 의 search 로 방을 찾고, 방마다 보낼 단계를 만든다."""
    by_id = {spec.id: spec for spec in room_specs}
    wanted = [room for room in campaign.rooms if only_ids is None or room.id in only_ids]
    if only_ids is not None:
        known = {room.id for room in campaign.rooms}
        missing = sorted(only_ids - known)
        if missing:
            raise PromoCampaignError(
                "캠페인에 없는 방 id: " + ", ".join(missing)
            )
    active = []
    for room in wanted:
        if room.enabled:
            active.append(room)
            continue
        log.info("promo skip disabled room=%s", room.id)
    if not active:
        disabled = ", ".join(room.id for room in wanted if not room.enabled)
        raise PromoCampaignError(
            "enabled: true 인 방이 없습니다"
            + (f" (꺼진 방: {disabled})" if disabled else "")
        )
    plans: list[RoomPlan] = []
    for room in active:
        spec = by_id.get(room.id)
        if spec is None:
            raise PromoCampaignError(
                f"rooms.yaml 에 없는 방 id: {room.id} — search 문자열을 알 수 없습니다"
            )
        steps = build_steps(campaign, room)
        if not steps:
            raise PromoCampaignError(f"방에 보낼 내용이 없습니다: {room.id}")
        plans.append(RoomPlan(id=room.id, search=spec.search, steps=steps))
        log.info(
            "promo plan room=%s search=%r steps=%s",
            room.id,
            spec.search,
            ",".join(step.label for step in steps),
        )
    return plans


def is_due(campaign: PromoCampaign, now: datetime) -> bool:
    """send_at 이 없거나 now 이상이면 전송 시각."""
    if campaign.send_at is None:
        return True
    return now >= campaign.send_at


def load_sent(path: Path) -> dict[str, dict]:
    """방 id → {ok, error, steps, at}. 파일 없으면 빈 기록."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    rooms = raw.get("rooms") if isinstance(raw, dict) else None
    if not isinstance(rooms, dict):
        return {}
    return {str(key): value for key, value in rooms.items() if isinstance(value, dict)}


def mark_sent(path: Path, room_id: str, record: dict) -> None:
    """방 하나 기록을 바로 저장. 중간에 끊겨도 이미 보낸 방은 남긴다."""
    rooms = load_sent(path)
    rooms[room_id] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"rooms": rooms}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(
        "promo sent record room=%s ok=%s file=%s",
        room_id,
        bool(record.get("ok")),
        path.name,
    )


def pending_plans(
    plans: list[RoomPlan],
    sent: dict[str, dict],
    *,
    force: bool,
) -> list[RoomPlan]:
    """ok 인 방은 건너뛴다. force 면 성공한 방도 다시 포함한다."""
    if force:
        return list(plans)
    pending: list[RoomPlan] = []
    for plan in plans:
        record = sent.get(plan.id) or {}
        if record.get("ok"):
            log.info("promo skip already sent room=%s", plan.id)
            continue
        pending.append(plan)
    return pending


def missing_image_files(plans: list[RoomPlan]) -> list[str]:
    """전송 전에 없는 이미지 경로. 본문 전송을 시작하지 않기 위해."""
    missing: list[str] = []
    seen: set[str] = set()
    for plan in plans:
        for step in plan.steps:
            if step.kind != "image" or step.value in seen:
                continue
            seen.add(step.value)
            if not Path(step.value).is_file():
                missing.append(f"{plan.id}:{step.label}:{step.value}")
    return missing

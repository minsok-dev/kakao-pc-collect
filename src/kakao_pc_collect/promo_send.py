# [변경사유]: 홍보 캠페인을 채팅 탭 검색으로 방마다 말풍선 단위 전송. 수집·완료 알림은 호출하지 않음
"""카카오톡 PC 홍보 전송."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from kakao_pc_collect.config import RoomSpec
from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.promo_campaign import (
    PromoCampaignError,
    PromoStep,
    RoomPlan,
    build_plans,
    is_due,
    load_campaign,
    load_sent,
    mark_sent,
    missing_image_files,
    pending_plans,
    sent_path_for,
)

log = get_logger(__name__)

# [변경사유]: 사진 붙여넣기 직후 Enter 가 글과 한 말풍선으로 합쳐지지 않게 간격을 둔다.
IMAGE_BEFORE_ENTER_SEC = 1.0
IMAGE_AFTER_ENTER_SEC = 1.2
TEXT_BEFORE_ENTER_SEC = 0.25
TEXT_AFTER_ENTER_SEC = 0.55
BETWEEN_ROOMS_SEC = 2.0


def _message_input_xy(hwnd: int, coords: Any) -> tuple[int, int]:
    """메시지 입력칸. coords.message_input 이 없으면 하단 중앙."""
    from kakao_pc_collect.win_click import window_client_size

    configured = getattr(coords, "message_input", None)
    if configured and isinstance(configured, tuple) and len(configured) >= 2:
        return int(configured[0]), int(configured[1])
    width, height = window_client_size(hwnd)
    return (max(40, width // 2), max(120, height - 55))


def _focus_input(hwnd: int, coords: Any) -> None:
    from kakao_pc_collect.win_click import bring_to_front, click_client

    bring_to_front(hwnd)
    time.sleep(0.2)
    click_client(hwnd, _message_input_xy(hwnd, coords), dry_run=False, label="promo_input")
    time.sleep(0.15)


def send_step_to_room(hwnd: int, step: PromoStep, coords: Any) -> None:
    """
    말풍선 하나.
    이미지는 클립보드 DIB 붙여넣기 후 Enter, 글·URL 은 텍스트 붙여넣기 후 Enter.
    """
    from kakao_pc_collect.win_click import (
        ctrl_v_if_foreground,
        paste_into_hwnd,
        press_enter_if_foreground,
        set_clipboard_image,
    )

    _focus_input(hwnd, coords)
    if step.kind == "image":
        set_clipboard_image(Path(step.value))
        if not ctrl_v_if_foreground(hwnd):
            raise RuntimeError("image_paste_failed")
        time.sleep(IMAGE_BEFORE_ENTER_SEC)
    else:
        if not paste_into_hwnd(hwnd, step.value):
            raise RuntimeError("text_paste_failed")
        time.sleep(TEXT_BEFORE_ENTER_SEC)
    if not press_enter_if_foreground(hwnd):
        raise RuntimeError("enter_failed")
    time.sleep(IMAGE_AFTER_ENTER_SEC if step.kind == "image" else TEXT_AFTER_ENTER_SEC)
    if step.kind == "image":
        log.info("promo sent step=%s kind=image file=%s", step.label, Path(step.value).name)
    else:
        # [변경사유]: 홍보 본문은 로그에 남기지 않는다. 길이만 남긴다.
        log.info("promo sent step=%s kind=text chars=%s", step.label, len(step.value))


def open_room_for_promo(search: str, coords: Any) -> tuple[int, str]:
    """
    채팅 탭 검색으로 방을 연다.
    창 제목에 search 가 없으면 전송하지 않는다.
    """
    from kakao_pc_collect.uia_kakao import (
        find_room_window,
        hwnd_of,
        open_room_by_search,
        title_is_room_match,
    )
    from kakao_pc_collect.win_click import window_title

    win = open_room_by_search(search, coords=coords, dry_run=False, side_tab="chats")
    hwnd = hwnd_of(win)
    title = window_title(hwnd) if hwnd else ""
    if not title_is_room_match(title, search):
        room2 = find_room_window(search, timeout=3.0)
        if room2 is not None:
            win = room2
            hwnd = hwnd_of(win)
            title = window_title(hwnd) if hwnd else ""
    if not title_is_room_match(title, search):
        log.error("promo abort title_mismatch search=%r title=%r", search, title)
        raise RuntimeError(f"title_mismatch:{title}")
    log.info("promo room open search=%r title=%r hwnd=%s", search, title, hwnd)
    return int(hwnd), title


def _step_public(step: PromoStep, *, include_text: bool) -> dict[str, Any]:
    item: dict[str, Any] = {
        "label": step.label,
        "kind": step.kind,
        "chars": len(step.value) if step.kind == "text" else 0,
    }
    if step.kind == "image":
        item["file"] = Path(step.value).name
    elif include_text:
        item["text"] = step.value
    return item


def _restore_chats_tab(coords: Any) -> None:
    """전송 후 채팅 탭. 다음 수집 검색이 친구 탭에 남지 않게."""
    from kakao_pc_collect.uia_kakao import ensure_chats_tab_on_main

    try:
        ensure_chats_tab_on_main(coords)
    except Exception:  # noqa: BLE001
        log.exception("promo ensure chats tab failed")


def run_promo(
    campaign_path: Path,
    room_specs: list[RoomSpec],
    *,
    coords: Any = None,
    dry_run: bool = False,
    force: bool = False,
    ignore_schedule: bool = False,
    now: datetime | None = None,
    only_ids: set[str] | None = None,
    opener: Callable[[str], tuple[int, str]] | None = None,
    sender: Callable[[int, PromoStep], None] | None = None,
) -> dict[str, Any]:
    """
    예약 시각이 지났고 아직 성공하지 않은 방에만 전송.
    dry_run 은 카톡을 열지 않고 순서만 돌려준다.
    opener/sender 는 테스트용. 없으면 PC 카톡 UI 를 사용한다.
    """
    campaign = load_campaign(campaign_path)
    moment = now or datetime.now()
    due = ignore_schedule or is_due(campaign, moment)
    plans = build_plans(campaign, room_specs, only_ids=only_ids)
    sent_path = sent_path_for(campaign.path)
    sent = load_sent(sent_path)
    pending = pending_plans(plans, sent, force=force)
    out: dict[str, Any] = {
        "ok": True,
        "campaign_id": campaign.campaign_id,
        "send_at": campaign.send_at.isoformat(sep=" ") if campaign.send_at else None,
        "dry_run": dry_run,
        "force": force,
        "rooms": [],
    }
    if not due and not dry_run:
        out["status"] = "not_due"
        log.info(
            "promo not due id=%s send_at=%s now=%s",
            campaign.campaign_id,
            out["send_at"],
            moment.isoformat(sep=" "),
        )
        return out
    if not pending:
        out["status"] = "already_sent"
        log.info("promo already sent id=%s file=%s", campaign.campaign_id, sent_path.name)
        return out

    missing = missing_image_files(pending)
    if missing:
        out["ok"] = False
        out["status"] = "missing_image"
        out["missing"] = missing
        log.error("promo missing image count=%s", len(missing))
        return out

    if dry_run:
        out["status"] = "dry_run"
        out["rooms"] = [
            {
                "id": plan.id,
                "search": plan.search,
                "ok": True,
                "steps": [_step_public(step, include_text=True) for step in plan.steps],
            }
            for plan in pending
        ]
        out["due"] = due
        log.info(
            "promo dry-run id=%s rooms=%s due=%s",
            campaign.campaign_id,
            len(pending),
            due,
        )
        return out

    use_ui = opener is None or sender is None
    if use_ui and (opener is not None or sender is not None):
        raise PromoCampaignError("opener 와 sender 는 함께 넘기거나 둘 다 비웁니다")
    open_room = opener or (lambda search: open_room_for_promo(search, coords))
    send_step = sender or (lambda hwnd, step: send_step_to_room(hwnd, step, coords))
    opened = False
    any_fail = False
    try:
        for index, plan in enumerate(pending):
            # [변경사유]: 테스트용 sender 에는 방 사이 대기를 걸지 않는다.
            if index > 0 and use_ui:
                time.sleep(BETWEEN_ROOMS_SEC)
            room_out: dict[str, Any] = {
                "id": plan.id,
                "search": plan.search,
                "ok": False,
                "steps": [step.label for step in plan.steps],
            }
            try:
                hwnd, title = open_room(plan.search)
                opened = True
                room_out["title"] = title
                for step in plan.steps:
                    send_step(hwnd, step)
                room_out["ok"] = True
                mark_sent(
                    sent_path,
                    plan.id,
                    {
                        "ok": True,
                        "steps": [step.label for step in plan.steps],
                        "at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                any_fail = True
                room_out["error"] = str(exc)
                log.exception("promo room fail id=%s", plan.id)
                mark_sent(
                    sent_path,
                    plan.id,
                    {
                        "ok": False,
                        "error": str(exc),
                        "steps": [step.label for step in plan.steps],
                        "at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
            out["rooms"].append(room_out)
    finally:
        if use_ui and opened:
            _restore_chats_tab(coords)
    out["ok"] = not any_fail
    out["status"] = "sent" if out["ok"] else "partial"
    log.info(
        "promo done id=%s status=%s rooms=%s",
        campaign.campaign_id,
        out["status"],
        len(out["rooms"]),
    )
    return out

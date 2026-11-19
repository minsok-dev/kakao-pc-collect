# [변경사유]: 홍보 말풍선 순서·예약 시각·성공 방 건너뛰기. UI 없음
"""promo campaign."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from kakao_pc_collect.config import RoomSpec
from kakao_pc_collect.promo_campaign import (
    KAKAO_EDGE_BREAK,
    PromoCampaignError,
    PromoStep,
    build_plans,
    load_campaign,
    load_sent,
    mark_sent,
    missing_image_files,
    pending_plans,
    sent_path_for,
)
from kakao_pc_collect.promo_send import (
    image_enter_hwnd,
    link_step,
    run_promo,
    text_pause_seconds,
)


def _specs() -> list[RoomSpec]:
    return [
        RoomSpec(id="gangnam_latin", search="강남 라틴클럽"),
        RoomSpec(id="hongdae_bonita", search="홍대보니따 오픈채팅방"),
    ]


def _write_campaign(folder: Path, body: str) -> Path:
    path = folder / "current.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"img")


def test_steps_image_body_url_then_optional_second_set(tmp_path: Path) -> None:
    poster = tmp_path / "poster.jpg"
    extra = tmp_path / "extra.jpg"
    _touch(poster)
    _touch(extra)
    path = _write_campaign(
        tmp_path,
        """
id: week
send_at: "2026-11-21 10:00"
image: poster.jpg
body: |
  공통 안내
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
  - id: hongdae_bonita
    url: "https://danceinfo.net/b"
    image2: extra.jpg
    body2: "추가 안내"
    url2: "https://danceinfo.net/b2"
""",
    )
    campaign = load_campaign(path)
    plans = build_plans(campaign, _specs())
    assert [step.label for step in plans[0].steps] == ["image", "body", "url"]
    assert plans[0].steps[1].value == "공통 안내"
    assert plans[0].steps[2].value == "https://danceinfo.net/a"
    assert [step.label for step in plans[1].steps] == [
        "image",
        "body",
        "url",
        "image2",
        "body2",
        "url2",
    ]
    assert plans[1].steps[3].value == str(extra.resolve())
    assert plans[1].steps[5].value == "https://danceinfo.net/b2"


def test_second_set_without_image2(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
image: ""
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
    body2: "문구2"
    url2: "https://danceinfo.net/a2"
""",
    )
    plans = build_plans(load_campaign(path), _specs())
    assert [step.label for step in plans[0].steps] == ["body", "url", "body2", "url2"]


def test_body_blank_edges_stay_as_line_breaks(tmp_path: Path) -> None:
    # [변경사유]: `|` 의 끝 빈 줄도 남기고, 카톡이 지우는 앞뒤 빈 줄은 채움 글자로 보낸다
    path = _write_campaign(
        tmp_path,
        """
image: ""
body: |

  공통 첫줄

  공통 끝
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
    body2: |

      - 한눈에 편하게!!!
      라틴 행사만 모아서 보세요~

""",
    )
    plans = build_plans(load_campaign(path), _specs())
    blank = KAKAO_EDGE_BREAK
    assert plans[0].steps[0].value == f"{blank}\n공통 첫줄\n\n공통 끝"
    assert plans[0].steps[2].value == (
        f"{blank}\n- 한눈에 편하게!!!\n라틴 행사만 모아서 보세요~\n{blank}"
    )


def test_link_step_waits_before_next_bubble() -> None:
    # [변경사유]: 주소 직후 다음 붙여넣기가 미리보기 중인 주소를 지웠다
    url = PromoStep("url", "text", "https://danceinfo.net/a")
    body = PromoStep("body", "text", "문구")
    assert link_step(url)
    assert link_step(PromoStep("url2", "text", "https://danceinfo.net/b"))
    assert not link_step(body)
    url_before, url_after = text_pause_seconds(url)
    body_before, body_after = text_pause_seconds(body)
    assert url_before > body_before
    assert url_after > body_after


def test_enabled_false_room_is_not_sent(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
body: "문구"
rooms:
  - id: gangnam_latin
    enabled: true
    url: "https://danceinfo.net/a"
  - id: hongdae_bonita
    enabled: false
    url: "https://danceinfo.net/b"
""",
    )
    plans = build_plans(load_campaign(path), _specs())
    assert [plan.id for plan in plans] == ["gangnam_latin"]


def test_enabled_omitted_still_sends(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
""",
    )
    plans = build_plans(load_campaign(path), _specs())
    assert [plan.id for plan in plans] == ["gangnam_latin"]


def test_enabled_typo_is_rejected(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
body: "문구"
rooms:
  - id: gangnam_latin
    enabled: faluse
    url: "https://danceinfo.net/a"
""",
    )
    with pytest.raises(PromoCampaignError, match="enabled"):
        load_campaign(path)


def test_all_rooms_disabled(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
body: "문구"
rooms:
  - id: gangnam_latin
    enabled: false
    url: "https://danceinfo.net/a"
""",
    )
    with pytest.raises(PromoCampaignError, match="enabled: true"):
        build_plans(load_campaign(path), _specs())


def test_blank_optional_fields_are_omitted(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
    image2: "  "
    body2: ""
    url2: ""
""",
    )
    plans = build_plans(load_campaign(path), _specs())
    assert [step.label for step in plans[0].steps] == ["body", "url"]


def test_unknown_room_id(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
body: "문구"
rooms:
  - id: missing_room
    url: "https://danceinfo.net/a"
""",
    )
    with pytest.raises(PromoCampaignError, match="rooms.yaml"):
        build_plans(load_campaign(path), _specs())


def test_dry_run_before_send_at_lists_steps(tmp_path: Path) -> None:
    poster = tmp_path / "poster.jpg"
    _touch(poster)
    path = _write_campaign(
        tmp_path,
        """
send_at: "2026-11-21 10:00"
image: poster.jpg
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
""",
    )
    opened: list[str] = []
    out = run_promo(
        path,
        _specs(),
        dry_run=True,
        now=datetime(2026, 11, 21, 9, 0),
        opener=lambda search: opened.append(search) or (1, search),
        sender=lambda hwnd, step: None,
    )
    assert out["status"] == "dry_run"
    assert out["due"] is False
    assert opened == []
    assert [step["label"] for step in out["rooms"][0]["steps"]] == ["image", "body", "url"]
    assert out["rooms"][0]["steps"][1]["text"] == "문구"


def test_not_due_does_not_open_room(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
send_at: "2026-11-21 10:00"
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
""",
    )
    opened: list[str] = []

    def _open(search: str) -> tuple[int, str]:
        opened.append(search)
        return 1, search

    out = run_promo(
        path,
        _specs(),
        now=datetime(2026, 11, 21, 9, 0),
        opener=_open,
        sender=lambda hwnd, step: None,
    )
    assert out["status"] == "not_due"
    assert out["ok"] is True
    assert opened == []


def test_send_order_and_skip_success_on_retry(tmp_path: Path) -> None:
    poster = tmp_path / "poster.jpg"
    _touch(poster)
    path = _write_campaign(
        tmp_path,
        """
send_at: "2026-11-21 10:00"
image: poster.jpg
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
  - id: hongdae_bonita
    url: "https://danceinfo.net/b"
    body2: "추가"
""",
    )
    calls: list[tuple[str, str]] = []

    def _open(search: str) -> tuple[int, str]:
        return 7, search

    def _send(hwnd: int, step) -> None:
        calls.append((str(hwnd), step.label))
        if step.label == "url" and step.value.endswith("/b"):
            raise RuntimeError("boom")

    first = run_promo(
        path,
        _specs(),
        now=datetime(2026, 11, 21, 10, 5),
        opener=_open,
        sender=_send,
    )
    assert first["status"] == "partial"
    assert calls == [
        ("7", "image"),
        ("7", "body"),
        ("7", "url"),
        ("7", "image"),
        ("7", "body"),
        ("7", "url"),
    ]
    sent = load_sent(sent_path_for(path))
    assert sent["gangnam_latin"]["ok"] is True
    assert sent["hongdae_bonita"]["ok"] is False

    calls.clear()

    def _send_ok(hwnd: int, step) -> None:
        calls.append((str(hwnd), step.label))

    second = run_promo(
        path,
        _specs(),
        now=datetime(2026, 11, 21, 10, 15),
        opener=_open,
        sender=_send_ok,
    )
    assert second["status"] == "sent"
    assert [label for _hwnd, label in calls] == ["image", "body", "url", "body2"]
    assert load_sent(sent_path_for(path))["hongdae_bonita"]["ok"] is True


def test_dry_run_checks_missing_image_and_skips_kakao(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
image: missing.jpg
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
""",
    )
    out = run_promo(
        path,
        _specs(),
        dry_run=True,
        now=datetime(2026, 11, 21, 12, 0),
        opener=lambda search: (_ for _ in ()).throw(AssertionError("opened")),
        sender=lambda hwnd, step: None,
    )
    assert out["status"] == "missing_image"
    assert out["ok"] is False


def test_force_resends_done_room(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
""",
    )
    mark_sent(sent_path_for(path), "gangnam_latin", {"ok": True, "steps": ["body", "url"]})
    plans = build_plans(load_campaign(path), _specs())
    assert pending_plans(plans, load_sent(sent_path_for(path)), force=False) == []
    assert len(pending_plans(plans, load_sent(sent_path_for(path)), force=True)) == 1


def test_image_enter_goes_to_clipboard_dialog() -> None:
    assert (
        image_enter_hwnd(
            room_hwnd=10,
            foreground_hwnd=99,
            foreground_title="클립보드 이미지 전송",
            dialog_hwnd=77,
        )
        == 77
    )
    assert (
        image_enter_hwnd(
            room_hwnd=10,
            foreground_hwnd=10,
            foreground_title="댄스인포관리자",
            dialog_hwnd=None,
        )
        == 10
    )
    assert (
        image_enter_hwnd(
            room_hwnd=10,
            foreground_hwnd=3,
            foreground_title="메모장",
            dialog_hwnd=None,
        )
        is None
    )
    # [변경사유]: 전송 창 제목이 비어 있으면 같은 프로세스일 때만 Enter
    assert (
        image_enter_hwnd(
            room_hwnd=10,
            foreground_hwnd=99,
            foreground_title="",
            dialog_hwnd=None,
            foreground_same_process=True,
        )
        == 99
    )
    assert (
        image_enter_hwnd(
            room_hwnd=10,
            foreground_hwnd=99,
            foreground_title="",
            dialog_hwnd=None,
            foreground_same_process=False,
        )
        is None
    )


def test_missing_image_helper(tmp_path: Path) -> None:
    path = _write_campaign(
        tmp_path,
        """
image: no-such.jpg
body: "문구"
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/a"
""",
    )
    plans = build_plans(load_campaign(path), _specs())
    missing = missing_image_files(plans)
    assert len(missing) == 1
    assert "no-such.jpg" in missing[0]

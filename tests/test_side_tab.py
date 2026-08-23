# [변경사유]: 친구/채팅 탭 좌표·side_tab 분기 단위 테스트
"""ensure_side_tab / open_room side_tab / coords 로드."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kakao_pc_collect.config import CoordConfig, load_coords
from kakao_pc_collect.uia_kakao import ensure_side_tab


def test_load_coords_friends_chats_tabs(tmp_path: Path) -> None:
    p = tmp_path / "coords.yaml"
    p.write_text(
        "friends_tab: [31, 59]\nchats_tab: [33, 119]\n",
        encoding="utf-8",
    )
    cfg = load_coords(p)
    assert cfg.friends_tab == (31, 59)
    assert cfg.chats_tab == (33, 119)


def test_load_coords_default_tabs_when_missing(tmp_path: Path) -> None:
    p = tmp_path / "coords.yaml"
    p.write_text("main_search: [213, 106]\n", encoding="utf-8")
    cfg = load_coords(p)
    # [변경사유]: F: 로컬 실측 기본값
    assert cfg.friends_tab == (33, 56)
    assert cfg.chats_tab == (30, 118)


def test_ensure_side_tab_clicks_friends() -> None:
    coords = CoordConfig(friends_tab=(33, 56), chats_tab=(30, 118))
    with patch("kakao_pc_collect.win_click.click_client") as click:
        ensure_side_tab(1, coords, "friends")
    click.assert_called_once()
    args, kwargs = click.call_args
    assert args[1] == (33, 56)
    assert kwargs.get("label") == "friends_tab"


def test_ensure_side_tab_clicks_chats() -> None:
    coords = CoordConfig(friends_tab=(33, 56), chats_tab=(30, 118))
    with patch("kakao_pc_collect.win_click.click_client") as click:
        ensure_side_tab(1, coords, "chats")
    args, _kwargs = click.call_args
    assert args[1] == (30, 118)


def test_ensure_side_tab_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        ensure_side_tab(1, CoordConfig(), "settings")


def test_send_admin_summary_uses_friends_tab_and_restores_chats() -> None:
    from kakao_pc_collect.admin_notify import send_admin_summary

    coords = MagicMock()
    fake_win = MagicMock()
    with (
        patch(
            "kakao_pc_collect.admin_notify.open_room_by_search",
            return_value=fake_win,
        ) as open_room,
        patch("kakao_pc_collect.admin_notify.hwnd_of", return_value=42),
        patch(
            "kakao_pc_collect.admin_notify.window_title",
            return_value="댄스인포관리자",
        ),
        patch(
            "kakao_pc_collect.admin_notify.title_is_room_match",
            return_value=True,
        ),
        patch("kakao_pc_collect.admin_notify.focus_window"),
        patch("kakao_pc_collect.admin_notify.click_client"),
        patch(
            "kakao_pc_collect.admin_notify.paste_into_hwnd",
            return_value=True,
        ),
        patch("kakao_pc_collect.admin_notify._press_enter"),
        patch(
            "kakao_pc_collect.admin_notify.ensure_chats_tab_on_main"
        ) as restore,
        patch(
            "kakao_pc_collect.admin_notify._message_input_xy",
            return_value=(100, 900),
        ),
    ):
        out = send_admin_summary(
            search="댄스인포관리자",
            text="요약",
            coords=coords,
            dry_run=False,
        )
    assert out["ok"] is True
    assert open_room.call_args.kwargs.get("side_tab") == "friends"
    restore.assert_called_once_with(coords)

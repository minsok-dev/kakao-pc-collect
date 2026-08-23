# [변경사유]: I5 — 관리자 1:1/방에 실행 요약 카톡 전송 (opt-in, UI 자동화)
"""검색 → 창 제목 검증 → 입력칸 붙여넣기 → Enter."""

from __future__ import annotations

import time
from typing import Any

from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.uia_kakao import (
    ensure_chats_tab_on_main,
    find_room_window,
    focus_window,
    hwnd_of,
    open_room_by_search,
    title_is_room_match,
)
from kakao_pc_collect.win_click import (
    click_client,
    paste_into_hwnd,
    window_client_size,
    window_title,
)

log = get_logger(__name__)


def _message_input_xy(hwnd: int, coords: Any) -> tuple[int, int]:
    """메시지 입력칸 client 좌표. coords.message_input 없으면 하단 중앙 추정."""
    configured = getattr(coords, "message_input", None)
    if configured and isinstance(configured, tuple) and len(configured) >= 2:
        return int(configured[0]), int(configured[1])
    w, h = window_client_size(hwnd)
    # [변경사유]: 방 창 하단 입력줄 — 헤더/☰ 피해서 가로 중앙·하단
    return (max(40, w // 2), max(120, h - 55))


def _press_enter(hwnd: int) -> None:
    import win32api
    import win32con
    import win32gui

    if int(win32gui.GetForegroundWindow()) != int(hwnd):
        log.warning("enter skipped — not foreground hwnd=%s", hwnd)
        return
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    time.sleep(0.04)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)


def send_admin_summary(
    *,
    search: str,
    text: str,
    coords: Any = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    관리자 친구 닉네임으로 1:1 연 뒤 요약 전송.
    [변경사유]: 친구 탭 검색만 사용 — 채팅 탭 통합검색은 오픈채팅·방명이 섞여 오발송 위험.
    [변경사유]: 전송 후(성공/실패 무관) 채팅 탭 복귀 — 다음 방 수집 대비.
    [변경사유]: 창 제목에 search 가 포함될 때만 전송 — 오발송 방지
    """
    out: dict[str, Any] = {
        "ok": False,
        "search": search,
        "chars": len(text or ""),
        "dry_run": dry_run,
        "side_tab": "friends",
    }
    search = (search or "").strip()
    text = (text or "").strip()
    if not search or not text:
        out["error"] = "empty_search_or_text"
        return out
    if dry_run:
        out["ok"] = True
        out["skipped"] = "dry_run"
        log.info("admin-notify dry-run search=%r chars=%s", search, len(text))
        return out

    try:
        # [변경사유]: 친구 탭에서만 검색 — open_room_by_search(side_tab=friends)
        win = open_room_by_search(
            search, coords=coords, dry_run=False, side_tab="friends"
        )
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"open_room:{exc}"
        log.exception("admin-notify open_room fail search=%r", search)
        # [변경사유]: 실패해도 채팅 탭 복귀 — 다음 스케줄 방 수집 보호
        if coords is not None:
            ensure_chats_tab_on_main(coords)
        return out

    try:
        hwnd = hwnd_of(win)
        title = window_title(hwnd) if hwnd else ""
        # [변경사유]: 제목 재확인 — 첫 검색 결과가 다른 방이면 전송 금지
        if not title_is_room_match(title, search):
            # open 직후 제목이 아직 안 바뀌면 find 재시도
            room2 = find_room_window(search, timeout=3.0)
            if room2 is not None:
                win = room2
                hwnd = hwnd_of(win)
                title = window_title(hwnd) if hwnd else ""
        if not title_is_room_match(title, search):
            out["error"] = "title_mismatch"
            out["title"] = title
            log.error(
                "admin-notify abort title_mismatch search=%r title=%r",
                search,
                title,
            )
            return out

        focus_window(win)
        time.sleep(0.25)
        xy = _message_input_xy(hwnd, coords)
        click_client(hwnd, xy, dry_run=False, label="message_input")
        time.sleep(0.2)
        if not paste_into_hwnd(hwnd, text):
            out["error"] = "paste_failed"
            return out
        time.sleep(0.15)
        _press_enter(hwnd)
        time.sleep(0.3)
        out["ok"] = True
        out["title"] = title
        log.info(
            "admin-notify sent search=%r title=%r chars=%s", search, title, len(text)
        )
        return out
    finally:
        # [변경사유]: 친구 탭에 남으면 이후 방 수집 검색이 실패하므로 채팅 탭 복귀
        if coords is not None:
            ensure_chats_tab_on_main(coords)

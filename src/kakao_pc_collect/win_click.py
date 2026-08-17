# [변경사유]: 창 클라이언트 상대 좌표 클릭 — 절대 화면 좌표 금지
"""윈도우 상대 클릭."""

from __future__ import annotations

import time
from typing import Any

from kakao_pc_collect.logging_util import get_logger

log = get_logger(__name__)


def _client_origin(hwnd: int) -> tuple[int, int]:
    import win32gui

    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    return int(left), int(top)


def window_client_size(hwnd: int) -> tuple[int, int]:
    import win32gui

    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return int(right - left), int(bottom - top)


def click_client(
    hwnd: int,
    xy: tuple[int, int],
    *,
    dry_run: bool = False,
    label: str = "",
) -> None:
    """클라이언트 (x,y) 클릭."""
    import win32api
    import win32con
    import win32gui

    ox, oy = _client_origin(hwnd)
    sx, sy = ox + int(xy[0]), oy + int(xy[1])
    log.info(
        "click_client label=%s hwnd=%s client=%s screen=%s dry_run=%s",
        label or "-",
        hwnd,
        xy,
        (sx, sy),
        dry_run,
    )
    if dry_run:
        return
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    win32api.SetCursorPos((sx, sy))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.04)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)


def foreground_hwnd() -> int:
    import win32gui

    return int(win32gui.GetForegroundWindow())


def print_cursor_client_offset(hwnd: int | None = None) -> tuple[int, int]:
    """캘리브레이션용 — 현재 커서의 창 클라이언트 오프셋."""
    import win32api
    import win32gui

    hwnd = hwnd or foreground_hwnd()
    cx, cy = win32api.GetCursorPos()
    ox, oy = _client_origin(hwnd)
    off = (cx - ox, cy - oy)
    title = win32gui.GetWindowText(hwnd)
    size = window_client_size(hwnd)
    log.info(
        "calibrate title=%r hwnd=%s client_size=%s cursor_client=%s",
        title,
        hwnd,
        size,
        off,
    )
    return off


def find_hwnd_by_title_contains(substr: str) -> int | None:
    import win32gui

    found: list[int] = []

    def _enum(hwnd: int, _lparam: Any) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd) or ""
        if substr in title:
            found.append(int(hwnd))
        return True

    win32gui.EnumWindows(_enum, None)
    return found[0] if found else None

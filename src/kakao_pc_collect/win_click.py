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


def set_client_size(
    hwnd: int,
    width: int,
    height: int,
    *,
    tol: int = 6,
) -> tuple[int, int]:
    """
    클라이언트 크기를 목표로 맞춤. 위치는 유지.
    [변경사유]: 방마다 기억된 크기가 달라 ☰ 좌표가 창 밖으로 나가는 것 방지.
    """
    import win32con
    import win32gui

    cur = window_client_size(hwnd)
    if abs(cur[0] - width) <= tol and abs(cur[1] - height) <= tol:
        log.info("client size already ok hwnd=%s size=%s", hwnd, cur)
        return cur
    wr_l, wr_t, wr_r, wr_b = win32gui.GetWindowRect(hwnd)
    outer_w = int(wr_r - wr_l)
    outer_h = int(wr_b - wr_t)
    chrome_w = outer_w - cur[0]
    chrome_h = outer_h - cur[1]
    new_w = int(width) + chrome_w
    new_h = int(height) + chrome_h
    log.info(
        "set_client_size hwnd=%s from=%s target=%s outer %sx%s -> %sx%s",
        hwnd,
        cur,
        (width, height),
        outer_w,
        outer_h,
        new_w,
        new_h,
    )
    win32gui.SetWindowPos(
        hwnd,
        None,
        0,
        0,
        new_w,
        new_h,
        win32con.SWP_NOMOVE | win32con.SWP_NOZORDER,
    )
    time.sleep(0.25)
    after = window_client_size(hwnd)
    log.info("set_client_size after hwnd=%s size=%s", hwnd, after)
    return after


def right_anchored_xy(
    xy: tuple[int, int],
    *,
    calibrated_size: tuple[int, int],
    actual_size: tuple[int, int],
) -> tuple[int, int]:
    """
    우측 고정 버튼(☰ 등). 캘리브레이션 창에서 오른쪽 여백을 실제 너비에 적용.
    예: 424폭에서 x=402 → 여백 22. 385폭이면 x=363.
    """
    x, y = int(xy[0]), int(xy[1])
    cal_w = int(calibrated_size[0])
    act_w = int(actual_size[0])
    if cal_w <= 0 or act_w <= 0:
        return (x, y)
    margin_r = cal_w - x
    nx = act_w - margin_r
    return (nx, y)


def bring_to_front(hwnd: int) -> bool:
    """
    전경 창으로.
    [변경사유]: fg hwnd=0 이면 AttachThreadInput(87). Alt 키 트릭으로 SetForegroundWindow 허용.
    """
    import win32api
    import win32con
    import win32gui
    import win32process

    if not hwnd or not win32gui.IsWindow(hwnd):
        log.warning("bring_to_front invalid hwnd=%s", hwnd)
        return False
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    except Exception:  # noqa: BLE001
        pass

    try:
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.05)
    if int(win32gui.GetForegroundWindow() or 0) == int(hwnd):
        return True

    # 백그라운드 프로세스 제한 — Alt 는 실패할 때만 (메뉴가 열리는 부작용 방지)
    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception as exc:  # noqa: BLE001
        log.warning("SetForegroundWindow hwnd=%s err=%s", hwnd, exc)
    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

    cur_tid = win32api.GetCurrentThreadId()
    tgt_tid, _tgt_pid = win32process.GetWindowThreadProcessId(hwnd)
    fg = win32gui.GetForegroundWindow()
    fg_tid = 0
    if fg:
        fg_tid, _ = win32process.GetWindowThreadProcessId(fg)

    attached: list[int] = []
    for tid in (fg_tid, tgt_tid):
        if not tid or tid == cur_tid:
            continue
        try:
            win32process.AttachThreadInput(cur_tid, tid, True)
            attached.append(tid)
        except Exception as exc:  # noqa: BLE001
            log.warning("AttachThreadInput skip tid=%s err=%s", tid, exc)

    try:
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception as exc:  # noqa: BLE001
        log.warning("SetForegroundWindow hwnd=%s err=%s", hwnd, exc)
    finally:
        for tid in attached:
            try:
                win32process.AttachThreadInput(cur_tid, tid, False)
            except Exception:  # noqa: BLE001
                pass

    time.sleep(0.12)
    fg_now = win32gui.GetForegroundWindow()
    ok = int(fg_now) == int(hwnd)
    if not ok:
        log.warning(
            "bring_to_front still fg=%s want=%s fg_title=%r",
            fg_now,
            hwnd,
            window_title(int(fg_now)) if fg_now else "",
        )
    return ok


def window_title(hwnd: int) -> str:
    import win32gui

    try:
        return win32gui.GetWindowText(hwnd) or ""
    except Exception:  # noqa: BLE001
        return ""


def _foreground_is_browser() -> bool:
    """실제 마우스 클릭이 크롬으로 새는지 전경 제목으로 판별."""
    title = window_title(foreground_hwnd()) or ""
    return any(m in title for m in ("Chrome", "Edge", "Firefox", "Google Chrome"))


def click_client(
    hwnd: int,
    xy: tuple[int, int],
    *,
    dry_run: bool = False,
    label: str = "",
) -> None:
    """클라이언트 (x,y) 클릭 — 해당 hwnd 로 WM 클릭 + 실제 마우스."""
    import win32api
    import win32con
    import win32gui

    size = window_client_size(hwnd)
    ox, oy = _client_origin(hwnd)
    sx, sy = ox + int(xy[0]), oy + int(xy[1])
    log.info(
        "click_client label=%s hwnd=%s client=%s screen=%s size=%s dry_run=%s",
        label or "-",
        hwnd,
        xy,
        (sx, sy),
        size,
        dry_run,
    )
    # [변경사유]: 창 밖 클릭이 크롬 등 다른 창으로 새는 것 차단
    if (
        int(xy[0]) < 0
        or int(xy[1]) < 0
        or int(xy[0]) >= size[0]
        or int(xy[1]) >= size[1]
    ):
        raise RuntimeError(
            f"click {label or '-'} client={xy} 가 창 밖 size={size} — "
            "창 크기를 캘리브레이션과 맞추거나 hamburger를 우측 기준으로 재계산하세요."
        )
    if dry_run:
        return
    bring_to_front(hwnd)
    time.sleep(0.12)
    # [변경사유]: 긴 배치 후 전경이 크롬이면 물리 클릭이 브라우저로 감
    if _foreground_is_browser():
        log.warning(
            "foreground is browser title=%r — refocus hwnd=%s",
            window_title(foreground_hwnd()),
            hwnd,
        )
        bring_to_front(hwnd)
        time.sleep(0.25)
    if _foreground_is_browser():
        raise RuntimeError(
            "전경이 브라우저라 클릭하지 않음 — 카톡 창을 앞으로 두고 다시 실행하세요. "
            f"fg={window_title(foreground_hwnd())!r}"
        )
    # [변경사유]: 커서가 다른 모니터에 있어도 이 창 좌표로 클릭이 들어가게
    lparam = win32api.MAKELONG(max(0, int(xy[0])), max(0, int(xy[1])))
    try:
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(0.04)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
    except Exception as exc:  # noqa: BLE001
        log.warning("PostMessage click fail err=%s", exc)
    # [변경사유]: PostMessage 직후 전경이 브라우저면 물리 클릭은 보내지 않음
    if _foreground_is_browser():
        log.warning(
            "skip physical mouse fg=%r label=%s",
            window_title(foreground_hwnd()),
            label or "-",
        )
        return
    win32api.SetCursorPos((sx, sy))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.04)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)


def click_chat_body(hwnd: int, *, dry_run: bool = False) -> None:
    """
    헤더(☰)·하단 입력칸을 피해 대화 본문을 클릭.
    [변경사유]: Ctrl+S 직전에 쓰지 말 것 — 포스터를 열어 이미지 저장이 됨.
    """
    w, h = window_client_size(hwnd)
    # 가로 중앙(☰ 은 우측), 세로는 헤더·입력칸 사이
    xy = (max(40, w // 2), max(80, int(h * 0.42)))
    click_client(hwnd, xy, dry_run=dry_run, label="chat_body")


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


def find_hwnd_by_title_contains(substr: str, *, parent: int | None = None) -> int | None:
    """최상위 또는 parent 자식 중 제목 포함 hwnd."""
    import win32gui

    found: list[int] = []

    def _enum(hwnd: int, _lparam: Any) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd) or ""
        if substr in title:
            found.append(int(hwnd))
        return True

    if parent:
        try:
            win32gui.EnumChildWindows(parent, _enum, None)
        except Exception:  # noqa: BLE001
            pass
        if found:
            return found[0]
    win32gui.EnumWindows(_enum, None)
    return found[0] if found else None


def set_clipboard_text(text: str) -> None:
    import win32clipboard
    import win32con

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def paste_into_hwnd(hwnd: int, text: str) -> bool:
    """
    클립보드 설정 후, 전경이 hwnd 일 때만 Ctrl+V.
    전경이 아니면 키를 보내지 않음 (친구 추가/Cursor 로 입력이 새는 것 방지).
    """
    import win32api
    import win32con
    import win32gui

    set_clipboard_text(text)
    ok = bring_to_front(hwnd)
    fg = win32gui.GetForegroundWindow()
    if int(fg) != int(hwnd):
        log.warning(
            "paste skipped — foreground is not target fg=%s title=%r",
            fg,
            window_title(int(fg)) if fg else "",
        )
        return False
    time.sleep(0.08)
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord("V"), 0, 0, 0)
    time.sleep(0.04)
    win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
    log.info("paste_into_hwnd ok hwnd=%s chars=%s", hwnd, len(text))
    return True


def paste_unicode(text: str) -> None:
    """하위 호환 — 전경 창에 Ctrl+V. 검색 입력은 paste_into_hwnd 사용."""
    from pywinauto.keyboard import send_keys

    set_clipboard_text(text)
    send_keys("^v")

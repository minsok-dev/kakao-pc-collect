# [변경사유]: 검색 Edit + Enter 방 열기, Ctrl+S 대화 내보내기 (표준 저장창)
"""카카오톡 UIA / 키보드."""

from __future__ import annotations

import time
from pathlib import Path

from kakao_pc_collect.logging_util import get_logger

log = get_logger(__name__)

KAKAO_TITLE = "카카오톡"
SAVE_AS_TITLE = "다른 이름으로 저장"
DRAWER_TITLE = "채팅방 서랍"


def _desktop():
    from pywinauto import Desktop

    return Desktop(backend="uia")


def title_is_room_match(title: str, search: str) -> bool:
    """방 창 제목이 검색어를 포함하는지 (메인/서랍/저장창 제외)."""
    if not title or not search:
        return False
    if SAVE_AS_TITLE in title or DRAWER_TITLE in title:
        return False
    # 메인 목록 창은 보통 제목이 정확히 '카카오톡'
    if title.strip() == KAKAO_TITLE:
        return False
    return search in title


def _iter_top_windows():
    """UIA 최상위 창. 실패 항목은 건너뜀."""
    try:
        wins = _desktop().windows()
    except Exception as exc:  # noqa: BLE001
        log.warning("desktop.windows fail err=%s", exc)
        return
    for w in wins:
        try:
            title = w.window_text() or ""
        except Exception:
            continue
        yield w, title


def _log_candidate_windows() -> list[str]:
    titles: list[str] = []
    for _w, title in _iter_top_windows():
        if not title:
            continue
        if KAKAO_TITLE in title or DRAWER_TITLE in title:
            titles.append(title)
            log.info("kakao candidate title=%r", title)
    return titles


def find_kakao_window(*, timeout: float = 10.0):
    """메인 목록 창(검색 Edit 있는 '카카오톡') 우선. 없으면 제목에 카카오톡 포함."""
    deadline = time.time() + timeout
    last_err: Exception | None = None
    fallback = None
    while time.time() < deadline:
        try:
            for w, title in _iter_top_windows():
                if SAVE_AS_TITLE in title or DRAWER_TITLE in title:
                    continue
                if title.strip() != KAKAO_TITLE and KAKAO_TITLE not in title:
                    continue
                edits = _list_edits(w)
                log.info(
                    "kakao window title=%r edit_count=%s",
                    title,
                    len(edits),
                )
                if edits:
                    return w
                if fallback is None:
                    fallback = w
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.3)
    if fallback is not None:
        log.warning("search Edit 없는 카카오톡 창으로 fallback")
        return fallback
    _log_candidate_windows()
    raise RuntimeError(f"카카오톡 창을 찾지 못함: {last_err}")


def find_room_window(search: str, *, timeout: float = 8.0):
    """제목에 검색어가 들어 있는 채팅방 창."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for w, title in _iter_top_windows():
            if title_is_room_match(title, search):
                log.info("room window title=%r search=%r", title, search)
                return w
        time.sleep(0.25)
    return None


def _list_edits(win) -> list:
    try:
        return list(win.descendants(control_type="Edit"))
    except Exception as exc:  # noqa: BLE001
        log.warning("descendants Edit fail err=%s", exc)
        return []


def focus_window(win) -> None:
    try:
        win.set_focus()
    except Exception:
        try:
            win.wrapper_object().set_focus()
        except Exception as exc:  # noqa: BLE001
            log.warning("set_focus fail err=%s", exc)
    time.sleep(0.25)


def hwnd_of(win) -> int:
    return int(win.handle)


def find_search_edit(win):
    """메인 검색 Edit — SearchListCtrl 하위 우선."""
    edits = _list_edits(win)
    if not edits:
        return None
    # 보통 목록 검색이 첫 Edit 중 하나. 가장 위쪽(top 작음) 선택
    ranked = sorted(edits, key=lambda e: e.rectangle().top)
    edit = ranked[0]
    log.info(
        "search edit top=%s left=%s",
        edit.rectangle().top,
        edit.rectangle().left,
    )
    return edit


def open_room_by_search(search: str, *, dry_run: bool = False):
    """
    이미 열린 방 창이 있으면 그걸 사용.
    없으면 메인 '카카오톡' 검색 → Enter.
    반환=채팅방 창 (Ctrl+S / ☰ 대상).
    """
    from pywinauto.keyboard import send_keys

    existing = find_room_window(search, timeout=1.5)
    if existing is not None:
        log.info("open_room already_open search=%r dry_run=%s", search, dry_run)
        focus_window(existing)
        return existing

    main = find_kakao_window()
    focus_window(main)
    edit = find_search_edit(main)
    log.info("open_room search=%r dry_run=%s has_edit=%s", search, dry_run, edit is not None)
    if edit is None:
        titles = _log_candidate_windows()
        raise RuntimeError(
            "검색 Edit 없음 — 메인 창에서 채팅 탭을 연 뒤 검색창이 보이게 하세요. "
            f"후보 창={titles!r}"
        )
    if dry_run:
        return main

    edit.set_focus()
    time.sleep(0.15)
    send_keys("^a{BACKSPACE}")
    time.sleep(0.1)
    edit.set_edit_text(search)
    time.sleep(0.35)
    send_keys("{ENTER}")
    time.sleep(1.2)

    room_win = find_room_window(search, timeout=8.0)
    if room_win is None:
        log.warning("room window not found after search — using main")
        return main
    focus_window(room_win)
    return room_win


def export_chat_txt(
    win,
    chats_dir: Path,
    *,
    dry_run: bool = False,
) -> None:
    """
    Ctrl+S → 저장 창. 파일명 자동, 경로는 chats_dir.
    마지막 폴더가 이미 chats면 저장만 눌러도 됨 — 경로는 안전하게 재지정.
    """
    from pywinauto.keyboard import send_keys

    chats_dir.mkdir(parents=True, exist_ok=True)
    focus_window(win)
    log.info("export_chat_txt chats_dir=%s dry_run=%s", chats_dir, dry_run)
    if dry_run:
        return

    send_keys("^s")
    time.sleep(0.8)
    desk = _desktop()
    save = None
    for _ in range(25):
        try:
            cands = desk.windows(title_re=f".*{SAVE_AS_TITLE}.*")
            if cands:
                save = cands[0]
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
    if save is None:
        raise RuntimeError("「다른 이름으로 저장」 창이 뜨지 않음 — 방 포커스·Ctrl+S 확인")

    focus_window(save)
    time.sleep(0.2)
    # 파일 이름 콤보/Edit 는 건드리지 않음 (카톡 자동 생성)
    # 주소 표시줄로 경로 이동: Alt+D → 경로 → Enter
    send_keys("%d")
    time.sleep(0.2)
    path_str = str(chats_dir.resolve())
    send_keys("^a")
    time.sleep(0.05)
    # 중괄호·공백 이스케이프: type_keys with with_spaces
    send_keys(path_str, with_spaces=True)
    send_keys("{ENTER}")
    time.sleep(0.5)
    # 저장 버튼
    try:
        btn = save.child_window(title="저장(S)", control_type="Button")
        if btn.exists(timeout=1):
            btn.click()
        else:
            send_keys("{ENTER}")
    except Exception:
        send_keys("{ENTER}")
    time.sleep(0.8)
    log.info("export_chat_txt done")

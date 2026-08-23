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
FRIEND_ADD_TITLE = "친구 추가"
# 시각 타이틀일 뿐 Win32 Name 은 비어 있음 — 제목 검색에 쓰지 않음
EXPORT_DIALOG_TITLE = "대화 내보내기"
# [변경사유]: 제목에 검색어가 있는 브라우저를 방 창으로 오인하지 않음
BROWSER_MARKERS = (
    "Chrome",
    "Edge",
    "Firefox",
    "Google 검색",
    "Cursor",
    "Claude",
)


def _desktop():
    from pywinauto import Desktop

    return Desktop(backend="uia")


def is_browser_title(title: str) -> bool:
    """브라우저·에디터 창 — 카톡 메인/방과 구분."""
    t = title or ""
    return any(m in t for m in BROWSER_MARKERS)


def title_is_room_match(title: str, search: str) -> bool:
    """방 창 제목이 검색어를 포함하는지 (메인/서랍/저장창/브라우저 제외)."""
    if not title or not search:
        return False
    if SAVE_AS_TITLE in title or DRAWER_TITLE in title or EXPORT_DIALOG_TITLE in title:
        return False
    if is_browser_title(title):
        return False
    # 메인 목록 창은 보통 제목이 정확히 '카카오톡'
    if title.strip() == KAKAO_TITLE:
        return False
    return search in title


def classify_save_wait(
    *,
    elapsed: float,
    found: bool,
    fg_title: str,
    room_title: str,
) -> str:
    """
    저장 창 대기 상태. 느림 vs 키 씹힘 구분용.
    found / waiting_kakao / focus_lost / waiting
    """
    if found:
        return "found"
    fg = fg_title or ""
    if SAVE_AS_TITLE in fg:
        return "found"
    if room_title and room_title[:12] in fg:
        return "waiting_kakao"
    if KAKAO_TITLE in fg:
        return "waiting_kakao"
    if fg:
        return "focus_lost"
    return "waiting"


def _txt_names(chats_dir: Path) -> set[str]:
    if not chats_dir.is_dir():
        return set()
    return {p.name for p in chats_dir.glob("*.txt")}


def _txt_sizes(chats_dir: Path, names: set[str]) -> dict[str, int]:
    """새 txt 바이트 크기. 쓰기가 끝나기 전에는 값이 변한다."""
    out: dict[str, int] = {}
    for name in names:
        path = chats_dir / name
        try:
            out[name] = int(path.stat().st_size) if path.is_file() else -1
        except OSError:
            out[name] = -1
    return out


def txt_write_is_stable(
    prev: dict[str, int] | None, curr: dict[str, int]
) -> bool:
    """
    새 txt 크기가 이전과 같고 0보다 크면 쓰기 완료.
    [변경사유]: 팝업 Name 없음 — 파일 크기로 완료 판정.
    """
    if not curr or prev is None:
        return False
    if prev != curr:
        return False
    return all(sz > 0 for sz in curr.values())


def _fg_is_room(fg: str, room_title: str) -> bool:
    if not fg or not room_title:
        return False
    return fg == room_title or room_title[:12] in fg


def dismiss_export_complete_dialog(
    *,
    room_hwnd: int,
    room_title: str,
    chats_dir: Path,
    txt_before: set[str],
    wait_sec: float = 300.0,
    stable_sec: float = 1.8,
) -> None:
    """
    새 txt 크기가 멈출 때까지 대기 → Enter(확인).
    [변경사유]: 팝업은 Name 없는 방 자식 창. 제목 검색 불가. 포커스 있으면 Enter.
    진행 중 Enter 는 취소가 될 수 있어 파일 안정화 후에만 보낸다.
    """
    from pywinauto.keyboard import send_keys

    from kakao_pc_collect.win_click import foreground_hwnd, window_title

    log.info(
        "wait export txt wait_sec=%.0f stable_sec=%.1f room_hwnd=%s",
        wait_sec,
        stable_sec,
        room_hwnd,
    )
    started = time.time()
    last_beat = 0.0
    last_state = ""
    last_sizes: dict[str, int] | None = None
    stable_since: float | None = None
    new_txt: set[str] = set()

    while time.time() - started < wait_sec:
        elapsed = time.time() - started
        new_txt = _txt_names(chats_dir) - txt_before
        sizes = _txt_sizes(chats_dir, new_txt)
        fg = window_title(foreground_hwnd())
        if new_txt and txt_write_is_stable(last_sizes, sizes):
            if stable_since is None:
                stable_since = time.time()
        else:
            stable_since = None
        last_sizes = sizes
        stable_for = (time.time() - stable_since) if stable_since else 0.0
        if not new_txt:
            state = "waiting_txt"
        elif stable_for >= stable_sec:
            state = "txt_stable"
        else:
            state = "txt_writing"
        if state != last_state or (elapsed - last_beat) >= 2.0:
            log.info(
                "export-txt wait elapsed=%.1fs state=%s fg=%r new_txt=%s sizes=%s",
                elapsed,
                state,
                fg,
                sorted(new_txt),
                sizes,
            )
            last_beat = elapsed
            last_state = state
        if state == "txt_stable":
            break
        time.sleep(0.35)
    else:
        raise RuntimeError(
            f"내보내기 txt 가 {wait_sec:.0f}초 안에 완성되지 않음. "
            f"new_txt={sorted(new_txt)}"
        )

    fg = window_title(foreground_hwnd())
    # 팝업이 이미 없고 방만 전경이면 Enter 가 채팅 입력으로 감
    if _fg_is_room(fg, room_title):
        log.info("export popup already gone fg=%r — skip Enter", fg)
        return

    # 방 창을 올리지 않음 — 완료 팝업이 포커스를 갖고 있어야 Enter=확인
    log.info("export txt stable — Enter (확인) fg=%r", fg)
    send_keys("{ENTER}")
    gone_deadline = time.time() + 8.0
    while time.time() < gone_deadline:
        fg2 = window_title(foreground_hwnd())
        if _fg_is_room(fg2, room_title):
            log.info("export popup dismissed fg=%r", fg2)
            return
        time.sleep(0.25)
    log.info(
        "export popup still up — Enter retry fg=%r",
        window_title(foreground_hwnd()),
    )
    send_keys("{ENTER}")
    time.sleep(0.5)
    fg3 = window_title(foreground_hwnd())
    if not _fg_is_room(fg3, room_title):
        raise RuntimeError(
            "Enter 후에도 방 창이 전경이 아님 "
            f"(fg={fg3!r}). 완료 팝업이 남아 있으면 ☰ 가 막힙니다."
        )


def _confirm_save_as(save_hwnd: int, *, wait_sec: float = 12.0) -> None:
    """
    「다른 이름으로 저장」에서 저장(S).
    [변경사유]: 주소창 Enter 는 폴더 이동만 하고 저장 버튼을 누르지 않음.
    """
    from pywinauto.keyboard import send_keys

    from kakao_pc_collect.win_click import (
        bring_to_front,
        find_hwnd_by_title_contains,
        foreground_hwnd,
        window_title,
    )

    bring_to_front(save_hwnd)
    time.sleep(0.15)
    log.info("save-dialog confirm Alt+S (저장)")
    send_keys("%s")
    started = time.time()
    last_beat = 0.0
    retried = False
    while time.time() - started < wait_sec:
        elapsed = time.time() - started
        still = find_hwnd_by_title_contains(SAVE_AS_TITLE)
        fg = window_title(foreground_hwnd())
        if still is None and SAVE_AS_TITLE not in (fg or ""):
            log.info("save-dialog closed elapsed=%.1fs fg=%r", elapsed, fg)
            return
        if elapsed - last_beat >= 2.0:
            log.info(
                "save-dialog closing elapsed=%.1fs fg=%r still=%s",
                elapsed,
                fg,
                still,
            )
            last_beat = elapsed
        # 덮어쓰기 확인 창이면 Enter
        if fg and SAVE_AS_TITLE not in fg and "확인" in fg:
            log.info("save overwrite prompt fg=%r — Enter", fg)
            send_keys("{ENTER}")
        # 주소창에 포커스가 남은 경우 Alt+S 재시도 1회
        if not retried and elapsed >= 2.5 and still is not None:
            log.info("save-dialog still open — Alt+S retry")
            bring_to_front(still)
            send_keys("%s")
            retried = True
        time.sleep(0.25)
    raise RuntimeError(
        "「다른 이름으로 저장」이 닫히지 않음 — 저장(S)이 눌리지 않았습니다. "
        "주소창이 아니라 저장 버튼에 포커스가 있는지 확인하세요."
    )


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
        if (
            KAKAO_TITLE in title
            or DRAWER_TITLE in title
            or EXPORT_DIALOG_TITLE in title
        ):
            titles.append(title)
            log.info("kakao candidate title=%r", title)
    return titles


def find_kakao_window(*, timeout: float = 10.0):
    """메인 목록 창 — 제목이 정확히 '카카오톡' 인 창만 (브라우저 제외)."""
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            for w, title in _iter_top_windows():
                if is_browser_title(title):
                    continue
                if (
                    SAVE_AS_TITLE in title
                    or DRAWER_TITLE in title
                    or EXPORT_DIALOG_TITLE in title
                ):
                    continue
                # [변경사유]: '카카오톡' 포함만 보면 Chrome 탭 제목에 걸림
                if title.strip() != KAKAO_TITLE:
                    continue
                edits = _list_edits(w)
                log.info(
                    "kakao window title=%r edit_count=%s search_open=%s",
                    title,
                    len(edits),
                    is_search_bar_open_by_edit_count(len(edits)),
                )
                # [변경사유]: 검색창 닫힘(Edit=0)이어도 메인 창은 바로 반환 — 10초 대기 금지
                return w
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.3)
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


def is_search_bar_open_by_edit_count(edit_count: int) -> bool:
    """메인 창 Edit 1개 이상이면 검색 입력창 열림. 0이면 닫힘."""
    return int(edit_count or 0) > 0


def search_bar_is_open(win) -> bool:
    """UIA Edit 유무로 검색창 열림 판정. 카톡 내부 상태는 없음."""
    n = len(_list_edits(win))
    open_ = is_search_bar_open_by_edit_count(n)
    log.info("search_bar_is_open edit_count=%s open=%s", n, open_)
    return open_


def ensure_search_bar_open(win, hwnd: int, coords) -> None:
    """
    검색창이 닫혀 있으면 돋보기 1회만 클릭 후 Edit 재확인.
    이미 열려 있으면 돋보기를 누르지 않음 (토글이라 닫힘).
    """
    from kakao_pc_collect.win_click import click_client

    if search_bar_is_open(win):
        return
    log.info(
        "search bar closed — click search_icon once client=%s",
        coords.search_icon,
    )
    click_client(hwnd, coords.search_icon, dry_run=False, label="search_icon")
    deadline = time.time() + 2.5
    while time.time() < deadline:
        time.sleep(0.25)
        if search_bar_is_open(win):
            log.info("search bar opened after search_icon")
            return
    raise RuntimeError(
        "검색 입력창이 열리지 않음 — 돋보기 좌표(search_icon)를 재측정하거나 "
        "실행 전에 검색창을 열어 두세요. 돋보기는 토글이라 두 번 누르면 닫힙니다."
    )


def ensure_side_tab(hwnd: int, coords, tab: str) -> None:
    """
    메인 창 왼쪽 레일 탭 전환.
    [변경사유]: 방 수집=채팅 탭, 관리자 알림=친구 탭. 탭이 다르면 검색 결과가 달라지고
    친구 탭에 남으면 이후 방 수집이 실패한다.
    tab: "chats" | "friends"
    """
    from kakao_pc_collect.win_click import click_client

    key = (tab or "chats").strip().lower()
    if key not in ("chats", "friends"):
        raise ValueError(f"side_tab must be chats|friends, got {tab!r}")
    xy = coords.chats_tab if key == "chats" else coords.friends_tab
    label = "chats_tab" if key == "chats" else "friends_tab"
    log.info("ensure_side_tab tab=%s client=%s", key, xy)
    click_client(hwnd, xy, dry_run=False, label=label)
    time.sleep(0.35)


def ensure_chats_tab_on_main(coords) -> None:
    """
    메인 목록을 찾아 채팅 탭으로 복귀.
    [변경사유]: 관리자 알림(친구 탭) 이후 다음 방 수집을 위해 필수.
    """
    try:
        main = find_kakao_window()
        hwnd = hwnd_of(main)
        focus_window(main)
        ensure_side_tab(hwnd, coords, "chats")
    except Exception as exc:  # noqa: BLE001
        log.warning("ensure_chats_tab_on_main fail err=%s", exc)


def replace_search_text_via_tab(hwnd: int, search: str) -> bool:
    """
    검색칸 클릭 → Tab → Shift+Tab(전체 선택) → 붙여넣기.
    Ctrl+A 금지(카톡=친구 추가). X 클릭 금지(입력창이 닫힘).
    """
    from pywinauto.keyboard import send_keys

    from kakao_pc_collect.win_click import paste_into_hwnd

    log.info("search replace Tab, Shift+Tab then paste chars=%s", len(search))
    send_keys("{TAB}")
    time.sleep(0.2)
    send_keys("+{TAB}")
    time.sleep(0.2)
    return paste_into_hwnd(hwnd, search)


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


def _dismiss_friend_add(*, kakao_hwnd: int | None = None) -> bool:
    """친구 추가 모달이 있으면 ESC. 있으면 True."""
    from pywinauto.keyboard import send_keys

    from kakao_pc_collect.win_click import (
        bring_to_front,
        find_hwnd_by_title_contains,
    )

    hwnd = find_hwnd_by_title_contains(FRIEND_ADD_TITLE)
    if hwnd is None and kakao_hwnd:
        hwnd = find_hwnd_by_title_contains(FRIEND_ADD_TITLE, parent=kakao_hwnd)
    if hwnd is None:
        return False
    log.info("dismiss friend-add hwnd=%s", hwnd)
    bring_to_front(hwnd)
    time.sleep(0.15)
    send_keys("{ESC}")
    time.sleep(0.35)
    return True


def open_room_by_search(
    search: str,
    *,
    coords=None,
    dry_run: bool = False,
    side_tab: str = "chats",
):
    """
    이미 열린 방 창이 있으면 그걸 사용.
    없으면 메인 목록에서 (side_tab) 탭 → 검색창 확인 → 입력칸 클릭 → Tab/Shift+Tab → 붙여넣기 → 첫 결과.
    Ctrl+A 금지(친구 추가). 돋보기는 검색창 닫힘일 때만 1회.
    [변경사유]: side_tab=chats(방 수집) / friends(관리자 1:1). 기본 chats.
    """
    from kakao_pc_collect.config import CoordConfig
    from kakao_pc_collect.win_click import click_client, set_client_size

    cfg = coords if coords is not None else CoordConfig()
    tab = (side_tab or "chats").strip().lower() or "chats"

    existing = find_room_window(search, timeout=1.5)
    if existing is not None:
        log.info("open_room already_open search=%r dry_run=%s", search, dry_run)
        focus_window(existing)
        return existing

    main = find_kakao_window()
    hwnd = hwnd_of(main)
    focus_window(main)
    # [변경사유]: 메인 목록도 기억된 크기가 있음 — 검색 좌표 전에 맞춤
    set_client_size(hwnd, cfg.main_client_size[0], cfg.main_client_size[1])
    _dismiss_friend_add(kakao_hwnd=hwnd)
    # [변경사유]: 검색 전 탭 고정 — 친구 탭에 있으면 방 검색이 안 됨
    ensure_side_tab(hwnd, cfg, tab)
    log.info(
        "open_room search=%r dry_run=%s side_tab=%s hwnd=%s main_search=%s "
        "first_result=%s search_icon=%s",
        search,
        dry_run,
        tab,
        hwnd,
        cfg.main_search,
        cfg.first_search_result,
        cfg.search_icon,
    )
    if dry_run:
        return main

    # [변경사유]: Edit=0 이면 닫힘 — 돋보기 1회. 열려 있으면 누르지 않음.
    ensure_search_bar_open(main, hwnd, cfg)

    # 1) 검색칸 클릭 — Ctrl+A·X 금지
    click_client(hwnd, cfg.main_search, dry_run=False, label="main_search")
    time.sleep(0.35)
    if _dismiss_friend_add(kakao_hwnd=hwnd):
        log.warning("friend-add opened after search click — retry search click")
        click_client(hwnd, cfg.main_search, dry_run=False, label="main_search_retry")
        time.sleep(0.35)

    pasted = replace_search_text_via_tab(hwnd, search)
    if not pasted:
        raise RuntimeError(
            "검색어를 카카오톡 창에 붙여넣지 못함 — 전경이 카톡이 아님. "
            "터미널에서 직접 실행하고, 실행 중 다른 창을 클릭하지 마세요."
        )
    time.sleep(0.5)
    if _dismiss_friend_add(kakao_hwnd=hwnd):
        raise RuntimeError(
            "검색 입력 중 「친구 추가」가 열림 — 검색칸 좌표가 헤더 아이콘과 겹칩니다. "
            "calibrate --title 카카오톡 으로 main_search 를 검색 입력줄 한가운데로 다시 재세요."
        )

    # 2) 첫 검색결과 행
    click_client(
        hwnd, cfg.first_search_result, dry_run=False, label="first_search_result"
    )
    time.sleep(1.2)

    room_win = find_room_window(search, timeout=8.0)
    if room_win is None:
        log.info("room window missing after click — try Enter")
        from pywinauto.keyboard import send_keys

        send_keys("{ENTER}")
        time.sleep(1.0)
        room_win = find_room_window(search, timeout=6.0)
    if room_win is None:
        log.warning("room window not found after search — using main")
        return main
    focus_window(room_win)
    return room_win


def _ensure_room_foreground(hwnd: int, room_title: str) -> None:
    """
    방 창을 전경으로. 이미지 뷰어·잔여 저장창이 앞에 있으면 ESC 후 재시도.
    [변경사유]: 본문 클릭이 포스터를 열어 Ctrl+S 가 이미지 저장으로 감.
    """
    from pywinauto.keyboard import send_keys

    from kakao_pc_collect.win_click import bring_to_front, foreground_hwnd, window_title

    def _is_room(fg: str) -> bool:
        if not fg:
            return False
        if room_title and (fg == room_title or room_title[:12] in fg):
            return True
        return False

    bring_to_front(hwnd)
    time.sleep(0.15)
    fg = window_title(foreground_hwnd())
    if _is_room(fg) and SAVE_AS_TITLE not in fg:
        log.info("room foreground ok title=%r", fg)
        return
    log.info("overlay in front fg=%r — ESC then refocus room", fg)
    send_keys("{ESC}")
    time.sleep(0.35)
    if SAVE_AS_TITLE in (window_title(foreground_hwnd()) or ""):
        send_keys("{ESC}")
        time.sleep(0.25)
    bring_to_front(hwnd)
    time.sleep(0.15)
    fg2 = window_title(foreground_hwnd())
    log.info("room foreground after overlay close fg=%r", fg2)


def export_chat_txt(
    win,
    chats_dir: Path,
    *,
    dry_run: bool = False,
    wait_sec: float = 45.0,
) -> None:
    """
    방 창 전경 확인 후 Ctrl+S 만 (본문 클릭 없음).
    파일명 자동, 경로는 chats_dir.
    """
    from pywinauto.keyboard import send_keys

    from kakao_pc_collect.win_click import (
        bring_to_front,
        find_hwnd_by_title_contains,
        foreground_hwnd,
        paste_unicode,
        window_title,
    )

    chats_dir.mkdir(parents=True, exist_ok=True)
    hwnd = hwnd_of(win)
    room_title = window_title(hwnd)
    log.info(
        "export_chat_txt chats_dir=%s dry_run=%s hwnd=%s room_title=%r",
        chats_dir,
        dry_run,
        hwnd,
        room_title,
    )
    if dry_run:
        return

    # [변경사유]: 방 열림 후 클릭 없이 Ctrl+S — 본문 클릭이 이미지를 염
    _ensure_room_foreground(hwnd, room_title)
    fg_before = window_title(foreground_hwnd())
    log.info("ctrl+s send fg_before=%r (no chat_body click)", fg_before)
    send_keys("^s")
    log.info("ctrl+s sent — waiting save dialog up to %.0fs", wait_sec)

    started = time.time()
    save_hwnd: int | None = None
    last_beat = 0.0
    last_state = ""
    while time.time() - started < wait_sec:
        elapsed = time.time() - started
        save_hwnd = find_hwnd_by_title_contains(SAVE_AS_TITLE)
        fg = window_title(foreground_hwnd())
        state = classify_save_wait(
            elapsed=elapsed,
            found=save_hwnd is not None,
            fg_title=fg,
            room_title=room_title,
        )
        # 하트비트: 2초마다 또는 상태가 바뀔 때
        if state != last_state or (elapsed - last_beat) >= 2.0:
            log.info(
                "save-dialog wait elapsed=%.1fs state=%s fg=%r save_hwnd=%s",
                elapsed,
                state,
                fg,
                save_hwnd,
            )
            last_beat = elapsed
            last_state = state
        if save_hwnd is not None or state == "found":
            if save_hwnd is None:
                save_hwnd = foreground_hwnd()
            log.info("save-dialog found elapsed=%.1fs hwnd=%s", elapsed, save_hwnd)
            break
        # 키가 다른 창으로 간 것이 분명하면 짧게 재시도 후 실패 메시지에 반영
        if state == "focus_lost" and elapsed >= 6.0:
            log.warning(
                "Ctrl+S 전경이 방이 아님 — 키가 씹혔을 가능성 fg=%r",
                fg,
            )
            break
        time.sleep(0.35)

    if save_hwnd is None:
        fg = window_title(foreground_hwnd())
        state = classify_save_wait(
            elapsed=time.time() - started,
            found=False,
            fg_title=fg,
            room_title=room_title,
        )
        if state == "focus_lost":
            raise RuntimeError(
                "「다른 이름으로 저장」 창이 없음 — Ctrl+S가 방 창에 전달되지 않음 "
                f"(전경={fg!r}). 실행 중 다른 창을 클릭하지 마세요."
            )
        raise RuntimeError(
            "「다른 이름으로 저장」 창이 없음 — 카톡 내보내기 준비(느림)이거나 "
            f"단축키가 무시됨 (전경={fg!r}, {time.time() - started:.0f}초 대기). "
            "방 창을 클릭한 뒤 직접 Ctrl+S가 되는지만 확인하세요."
        )

    bring_to_front(save_hwnd)
    time.sleep(0.25)
    # 파일 이름 필드는 건드리지 않음 (카톡 자동 생성)
    # 주소 표시줄: Alt+D → 경로 붙여넣기 → Enter → Alt+S(저장)
    # [변경사유]: 주소창에 포커스가 남으면 Enter 가 저장이 아니라 경로 확인만 됨
    txt_before = _txt_names(chats_dir)
    log.info("save-dialog set folder chats_dir=%s txt_before=%s", chats_dir, len(txt_before))
    send_keys("%d")
    time.sleep(0.25)
    send_keys("^a")
    time.sleep(0.05)
    paste_unicode(str(chats_dir.resolve()))
    time.sleep(0.2)
    send_keys("{ENTER}")
    time.sleep(0.6)
    _confirm_save_as(save_hwnd)
    dismiss_export_complete_dialog(
        room_hwnd=hwnd,
        room_title=room_title,
        chats_dir=chats_dir,
        txt_before=txt_before,
    )
    bring_to_front(hwnd)
    log.info("export_chat_txt done")

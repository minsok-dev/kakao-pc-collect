# [변경사유]: 서랍 좌표 3곳 + 가상스크롤 Shift 선택 + 다운로드 클릭
"""서랍 사진 배치."""

from __future__ import annotations

import time
from pathlib import Path

from kakao_pc_collect.config import CoordConfig
from kakao_pc_collect.files import (
    copy_new_images,
    snapshot_mtimes,
    snapshot_names,
    wait_for_new_files,
)
from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.uia_kakao import hwnd_of
from kakao_pc_collect.win_click import (
    bring_to_front,
    click_client,
    find_hwnd_by_title_contains,
    right_anchored_xy,
    set_client_size,
    window_client_size,
)

log = get_logger(__name__)

DRAWER_TITLE = "채팅방 서랍"
FILE_SAVE_TITLE = "파일 저장"


def _send(keys: str) -> None:
    from pywinauto.keyboard import send_keys

    send_keys(keys)


def open_drawer(
    room_hwnd: int,
    coords: CoordConfig,
    *,
    dry_run: bool = False,
    drawer_menu_downs_override: int | None = None,
) -> int:
    """☰ → 서랍 → 사진/동영상. 반환=서랍 hwnd.

    drawer_menu_downs_override:
        None  → coords.drawer_menu_downs (coords.yaml 전역값)
        정수   → 방별 설정 우선 (room_type 에서 결정한 값)
    """
    # [변경사유]: 이미지 뷰어가 앞에 있으면 ☰·키가 빗나감 — 방 창 전경 후 클릭
    bring_to_front(room_hwnd)
    time.sleep(0.2)
    # [변경사유]: 방마다 기억된 너비가 다름 — 캘리브레이션 크기로 맞춘 뒤 ☰
    set_client_size(room_hwnd, coords.room_client_size[0], coords.room_client_size[1])
    room_size = window_client_size(room_hwnd)
    hamburger = right_anchored_xy(
        coords.hamburger,
        calibrated_size=coords.room_client_size,
        actual_size=room_size,
    )
    log.info(
        "hamburger click xy=%s calibrated=%s actual_size=%s",
        hamburger,
        coords.hamburger,
        room_size,
    )
    click_client(room_hwnd, hamburger, dry_run=dry_run, label="hamburger")
    time.sleep(0.45)

    if coords.use_menu_coords:
        click_client(
            room_hwnd, coords.drawer_menu, dry_run=dry_run, label="drawer_menu"
        )
        time.sleep(0.35)
        click_client(
            room_hwnd,
            coords.photos_submenu,
            dry_run=dry_run,
            label="photos_submenu",
        )
    else:
        # [변경사유]: 방 타입별 Down 횟수 — 오픈 단톡방×2, 일반 단톡방×3
        # drawer_menu_downs_override 가 있으면 coords 전역값 대신 사용
        dmd = (
            drawer_menu_downs_override
            if drawer_menu_downs_override is not None
            else coords.drawer_menu_downs
        )
        log.info(
            "drawer_menu_downs=%s (override=%s coords=%s)",
            dmd,
            drawer_menu_downs_override,
            coords.drawer_menu_downs,
        )
        for _ in range(max(0, dmd)):
            _send("{DOWN}")
            time.sleep(0.08)
        _send("{RIGHT}")
        time.sleep(0.15)
        for _ in range(max(0, coords.photos_menu_downs)):
            _send("{DOWN}")
            time.sleep(0.08)
        _send("{ENTER}")

    time.sleep(1.0)
    if dry_run:
        return room_hwnd

    hwnd = find_hwnd_by_title_contains(DRAWER_TITLE)
    if hwnd is None:
        # 일부 빌드는 제목이 다를 수 있음 — 잠시 대기 후 재시도
        time.sleep(0.8)
        hwnd = find_hwnd_by_title_contains(DRAWER_TITLE)
    if hwnd is None:
        raise RuntimeError(
            f"「{DRAWER_TITLE}」 창을 찾지 못함 — coords hamburger/drawer_menu 캘리브레이션"
        )
    w, h = window_client_size(hwnd)
    set_client_size(hwnd, coords.drawer_client_size[0], coords.drawer_client_size[1])
    w, h = window_client_size(hwnd)
    ew, eh = coords.drawer_client_size
    if abs(w - ew) > 80 or abs(h - eh) > 80:
        log.warning(
            "drawer size mismatch actual=%s expected=%s — 좌표 재측정 권장",
            (w, h),
            (ew, eh),
        )
    log.info("drawer hwnd=%s size=%s", hwnd, (w, h))
    return hwnd


def _arrow_sequence(coords: CoordConfig, presses: int) -> list[str]:
    # [변경사유]: 기본 right — Shift 범위 선택과 맞춤 (지그재그 DOWN/LEFT 는 선택 깨짐)
    mode = (coords.arrow_mode or "right").lower()
    cols = max(1, coords.grid_columns)
    keys: list[str] = []
    if mode == "right":
        keys = ["{RIGHT}"] * presses
    elif mode == "down":
        keys = ["{DOWN}"] * presses
    else:
        # right_then_down 등 — 한 키=한 칸 지그재그 (레거시, Shift 선택에 비권장)
        keys = _snake_sequence(presses, cols)
    return keys


def _snake_sequence(presses: int, cols: int) -> list[str]:
    """좌상단에서 가로로 채운 뒤 한 칸 내려 반대 방향."""
    cols = max(1, int(cols))
    keys: list[str] = []
    col = 0
    direction = 1
    for _ in range(max(0, presses)):
        nxt = col + direction
        if 0 <= nxt < cols:
            keys.append("{RIGHT}" if direction == 1 else "{LEFT}")
            col = nxt
        else:
            keys.append("{DOWN}")
            direction = -direction
    return keys


def _home_to_first_tile(coords: CoordConfig) -> None:
    """
    위·왼쪽을 더 이상 못 갈 때까지 이동 = 첫 이미지.
    [변경사유]: first_photo 좌표는 그리드 포커스용. 맨 앞 칸이 아님.
    """
    ups = max(40, coords.preload_arrow_presses)
    lefts = max(10, coords.grid_columns + 4)
    log.info("home first-tile up=%s left=%s", ups, lefts)
    for _ in range(ups):
        _send("{UP}")
        time.sleep(0.03)
    for _ in range(lefts):
        _send("{LEFT}")
        time.sleep(0.03)
    time.sleep(0.2)


def select_photo_batch(
    drawer_hwnd: int,
    coords: CoordConfig,
    *,
    skip_tiles: int = 0,
    dry_run: bool = False,
) -> None:
    """
    포커스 → 첫 칸 → Shift 없이 칸 로드 → 첫 칸 → skip → Shift+방향키로 최대 50칸.
    [변경사유]: 방향키로 지나지 않은 칸은 선택이 안 됨. 50 초과 시 다운로드 비활성.
    [변경사유]: arrow_mode=right 권장 — Shift+RIGHT만(줄 끝은 UI가 다음 줄). 지그재그는 선택 깨짐.
    """
    n = max(1, min(50, coords.select_count))
    skip = max(0, int(skip_tiles))
    preload = max(n + skip, coords.preload_arrow_presses)

    click_client(
        drawer_hwnd, coords.first_photo, dry_run=dry_run, label="first_photo"
    )
    time.sleep(0.25)
    if dry_run:
        return

    _home_to_first_tile(coords)

    # Shift 없이 지나가서 가상스크롤 로드 (초기 화면 밖 칸)
    log.info("preload tiles=%s skip=%s n=%s", preload, skip, n)
    for key in _arrow_sequence(coords, preload):
        _send(key)
        time.sleep(0.04)
    time.sleep(0.25)

    _home_to_first_tile(coords)

    if skip:
        for key in _arrow_sequence(coords, skip):
            _send(key)
            time.sleep(0.03)
        time.sleep(0.15)

    for key in _arrow_sequence(coords, n - 1):
        _send("+" + key)
        time.sleep(0.05)
    time.sleep(0.2)
    log.info("select_photo_batch count=%s skip=%s (max 50)", n, skip)


def click_download(
    drawer_hwnd: int,
    coords: CoordConfig,
    *,
    dry_run: bool = False,
) -> None:
    click_client(
        drawer_hwnd, coords.download, dry_run=dry_run, label="download"
    )
    time.sleep(0.5)
    if dry_run:
        return
    # [변경사유]: 저장 중 다음 배치로 가면 안 됨 — 「파일 저장」창이 닫힐 때까지
    _wait_file_save_dialog()


def _wait_file_save_dialog(
    *,
    appear_sec: float = 12.0,
    complete_sec: float = 180.0,
) -> None:
    """제목 「파일 저장」이 떴다가 사라질 때까지. 취소는 누르지 않음."""
    from kakao_pc_collect.win_click import (
        find_hwnd_by_title_contains,
        foreground_hwnd,
        window_title,
    )

    started = time.time()
    seen = False
    last_beat = 0.0
    while time.time() - started < appear_sec:
        hwnd = find_hwnd_by_title_contains(FILE_SAVE_TITLE)
        fg = window_title(foreground_hwnd())
        if hwnd is not None or FILE_SAVE_TITLE in (fg or ""):
            seen = True
            log.info(
                "file-save appeared elapsed=%.1fs hwnd=%s fg=%r",
                time.time() - started,
                hwnd,
                fg,
            )
            break
        time.sleep(0.3)
    if not seen:
        log.info(
            "file-save not seen in %.0fs — 폴더 감시로 이어감",
            appear_sec,
        )
        return

    wait_start = time.time()
    while time.time() - wait_start < complete_sec:
        elapsed = time.time() - wait_start
        hwnd = find_hwnd_by_title_contains(FILE_SAVE_TITLE)
        fg = window_title(foreground_hwnd())
        gone = hwnd is None and FILE_SAVE_TITLE not in (fg or "")
        if gone:
            log.info("file-save closed elapsed=%.1fs", elapsed)
            return
        if elapsed - last_beat >= 2.0:
            log.info("file-save waiting elapsed=%.1fs fg=%r", elapsed, fg)
            last_beat = elapsed
        time.sleep(0.4)
    log.warning("file-save still open after %.0fs", complete_sec)


def download_one_batch(
    *,
    room_win,
    coords: CoordConfig,
    download_dir: Path,
    photos_dir: Path,
    skip_tiles: int = 0,
    dry_run: bool = False,
    drawer_menu_downs_override: int | None = None,
) -> list[str]:
    """
    서랍 열고 50칸 선택·다운로드·photos 복사.
    반환=이번에 복사된(또는 dry_run이면 감지된) 이미지 파일명.
    drawer_menu_downs_override: 방 타입별 Down 횟수 (None=coords 전역값 사용).
    """
    room_hwnd = hwnd_of(room_win)
    # [변경사유]: 방 타입별 drawer_menu_downs 우선 적용
    drawer_hwnd = open_drawer(
        room_hwnd, coords, dry_run=dry_run,
        drawer_menu_downs_override=drawer_menu_downs_override,
    )
    select_photo_batch(
        drawer_hwnd, coords, skip_tiles=skip_tiles, dry_run=dry_run
    )
    # [변경사유]: 다운로드 직전 스냅샷 — 덮어쓰기도 새 배치로 본다
    before = snapshot_names(download_dir)
    before_mtime = snapshot_mtimes(download_dir)
    click_download(drawer_hwnd, coords, dry_run=dry_run)

    if dry_run:
        return []

    new_names = wait_for_new_files(
        download_dir, before=before, before_mtime=before_mtime
    )
    copied = copy_new_images(
        download_dir=download_dir,
        photos_dir=photos_dir,
        names=new_names,
    )
    log.info(
        "batch done detected=%s copied=%s",
        len(new_names),
        len(copied),
    )
    return copied if copied else new_names

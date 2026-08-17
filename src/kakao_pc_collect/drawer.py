# [변경사유]: 서랍 좌표 3곳 + 가상스크롤 Shift 선택 + 다운로드 클릭
"""서랍 사진 배치."""

from __future__ import annotations

import time
from pathlib import Path

from kakao_pc_collect.config import CoordConfig
from kakao_pc_collect.files import (
    copy_new_images,
    snapshot_names,
    wait_for_new_files,
)
from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.uia_kakao import hwnd_of
from kakao_pc_collect.win_click import (
    click_client,
    find_hwnd_by_title_contains,
    window_client_size,
)

log = get_logger(__name__)

DRAWER_TITLE = "채팅방 서랍"


def _send(keys: str) -> None:
    from pywinauto.keyboard import send_keys

    send_keys(keys)


def open_drawer(
    room_hwnd: int,
    coords: CoordConfig,
    *,
    dry_run: bool = False,
) -> int:
    """☰ → 서랍 → 사진/동영상. 반환=서랍 hwnd."""
    click_client(room_hwnd, coords.hamburger, dry_run=dry_run, label="hamburger")
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
        # Down × N → Right → Down × M → Enter
        for _ in range(max(0, coords.drawer_menu_downs)):
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
    mode = (coords.arrow_mode or "right_then_down").lower()
    cols = max(1, coords.grid_columns)
    keys: list[str] = []
    if mode == "right":
        keys = ["{RIGHT}"] * presses
    elif mode == "down":
        keys = ["{DOWN}"] * presses
    else:
        # 그리드: 오른쪽으로 cols-1, 다음 줄 Down, 반복
        for i in range(presses):
            if (i + 1) % cols == 0:
                keys.append("{DOWN}")
            else:
                keys.append("{RIGHT}")
    return keys


def select_photo_batch(
    drawer_hwnd: int,
    coords: CoordConfig,
    *,
    skip_tiles: int = 0,
    dry_run: bool = False,
) -> None:
    """
    첫 칸 앵커 → 방향키로 프리로드 → 첫 칸 복귀
    → (선택적) skip_tiles 만큼 이동 → Shift+방향키로 ≤50칸.
    skip_tiles: 이전 배치에서 이미 받은 칸 수 (batch_i * select_count).
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

    # 2) Shift 없이 프리로드 (가상 스크롤 로딩)
    for key in _arrow_sequence(coords, preload):
        _send(key)
        time.sleep(0.04)
    time.sleep(0.3)

    # 3) 첫 사진으로 복귀
    click_client(
        drawer_hwnd, coords.first_photo, dry_run=False, label="first_photo_reset"
    )
    time.sleep(0.25)

    # 3b) 이전 배치 칸 건너뛰기
    if skip:
        for key in _arrow_sequence(coords, skip):
            _send(key)
            time.sleep(0.03)
        time.sleep(0.15)

    # 4) Shift+방향키로 n-1 칸 추가 선택 (총 n칸)
    for key in _arrow_sequence(coords, n - 1):
        # + = Shift down in pywinauto send_keys
        _send("+" + key)
        time.sleep(0.05)
    time.sleep(0.2)
    log.info("select_photo_batch count=%s skip=%s", n, skip)


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


def download_one_batch(
    *,
    room_win,
    coords: CoordConfig,
    download_dir: Path,
    photos_dir: Path,
    skip_tiles: int = 0,
    dry_run: bool = False,
) -> list[str]:
    """
    서랍 열고 50칸 선택·다운로드·photos 복사.
    반환=이번에 복사된(또는 dry_run이면 감지된) 이미지 파일명.
    """
    room_hwnd = hwnd_of(room_win)
    before = snapshot_names(download_dir)

    drawer_hwnd = open_drawer(room_hwnd, coords, dry_run=dry_run)
    select_photo_batch(
        drawer_hwnd, coords, skip_tiles=skip_tiles, dry_run=dry_run
    )
    click_download(drawer_hwnd, coords, dry_run=dry_run)

    if dry_run:
        return []

    new_names = wait_for_new_files(download_dir, before=before)
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

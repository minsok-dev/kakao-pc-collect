# [변경사유]: Documents 고정 폴더 → photos 이름 유지 복사
"""다운로드 폴더 감시·복사."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.stems import is_kakao_image

log = get_logger(__name__)


def snapshot_names(folder: Path) -> set[str]:
    if not folder.is_dir():
        return set()
    return {p.name for p in folder.iterdir() if p.is_file()}


def wait_for_new_files(
    folder: Path,
    *,
    before: set[str],
    idle_sec: float = 2.5,
    timeout_sec: float = 180.0,
) -> list[str]:
    """
    before 대비 새 KakaoTalk 이미지가 생기고, idle_sec 동안 더 안 늘면 배치 끝.
    """
    folder.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_sec
    last_count = -1
    stable_since: float | None = None
    newest: set[str] = set()

    while time.time() < deadline:
        now = snapshot_names(folder)
        fresh = {n for n in now - before if is_kakao_image(n)}
        newest = fresh
        count = len(fresh)
        if count != last_count:
            last_count = count
            stable_since = time.time()
            if count:
                log.info("download progress new_images=%s", count)
        elif count > 0 and stable_since is not None:
            if time.time() - stable_since >= idle_sec:
                return sorted(newest)
        time.sleep(0.4)

    log.warning(
        "download wait timeout new_images=%s folder=%s",
        len(newest),
        folder,
    )
    return sorted(newest)


def copy_new_images(
    *,
    download_dir: Path,
    photos_dir: Path,
    names: list[str],
) -> list[str]:
    """이름 유지 복사. photos에 이미 있으면 스킵. 반환=실제 복사된 파일명."""
    photos_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in names:
        if not is_kakao_image(name):
            continue
        src = download_dir / name
        dst = photos_dir / name
        if not src.is_file():
            log.warning("copy missing src=%s", name)
            continue
        if dst.is_file():
            log.info("copy skip exists name=%s", name)
            continue
        shutil.copy2(src, dst)
        copied.append(name)
        log.info("copy ok name=%s", name)
    return copied

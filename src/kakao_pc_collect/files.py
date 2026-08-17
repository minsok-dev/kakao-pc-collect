# [변경사유]: Documents 고정 폴더 → photos 이름 유지 복사
"""다운로드 폴더 감시·복사."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.stems import canonical_kakao_name, is_kakao_image

log = get_logger(__name__)


def snapshot_names(folder: Path) -> set[str]:
    if not folder.is_dir():
        return set()
    return {p.name for p in folder.iterdir() if p.is_file()}


def snapshot_mtimes(folder: Path) -> dict[str, float]:
    """[변경사유]: 같은 파일명 덮어쓰기 감지 — 카톡 받은 파일은 원본명을 재사용."""
    if not folder.is_dir():
        return {}
    out: dict[str, float] = {}
    for p in folder.iterdir():
        if not p.is_file() or not is_kakao_image(p.name):
            continue
        try:
            out[p.name] = p.stat().st_mtime
        except OSError:
            continue
    return out


def _fresh_kakao_names(
    folder: Path,
    *,
    before: set[str],
    before_mtime: dict[str, float],
) -> tuple[set[str], int, int]:
    """새 이름 + mtime이 올라간 기존 이름. (fresh, new_count, overwritten_count)."""
    current = snapshot_mtimes(folder)
    new_names = {n for n in current if n not in before}
    # NTFS 해상도·시계 오차 — 50ms 이상 커진 경우만 덮어쓰기로 본다
    overwritten = {
        n
        for n, mt in current.items()
        if n in before and mt > (before_mtime.get(n, 0.0) + 0.05)
    }
    return new_names | overwritten, len(new_names), len(overwritten)


def wait_for_new_files(
    folder: Path,
    *,
    before: set[str],
    before_mtime: dict[str, float] | None = None,
    idle_sec: float = 2.5,
    timeout_sec: float = 180.0,
) -> list[str]:
    """
    before 대비 새 KakaoTalk 이미지(새 이름 또는 같은 이름 덮어쓰기)가 생기고,
    idle_sec 동안 더 안 늘면 배치 끝.
    """
    folder.mkdir(parents=True, exist_ok=True)
    mtimes = before_mtime if before_mtime is not None else snapshot_mtimes(folder)
    deadline = time.time() + timeout_sec
    last_count = -1
    last_empty_log = -10.0
    stable_since: float | None = None
    newest: set[str] = set()

    while time.time() < deadline:
        fresh, n_new, n_ow = _fresh_kakao_names(
            folder, before=before, before_mtime=mtimes
        )
        newest = fresh
        count = len(fresh)
        elapsed = timeout_sec - (deadline - time.time())
        if count != last_count:
            last_count = count
            stable_since = time.time()
            if count:
                log.info(
                    "download progress new_images=%s new_name=%s overwritten=%s elapsed=%.0fs",
                    count,
                    n_new,
                    n_ow,
                    elapsed,
                )
            else:
                log.info("download wait new_images=0 elapsed=%.0fs (폴링 중)", elapsed)
                last_empty_log = elapsed
        elif count > 0 and stable_since is not None:
            if time.time() - stable_since >= idle_sec:
                return sorted(newest)
        elif count == 0 and (elapsed - last_empty_log) >= 5.0:
            # 파일 0개로 대기 중 — 죽은 것이 아니라 다운로드 대기
            log.info(
                "download wait still empty elapsed=%.0fs / %.0fs",
                elapsed,
                timeout_sec,
            )
            last_empty_log = elapsed
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
    """
    방 photos 로 복사. ` (N)` 은 카톡 원본명으로 저장.
    dest 가 있으면 스킵. 반환=실제 복사된 원본 파일명.
    """
    photos_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in names:
        dest_name = canonical_kakao_name(name)
        if not dest_name:
            continue
        src = download_dir / name
        dst = photos_dir / dest_name
        if not src.is_file():
            log.warning("copy missing src=%s", name)
            continue
        if dst.is_file():
            log.info("copy skip exists src=%s dest=%s", name, dest_name)
            continue
        shutil.copy2(src, dst)
        copied.append(dest_name)
        log.info("copy ok src=%s dest=%s", name, dest_name)
    return copied

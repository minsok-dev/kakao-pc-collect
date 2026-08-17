# [변경사유]: 같은 파일명 덮어쓰기도 새 다운로드로 감지
"""download wait — 새 이름 + mtime 갱신."""

from __future__ import annotations

import os
from pathlib import Path

from kakao_pc_collect.files import (
    copy_new_images,
    snapshot_mtimes,
    snapshot_names,
    wait_for_new_files,
)


def test_wait_detects_overwrite_same_name(tmp_path: Path) -> None:
    name = "KakaoTalk_20260817_212453249.png"
    p = tmp_path / name
    p.write_bytes(b"old")
    before = snapshot_names(tmp_path)
    before_mtime = snapshot_mtimes(tmp_path)
    p.write_bytes(b"new-download")
    # [변경사유]: NTFS가 아니라 FAT여도 덮어쓰기로 보이게 mtime을 명시적으로 올림
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 2))
    found = wait_for_new_files(
        tmp_path,
        before=before,
        before_mtime=before_mtime,
        idle_sec=0.2,
        timeout_sec=3.0,
    )
    assert name in found


def test_wait_ignores_untouched_existing(tmp_path: Path) -> None:
    name = "KakaoTalk_20260817_212453249.png"
    (tmp_path / name).write_bytes(b"old")
    before = snapshot_names(tmp_path)
    before_mtime = snapshot_mtimes(tmp_path)
    found = wait_for_new_files(
        tmp_path,
        before=before,
        before_mtime=before_mtime,
        idle_sec=0.2,
        timeout_sec=1.0,
    )
    assert found == []


def test_wait_detects_windows_duplicate_name(tmp_path: Path) -> None:
    orig = "KakaoTalk_20260817_193136507.png"
    dup = "KakaoTalk_20260817_193136507 (3).png"
    (tmp_path / orig).write_bytes(b"old")
    before = snapshot_names(tmp_path)
    before_mtime = snapshot_mtimes(tmp_path)
    (tmp_path / dup).write_bytes(b"new")
    found = wait_for_new_files(
        tmp_path,
        before=before,
        before_mtime=before_mtime,
        idle_sec=0.2,
        timeout_sec=3.0,
    )
    assert dup in found


def test_copy_strips_duplicate_suffix(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    photos = tmp_path / "photos"
    dl.mkdir()
    src_name = "KakaoTalk_20260817_171930427_13 (3).jpg"
    (dl / src_name).write_bytes(b"img")
    copied = copy_new_images(
        download_dir=dl, photos_dir=photos, names=[src_name]
    )
    dest = "KakaoTalk_20260817_171930427_13.jpg"
    assert copied == [dest]
    assert (photos / dest).is_file()
    again = copy_new_images(
        download_dir=dl, photos_dir=photos, names=[src_name]
    )
    assert again == []

# [변경사유]: --room E2E 전달 · classify fail-closed when upload
"""collect → import 체인 방 필터·fail 정책."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kakao_pc_collect import pipeline as col_pipe
from kakao_pc_collect.config import Settings


def _settings(tmp_path: Path) -> Settings:
    raw = tmp_path / "raw"
    return Settings(
        project_root=tmp_path,
        kakao_import_root=tmp_path / "import",
        download_dir=tmp_path / "dl",
        raw_root=raw,
        chats_dir=raw / "chats",
        photos_dir=raw / "photos",
        coords=MagicMock(),
        rooms=[],
        log_level="INFO",
        run_import=True,
        run_upload=False,
    )


def test_call_passes_room_and_no_review(monkeypatch, tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd, cwd=None, check=False):  # noqa: ANN001
        seen.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr(col_pipe.subprocess, "run", fake_run)
    (tmp_path / "import").mkdir()
    col_pipe._call_kakao_import(
        _settings(tmp_path), run_upload=True, room_ids=["hongdae_bonita"]
    )
    assert any(
        c[1] == "run" and "--room" in c and "hongdae_bonita" in c for c in seen
    )
    assert any(
        c[1] == "poster-classify" and "--no-review" in c and "hongdae_bonita" in c
        for c in seen
    )
    assert any(
        c[1] == "upload" and "--no-dry-run" in c and "hongdae_bonita" in c for c in seen
    )


def test_classify_fail_closed_blocks_upload(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_run(cmd, cwd=None, check=False):  # noqa: ANN001
        calls.append(cmd[1])
        if cmd[1] == "poster-classify":
            raise col_pipe.subprocess.CalledProcessError(1, cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(col_pipe.subprocess, "run", fake_run)
    (tmp_path / "import").mkdir()
    with pytest.raises(col_pipe.subprocess.CalledProcessError):
        col_pipe._call_kakao_import(
            _settings(tmp_path), run_upload=True, room_ids=["r1"]
        )
    assert "upload" not in calls


def test_classify_fail_open_without_upload(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_run(cmd, cwd=None, check=False):  # noqa: ANN001
        calls.append(cmd[1])
        if cmd[1] == "poster-classify":
            raise col_pipe.subprocess.CalledProcessError(1, cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(col_pipe.subprocess, "run", fake_run)
    (tmp_path / "import").mkdir()
    col_pipe._call_kakao_import(_settings(tmp_path), run_upload=False, room_ids=["r1"])
    assert "similar-detect" in calls
    assert "upload" not in calls


def test_similar_fail_blocks_upload(monkeypatch, tmp_path: Path) -> None:
    """[변경사유]: S3 — similar-detect 실패 시 upload 미호출 (check=True 계약 고정)."""
    calls: list[str] = []

    def fake_run(cmd, cwd=None, check=False):  # noqa: ANN001
        calls.append(cmd[1])
        if cmd[1] == "similar-detect":
            raise col_pipe.subprocess.CalledProcessError(1, cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(col_pipe.subprocess, "run", fake_run)
    (tmp_path / "import").mkdir()
    with pytest.raises(col_pipe.subprocess.CalledProcessError):
        col_pipe._call_kakao_import(
            _settings(tmp_path), run_upload=True, room_ids=["r1"]
        )
    assert "similar-detect" in calls
    assert "upload" not in calls

# [변경사유]: KAKAO_COLLECT_RUN_UPLOAD 기본 off / opt-in 파싱
"""collect run_upload 설정."""

from __future__ import annotations

import os
from pathlib import Path

from kakao_pc_collect.config import load_settings


def test_run_upload_default_off(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "KAKAO_IMPORT_ROOT=.\nKAKAO_COLLECT_RUN_IMPORT=1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("KAKAO_COLLECT_RUN_UPLOAD", raising=False)
    # load_settings 는 PROJECT_ROOT .env — monkeypatch 환경만으로 검증
    monkeypatch.setenv("KAKAO_COLLECT_RUN_UPLOAD", "0")
    monkeypatch.setenv("KAKAO_IMPORT_ROOT", str(tmp_path))
    s = load_settings(env_path=env)
    assert s.run_upload is False


def test_run_upload_env_on(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("KAKAO_IMPORT_ROOT=.\n", encoding="utf-8")
    monkeypatch.setenv("KAKAO_COLLECT_RUN_UPLOAD", "1")
    monkeypatch.setenv("KAKAO_IMPORT_ROOT", str(tmp_path))
    s = load_settings(env_path=env)
    assert s.run_upload is True

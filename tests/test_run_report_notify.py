# [변경사유]: I5 — run-report / admin_summary / notify dry-run
"""실행 리포트·관리자 요약."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from kakao_pc_collect.run_report import (
    build_admin_summary_ko,
    build_run_report,
    write_run_report,
)
from kakao_pc_collect.admin_notify import send_admin_summary


def test_build_run_report_success(tmp_path: Path) -> None:
    import_root = tmp_path / "import"
    data = import_root / "data"
    data.mkdir(parents=True)
    (data / "upload-result.json").write_text(
        json.dumps(
            {
                "summary": {
                    "OK": 3,
                    "FAIL": 0,
                    "ocr_queued": 2,
                    "by_next": {"ocr_queued": 2, "sns_appended": 1},
                    "SIMILAR_DEFERRED_BLOCKED": 1,
                    "FILE_MISSING": 0,
                },
                "candidate_sync": {"skipped_uploaded_count": 10},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = build_run_report(
        collect_results=[{"room_id": "hongdae_bonita", "copied": 4}],
        import_root=import_root,
        room_ids=["hongdae_bonita"],
        run_upload=True,
        import_error=None,
    )
    assert report["ok"] is True
    assert report["exit_reason"] == "success"
    assert report["upload"]["ocr_queued"] == 2
    assert report["upload"]["skipped_uploaded"] == 10
    assert "성공" in report["admin_summary_ko"]
    assert "hongdae_bonita" in report["admin_summary_ko"]


def test_build_run_report_cookie_expired(tmp_path: Path) -> None:
    report = build_run_report(
        collect_results=[{"room_id": "r1", "copied": 0}],
        import_root=tmp_path,
        room_ids=["r1"],
        run_upload=True,
        import_error="KAKAO_IMPORT_SESSION_COOKIE required",
    )
    assert report["ok"] is False
    assert report["exit_reason"] == "cookie_expired"
    assert report["cookie"]["ok"] is False
    assert "실패" in build_admin_summary_ko(report)


def test_write_run_report_archives(tmp_path: Path) -> None:
    # [변경사유]: 실행마다 data/runs/<run_id>/ 보존
    import_root = tmp_path / "import"
    data = import_root / "data"
    data.mkdir(parents=True)
    (data / "upload-result.json").write_text(
        json.dumps({"summary": {"OK": 1, "ocr_queued": 1}}, ensure_ascii=False),
        encoding="utf-8",
    )
    report = build_run_report(
        collect_results=[{"room_id": "r1", "copied": 2, "error": "timeout"}],
        import_root=import_root,
        room_ids=["r1"],
        run_upload=True,
        run_id="20260914-091340-1",
    )
    assert report["exit_reason"] == "partial_collect_error"
    from kakao_pc_collect.run_report import write_run_report_latest_and_archive

    data_dir = tmp_path / "collect-data"
    arch = write_run_report_latest_and_archive(
        data_dir, report, import_root=import_root
    )
    assert (data_dir / "run-report.json").is_file()
    assert (arch / "run-report.json").is_file()
    assert (arch / "upload-result.json").is_file()
    loaded = json.loads((arch / "run-report.json").read_text(encoding="utf-8"))
    assert loaded["collect"]["room_errors"][0]["room_id"] == "r1"


def test_write_run_report(tmp_path: Path) -> None:
    report = {
        "ok": True,
        "exit_reason": "success",
        "admin_summary_ko": "ok",
    }
    path = write_run_report(tmp_path / "run-report.json", report)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["ok"] is True


def test_send_admin_summary_dry_run() -> None:
    out = send_admin_summary(
        search="관리자",
        text="테스트 요약",
        coords=MagicMock(),
        dry_run=True,
    )
    assert out["ok"] is True
    assert out.get("skipped") == "dry_run"


def test_send_admin_summary_empty() -> None:
    out = send_admin_summary(search="", text="x", dry_run=False)
    assert out["ok"] is False
    assert out["error"] == "empty_search_or_text"

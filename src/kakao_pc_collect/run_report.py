# [변경사유]: I5 — 실행 리포트 JSON + 관리자용 한 줄 요약
"""collect/upload 실행 요약 리포트."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kakao_pc_collect.logging_util import get_logger

log = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load_upload_result(import_root: Path) -> dict[str, Any] | None:
    """kakao-import data/upload-result.json 로드."""
    candidates = [
        import_root / "data" / "upload-result.json",
        import_root / "upload-result.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("upload-result read fail path=%s err=%s", path, exc)
    return None


def _detect_cookie_issue(upload: dict[str, Any] | None, error: str | None) -> bool:
    """쿠키/인증 실패 추정."""
    blob = " ".join(
        [
            str(error or ""),
            json.dumps(upload or {}, ensure_ascii=False)[:2000],
        ]
    ).lower()
    markers = (
        "session_cookie",
        "unauthorized",
        "401",
        "cookie",
        "인증",
        "로그인",
    )
    return any(m in blob for m in markers)


def build_admin_summary_ko(report: dict[str, Any]) -> str:
    """관리자 카톡용 한 줄~수 줄 요약."""
    ok = bool(report.get("ok"))
    status = "성공" if ok else "실패"
    reason = str(report.get("exit_reason") or "")
    rooms = report.get("rooms") or []
    room_s = ",".join(str(r) for r in rooms[:5]) if rooms else "-"
    upload = report.get("upload") if isinstance(report.get("upload"), dict) else {}
    ocr = upload.get("ocr_queued")
    http_ok = upload.get("http_ok")
    skipped = upload.get("skipped_uploaded")
    holds = upload.get("holds") if isinstance(upload.get("holds"), dict) else {}
    hold_n = sum(int(v or 0) for v in holds.values()) if holds else 0
    collect = report.get("collect") if isinstance(report.get("collect"), dict) else {}
    copied = collect.get("copied_total")
    lines = [
        f"[카카오수집] {status}",
        f"방: {room_s}",
    ]
    if copied is not None:
        lines.append(f"수집복사: {copied}")
    if ocr is not None or http_ok is not None:
        lines.append(
            f"업로드: OCR큐 {ocr if ocr is not None else '-'} / "
            f"HTTP OK {http_ok if http_ok is not None else '-'} / "
            f"스킵 {skipped if skipped is not None else '-'} / hold {hold_n}"
        )
    if reason and reason not in ("success",):
        lines.append(f"사유: {reason}")
    if report.get("error"):
        lines.append(f"오류: {str(report.get('error'))[:120]}")
    lines.append(f"시각: {str(report.get('finished_at') or '')[:19]}")
    return "\n".join(lines)


def build_run_report(
    *,
    collect_results: list[dict[str, Any]],
    import_root: Path,
    room_ids: list[str] | None = None,
    run_upload: bool = False,
    import_error: str | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    """collect + (선택) upload-result 를 합친 실행 리포트."""
    rooms = room_ids or [
        str(r.get("room_id") or "")
        for r in collect_results
        if str(r.get("room_id") or "")
    ]
    copied_total = 0
    room_errors: list[dict[str, str]] = []
    for r in collect_results:
        if r.get("error"):
            room_errors.append(
                {"room_id": str(r.get("room_id") or ""), "error": str(r.get("error"))}
            )
        copied_total += int(r.get("copied") or 0)

    upload_raw = _load_upload_result(import_root) if run_upload else None
    upload_summary = {}
    if isinstance(upload_raw, dict):
        summary = upload_raw.get("summary") if isinstance(upload_raw.get("summary"), dict) else upload_raw
        upload_summary = {
            "http_ok": summary.get("OK", summary.get("ok", summary.get("http_ok"))),
            "http_fail": summary.get("FAIL", summary.get("fail", summary.get("http_fail"))),
            "ocr_queued": summary.get("ocr_queued"),
            "by_next": summary.get("by_next"),
            "ocr_idx_present": summary.get("ocr_idx_present"),
            "skipped_uploaded": (upload_raw.get("candidate_sync") or {}).get(
                "skipped_uploaded_count"
            )
            if isinstance(upload_raw.get("candidate_sync"), dict)
            else summary.get("skipped_uploaded"),
            "holds": {
                "similar_deferred": summary.get("SIMILAR_DEFERRED_BLOCKED"),
                "file_missing": summary.get("FILE_MISSING"),
            },
            "error": summary.get("error") or upload_raw.get("error"),
        }

    cookie_bad = _detect_cookie_issue(upload_raw, import_error)
    ok = import_error is None and not room_errors and not cookie_bad
    if cookie_bad:
        exit_reason = "cookie_expired"
        ok = False
    elif import_error:
        exit_reason = "import_or_upload_failed"
        ok = False
    elif room_errors and not collect_results:
        exit_reason = "collect_failed"
        ok = False
    elif room_errors:
        exit_reason = "partial_collect_error"
        # 일부 방만 실패해도 리포트는 남기되 ok=false
        ok = False
    else:
        exit_reason = "success"

    report: dict[str, Any] = {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "started_at": started_at or _now_iso(),
        "finished_at": _now_iso(),
        "ok": ok,
        "exit_reason": exit_reason,
        "rooms": rooms,
        "collect": {
            "copied_total": copied_total,
            "room_count": len(collect_results),
            "room_errors": room_errors,
            "rooms": collect_results,
        },
        "upload": upload_summary if run_upload else None,
        "cookie": {"ok": not cookie_bad},
        "error": import_error,
    }
    report["admin_summary_ko"] = build_admin_summary_ko(report)
    return report


def write_run_report(path: Path, report: dict[str, Any]) -> Path:
    """UTF-8 JSON 저장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log.info("run-report written path=%s ok=%s reason=%s", path, report.get("ok"), report.get("exit_reason"))
    return path

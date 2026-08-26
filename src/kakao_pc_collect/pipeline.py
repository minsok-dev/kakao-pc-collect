# [변경사유]: 방 루프 — 사진 서랍 먼저 → 대화 txt → 워터마크·import 호출
# [변경사유]: txt→사진 순서였을 때 다운로드 중 신규 이미지에 캡션 매칭 실패 → 사진 후 txt로 변경
"""수집 파이프라인."""

from __future__ import annotations

import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from kakao_pc_collect.config import RoomSpec, Settings, effective_drawer_menu_downs
from kakao_pc_collect.drawer import (
    click_download,
    open_drawer,
    select_photo_batch,
)
from kakao_pc_collect.files import (
    copy_new_images,
    snapshot_mtimes,
    snapshot_names,
    wait_for_new_files,
)
from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.stems import (
    canonical_kakao_name,
    is_kakao_image,
    parse_kakao_stem,
    stem_key,
)
from kakao_pc_collect.uia_kakao import (
    export_chat_txt,
    focus_window,
    hwnd_of,
    open_room_by_search,
)
from kakao_pc_collect.watermark import (
    load_watermarks,
    max_stem_among,
    max_stem_in_dir,
    min_stem_among,
    save_watermarks,
    unique_stems,
)

log = get_logger(__name__)

# [변경사유]: 워터마크 없는 첫 수집·신규 방은 최근 N일 사진만
FIRST_RUN_LOOKBACK_DAYS = 3


def first_run_cutoff_stem(*, days: int = FIRST_RUN_LOOKBACK_DAYS) -> str:
    """오늘 기준 days일 전 0시 스템. 이보다 오래된 파일은 첫 수집에서 복사하지 않음."""
    d = date.today() - timedelta(days=days)
    return d.strftime("%Y%m%d") + "_000000000"


def _names_on_or_after(names: list[str], cutoff: str) -> list[str]:
    """첫 수집 시 cutoff 스템 이상만 복사 대상으로 남김."""
    kept: list[str] = []
    for name in names:
        stem, _seq, _ext = parse_kakao_stem(name)
        if not stem:
            continue
        if stem_key(stem) >= cutoff:
            kept.append(name)
    return kept


def _existing_photo_names(photos_dir: Path) -> set[str]:
    if not photos_dir.is_dir():
        return set()
    return {p.name for p in photos_dir.iterdir() if p.is_file() and is_kakao_image(p.name)}


def _close_drawer() -> None:
    from pywinauto.keyboard import send_keys

    try:
        send_keys("{ESC}")
        time.sleep(0.4)
        send_keys("{ESC}")
        time.sleep(0.3)
    except Exception:  # noqa: BLE001
        pass


def _should_stop_room(
    *,
    batch_names: list[str],
    watermark: str | None,
    photos_before: set[str],
    first_run_cutoff: str | None = None,
) -> tuple[bool, str]:
    """배치 후 중단 여부."""
    images = [n for n in batch_names if is_kakao_image(n)]
    if not images:
        return True, "no_new_images"

    stems = unique_stems(images)
    if not stems:
        return True, "no_stems"

    # [변경사유]: ` (N)` 원본명으로 비교 — 방 photos 에는 정규화 이름만 있음
    dest_names = [canonical_kakao_name(n) for n in images]
    if dest_names and all(d is not None and d in photos_before for d in dest_names):
        return True, "all_already_in_photos"

    if watermark:
        oldest = min_stem_among(images)
        newest = max_stem_among(images)
        log.info(
            "batch stems watermark=%s oldest=%s newest=%s",
            watermark,
            oldest,
            newest,
        )
        # 워터마크보다 오래된 스템이 나오면 따라잡은 것
        if oldest is not None and oldest <= watermark:
            return True, "reached_watermark"

    # [변경사유]: 신규 방·첫 수집은 최근 3일만 — 그리드가 더 과거로 가면 중단
    if first_run_cutoff:
        oldest = min_stem_among(images)
        log.info(
            "batch stems first_run_cutoff=%s oldest=%s",
            first_run_cutoff,
            oldest,
        )
        if oldest is not None and oldest < first_run_cutoff:
            return True, "first_run_days"

    return False, "continue"


def collect_room(
    settings: Settings,
    room: RoomSpec,
    *,
    chats: bool = True,
    photos: bool = True,
    dry_run: bool = False,
    max_photo_batches: int = 40,
) -> dict:
    """한 방 수집 (사진 → 대화 txt). 반환 요약 dict."""
    summary: dict = {
        "room_id": room.id,
        "search": room.search,
        "chat_exported": False,
        "photo_batches": 0,
        "copied": 0,
        "stop_reason": None,
    }
    marks = load_watermarks(settings.watermark_path)
    chats_dir = settings.room_chats_dir(room.id)
    photos_dir = settings.room_photos_dir(room.id)
    chats_dir.mkdir(parents=True, exist_ok=True)
    photos_dir.mkdir(parents=True, exist_ok=True)
    # [변경사유]: 워터마크·기존 파일은 방 폴더 기준
    watermark = marks.get(room.id) or max_stem_in_dir(photos_dir)
    # [변경사유]: 저장된 사진·워터마크가 없으면 최근 3일만 (신규 방 포함)
    first_run_cutoff = None if watermark else first_run_cutoff_stem()
    log.info(
        "collect_room id=%s search=%r watermark=%s first_run_cutoff=%s chats_dir=%s photos_dir=%s",
        room.id,
        room.search,
        watermark,
        first_run_cutoff,
        chats_dir,
        photos_dir,
    )

    # Ctrl+S·☰ 는 메인 목록이 아니라 채팅방 창에서 수행
    win = open_room_by_search(
        room.search, coords=settings.coords, dry_run=dry_run
    )

    # [변경사유]: 사진 먼저 → 대화 txt 나중.
    # 예전(txt→사진)은 서랍 다운로드 중 새 이미지가 들어오면 대화 파일에 캡션이 없어 매칭 실패함.
    coords = settings.coords
    room_hwnd = hwnd_of(win)
    total_copied = 0
    best_stem = watermark

    if photos:
        for batch_i in range(max_photo_batches):
            photos_before = _existing_photo_names(photos_dir)
            skip = batch_i * coords.select_count

            log.info("photo batch=%s skip_tiles=%s", batch_i + 1, skip)

            # [변경사유]: 방 타입별 drawer_menu_downs — 오픈 단톡방×2, 일반 단톡방×3
            dmd = effective_drawer_menu_downs(room, coords.drawer_menu_downs)
            drawer_hwnd = open_drawer(
                room_hwnd, coords, dry_run=dry_run, drawer_menu_downs_override=dmd
            )
            select_photo_batch(
                drawer_hwnd,
                coords,
                skip_tiles=skip,
                dry_run=dry_run,
            )
            # [변경사유]: 선택 직후 스냅샷 — 같은 파일명 덮어쓰기는 mtime으로 감지
            before_dl = snapshot_names(settings.download_dir)
            before_mtime = snapshot_mtimes(settings.download_dir)
            click_download(drawer_hwnd, coords, dry_run=dry_run)

            if dry_run:
                summary["photo_batches"] = batch_i + 1
                summary["stop_reason"] = "dry_run"
                break

            new_names = wait_for_new_files(
                settings.download_dir,
                before=before_dl,
                before_mtime=before_mtime,
            )
            to_copy = new_names
            # [변경사유]: 첫 수집 3일 컷 + 이후에는 이미 가진 가장 오래된 스템보다 과거는 복사하지 않음
            copy_floor = first_run_cutoff
            if copy_floor is None and photos_before:
                copy_floor = min_stem_among(list(photos_before))
            if copy_floor:
                to_copy = _names_on_or_after(new_names, copy_floor)
                skipped_old = len(new_names) - len(to_copy)
                if skipped_old:
                    log.info(
                        "skip_old count=%s floor=%s",
                        skipped_old,
                        copy_floor,
                    )
            copied = copy_new_images(
                download_dir=settings.download_dir,
                photos_dir=photos_dir,
                names=to_copy,
            )
            total_copied += len(copied)
            summary["photo_batches"] = batch_i + 1

            batch_for_judge = new_names or copied
            stop, reason = _should_stop_room(
                batch_names=batch_for_judge,
                watermark=watermark,
                photos_before=photos_before,
                first_run_cutoff=first_run_cutoff,
            )
            # [변경사유]: 첫 수집에서 오래된 파일은 복사하지 않으므로 워터마크는 복사본 기준
            mx = max_stem_among(copied)
            if mx and (best_stem is None or mx > best_stem):
                best_stem = mx

            log.info(
                "batch judge stop=%s reason=%s copied=%s",
                stop,
                reason,
                len(copied),
            )

            _close_drawer()
            focus_window(win)

            if stop:
                summary["stop_reason"] = reason
                break
        else:
            summary["stop_reason"] = "max_batches"

        summary["copied"] = total_copied
        if best_stem and not dry_run:
            marks[room.id] = best_stem
            save_watermarks(settings.watermark_path, marks)
            log.info("watermark updated room=%s stem=%s", room.id, best_stem)

    # [변경사유]: 사진 수집(서랍) 종료 후 방 창에서 txt — 다운로드 구간 중 생긴 캡션도 포함
    if chats:
        focus_window(win)
        export_chat_txt(win, chats_dir, dry_run=dry_run)
        summary["chat_exported"] = True

    return summary


def run_collect(
    settings: Settings,
    *,
    room_ids: list[str] | None = None,
    chats: bool = True,
    photos: bool = True,
    dry_run: bool = False,
    run_import: bool | None = None,
    run_upload: bool | None = None,
) -> list[dict]:
    """허용 방 순회 수집."""
    from kakao_pc_collect.admin_notify import send_admin_summary
    from kakao_pc_collect.run_report import build_run_report, write_run_report

    settings.raw_root.mkdir(parents=True, exist_ok=True)
    settings.download_dir.mkdir(parents=True, exist_ok=True)

    rooms = [r for r in settings.rooms if r.enabled]
    if room_ids:
        want = set(room_ids)
        rooms = [r for r in rooms if r.id in want]
    if not rooms:
        raise RuntimeError("enabled room 없음 — config/rooms.yaml 확인")

    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    results: list[dict] = []
    for room in rooms:
        log.info("=== room %s ===", room.id)
        try:
            results.append(
                collect_room(
                    settings,
                    room,
                    chats=chats,
                    photos=photos,
                    dry_run=dry_run,
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("room failed id=%s", room.id)
            results.append(
                {
                    "room_id": room.id,
                    "search": room.search,
                    "error": str(exc),
                }
            )
            continue

    do_import = settings.run_import if run_import is None else run_import
    do_upload = settings.run_upload if run_upload is None else run_upload
    import_error: str | None = None
    if do_import and not dry_run:
        # [변경사유]: import 체인 완료 직후(시각 추정 없이) opt-in 시 upload --no-dry-run
        # [변경사유]: CLI --room 이 있으면 import/upload 에도 동일 방 집합 전달 (E2E)
        try:
            _call_kakao_import(
                settings,
                run_upload=do_upload,
                room_ids=list(room_ids) if room_ids else None,
            )
        except Exception as exc:  # noqa: BLE001 — 리포트·알림 후 재raise
            import_error = str(exc)
            log.error("kakao-import chain failed err=%s", import_error)

    # [변경사유]: I5 — 실행 리포트 + (opt-in) 관리자 카톡 요약
    if not dry_run:
        report = build_run_report(
            collect_results=results,
            import_root=settings.kakao_import_root,
            room_ids=list(room_ids) if room_ids else [r.id for r in rooms],
            run_upload=bool(do_upload and do_import),
            import_error=import_error,
            started_at=started_at,
        )
        report_path = settings.data_dir / "run-report.json"
        write_run_report(report_path, report)
        # import data 에도 복사 — 운영이 import 폴더만 볼 때
        try:
            write_run_report(
                settings.kakao_import_root / "data" / "run-report.json", report
            )
        except OSError as exc:
            log.warning("run-report copy to import-root fail err=%s", exc)

        notify_search = (settings.admin_notify_search or "").strip()
        if notify_search:
            notify_out = send_admin_summary(
                search=notify_search,
                text=str(report.get("admin_summary_ko") or ""),
                coords=settings.coords,
                dry_run=False,
            )
            report["admin_notify"] = notify_out
            write_run_report(report_path, report)
            log.info(
                "admin-notify done ok=%s err=%s",
                notify_out.get("ok"),
                notify_out.get("error"),
            )
        else:
            # [변경사유]: 빈 값이면 전송 안 함 — 예전엔 로그 없이 스킵되어 .env 미적용과 구분 불가
            log.info(
                "admin-notify skipped — KAKAO_ADMIN_NOTIFY_SEARCH empty "
                "(set in kakao-pc-collect/.env under PROJECT_ROOT)"
            )

    if import_error:
        raise RuntimeError(import_error)
    return results


def _call_kakao_import(
    settings: Settings,
    *,
    run_upload: bool = False,
    room_ids: list[str] | None = None,
) -> None:
    """
    수집 후 kakao-import run + poster-classify --no-review + similar-detect.
    run_upload=True 이면 위 체인 **완료 직후** upload --no-dry-run (similar deferred 는 hold).
    room_ids 있으면 전 단계에 --room 전달.
    """
    root = settings.kakao_import_root
    log.info(
        "calling kakao-import root=%s run_upload=%s rooms=%s",
        root,
        run_upload,
        room_ids,
    )
    room_args: list[str] = []
    for rid in room_ids or []:
        room_args.extend(["--room", rid])
    # [변경사유]: 자동 체인(스케줄/--with-upload)에서 poster-review UI 대기 금지 — classify만 하고 다음 단계로
    cmds: list[list[str]] = [
        ["kakao-import", "run", *room_args],
        ["kakao-import", "poster-classify", "--no-review", *room_args],
        ["kakao-import", "similar-detect", *room_args],
    ]
    # [변경사유]: 수집·매칭·similar-detect 가 끝난 뒤에만 upload — 별도 시각 스케줄 불필요
    if run_upload:
        cmds.append(["kakao-import", "upload", "--no-dry-run", *room_args])
    for cmd in cmds:
        log.info("exec %s", " ".join(cmd))
        try:
            subprocess.run(cmd, cwd=str(root), check=True)
        except FileNotFoundError:
            py = root / ".venv" / "Scripts" / "python.exe"
            if not py.is_file():
                py = Path("python")
            # [변경사유]: upload 는 서브커맨드+플래그 — -m kakao_import 뒤에 그대로 전달
            alt = [str(py), "-m", "kakao_import", *cmd[1:]]
            log.info("fallback exec %s", " ".join(alt))
            try:
                subprocess.run(alt, cwd=str(root), check=True)
            except subprocess.CalledProcessError as exc:
                # [변경사유]: upload OFF 일 때만 classify fail-open. upload ON 이면 fail-closed
                if cmd[1] == "poster-classify" and not run_upload:
                    log.error("poster-classify failed code=%s — continue", exc.returncode)
                    continue
                log.error("kakao-import failed cmd=%s code=%s", cmd, exc.returncode)
                raise
        except subprocess.CalledProcessError as exc:
            if cmd[1] == "poster-classify" and not run_upload:
                log.error("poster-classify failed code=%s — continue", exc.returncode)
                continue
            log.error("kakao-import failed cmd=%s code=%s", cmd, exc.returncode)
            raise

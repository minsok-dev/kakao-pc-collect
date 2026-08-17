# [변경사유]: 방 루프 — txt 내보내기 + 서랍 50칸 배치 + 워터마크 중단 + import 호출
"""수집 파이프라인."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from kakao_pc_collect.config import RoomSpec, Settings
from kakao_pc_collect.drawer import (
    click_download,
    open_drawer,
    select_photo_batch,
)
from kakao_pc_collect.files import (
    copy_new_images,
    snapshot_names,
    wait_for_new_files,
)
from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.stems import is_kakao_image
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
) -> tuple[bool, str]:
    """배치 후 중단 여부."""
    images = [n for n in batch_names if is_kakao_image(n)]
    if not images:
        return True, "no_new_images"

    stems = unique_stems(images)
    if not stems:
        return True, "no_stems"

    # 전부 이미 photos에 있었음
    if all(n in photos_before for n in images):
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
    """한 방 수집. 반환 요약 dict."""
    summary: dict = {
        "room_id": room.id,
        "search": room.search,
        "chat_exported": False,
        "photo_batches": 0,
        "copied": 0,
        "stop_reason": None,
    }
    marks = load_watermarks(settings.watermark_path)
    watermark = marks.get(room.id) or max_stem_in_dir(settings.photos_dir)
    log.info(
        "collect_room id=%s search=%r watermark=%s",
        room.id,
        room.search,
        watermark,
    )

    # Ctrl+S·☰ 는 메인 목록이 아니라 채팅방 창에서 수행
    win = open_room_by_search(room.search, dry_run=dry_run)

    if chats:
        export_chat_txt(win, settings.chats_dir, dry_run=dry_run)
        summary["chat_exported"] = True

    if not photos:
        return summary

    coords = settings.coords
    room_hwnd = hwnd_of(win)
    total_copied = 0
    best_stem = watermark

    for batch_i in range(max_photo_batches):
        photos_before = _existing_photo_names(settings.photos_dir)
        before_dl = snapshot_names(settings.download_dir)
        skip = batch_i * coords.select_count

        log.info("photo batch=%s skip_tiles=%s", batch_i + 1, skip)

        drawer_hwnd = open_drawer(room_hwnd, coords, dry_run=dry_run)
        select_photo_batch(
            drawer_hwnd,
            coords,
            skip_tiles=skip,
            dry_run=dry_run,
        )
        click_download(drawer_hwnd, coords, dry_run=dry_run)

        if dry_run:
            summary["photo_batches"] = batch_i + 1
            summary["stop_reason"] = "dry_run"
            break

        new_names = wait_for_new_files(
            settings.download_dir, before=before_dl
        )
        copied = copy_new_images(
            download_dir=settings.download_dir,
            photos_dir=settings.photos_dir,
            names=new_names,
        )
        total_copied += len(copied)
        summary["photo_batches"] = batch_i + 1

        batch_for_judge = new_names or copied
        stop, reason = _should_stop_room(
            batch_names=batch_for_judge,
            watermark=watermark,
            photos_before=photos_before,
        )
        mx = max_stem_among(copied or new_names)
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

    return summary


def run_collect(
    settings: Settings,
    *,
    room_ids: list[str] | None = None,
    chats: bool = True,
    photos: bool = True,
    dry_run: bool = False,
    run_import: bool | None = None,
) -> list[dict]:
    """허용 방 순회 수집."""
    settings.chats_dir.mkdir(parents=True, exist_ok=True)
    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    settings.download_dir.mkdir(parents=True, exist_ok=True)

    rooms = [r for r in settings.rooms if r.enabled]
    if room_ids:
        want = set(room_ids)
        rooms = [r for r in rooms if r.id in want]
    if not rooms:
        raise RuntimeError("enabled room 없음 — config/rooms.yaml 확인")

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
    if do_import and not dry_run:
        _call_kakao_import(settings)

    return results


def _call_kakao_import(settings: Settings) -> None:
    """수집 후 kakao-import run + similar-detect (upload 호출 금지)."""
    root = settings.kakao_import_root
    log.info("calling kakao-import root=%s", root)
    cmds = [
        ["kakao-import", "run"],
        ["kakao-import", "similar-detect"],
    ]
    for cmd in cmds:
        log.info("exec %s", " ".join(cmd))
        try:
            subprocess.run(cmd, cwd=str(root), check=True)
        except FileNotFoundError:
            py = root / ".venv" / "Scripts" / "python.exe"
            if not py.is_file():
                py = Path("python")
            alt = [str(py), "-m", "kakao_import", cmd[1]]
            log.info("fallback exec %s", " ".join(alt))
            subprocess.run(alt, cwd=str(root), check=True)
        except subprocess.CalledProcessError as exc:
            log.error("kakao-import failed cmd=%s code=%s", cmd, exc.returncode)
            raise

# [변경사유]: kakao-pc-collect CLI — run / calibrate
"""CLI."""

from __future__ import annotations

import json
import time

import click

from kakao_pc_collect.config import load_settings
from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.pipeline import run_collect
from kakao_pc_collect.win_click import (
    find_hwnd_by_title_contains,
    foreground_hwnd,
    print_cursor_client_offset,
    window_client_size,
)


@click.group()
@click.option("--log-level", default=None, help="DEBUG|INFO|WARNING")
@click.pass_context
def main(ctx: click.Context, log_level: str | None) -> None:
    """카카오톡 PC 하이브리드 수집 → kakao-import input/raw."""
    settings = load_settings()
    level = log_level or settings.log_level
    get_logger("kakao_pc_collect", level=level)
    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings


@main.command("run")
@click.option(
    "--room",
    "rooms",
    multiple=True,
    help="방 id (rooms.yaml). 수집+import+upload E2E 한정. 생략 시 enabled 방 수집·import는 전체 raw",
)
@click.option("--chats-only", is_flag=True, help="txt 내보내기만")
@click.option("--photos-only", is_flag=True, help="서랍 사진만")
@click.option("--no-import", is_flag=True, help="수집 후 kakao-import 호출 안 함")
@click.option(
    "--with-upload",
    is_flag=True,
    help="import 체인 완료 직후 kakao-import upload --no-dry-run (similar hold 유지)",
)
@click.option("--dry-run", is_flag=True, help="클릭·키 입력 없이 경로만 확인")
@click.pass_context
def cmd_run(
    ctx: click.Context,
    rooms: tuple[str, ...],
    chats_only: bool,
    photos_only: bool,
    no_import: bool,
    with_upload: bool,
    dry_run: bool,
) -> None:
    """허용 방 수집. 기본은 upload 없음. --with-upload 또는 KAKAO_COLLECT_RUN_UPLOAD=1 이면 완료 후 upload."""
    if chats_only and photos_only:
        raise click.UsageError("--chats-only 와 --photos-only 동시 사용 불가")
    if no_import and with_upload:
        raise click.UsageError("--no-import 와 --with-upload 동시 사용 불가")
    settings = ctx.obj["settings"]
    chats = not photos_only
    photos = not chats_only
    results = run_collect(
        settings,
        room_ids=list(rooms) if rooms else None,
        chats=chats,
        photos=photos,
        dry_run=dry_run,
        run_import=False if no_import else None,
        run_upload=True if with_upload else None,
    )
    click.echo(json.dumps(results, ensure_ascii=False, indent=2))


@main.command("calibrate")
@click.option(
    "--title",
    default=None,
    help="창 제목 부분 문자열 (예: 카카오톡 / 채팅방 서랍). 없으면 전경 창",
)
@click.option(
    "--watch",
    is_flag=True,
    help="0.5초마다 커서 클라이언트 오프셋 출력 (Ctrl+C 종료)",
)
def cmd_calibrate(title: str | None, watch: bool) -> None:
    """
    현재 커서의 창 클라이언트 상대 좌표를 출력.
    coords.yaml 의 hamburger / first_photo / download / search_icon 에 기입.
    """
    def _once() -> tuple[int, int]:
        hwnd = None
        if title:
            hwnd = find_hwnd_by_title_contains(title)
            if hwnd is None:
                raise click.ClickException(f"창 없음 title 포함={title!r}")
        else:
            hwnd = foreground_hwnd()
        off = print_cursor_client_offset(hwnd)
        size = window_client_size(hwnd)
        click.echo(f"client_offset={list(off)}  client_size={list(size)}")
        return off

    if watch:
        click.echo("watch mode — 목표 위에 마우스 올리고 값 확인 (Ctrl+C)")
        try:
            while True:
                _once()
                time.sleep(0.5)
        except KeyboardInterrupt:
            click.echo("stopped")
            return
    _once()


if __name__ == "__main__":
    main(prog_name="kakao-pc-collect")

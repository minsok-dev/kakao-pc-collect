# [변경사유]: 방별 마지막 처리 스템 — 배치 중단 워터마크
"""워터마크 저장."""

from __future__ import annotations

import json
from pathlib import Path

from kakao_pc_collect.logging_util import get_logger
from kakao_pc_collect.stems import is_kakao_image, parse_kakao_stem, stem_key

log = get_logger(__name__)


def load_watermarks(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in (data or {}).items()}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("watermark load fail path=%s err=%s", path, exc)
        return {}


def save_watermarks(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def max_stem_in_dir(folder: Path) -> str | None:
    """폴더 안 KakaoTalk 이미지 스템 최댓값."""
    if not folder.is_dir():
        return None
    best: str | None = None
    for p in folder.iterdir():
        if not p.is_file() or not is_kakao_image(p.name):
            continue
        stem, _seq, _ext = parse_kakao_stem(p.name)
        if not stem:
            continue
        sk = stem_key(stem)
        if best is None or sk > best:
            best = sk
    return best


def max_stem_among(names: list[str]) -> str | None:
    best: str | None = None
    for name in names:
        stem, _seq, _ext = parse_kakao_stem(name)
        if not stem:
            continue
        sk = stem_key(stem)
        if best is None or sk > best:
            best = sk
    return best


def min_stem_among(names: list[str]) -> str | None:
    best: str | None = None
    for name in names:
        stem, _seq, _ext = parse_kakao_stem(name)
        if not stem:
            continue
        sk = stem_key(stem)
        if best is None or sk < best:
            best = sk
    return best


def unique_stems(names: list[str]) -> set[str]:
    out: set[str] = set()
    for name in names:
        stem, _seq, _ext = parse_kakao_stem(name)
        if stem:
            out.add(stem_key(stem))
    return out

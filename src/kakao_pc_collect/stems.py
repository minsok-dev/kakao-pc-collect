# [변경사유]: KakaoTalk_YYYYMMDD_HHMMSSmmm[_NN].ext 스템 — 워터마크·앨범 키
"""파일명 스템 파싱."""

from __future__ import annotations

import re
from pathlib import Path

# KakaoTalk_20260815_234947259.png / _01.png
_STEM_RE = re.compile(
    r"^KakaoTalk_(\d{8}_\d{9})(?:_(\d+))?\.([A-Za-z0-9]+)$",
    re.IGNORECASE,
)

IMAGE_EXTS = frozenset({"png", "jpg", "jpeg", "webp", "gif", "bmp"})


def parse_kakao_stem(file_name: str) -> tuple[str | None, int, str]:
    """(stem, sequence, ext_lower). 실패 시 (None, 0, '')."""
    m = _STEM_RE.match(Path(file_name).name)
    if not m:
        return None, 0, ""
    stem = m.group(1)
    seq = int(m.group(2)) if m.group(2) is not None else 0
    return stem, seq, m.group(3).lower()


def is_kakao_image(file_name: str) -> bool:
    stem, _seq, ext = parse_kakao_stem(file_name)
    return stem is not None and ext in IMAGE_EXTS


def stem_key(stem: str) -> str:
    """정렬·비교용 — YYYYMMDD_HHMMSSmmm 문자열 비교로 시간순."""
    return stem

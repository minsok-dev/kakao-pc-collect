# [변경사유]: KakaoTalk_YYYYMMDD_HHMMSSmmm[_NN].ext 스템 — 워터마크·앨범 키
# [변경사유]: 카톡이 같은 이름이면 ` (1)` 을 붙임 — 원본명으로 정규화
"""파일명 스템 파싱."""

from __future__ import annotations

import re
from pathlib import Path

# KakaoTalk_20260815_234947259.png / _01.png / ` (3).png` (Windows 중복)
_STEM_RE = re.compile(
    r"^KakaoTalk_(\d{8}_\d{9})(_\d+)?(?: \((\d+)\))?\.([A-Za-z0-9]+)$",
    re.IGNORECASE,
)

IMAGE_EXTS = frozenset({"png", "jpg", "jpeg", "webp", "gif", "bmp"})


def parse_kakao_stem(file_name: str) -> tuple[str | None, int, str]:
    """(stem, sequence, ext_lower). 실패 시 (None, 0, ''). ` (N)` 은 무시."""
    m = _STEM_RE.match(Path(file_name).name)
    if not m:
        return None, 0, ""
    stem = m.group(1)
    album = m.group(2)
    seq = int(album[1:]) if album else 0
    return stem, seq, m.group(4).lower()


def canonical_kakao_name(file_name: str) -> str | None:
    """
    방 photos 저장명. ` (N)` 제거, 확장자 소문자.
    KakaoTalk_…_13 (3).jpg → KakaoTalk_…_13.jpg
    """
    m = _STEM_RE.match(Path(file_name).name)
    if not m:
        return None
    ext = m.group(4).lower()
    if ext not in IMAGE_EXTS:
        return None
    album = m.group(2) or ""
    return f"KakaoTalk_{m.group(1)}{album}.{ext}"


def is_kakao_image(file_name: str) -> bool:
    stem, _seq, ext = parse_kakao_stem(file_name)
    return stem is not None and ext in IMAGE_EXTS


def stem_key(stem: str) -> str:
    """정렬·비교용 — YYYYMMDD_HHMMSSmmm 문자열 비교로 시간순."""
    return stem

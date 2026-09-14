# [변경사유]: 수집 도구 로그 — 메시지 본문 덤프 금지. 패키지 루트만 핸들러(중복 출력 방지)
"""로깅."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_PKG = "kakao_pc_collect"


def get_logger(name: str = _PKG, level: str = "INFO") -> logging.Logger:
    pkg = logging.getLogger(_PKG)
    if not pkg.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        pkg.addHandler(handler)
        pkg.propagate = False
    pkg.setLevel(getattr(logging, level.upper(), logging.INFO))
    if name == _PKG:
        return pkg
    # 자식은 루트로만 전파 — 모듈마다 핸들러를 달면 같은 줄이 두 번 찍힘
    child = logging.getLogger(name)
    for handler in list(child.handlers):
        child.removeHandler(handler)
    child.propagate = True
    return child


def attach_file_handler(path: Path, level: str = "INFO") -> logging.Handler:
    """실행별 collect.log — 콘솔 핸들러는 유지하고 파일만 추가."""
    pkg = logging.getLogger(_PKG)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    pkg.addHandler(handler)
    return handler


def detach_file_handler(handler: logging.Handler) -> None:
    pkg = logging.getLogger(_PKG)
    pkg.removeHandler(handler)
    handler.close()

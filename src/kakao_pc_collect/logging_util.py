# [변경사유]: 수집 도구 로그 — 메시지 본문 덤프 금지
"""로깅."""

from __future__ import annotations

import logging
import sys


def get_logger(name: str = "kakao_pc_collect", level: str = "INFO") -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        log.addHandler(handler)
    log.setLevel(getattr(logging, level.upper(), logging.INFO))
    return log

"""
Structured Logging cho V-AI.
Thay thế toàn bộ print() bằng logger chuẩn Python.
Fixes: M1 — Không có Security Logging.
"""

import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_CONFIGURED = False


def _configure_root() -> None:
    """Cấu hình root logger một lần duy nhất."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    root = logging.getLogger("v_ai")
    root.setLevel(logging.DEBUG)

    # Console handler — human-readable
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console)

    # File handler — detailed
    file_handler = logging.FileHandler(
        str(LOG_DIR / "v_ai.log"),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(file_handler)

    # Security log — chỉ ghi WARNING+ (auth failures, injection attempts, rate limit)
    security_handler = logging.FileHandler(
        str(LOG_DIR / "security.log"),
        encoding="utf-8",
    )
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | SECURITY | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(security_handler)


def get_logger(name: str) -> logging.Logger:
    """Trả về logger con cho module cụ thể.

    Usage:
        from shared.security.logging import get_logger
        logger = get_logger("a0.orchestrator")
        logger.info("Đã khởi tạo session %s", session_id)
        logger.warning("SECURITY: prompt injection detected from %s", client_ip)
    """
    _configure_root()
    return logging.getLogger(f"v_ai.{name}")

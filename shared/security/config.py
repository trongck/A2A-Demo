"""
Security Configuration cho V-AI.
Đọc các biến bảo mật từ .env với cơ chế graceful degradation:
- Khi biến để trống → tắt enforcement (dev mode)
- Khi có giá trị → enforce nghiêm ngặt (staging/prod)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


# --- API Authentication ---
# Key cho frontend gọi backend A0. Trống = tắt auth (dev mode).
V_AI_API_KEY: str = os.environ.get("V_AI_API_KEY", "").strip()

# Shared secret giữa A0 ↔ A1 ↔ A2 ↔ MCP. Trống = tắt (dev mode).
V_AI_INTERNAL_SECRET: str = os.environ.get("V_AI_INTERNAL_SECRET", "").strip()

# --- CORS ---
_raw_origins = os.environ.get(
    "V_AI_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).strip()
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# --- Rate Limiting ---
RATE_LIMIT_PER_MINUTE: int = int(os.environ.get("V_AI_RATE_LIMIT_PER_MINUTE", "10"))
RATE_LIMIT_READ_PER_MINUTE: int = int(os.environ.get("V_AI_RATE_LIMIT_READ_PER_MINUTE", "60"))

# --- Input Validation ---
MAX_MESSAGE_LENGTH: int = int(os.environ.get("V_AI_MAX_MESSAGE_LENGTH", "2000"))
MAX_SESSION_ID_LENGTH: int = 128
SESSION_ID_PATTERN: str = r"^[a-zA-Z0-9_\-]+$"

# --- Flags ---
AUTH_ENABLED: bool = bool(V_AI_API_KEY)
INTERNAL_AUTH_ENABLED: bool = bool(V_AI_INTERNAL_SECRET)

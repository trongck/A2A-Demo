"""
Shared Security Module cho V-AI.
Tập trung toàn bộ cơ chế bảo mật: config, logging, auth, rate limit, sanitization.
"""

from shared.security.config import (
    ALLOWED_ORIGINS,
    AUTH_ENABLED,
    INTERNAL_AUTH_ENABLED,
    MAX_MESSAGE_LENGTH,
    V_AI_API_KEY,
    V_AI_INTERNAL_SECRET,
)
from shared.security.logging import get_logger
from shared.security.middleware import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    require_api_key,
    require_internal_secret,
)
from shared.security.rate_limiter import chat_limiter, read_limiter
from shared.security.sanitizer import (
    sanitize_user_input,
    validate_message,
    validate_session_id,
)

__all__ = [
    # Config
    "ALLOWED_ORIGINS",
    "AUTH_ENABLED",
    "INTERNAL_AUTH_ENABLED",
    "MAX_MESSAGE_LENGTH",
    "V_AI_API_KEY",
    "V_AI_INTERNAL_SECRET",
    # Logging
    "get_logger",
    # Middleware
    "RateLimitMiddleware",
    "SecurityHeadersMiddleware",
    "require_api_key",
    "require_internal_secret",
    # Rate limiter
    "chat_limiter",
    "read_limiter",
    # Sanitizer
    "sanitize_user_input",
    "validate_message",
    "validate_session_id",
]

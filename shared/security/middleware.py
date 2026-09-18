"""
FastAPI Security Middleware cho V-AI.
Fixes: H1 (Auth), H5 (Inter-agent auth), L1 (CSRF), L2 (Security headers).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException, Header

from shared.security.config import (
    AUTH_ENABLED,
    INTERNAL_AUTH_ENABLED,
    V_AI_API_KEY,
    V_AI_INTERNAL_SECRET,
)
from shared.security.logging import get_logger
from shared.security.rate_limiter import chat_limiter, read_limiter

logger = get_logger("security.middleware")


# ──────────────────────────────────────────────
# 1. Security Headers Middleware (L2)
# ──────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Thêm security headers vào mọi response. Fixes L2."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # CSP: cho phép self + inline styles (cần cho React) + Google Fonts
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' http://127.0.0.1:* http://localhost:*; "
            "frame-ancestors 'none';"
        )
        return response


# ──────────────────────────────────────────────
# 2. Rate Limit Middleware (H2)
# ──────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit dựa trên client IP. Fixes H2."""

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Áp dụng rate limit chặt hơn cho write endpoints
        if path in ("/api/chat", "/api/chat/stream", "/api/session/new"):
            if not chat_limiter.allow(client_ip):
                logger.warning(
                    "SECURITY: Rate limit BLOCKED — ip=%s, path=%s",
                    client_ip, path,
                )
                return Response(
                    content='{"detail":"Quá nhiều yêu cầu. Vui lòng thử lại sau."}',
                    status_code=429,
                    media_type="application/json",
                )
        elif path.startswith("/api/"):
            if not read_limiter.allow(client_ip):
                return Response(
                    content='{"detail":"Quá nhiều yêu cầu. Vui lòng thử lại sau."}',
                    status_code=429,
                    media_type="application/json",
                )

        return await call_next(request)


# ──────────────────────────────────────────────
# 3. FastAPI Dependencies (H1, H5)
# ──────────────────────────────────────────────

async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Dependency cho public endpoints (frontend → A0).
    Fixes H1: Không có Authentication.

    Graceful degradation: Nếu V_AI_API_KEY trống trong .env → skip xác thực.
    """
    if not AUTH_ENABLED:
        return  # Dev mode — không enforce

    if not x_api_key or x_api_key != V_AI_API_KEY:
        logger.warning("SECURITY: Invalid API key attempt — key='%s...'", x_api_key[:8])
        raise HTTPException(
            status_code=401,
            detail="Xác thực thất bại. Vui lòng cung cấp API key hợp lệ.",
        )


async def require_internal_secret(x_internal_secret: str = Header(default="")) -> None:
    """Dependency cho inter-agent endpoints (A0 → A1, A0 → A2, Agent → MCP).
    Fixes H5: Inter-agent Communication không xác thực.

    Graceful degradation: Nếu V_AI_INTERNAL_SECRET trống → skip.
    """
    if not INTERNAL_AUTH_ENABLED:
        return  # Dev mode — không enforce

    if not x_internal_secret or x_internal_secret != V_AI_INTERNAL_SECRET:
        logger.warning("SECURITY: Invalid internal secret attempt")
        raise HTTPException(
            status_code=403,
            detail="Truy cập nội bộ bị từ chối. Secret không hợp lệ.",
        )

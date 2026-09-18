"""
Rate Limiter cho V-AI.
In-memory Token Bucket — không thêm dependency Redis.
Fixes: H2 — Không có Rate Limiting.
"""

import time
import threading
from collections import defaultdict
from shared.security.config import RATE_LIMIT_PER_MINUTE, RATE_LIMIT_READ_PER_MINUTE
from shared.security.logging import get_logger

logger = get_logger("security.rate_limiter")


class TokenBucket:
    """Token Bucket rate limiter, thread-safe."""

    def __init__(self, rate_per_minute: int):
        self.rate = rate_per_minute
        self.interval = 60.0 / rate_per_minute if rate_per_minute > 0 else 0
        self._buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"tokens": float(rate_per_minute), "last_refill": time.monotonic()}
        )
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Kiểm tra và tiêu thụ 1 token. True = cho phép, False = bị rate limit."""
        if self.rate <= 0:
            return True

        with self._lock:
            now = time.monotonic()
            bucket = self._buckets[key]

            # Refill tokens
            elapsed = now - bucket["last_refill"]
            refill = elapsed / self.interval
            bucket["tokens"] = min(float(self.rate), bucket["tokens"] + refill)
            bucket["last_refill"] = now

            if bucket["tokens"] >= 1.0:
                bucket["tokens"] -= 1.0
                return True

            logger.warning(
                "SECURITY: Rate limit exceeded — key='%s', bucket_tokens=%.2f",
                key[:50], bucket["tokens"],
            )
            return False

    def cleanup(self, max_age_seconds: int = 600) -> None:
        """Xóa các bucket cũ không hoạt động (chống memory leak)."""
        with self._lock:
            now = time.monotonic()
            stale_keys = [
                k for k, v in self._buckets.items()
                if now - v["last_refill"] > max_age_seconds
            ]
            for k in stale_keys:
                del self._buckets[k]


# Singleton instances
chat_limiter = TokenBucket(RATE_LIMIT_PER_MINUTE)
read_limiter = TokenBucket(RATE_LIMIT_READ_PER_MINUTE)

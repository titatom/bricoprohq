"""
Lightweight in-process rate limiter for sensitive endpoints (login).

Uses a fixed-window counter keyed by (bucket_name, identity). Designed for
single-process Bricopro HQ deployments — a multi-worker setup should swap
this for Redis-backed counters (the public API would not change).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

DEFAULT_LOGIN_LIMIT = 10
DEFAULT_LOGIN_WINDOW_SECONDS = 60.0


@dataclass
class _Window:
    started_at: float
    count: int


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Window] = {}

    def check(
        self,
        bucket: str,
        identity: str,
        *,
        limit: int,
        window_seconds: float,
    ) -> tuple[bool, float]:
        """
        Return ``(allowed, retry_after_seconds)``.

        When ``allowed`` is True the caller should proceed. When False, the
        identity has exceeded ``limit`` requests inside ``window_seconds`` and
        the caller should respond with HTTP 429; ``retry_after_seconds`` tells
        the client when the window resets.
        """
        if limit <= 0:
            return True, 0.0
        now = time.monotonic()
        key = (bucket, identity)
        with self._lock:
            window = self._buckets.get(key)
            if window is None or (now - window.started_at) >= window_seconds:
                self._buckets[key] = _Window(started_at=now, count=1)
                return True, 0.0
            if window.count >= limit:
                return False, max(0.0, window_seconds - (now - window.started_at))
            window.count += 1
            return True, 0.0

    def reset(self, bucket: str, identity: str) -> None:
        with self._lock:
            self._buckets.pop((bucket, identity), None)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()


_default_limiter = RateLimiter()


def default_limiter() -> RateLimiter:
    return _default_limiter

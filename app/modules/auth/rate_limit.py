import threading
import time
from collections import deque
from typing import Annotated

from fastapi import Depends, Request, status

from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode, api_error


class SlidingWindowRateLimiter:
    """In-memory, per-process sliding-window limiter.

    Not shared across workers or hosts; for multi-process deployments use a
    shared store (e.g. Redis) behind the same interface.
    """

    _PRUNE_EVERY = 1024

    def __init__(self, prune_every: int = _PRUNE_EVERY) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0
        self._prune_every = prune_every

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            self._calls += 1
            if self._calls % self._prune_every == 0:
                self._prune_expired(cutoff)

            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= limit:
                return False

            hits.append(now)
            return True

    def _prune_expired(self, cutoff: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for key in stale:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._calls = 0


limiter = SlidingWindowRateLimiter()


def _enforce_limit(
    request: Request,
    settings: Settings,
    *,
    key_prefix: str,
    limit: int,
    window_seconds: int,
) -> None:
    client = request.client.host if request.client else "unknown"
    allowed = limiter.allow(
        key=f"{key_prefix}:{client}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        raise api_error(
            ErrorCode.RATE_LIMITED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(window_seconds)},
        )


def login_rate_limit(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    _enforce_limit(
        request,
        settings,
        key_prefix="login",
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )


def refresh_rate_limit(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    _enforce_limit(
        request,
        settings,
        key_prefix="refresh",
        limit=settings.refresh_rate_limit_attempts,
        window_seconds=settings.refresh_rate_limit_window_seconds,
    )

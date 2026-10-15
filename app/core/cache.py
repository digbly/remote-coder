import threading
import time
from collections.abc import Callable, Hashable
from typing import TypeVar

T = TypeVar("T")

_DEFAULT_MAX_ENTRIES = 2048


class TTLCache:
    """A bounded in-process cache with per-call TTL and prefix invalidation.

    Entries expire once their TTL elapses and are reused until then; a
    non-positive TTL always recomputes and stores nothing. Reads and writes are
    guarded by a lock while the factory runs outside it, so a slow computation
    (a git subprocess, a directory walk) never blocks unrelated keys. The store
    is capped at ``max_entries`` so a long-lived process cannot grow it without
    bound. Safe for the threadpool workers that serve requests, but the cache
    lives in one process: with multiple workers each keeps its own copy.
    """

    def __init__(self, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self._lock = threading.Lock()
        self._max_entries = max_entries
        # key -> (expiry monotonic timestamp, value)
        self._store: dict[Hashable, tuple[float, object]] = {}

    def get_or_set(self, key: Hashable, ttl_seconds: float, factory: Callable[[], T]) -> T:
        """Return the cached value for ``key`` or compute, store and return it."""
        if ttl_seconds > 0:
            with self._lock:
                entry = self._store.get(key)
                if entry is not None and entry[0] > time.monotonic():
                    return entry[1]  # type: ignore[return-value]
        value = factory()
        if ttl_seconds > 0:
            with self._lock:
                self._evict_locked()
                self._store[key] = (time.monotonic() + ttl_seconds, value)
        return value

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        """Drop every entry whose string key starts with ``prefix``."""
        with self._lock:
            stale = [key for key in self._store if isinstance(key, str) and key.startswith(prefix)]
            for key in stale:
                del self._store[key]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict_locked(self) -> None:
        """Make room for a new entry once the store is full.

        Expired entries go first; if the store is still full the oldest inserted
        entry is dropped (FIFO), keeping memory bounded regardless of how many
        distinct keys are seen.
        """
        if len(self._store) < self._max_entries:
            return
        now = time.monotonic()
        for key in [k for k, (expiry, _) in self._store.items() if expiry <= now]:
            del self._store[key]
        while len(self._store) >= self._max_entries:
            del self._store[next(iter(self._store))]

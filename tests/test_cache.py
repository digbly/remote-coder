import pytest

from app.core.cache import TTLCache


class _Clock:
    """A monotonic clock the tests can advance without sleeping."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr("app.core.cache.time.monotonic", fake)
    return fake


def test_reuses_value_within_ttl_then_recomputes(clock: _Clock) -> None:
    cache = TTLCache()
    calls: list[int] = []

    def factory() -> int:
        calls.append(1)
        return len(calls)

    assert cache.get_or_set("k", 10, factory) == 1
    clock.advance(5)
    assert cache.get_or_set("k", 10, factory) == 1
    clock.advance(6)
    assert cache.get_or_set("k", 10, factory) == 2
    assert len(calls) == 2


def test_non_positive_ttl_never_caches() -> None:
    cache = TTLCache()
    calls: list[int] = []

    def factory() -> int:
        calls.append(1)
        return len(calls)

    assert cache.get_or_set("k", 0, factory) == 1
    assert cache.get_or_set("k", 0, factory) == 2
    assert len(calls) == 2


def test_invalidate_drops_a_key() -> None:
    cache = TTLCache()
    assert cache.get_or_set("k", 10, lambda: "first") == "first"
    cache.invalidate("k")
    assert cache.get_or_set("k", 10, lambda: "second") == "second"


def test_invalidate_prefix_drops_only_matching_keys() -> None:
    cache = TTLCache()
    cache.get_or_set("/a\x00status", 10, lambda: "a-status")
    cache.get_or_set("/a\x00repo", 10, lambda: "a-repo")
    cache.get_or_set("/b\x00status", 10, lambda: "b-status")

    cache.invalidate_prefix("/a\x00")

    assert cache.get_or_set("/a\x00status", 10, lambda: "fresh") == "fresh"
    assert cache.get_or_set("/b\x00status", 10, lambda: "fresh") == "b-status"


def test_store_evicts_oldest_when_full() -> None:
    cache = TTLCache(max_entries=2)
    cache.get_or_set("a", 100, lambda: "a")
    cache.get_or_set("b", 100, lambda: "b")

    cache.get_or_set("c", 100, lambda: "c")

    # "a" was inserted first, so it is the entry evicted to make room.
    assert cache.get_or_set("b", 100, lambda: "fresh") == "b"
    assert cache.get_or_set("a", 100, lambda: "fresh") == "fresh"


def test_store_evicts_expired_before_live_entries(clock: _Clock) -> None:
    cache = TTLCache(max_entries=2)
    cache.get_or_set("old", 5, lambda: "old")
    clock.advance(6)
    cache.get_or_set("live", 100, lambda: "live")

    cache.get_or_set("new", 100, lambda: "new")

    # The expired "old" made room, so the live entry survived.
    assert cache.get_or_set("live", 100, lambda: "fresh") == "live"

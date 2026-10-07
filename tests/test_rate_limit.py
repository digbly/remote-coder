from app.modules.auth.rate_limit import SlidingWindowRateLimiter


def test_allows_up_to_limit_then_blocks() -> None:
    limiter = SlidingWindowRateLimiter()
    assert [limiter.allow("k", 3, 60) for _ in range(3)] == [True, True, True]
    assert limiter.allow("k", 3, 60) is False


def test_keys_are_independent() -> None:
    limiter = SlidingWindowRateLimiter()
    assert limiter.allow("a", 1, 60) is True
    assert limiter.allow("b", 1, 60) is True
    assert limiter.allow("a", 1, 60) is False


def test_window_expiry_frees_capacity() -> None:
    limiter = SlidingWindowRateLimiter()
    assert limiter.allow("k", 2, 0) is True
    assert limiter.allow("k", 2, 0) is True
    assert limiter.allow("k", 2, 0) is True


def test_prune_does_not_drop_current_hit() -> None:
    limiter = SlidingWindowRateLimiter(prune_every=1)
    assert limiter.allow("k", 2, 60) is True
    assert limiter.allow("k", 2, 60) is True
    assert limiter.allow("k", 2, 60) is False

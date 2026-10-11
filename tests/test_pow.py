import time

from app.modules.auth.pow import PowChallengeStore
from tests.conftest import solve_pow


def test_issue_returns_unique_challenges() -> None:
    store = PowChallengeStore()
    first = store.issue(ttl_seconds=60, length_bytes=16)
    second = store.issue(ttl_seconds=60, length_bytes=16)
    assert first != second
    assert len(first) == 32


def test_verify_accepts_valid_solution() -> None:
    store = PowChallengeStore()
    challenge = store.issue(ttl_seconds=60, length_bytes=16)
    assert store.verify(challenge, solve_pow(challenge, 2), 2) is True


def test_verify_is_single_use() -> None:
    store = PowChallengeStore()
    challenge = store.issue(ttl_seconds=60, length_bytes=16)
    nonce = solve_pow(challenge, 2)
    assert store.verify(challenge, nonce, 2) is True
    assert store.verify(challenge, nonce, 2) is False


def test_verify_rejects_invalid_solution() -> None:
    store = PowChallengeStore()
    challenge = store.issue(ttl_seconds=60, length_bytes=16)
    assert store.verify(challenge, "0", 8) is False


def test_verify_rejects_unknown_challenge() -> None:
    store = PowChallengeStore()
    assert store.verify("deadbeef", "0", 1) is False


def test_verify_rejects_expired_challenge() -> None:
    store = PowChallengeStore()
    challenge = store.issue(ttl_seconds=0, length_bytes=8)
    time.sleep(0.001)
    assert store.verify(challenge, solve_pow(challenge, 0), 0) is False


def test_verify_rejects_missing_values() -> None:
    store = PowChallengeStore()
    assert store.verify(None, "0", 1) is False
    assert store.verify("challenge", None, 1) is False


def test_zero_difficulty_accepts_any_nonce() -> None:
    store = PowChallengeStore()
    challenge = store.issue(ttl_seconds=60, length_bytes=8)
    assert store.verify(challenge, "anything", 0) is True


def test_reset_clears_challenges() -> None:
    store = PowChallengeStore()
    challenge = store.issue(ttl_seconds=60, length_bytes=8)
    store.reset()
    assert store.verify(challenge, solve_pow(challenge, 1), 1) is False

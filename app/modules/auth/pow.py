import hashlib
import secrets
import threading
import time

ALGORITHM = "sha256"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _has_leading_zero_nibbles(value: str, difficulty: int) -> bool:
    if difficulty <= 0:
        return True
    return _digest(value)[:difficulty] == "0" * difficulty


class PowChallengeStore:
    """In-memory, per-process store of single-use proof-of-work challenges.

    Not shared across workers or hosts; for multi-process deployments use a
    shared store (e.g. Redis) behind the same interface.
    """

    _PRUNE_EVERY = 1024

    def __init__(self, prune_every: int = _PRUNE_EVERY) -> None:
        self._challenges: dict[str, float] = {}
        self._lock = threading.Lock()
        self._calls = 0
        self._prune_every = prune_every

    def issue(self, ttl_seconds: int, length_bytes: int) -> str:
        challenge = secrets.token_hex(length_bytes)
        expiry = time.monotonic() + ttl_seconds
        with self._lock:
            self._calls += 1
            if self._calls % self._prune_every == 0:
                self._prune(time.monotonic())
            self._challenges[challenge] = expiry
        return challenge

    def verify(self, challenge: str | None, nonce: str | None, difficulty: int) -> bool:
        """Consume a challenge and check the solution it was solved with.

        The challenge is single-use: it is removed whether or not the solution
        is valid, so a wrong guess cannot be replayed against the same token.
        """
        if not challenge or not nonce:
            return False

        with self._lock:
            expiry = self._challenges.pop(challenge, None)

        if expiry is None or expiry < time.monotonic():
            return False

        return _has_leading_zero_nibbles(f"{challenge}{nonce}", difficulty)

    def _prune(self, now: float) -> None:
        stale = [challenge for challenge, expiry in self._challenges.items() if expiry < now]
        for challenge in stale:
            del self._challenges[challenge]

    def reset(self) -> None:
        with self._lock:
            self._challenges.clear()
            self._calls = 0


pow_store = PowChallengeStore()

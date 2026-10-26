"""Counting attempts in memory, to limit how often something can be tried.

The counts live in this process, not in Redis: on Upstash's free plan, a
write on every attempt would let an attack use up the monthly command quota,
and the login and game sessions stored there would go down with it. That only
works because each deployment runs exactly one instance (`--max-instances 1`);
with more instances, every one of them would allow the full limit. Counts
start over when the instance restarts.

Not thread-safe: use it from the event loop only. `acquire` never awaits, so
two requests can't both pass a check that only one of them should.
"""
import time
from collections import deque
from collections.abc import Callable

__all__ = ["AttemptLimiter"]


class AttemptLimiter:
    """Allow at most `limit` attempts per key in any `window_seconds`.

    A sliding window: each attempt counts for `window_seconds` after it was
    made. Attempts that were refused don't count, so waiting out the time
    `acquire` returns is always enough.

    At most `max_keys` keys are tracked, so a flood of made-up keys can't
    grow memory without bound. When that many keys have recent attempts, new
    keys are refused until some expire. Refusing is deliberate: forgetting old
    keys instead would let a flood reset the count of the key under attack.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}

    def acquire(self, key: str) -> float | None:
        """Record an attempt for `key`, or refuse it.

        Returns None if the attempt is allowed (and counted), or else the
        number of seconds until the next attempt for `key` will be allowed.
        """
        now = self._clock()
        attempts = self._attempts.get(key)
        if attempts is None:
            if len(self._attempts) >= self._max_keys:
                self._prune(now)
                if len(self._attempts) >= self._max_keys:
                    return self._window
            attempts = self._attempts[key] = deque()
        else:
            self._drop_expired(attempts, now)

        if len(attempts) >= self._limit:
            return attempts[0] + self._window - now
        attempts.append(now)
        return None

    def reset(self, key: str) -> None:
        """Forget the attempts for `key`, e.g. after a successful login."""
        self._attempts.pop(key, None)

    def _drop_expired(self, attempts: deque[float], now: float) -> None:
        while attempts and attempts[0] <= now - self._window:
            attempts.popleft()

    def _prune(self, now: float) -> None:
        """Drop every key whose attempts have all expired."""
        for key in list(self._attempts):
            self._drop_expired(self._attempts[key], now)
            if not self._attempts[key]:
                del self._attempts[key]

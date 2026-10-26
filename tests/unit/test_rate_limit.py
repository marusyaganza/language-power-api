# tests/unit/test_rate_limit.py
from auth.rate_limit import AttemptLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def limiter(limit=3, window=60, **kwargs):
    clock = FakeClock()
    return AttemptLimiter(limit, window, clock=clock, **kwargs), clock


def test_allows_up_to_the_limit_then_says_how_long_to_wait():
    limit, clock = limiter()
    assert [limit.acquire("a") for _ in range(3)] == [None, None, None]
    clock.now += 10
    assert limit.acquire("a") == 50  # the first attempt counts for 60 s


def test_the_window_slides():
    limit, clock = limiter()
    limit.acquire("a")
    clock.now += 30
    limit.acquire("a")
    limit.acquire("a")

    clock.now += 30  # the first attempt has just expired
    assert limit.acquire("a") is None
    assert limit.acquire("a") == 30  # the second one expires next


def test_refused_attempts_do_not_count():
    limit, clock = limiter()
    for _ in range(3):
        limit.acquire("a")
    for _ in range(10):
        limit.acquire("a")  # all refused
    clock.now += 60
    assert limit.acquire("a") is None


def test_keys_are_counted_separately():
    limit, _clock = limiter()
    for _ in range(3):
        limit.acquire("a")
    assert limit.acquire("a") is not None
    assert limit.acquire("b") is None


def test_reset_starts_the_count_over():
    limit, _clock = limiter()
    for _ in range(3):
        limit.acquire("a")
    limit.reset("a")
    assert limit.acquire("a") is None
    limit.reset("never-seen")  # not an error


def test_at_max_keys_new_keys_are_refused_but_known_ones_still_work():
    limit, clock = limiter(max_keys=2)
    limit.acquire("a")
    limit.acquire("b")
    # Refused rather than forgetting "a" or "b": forgetting would let a flood
    # of made-up keys reset the count of the key under attack.
    assert limit.acquire("c") == 60
    assert limit.acquire("a") is None


def test_keys_with_only_expired_attempts_are_dropped_to_make_room():
    limit, clock = limiter(max_keys=2)
    limit.acquire("a")
    limit.acquire("b")
    clock.now += 60
    assert limit.acquire("c") is None
    assert limit.acquire("d") is None  # "a" and "b" were both dropped
    assert limit.acquire("e") == 60

"""The current time, and the UTC day that daily limits are counted in.

Callers use `utc_day.now()` through the module, so tests can replace it.
"""

import math
from datetime import UTC, datetime, time, timedelta


def now() -> datetime:
    return datetime.now(UTC)


def start_of_day(moment: datetime) -> datetime:
    """Midnight UTC at the start of `moment`'s UTC day."""
    return datetime.combine(moment.astimezone(UTC).date(), time(), tzinfo=UTC)


def seconds_until_next_day(moment: datetime) -> int:
    """Whole seconds from `moment` until the next midnight UTC, at least 1.

    For a `Retry-After` header when a daily limit is reached.
    """
    remaining = start_of_day(moment) + timedelta(days=1) - moment
    return max(1, math.ceil(remaining.total_seconds()))

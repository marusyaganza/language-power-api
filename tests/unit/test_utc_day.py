# tests/unit/test_utc_day.py
from datetime import UTC, datetime, timedelta, timezone

import pytest

from core import utc_day


def test_start_of_day_is_midnight_utc_even_for_other_timezones():
    # 01:30 in UTC+3 is still the previous day in UTC.
    moment = datetime(2026, 10, 28, 1, 30, tzinfo=timezone(timedelta(hours=3)))
    assert utc_day.start_of_day(moment) == datetime(2026, 10, 27, tzinfo=UTC)


@pytest.mark.parametrize(
    ("moment", "seconds"),
    [
        (datetime(2026, 10, 28, 23, 0, tzinfo=UTC), 3600),
        (datetime(2026, 10, 28, 0, 0, tzinfo=UTC), 24 * 3600),
        (datetime(2026, 10, 28, 23, 59, 59, 500_000, tzinfo=UTC), 1),  # rounded up, never 0
    ],
)
def test_seconds_until_next_day(moment, seconds):
    assert utc_day.seconds_until_next_day(moment) == seconds

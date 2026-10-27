# tests/unit/test_game_selection.py
"""Which words a game session uses, and how its score is rounded.

These test private helpers of games.service directly: their logic is easy to
get wrong and slow to reach through the API.
"""

from datetime import UTC, datetime, timedelta

import pytest

from games.schemas import GameMode
from games.service import _percent_half_up, _pick_word_ids, _WordSchedule

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def new(word_id):
    return _WordSchedule(word_id, next_review_date=None, last_reviewed_at=None)


def practiced(word_id, *, due_in_days, reviewed_days_ago):
    return _WordSchedule(
        word_id,
        next_review_date=NOW + timedelta(days=due_in_days),
        last_reviewed_at=NOW - timedelta(days=reviewed_days_ago),
    )


SCHEDULES = [
    practiced(1, due_in_days=-1, reviewed_days_ago=5),  # due
    practiced(2, due_in_days=-3, reviewed_days_ago=9),  # due, more overdue
    practiced(3, due_in_days=2, reviewed_days_ago=1),  # not due
    practiced(4, due_in_days=4, reviewed_days_ago=20),  # not due, practiced longest ago
    new(5),
    new(6),
]


def pick(mode, new_words_first=False, limit=10):
    return _pick_word_ids(SCHEDULES, mode, new_words_first, NOW, limit)


def test_spaced_uses_due_words_most_overdue_first_then_new_words():
    ids = pick(GameMode.SPACED)
    assert ids[:2] == [2, 1]
    assert sorted(ids[2:]) == [5, 6]


def test_spaced_never_uses_words_that_are_not_due():
    assert not {3, 4} & set(pick(GameMode.SPACED))


def test_review_uses_every_word_least_recently_practiced_first():
    ids = pick(GameMode.REVIEW)
    assert ids[:4] == [4, 2, 1, 3]
    assert sorted(ids[4:]) == [5, 6]


def test_new_words_first_puts_new_words_ahead():
    ids = pick(GameMode.SPACED, new_words_first=True)
    assert sorted(ids[:2]) == [5, 6]
    assert ids[2:] == [2, 1]


def test_limit_keeps_the_first_words_in_order():
    assert pick(GameMode.REVIEW, limit=2) == [4, 2]


@pytest.mark.parametrize(
    ("part", "total", "percent"),
    [
        (0, 0, 0),  # empty session
        (1, 8, 13),  # 12.5 rounds up, not to even
        (3, 8, 38),  # 37.5
        (1, 3, 33),
        (2, 3, 67),
        (5, 5, 100),
    ],
)
def test_percent_rounds_half_up(part, total, percent):
    assert _percent_half_up(part, total) == percent

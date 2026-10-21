# tests/unit/test_spaced_repetition.py
from datetime import UTC, datetime, timedelta

import pytest

from games.scoring import AnswerGrade
from games.spaced_repetition import (
    SpacedRepetitionConfig,
    WordProgressState,
    initialize_progress,
    update_progress,
)

CORRECT, CLOSE, WRONG = AnswerGrade.CORRECT, AnswerGrade.CLOSE, AnswerGrade.WRONG
# Default learning steps: 15 minutes, 1 day, 6 days. Graduating interval: 6 days.
STEPS = [15, 1440, 8640]


def learning(step_index=0, lapses=0) -> WordProgressState:
    state = initialize_progress()
    state.learning_step_index = step_index
    state.lapses = lapses
    return state


def graduated(interval_days, consecutive_correct=3, lapses=0) -> WordProgressState:
    return WordProgressState(
        is_learning=False,
        learning_step_index=len(STEPS) - 1,
        interval_days=interval_days,
        consecutive_correct=consecutive_correct,
        lapses=lapses,
        next_review_date=datetime.now(UTC),
    )


def update(state, grade, config=None) -> tuple[WordProgressState, timedelta]:
    """Run `update_progress` and return the state plus how far ahead the next
    review is. The result is rounded to the second: `now` is read inside the
    function, a few microseconds after `before`."""
    kwargs = {"config": config} if config else {}
    before = datetime.now(UTC)
    state = update_progress(state, grade, **kwargs)
    delay = state.next_review_date - before
    return state, timedelta(seconds=round(delay.total_seconds()))


def test_initialize_progress_starts_learning_now():
    before = datetime.now(UTC)
    state = initialize_progress()
    assert (state.is_learning, state.learning_step_index, state.interval_days) == (True, 0, 0.0)
    assert (state.consecutive_correct, state.lapses) == (0, 0)
    assert before <= state.next_review_date <= datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Learning
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("step_index", [0, 1])
def test_learning_correct_advances_one_step(step_index):
    state, delay = update(learning(step_index), CORRECT)
    assert state.is_learning
    assert state.learning_step_index == step_index + 1
    assert delay == timedelta(minutes=STEPS[step_index + 1])


def test_learning_correct_on_last_step_graduates():
    state, delay = update(learning(step_index=2), CORRECT)
    assert not state.is_learning
    assert state.interval_days == 6.0
    assert state.consecutive_correct == 1
    assert delay == timedelta(days=6)


def test_three_correct_answers_graduate_a_new_word():
    state = initialize_progress()
    for _ in STEPS:
        state, _delay = update(state, CORRECT)
    assert not state.is_learning
    assert state.interval_days == 6.0


def test_learning_wrong_restarts_and_counts_a_lapse():
    state, delay = update(learning(step_index=2, lapses=1), WRONG)
    assert state.is_learning
    assert state.learning_step_index == 0
    assert state.lapses == 2
    assert delay == timedelta(minutes=15)


def test_learning_close_repeats_the_current_step():
    state, delay = update(learning(step_index=1), CLOSE)
    assert state.learning_step_index == 1
    assert state.lapses == 0
    assert delay == timedelta(minutes=STEPS[1])


def test_step_removed_from_config_continues_from_last_step():
    # The word was on step 2, but the user now has only two steps.
    config = SpacedRepetitionConfig(learning_steps_minutes=[10, 20])
    state, delay = update(learning(step_index=2), CLOSE, config)
    assert state.learning_step_index == 1
    assert delay == timedelta(minutes=20)


def test_graduating_interval_is_never_shorter_than_last_step():
    # Last step is 10 days, longer than the 6-day graduating interval.
    config = SpacedRepetitionConfig(learning_steps_minutes=[15, 14400])
    state, delay = update(learning(step_index=1), CORRECT, config)
    assert not state.is_learning
    assert state.interval_days == 10.0
    assert delay == timedelta(days=10)


# --------------------------------------------------------------------------- #
# Graduated
# --------------------------------------------------------------------------- #

def test_graduated_correct_doubles_interval():
    state, delay = update(graduated(interval_days=6.0, consecutive_correct=3), CORRECT)
    assert state.interval_days == 12.0
    assert state.consecutive_correct == 4
    assert delay == timedelta(days=12)


def test_graduated_correct_is_capped_at_max_interval():
    state, _delay = update(graduated(interval_days=60.0), CORRECT)
    assert state.interval_days == 90.0


def test_graduated_close_grows_interval_a_little_and_resets_streak():
    state, _delay = update(graduated(interval_days=10.0, consecutive_correct=3), CLOSE)
    assert state.interval_days == pytest.approx(12.0)
    assert state.consecutive_correct == 0
    assert state.lapses == 0


def test_graduated_close_is_capped_at_max_interval():
    state, _delay = update(graduated(interval_days=80.0), CLOSE)
    assert state.interval_days == 90.0


def test_graduated_wrong_halves_interval_and_counts_a_lapse():
    state, delay = update(graduated(interval_days=10.0, consecutive_correct=3, lapses=1), WRONG)
    assert not state.is_learning
    assert state.interval_days == 5.0
    assert (state.consecutive_correct, state.lapses) == (0, 2)
    assert delay == timedelta(days=5)


def test_graduated_wrong_never_drops_below_one_day():
    state, _delay = update(graduated(interval_days=1.5), WRONG)
    assert state.interval_days == 1.0


def test_strict_mode_wrong_sends_word_back_to_learning():
    config = SpacedRepetitionConfig(strict_mode=True)
    state, delay = update(graduated(interval_days=30.0, lapses=0), WRONG, config)
    assert state.is_learning
    assert state.learning_step_index == 0
    assert state.lapses == 1
    assert delay == timedelta(minutes=15)

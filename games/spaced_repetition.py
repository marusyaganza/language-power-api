# games/spaced_repetition.py
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from games.scoring import AnswerGrade


@dataclass
class SpacedRepetitionConfig:
    """How words are scheduled. The defaults are the "recommended" preset.

    `learning_steps_minutes`, `graduating_interval_days` and `strict_mode` can
    be set per user (`games.service.update_game_settings`); the rest are fixed.
    """

    learning_steps_minutes: list[int] = field(default_factory=lambda: [15, 1440, 8640])  # 15m, 1d, 6d
    # Never shorter than the last learning step: graduating must not bring
    # the next review closer than the step the word just passed.
    graduating_interval_days: float = 6.0
    interval_growth_factor: float = 2.0  # multiplier on a correct answer
    close_growth_factor: float = 1.2  # smaller multiplier on a near-miss
    lapse_penalty_factor: float = 0.5  # interval shrink on a wrong answer, graduated word
    max_interval_days: float = 90.0
    # strict_mode=True makes WRONG on a graduated word drop back into
    # learning_steps entirely, instead of just shrinking the interval —
    # closer to Anki's original behavior. Off by default: forgiving of
    # typos and slips is the better default for personal vocabulary practice.
    strict_mode: bool = False


DEFAULT_CONFIG = SpacedRepetitionConfig()


def _graduating_interval_days(config: SpacedRepetitionConfig) -> float:
    last_step_days = config.learning_steps_minutes[-1] / (24 * 60)
    return max(config.graduating_interval_days, last_step_days)


@dataclass
class WordProgressState:
    is_learning: bool
    learning_step_index: int
    interval_days: float
    consecutive_correct: int
    lapses: int
    next_review_date: datetime


def initialize_progress() -> WordProgressState:
    return WordProgressState(
        is_learning=True,
        learning_step_index=0,
        interval_days=0.0,
        consecutive_correct=0,
        lapses=0,
        next_review_date=datetime.now(UTC),
    )


def update_progress(
    state: WordProgressState,
    grade: AnswerGrade,
    config: SpacedRepetitionConfig = DEFAULT_CONFIG,
) -> WordProgressState:
    now = datetime.now(UTC)

    if state.is_learning:
        # The user may have removed learning steps since the word's last
        # review; continue from the last step that still exists.
        state.learning_step_index = min(state.learning_step_index, len(config.learning_steps_minutes) - 1)
        if grade == AnswerGrade.WRONG:
            state.learning_step_index = 0
            state.lapses += 1
            state.next_review_date = now + timedelta(minutes=config.learning_steps_minutes[0])
        elif grade == AnswerGrade.CLOSE:
            # repeat the current step rather than advancing or resetting
            state.next_review_date = now + timedelta(minutes=config.learning_steps_minutes[state.learning_step_index])
        else:  # CORRECT
            if state.learning_step_index < len(config.learning_steps_minutes) - 1:
                state.learning_step_index += 1
                state.next_review_date = now + timedelta(
                    minutes=config.learning_steps_minutes[state.learning_step_index]
                )
            else:
                state.is_learning = False
                state.interval_days = _graduating_interval_days(config)
                state.consecutive_correct = 1
                state.next_review_date = now + timedelta(days=state.interval_days)
    else:
        if grade == AnswerGrade.WRONG:
            state.lapses += 1
            state.consecutive_correct = 0
            if config.strict_mode:
                state.is_learning = True
                state.learning_step_index = 0
                state.next_review_date = now + timedelta(minutes=config.learning_steps_minutes[0])
            else:
                state.interval_days = max(1.0, state.interval_days * config.lapse_penalty_factor)
                state.next_review_date = now + timedelta(days=state.interval_days)
        elif grade == AnswerGrade.CLOSE:
            # partial credit: small bump, don't grow the streak
            state.consecutive_correct = 0
            state.interval_days = min(state.interval_days * config.close_growth_factor, config.max_interval_days)
            state.next_review_date = now + timedelta(days=state.interval_days)
        else:  # CORRECT
            state.consecutive_correct += 1
            state.interval_days = min(state.interval_days * config.interval_growth_factor, config.max_interval_days)
            state.next_review_date = now + timedelta(days=state.interval_days)

    return state

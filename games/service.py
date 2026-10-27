"""Games: which games a user can play, running a game session, and learning progress.

Two different things are called a "session" in this code, so they are named
differently:

* `db` is the database session (SQLAlchemy).
* A *game session* is a short-lived set of questions that lives in the session
  store (`games.session_store`), not in the database. It holds the expected
  answers, so they never have to be sent to the client.

The database only keeps what outlasts a game session: per-word learning
progress (`WordProgress`) and a log of every answer (`ReviewLog`).

Rules that apply to every function below:

* Games read words only through `words.service`, never from the `Word` table.
  `words` knows nothing about games; the words a game needs are described by
  `GAME_TYPE_REQUIREMENTS` (games.constants), whose keys must match the
  `requires_*` keyword arguments of `words.service.get_word_ids`.
* Failures are raised as subclasses of `GamesError`. This module knows nothing
  about HTTP; the router decides how each error is presented.
* `db` must be an `AsyncSession`.
"""

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from games import repository
from games.constants import (
    GAME_ANSWER_TYPES,
    GAME_SETTINGS_PRESETS,
    GAME_TASKS,
    GAME_TYPE_REQUIREMENTS,
)
from games.hints import hidden_definitions
from games.models import Game, GameSettings, ReviewLog, WordProgress
from games.options import definition_options, word_options
from games.schemas import (
    GameMode,
    GameOut,
    GameResultOut,
    GameSessionOut,
    GameSettingsOut,
    GameSettingsPreset,
    GameSettingsUpdate,
    QuestionAdditionalInfo,
    QuestionOut,
)
from games.scoring import (
    AnswerGrade,
    classify_choice_answer,
    classify_gender_answer,
    classify_typed_answer,
)
from games.session_store import (
    GameSessionNotFound,
    create_game_session,
    finish_game_session,
    get_game_session,
    get_question,
    is_answered,
    mark_question_answered,
)
from games.spaced_repetition import (
    SpacedRepetitionConfig,
    WordProgressState,
    initialize_progress,
    update_progress,
)
from words.models import Word
from words.service import WordSummary, get_word_ids, get_word_summaries, get_words_by_ids

logger = logging.getLogger(__name__)

__all__ = [
    "GamesError",
    "GameNotFoundError",
    "GameNotImplementedError",
    "SessionNotFoundError",
    "QuestionNotFoundError",
    "SessionFinishedError",
    "QuestionAlreadyAnsweredError",
    "NotEnoughWordsError",
    "AnswerCheck",
    "list_games_for_language",
    "start_game_session",
    "check_answer",
    "get_session_result",
    "persist_review_result",
    "get_game_settings",
    "update_game_settings",
    "list_game_settings_presets",
]

DEFAULT_WORDS_PER_SESSION = 10
# Options per question in the multiple-choice games, the answer included.
DEFAULT_OPTIONS_PER_QUESTION = 4
# The gender game's checkboxes; checking both answers "both".
GENDER_OPTIONS = ["masculine", "feminine"]
# How many of a word's definitions are shown as clues in a question.
MAX_DEFINITIONS_PER_QUESTION = 3


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class GamesError(Exception):
    """Base class for every error this module raises on purpose."""


class GameNotFoundError(GamesError):
    """There is no game with the given id."""


class GameNotImplementedError(GamesError):
    """The game exists but its type cannot be played yet."""


class SessionNotFoundError(GamesError):
    """The game session expired or never existed."""


class QuestionNotFoundError(GamesError):
    """The game session has no question for the given word."""


class SessionFinishedError(GamesError):
    """The game session is finished and takes no more answers."""


class QuestionAlreadyAnsweredError(GamesError):
    """The question was already answered; only the first answer counts."""


class NotEnoughWordsError(GamesError):
    """The user has fewer words than the game needs (`GameOut.min_word_count`)."""


# --------------------------------------------------------------------------- #
# Listing and starting games
# --------------------------------------------------------------------------- #


async def list_games_for_language(db: AsyncSession, user_id: int, language: str) -> list[GameOut]:
    """List the games offered for `language`, in display order (`Game.order_num`).

    A game is offered if it is marked for all languages or is linked to
    `language`. The word counts cover the user's saved words that meet the
    game's requirements; a word is due if it was never practiced in this game
    type or its review date has come. `next_due_at` is the earliest review
    date among the words that are not due yet (None if there are none).
    `min_word_count` is how many words the game needs before it can start.
    """
    games = await repository.get_games_for_language(db, language)

    now = datetime.now(UTC)
    result = []
    for game in games:
        schedules = await _load_schedules(db, user_id, language, game.game_type)
        upcoming = [s.next_review_date for s in schedules if not s.is_due(now)]
        result.append(
            GameOut(
                id=game.id,
                slug=game.slug,
                title=game.title,
                description=game.description,
                game_type=game.game_type,
                total_word_count=len(schedules),
                due_word_count=len(schedules) - len(upcoming),
                next_due_at=min(upcoming, default=None),
                min_word_count=_min_word_count(game),
            )
        )
    return result


async def start_game_session(
    db: AsyncSession,
    user_id: int,
    game_id: int,
    language: str,
    mode: GameMode = GameMode.SPACED,
    new_words_first: bool = False,
) -> GameSessionOut:
    """Start a game session with questions from the user's saved words.

    In `GameMode.SPACED` only due words are used, most overdue first; in
    `GameMode.REVIEW` every word is, least recently practiced first. Words
    never practiced in this game type go last, or first if `new_words_first`,
    in random order. The chosen words are asked in random order.

    The number of questions is the game's `words_per_session` setting. If the
    user has fewer eligible words than that, the session has fewer questions
    (possibly none); use `list_games_for_language` to find out beforehand.

    The session's expected answers are kept in the session store and are not
    part of the result. Whether the game is offered for `language` is not
    checked here.

    Raises:
        GameNotFoundError: no game has this id.
        GameNotImplementedError: the game's type cannot be played yet.
        NotEnoughWordsError: a multiple-choice game, and the user has fewer
            words than it needs for the options.
    """
    game = await db.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Game not found")
    spec = _GAME_SPECS.get(game.game_type)
    if spec is None:
        raise GameNotImplementedError("This game isn't implemented yet")
    return await _start_session(db, user_id, game, language, mode, new_words_first, spec)


def _word_recall_question(word: Word) -> QuestionOut:
    """type_word: guess the word from its definitions."""
    return QuestionOut(
        id=word.id,
        question=hidden_definitions(word.name, word.stems, word.defs)[:MAX_DEFINITIONS_PER_QUESTION],
        additional_info=QuestionAdditionalInfo(
            audio_url=word.audio_url,
            img_url=word.img_url,
            examples=word.examples or None,
        ),
    )


def _audio_question(word: Word) -> QuestionOut:
    """audio: type the word you hear. The audio is the question, so the hint
    is the meaning instead."""
    return QuestionOut(
        id=word.id,
        question=word.audio_url,
        additional_info=QuestionAdditionalInfo(
            img_url=word.img_url,
            examples=word.examples or None,
            definition=_meaning(word),
        ),
    )


def _image_question(word: Word) -> QuestionOut:
    """image: type the name of what the picture shows. The picture is the
    question, so the hints are the meaning and the pronunciation.

    `alt` is the first clue type_word would show, for when the image fails
    to load: the game stays playable, and the user can see the image is broken.
    """
    return QuestionOut(
        id=word.id,
        question=word.img_url,
        alt=hidden_definitions(word.name, word.stems, word.defs)[0],
        additional_info=QuestionAdditionalInfo(
            audio_url=word.audio_url,
            examples=word.examples or None,
            definition=_meaning(word),
        ),
    )


def _select_def_question(word: Word, pool: list[WordSummary], option_count: int) -> tuple[QuestionOut, str]:
    """select_def: pick the definition of the word."""
    answer, options = definition_options(word, pool, option_count)
    return QuestionOut(
        id=word.id,
        question=word.name,
        options=options,
        additional_info=QuestionAdditionalInfo(
            audio_url=word.audio_url,
            img_url=word.img_url,
            examples=word.examples or None,
        ),
    ), answer


def _select_word_question(word: Word, pool: list[WordSummary], option_count: int) -> tuple[QuestionOut, str]:
    """select_word: pick the word that the definitions describe."""
    return QuestionOut(
        id=word.id,
        question=hidden_definitions(word.name, word.stems, word.defs)[:MAX_DEFINITIONS_PER_QUESTION],
        options=word_options(word, pool, option_count),
        additional_info=QuestionAdditionalInfo(
            audio_url=word.audio_url,
            img_url=word.img_url,
            examples=word.examples or None,
        ),
    ), word.name


def _gender_question(word: Word, pool: list[WordSummary], option_count: int) -> tuple[QuestionOut, str]:
    """gender: tick the noun's gender(s). The answer is "masculine",
    "feminine" or "both"."""
    return QuestionOut(
        id=word.id,
        question=word.name,
        options=GENDER_OPTIONS,
        additional_info=QuestionAdditionalInfo(
            audio_url=word.audio_url,
            img_url=word.img_url,
            examples=word.examples or None,
            definition=_meaning(word),
        ),
    ), word.gender


def _meaning(word: Word) -> str:
    return f"{word.name} means {word.defs[0]}"


# Turns a word into a question and the answer the session store expects back.
# `pool` summarizes every word the game can use (empty unless `options_from_pool`).
_BuildQuestion = Callable[[Word, list[WordSummary], int], tuple[QuestionOut, str]]


def _typed(build: Callable[[Word], QuestionOut]) -> _BuildQuestion:
    """Adapt a typed game's builder: no options, and the answer is the word's name."""
    return lambda word, pool, option_count: (build(word), word.name)


@dataclass(frozen=True)
class _GameSpec:
    build: _BuildQuestion
    options_from_pool: bool = False


# The game types that can be played. How answers are graded is set by
# GAME_ANSWER_TYPES (games.constants).
_GAME_SPECS: dict[str, _GameSpec] = {
    "type_word": _GameSpec(_typed(_word_recall_question)),
    "audio": _GameSpec(_typed(_audio_question)),
    "image": _GameSpec(_typed(_image_question)),
    "select_def": _GameSpec(_select_def_question, options_from_pool=True),
    "select_word": _GameSpec(_select_word_question, options_from_pool=True),
    "gender": _GameSpec(_gender_question),
}


def _option_count(game: Game) -> int:
    return game.default_config.get("options_per_question", DEFAULT_OPTIONS_PER_QUESTION)


def _min_word_count(game: Game) -> int:
    """A game whose options are other words needs a word per option; any other needs one."""
    spec = _GAME_SPECS.get(game.game_type)
    return _option_count(game) if spec and spec.options_from_pool else 1


async def _start_session(
    db: AsyncSession,
    user_id: int,
    game: Game,
    language: str,
    mode: GameMode,
    new_words_first: bool,
    spec: _GameSpec,
) -> GameSessionOut:
    words_per_session = game.default_config.get("words_per_session", DEFAULT_WORDS_PER_SESSION)
    schedules = await _load_schedules(db, user_id, language, game.game_type)
    if spec.options_from_pool and len(schedules) < _min_word_count(game):
        raise NotEnoughWordsError(f"This game needs at least {_min_word_count(game)} words")
    word_ids = _pick_word_ids(schedules, mode, new_words_first, datetime.now(UTC), words_per_session)

    # Options are compared against every word the game can use, so that no
    # second correct answer slips in, but only through summaries: the full
    # words (with examples) are loaded just for the session's questions.
    pool = await get_word_summaries(db, user_id, [s.word_id for s in schedules]) if spec.options_from_pool else []
    words = await get_words_by_ids(db, user_id, word_ids)
    random.shuffle(words)

    built = [spec.build(w, pool, _option_count(game)) for w in words]

    # Expected answers go to the session store only; the client gets clues.
    answers = [{"word_id": q.id, "answer": answer} for q, answer in built]
    session_id = await create_game_session(user_id, game.id, game.game_type, answers)

    return GameSessionOut(
        task=GAME_TASKS[game.game_type],
        session_id=session_id,
        questions=[q for q, _ in built],
    )


@dataclass(frozen=True)
class _WordSchedule:
    """When a word is due in one game type. Both dates are None if never practiced."""

    word_id: int
    next_review_date: datetime | None
    last_reviewed_at: datetime | None

    @property
    def is_new(self) -> bool:
        return self.next_review_date is None

    def is_due(self, now: datetime) -> bool:
        return self.is_new or self.next_review_date <= now


async def _load_schedules(db: AsyncSession, user_id: int, language: str, game_type: str) -> list[_WordSchedule]:
    """The schedule of every saved word in `language` that this game type can use."""
    requirements = GAME_TYPE_REQUIREMENTS.get(game_type, {})
    word_ids = await get_word_ids(db, user_id, language, **requirements)
    dates = await repository.get_review_dates(db, game_type, word_ids)
    return [_WordSchedule(word_id, *dates.get(word_id, (None, None))) for word_id in word_ids]


# Sorts rows without `last_reviewed_at` (none are expected) as the oldest.
_NEVER = datetime.min.replace(tzinfo=UTC)


def _pick_word_ids(
    schedules: list[_WordSchedule],
    mode: GameMode,
    new_words_first: bool,
    now: datetime,
    limit: int,
) -> list[int]:
    """Choose up to `limit` words for a session; see `start_game_session` for the order."""
    new = [s for s in schedules if s.is_new]
    random.shuffle(new)  # otherwise the same new words would come up every time

    practiced = [s for s in schedules if not s.is_new]
    if mode == GameMode.SPACED:
        practiced = sorted((s for s in practiced if s.is_due(now)), key=lambda s: s.next_review_date)
    else:
        practiced = sorted(practiced, key=lambda s: s.last_reviewed_at or _NEVER)

    ordered = new + practiced if new_words_first else practiced + new
    return [s.word_id for s in ordered[:limit]]


# --------------------------------------------------------------------------- #
# Answering
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AnswerCheck:
    """The outcome of grading one answer.

    `correct_answer` is None when the answer was fully correct, otherwise the
    expected answer. `game_type` is passed along so the caller can record the
    review with `persist_review_result`.
    """

    grade: AnswerGrade
    correct_answer: str | None
    session_complete: bool
    game_type: str


async def check_answer(user_id: int, session_id: str, word_id: int, answer: str) -> AnswerCheck:
    """Grade `answer` for the question about `word_id` and mark it answered.

    Typed games are graded with `classify_typed_answer`, all others with
    `classify_choice_answer`. This only touches the session store; the review
    is not recorded until the caller passes the result to
    `persist_review_result`.

    Each question can be answered once: the response reveals the expected
    answer, so a second attempt would let the player copy it.

    Raises:
        SessionNotFoundError: the session expired, never existed, or belongs
            to another user.
        SessionFinishedError: the session is already finished.
        QuestionNotFoundError: the session has no question for `word_id`.
        QuestionAlreadyAnsweredError: the question was already answered.
    """
    session_data = await _get_own_session(user_id, session_id)

    if session_data.get("finished"):
        raise SessionFinishedError("Session is already finished")

    try:
        question = get_question(session_data, word_id)
    except GameSessionNotFound as exc:
        raise QuestionNotFoundError("Question not found in session") from exc

    if is_answered(question):
        raise QuestionAlreadyAnsweredError("Question was already answered")

    game_type = session_data["game_type"]
    grade = _grade(game_type, answer, question["answer"])
    session_complete = await mark_question_answered(session_id, session_data, word_id, grade.value)

    return AnswerCheck(
        grade=grade,
        correct_answer=None if grade == AnswerGrade.CORRECT else question["answer"],
        session_complete=session_complete,
        game_type=game_type,
    )


def _grade(game_type: str, given: str, expected: str) -> AnswerGrade:
    """Grade an answer by the way this game type collects answers."""
    answer_type = GAME_ANSWER_TYPES.get(game_type, "choice")
    if answer_type == "typed":
        return classify_typed_answer(given, expected)
    if answer_type == "gender":
        return classify_gender_answer(given, expected)
    return classify_choice_answer(given, expected)


async def _get_own_session(user_id: int, session_id: str) -> dict:
    """Load a game session that belongs to `user_id`.

    Another user's session is reported exactly like one that does not exist,
    so a leaked session id reveals nothing.

    Raises:
        SessionNotFoundError: the session expired, never existed, or belongs
            to another user.
    """
    try:
        session_data = await get_game_session(session_id)
    except GameSessionNotFound as exc:
        raise SessionNotFoundError("Session expired or not found") from exc

    if session_data.get("user_id") != user_id:
        raise SessionNotFoundError("Session expired or not found")
    return session_data


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


async def get_session_result(user_id: int, session_id: str) -> GameResultOut:
    """Finish the game session if it is still running and return its result.

    Asking for the result ends the session early: questions not answered yet
    stay unanswered, take no more answers, and never reach the learning
    progress. They count against the score.

    A close answer (a typo) counts as correct in `score_percent`; it is also
    reported separately in `close`.

    Raises:
        SessionNotFoundError: the session expired, never existed, or belongs
            to another user.
    """
    session_data = await _get_own_session(user_id, session_id)
    await finish_game_session(session_id, session_data)
    return _summarize(session_data["questions"])


def _summarize(questions: list[dict]) -> GameResultOut:
    counts = {grade: 0 for grade in (*AnswerGrade, "unanswered")}
    for question in questions:
        counts[question.get("grade", "unanswered")] += 1

    total = len(questions)
    passed = counts[AnswerGrade.CORRECT] + counts[AnswerGrade.CLOSE]
    return GameResultOut(
        total_words=total,
        correct=counts[AnswerGrade.CORRECT],
        close=counts[AnswerGrade.CLOSE],
        wrong=counts[AnswerGrade.WRONG],
        unanswered=counts["unanswered"],
        score_percent=_percent_half_up(passed, total),
    )


def _percent_half_up(part: int, total: int) -> int:
    """`part / total` as a whole percentage, rounding .5 up (1/8 -> 13, not 12).

    Integer arithmetic, because `round()` rounds half to even.
    """
    if total == 0:
        return 0
    return (200 * part + total) // (2 * total)


# --------------------------------------------------------------------------- #
# Learning progress
# --------------------------------------------------------------------------- #


async def persist_review_result(
    db: AsyncSession, user_id: int, word_id: int, game_type: str, grade: AnswerGrade
) -> None:
    """Log a review of a word and, if the word was due, update its schedule.

    The schedule follows the user's settings (`get_game_settings`) as they are
    now; reviews already scheduled are not moved when the settings change.

    Progress is kept per (word, game type) and is created on the first review;
    a word never reviewed is due. Answering a word that is not due yet (only
    possible in review mode) is logged and moves `last_reviewed_at`, but leaves
    the schedule alone, so extra practice cannot push a word into the future.

    Called after `check_answer` has marked the question answered, so the
    answer cannot be resubmitted. Failures are therefore logged and swallowed:
    the user still gets their grade, and only this review's progress is lost.
    Nothing is committed on failure; the request's session rolls it back.
    """
    try:
        progress = await repository.get_word_progress(db, word_id, game_type)
        now = datetime.now(UTC)
        if progress is None:
            progress = WordProgress(word_id=word_id, game_type=game_type)
            _write_state(progress, initialize_progress())
            db.add(progress)
            await db.flush()  # assigns progress.id for the ReviewLog FK below
            is_due = True
        else:
            is_due = progress.next_review_date <= now

        interval_at_review = progress.interval_days
        if is_due:
            config = await _load_config(db, user_id)
            _write_state(progress, update_progress(_read_state(progress), grade, config))
        progress.last_reviewed_at = now

        db.add(
            ReviewLog(
                progress=progress,
                grade=grade.value,
                interval_at_review=interval_at_review,
            )
        )
        await db.commit()
    except Exception:
        logger.exception(
            "Failed to persist review result for word_id=%s, game_type=%s",
            word_id,
            game_type,
        )


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


def list_game_settings_presets() -> list[GameSettingsPreset]:
    """The presets a user can pick from, the first being the default."""
    return [GameSettingsPreset(**preset) for preset in GAME_SETTINGS_PRESETS]


async def get_game_settings(db: AsyncSession, user_id: int) -> GameSettingsOut:
    """The user's spaced-repetition settings, or the default preset's if never set."""
    settings = await _read_settings(db, user_id)
    return GameSettingsOut(**settings.model_dump(), preset=_preset_id(settings))


async def update_game_settings(db: AsyncSession, user_id: int, settings: GameSettingsUpdate) -> GameSettingsOut:
    """Replace the user's spaced-repetition settings.

    They apply to each word from its next answer on; reviews already
    scheduled keep their dates.
    """
    row = await db.get(GameSettings, user_id)
    if row is None:
        row = GameSettings(user_id=user_id)
        db.add(row)
    row.learning_steps_minutes = settings.learning_steps_minutes
    row.graduating_interval_days = settings.graduating_interval_days
    row.strict_mode = settings.strict_mode
    await db.commit()
    return GameSettingsOut(**settings.model_dump(), preset=_preset_id(settings))


async def _read_settings(db: AsyncSession, user_id: int) -> GameSettingsUpdate:
    """The stored settings, or the default preset's.

    Stored values are validated again, and replaced by the defaults if they
    no longer pass (e.g. after the limits were tightened), so a bad row can
    never break scheduling.
    """
    row = await db.get(GameSettings, user_id)
    if row is not None:
        try:
            return GameSettingsUpdate(
                learning_steps_minutes=row.learning_steps_minutes,
                graduating_interval_days=row.graduating_interval_days,
                strict_mode=row.strict_mode,
            )
        except ValidationError:
            logger.warning("Invalid game settings for user_id=%s; using defaults", user_id)
    return list_game_settings_presets()[0].settings


async def _load_config(db: AsyncSession, user_id: int) -> SpacedRepetitionConfig:
    settings = await _read_settings(db, user_id)
    return SpacedRepetitionConfig(
        learning_steps_minutes=list(settings.learning_steps_minutes),
        graduating_interval_days=float(settings.graduating_interval_days),
        strict_mode=settings.strict_mode,
    )


def _preset_id(settings: GameSettingsUpdate) -> str:
    return next((p.id for p in list_game_settings_presets() if p.settings == settings), "custom")


# The fields shared by `WordProgress` (the row) and `WordProgressState` (what
# the spaced-repetition code reads and returns).
_STATE_FIELDS = (
    "is_learning",
    "learning_step_index",
    "interval_days",
    "consecutive_correct",
    "lapses",
    "next_review_date",
)


def _read_state(progress: WordProgress) -> WordProgressState:
    return WordProgressState(**{f: getattr(progress, f) for f in _STATE_FIELDS})


def _write_state(progress: WordProgress, state: WordProgressState) -> None:
    for field in _STATE_FIELDS:
        setattr(progress, field, getattr(state, field))

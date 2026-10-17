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
  `requires_*` keyword arguments of `words.service.get_random_words`.
* Failures are raised as subclasses of `GamesError`. This module knows nothing
  about HTTP; the router decides how each error is presented.
* `db` must be an `AsyncSession`.
"""
import logging
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from games.constants import GAME_ANSWER_TYPES, GAME_TASKS, GAME_TYPE_REQUIREMENTS
from games.models import Game, GameLanguage, ReviewLog, WordProgress
from games.schemas import (
    GameOut,
    GameResultOut,
    GameSessionOut,
    QuestionAdditionalInfo,
    QuestionOut,
    QuestionResult,
)
from games.scoring import AnswerGrade, classify_choice_answer, classify_typed_answer
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
    WordProgressState,
    initialize_progress,
    update_progress,
)
from words.service import count_words, get_random_words

logger = logging.getLogger(__name__)

__all__ = [
    "GamesError",
    "GameNotFoundError",
    "GameNotImplementedError",
    "SessionNotFoundError",
    "SessionGameMismatchError",
    "QuestionNotFoundError",
    "SessionFinishedError",
    "QuestionAlreadyAnsweredError",
    "AnswerCheck",
    "list_games_for_language",
    "start_game_session",
    "check_answer",
    "get_session_result",
    "persist_review_result",
]

# The only game type that can be played so far (the typed word-recall game).
WORD_RECALL_GAME_TYPE = "type_word"
DEFAULT_WORDS_PER_SESSION = 10
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


class SessionGameMismatchError(GamesError):
    """The game session was started for a different game."""


class QuestionNotFoundError(GamesError):
    """The game session has no question for the given word."""


class SessionFinishedError(GamesError):
    """The game session is finished and takes no more answers."""


class QuestionAlreadyAnsweredError(GamesError):
    """The question was already answered; only the first answer counts."""


# --------------------------------------------------------------------------- #
# Listing and starting games
# --------------------------------------------------------------------------- #

async def list_games_for_language(
    db: AsyncSession, user_id: int, language: str
) -> list[GameOut]:
    """List the games offered for `language`, in display order (`Game.order_num`).

    A game is offered if it is marked for all languages or is linked to
    `language`. `available_word_count` is how many of the user's saved words
    meet the game's requirements, and `is_enabled` is True when at least one
    does.
    """
    games = await db.scalars(
        select(Game)
        .where(
            or_(
                Game.all_languages.is_(True),
                Game.id.in_(
                    select(GameLanguage.game_id).where(GameLanguage.language == language)
                ),
            )
        )
        .order_by(Game.order_num)
    )

    result = []
    for game in games.all():
        requirements = GAME_TYPE_REQUIREMENTS.get(game.game_type, {})
        word_count = await count_words(db, user_id, language, **requirements)
        result.append(
            GameOut(
                id=game.id,
                slug=game.slug,
                title=game.title,
                description=game.description,
                game_type=game.game_type,
                available_word_count=word_count,
                is_enabled=word_count > 0,
            )
        )
    return result


async def start_game_session(
    db: AsyncSession, user_id: int, game_id: int, language: str
) -> GameSessionOut:
    """Start a game session of random questions from the user's saved words.

    The number of questions is the game's `words_per_session` setting. If the
    user has fewer matching words than that, the session has fewer questions
    (possibly none); use `list_games_for_language` to find out beforehand.

    The session's expected answers are kept in the session store and are not
    part of the result. Whether the game is offered for `language` is not
    checked here.

    Raises:
        GameNotFoundError: no game has this id.
        GameNotImplementedError: the game's type cannot be played yet.
    """
    game = await db.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Game not found")
    if game.game_type != WORD_RECALL_GAME_TYPE:
        raise GameNotImplementedError("This game isn't implemented yet")
    return await _start_word_recall_session(db, user_id, game, language)


async def _start_word_recall_session(
    db: AsyncSession, user_id: int, game: Game, language: str
) -> GameSessionOut:
    words_per_session = game.default_config.get(
        "words_per_session", DEFAULT_WORDS_PER_SESSION
    )
    requirements = GAME_TYPE_REQUIREMENTS.get(game.game_type, {})
    words = await get_random_words(
        db, user_id, language, words_per_session, **requirements
    )

    # Expected answers go to the session store only; the client gets clues.
    answers = [{"word_id": w.id, "answer": w.name} for w in words]
    session_id = await create_game_session(user_id, game.id, game.game_type, answers)

    questions = [
        QuestionOut(
            id=w.id,
            question=w.defs[:MAX_DEFINITIONS_PER_QUESTION],
            additional_info=QuestionAdditionalInfo(
                audio_url=w.audio_url,
                img_url=w.img_url,
                examples=w.examples or None,
            ),
        )
        for w in words
    ]
    return GameSessionOut(
        task=GAME_TASKS[game.game_type], session_id=session_id, questions=questions
    )


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


async def check_answer(
    user_id: int, session_id: str, game_id: int, word_id: int, answer: str
) -> AnswerCheck:
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
        SessionGameMismatchError: the session belongs to a different game.
        SessionFinishedError: the session is already finished.
        QuestionNotFoundError: the session has no question for `word_id`.
        QuestionAlreadyAnsweredError: the question was already answered.
    """
    session_data = await _get_own_session(user_id, session_id)

    if session_data["game_id"] != game_id:
        raise SessionGameMismatchError("Session does not belong to this game")

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
    session_complete = await mark_question_answered(
        session_id, session_data, word_id, grade.value
    )

    return AnswerCheck(
        grade=grade,
        correct_answer=None if grade == AnswerGrade.CORRECT else question["answer"],
        session_complete=session_complete,
        game_type=game_type,
    )


def _grade(game_type: str, given: str, expected: str) -> AnswerGrade:
    """Grade an answer by the way this game type collects answers."""
    if GAME_ANSWER_TYPES.get(game_type, "choice") == "typed":
        return classify_typed_answer(given, expected)
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
    results = [
        QuestionResult(
            word_id=q["word_id"],
            answer=q["answer"],
            grade=q.get("grade", "unanswered"),
        )
        for q in questions
    ]
    counts = {grade: 0 for grade in (*AnswerGrade, "unanswered")}
    for result in results:
        counts[result.grade] += 1

    total = len(results)
    passed = counts[AnswerGrade.CORRECT] + counts[AnswerGrade.CLOSE]
    return GameResultOut(
        total_words=total,
        correct=counts[AnswerGrade.CORRECT],
        close=counts[AnswerGrade.CLOSE],
        wrong=counts[AnswerGrade.WRONG],
        unanswered=counts["unanswered"],
        score_percent=_percent_half_up(passed, total),
        questions=results,
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
    word_id: int, game_type: str, grade: AnswerGrade
) -> None:
    """Update the spaced-repetition progress for a word and log the review.

    Progress is kept per (word, game type) and is created on the first review.
    Intended to run as a background task after the answer has been returned,
    so it opens its own database session (the request's is already closed).
    Failures are logged and swallowed, because the user has already received
    their answer and there is nobody to report the error to.
    """
    # The try wraps the session too, so a failure to connect is logged like
    # any other. Leaving the block without committing rolls back.
    try:
        async with AsyncSessionLocal() as db:
            progress = await db.scalar(
                select(WordProgress).where(
                    WordProgress.word_id == word_id,
                    WordProgress.game_type == game_type,
                )
            )
            if progress is None:
                progress = WordProgress(word_id=word_id, game_type=game_type)
                _write_state(progress, initialize_progress())
                db.add(progress)
                await db.flush()  # assigns progress.id for the ReviewLog FK below

            _write_state(progress, update_progress(_read_state(progress), grade))

            # TODO: this logs the interval *after* the update. If the column
            # means "interval when the review happened", log the old one.
            db.add(
                ReviewLog(
                    progress=progress,
                    grade=grade.value,
                    interval_at_review=progress.interval_days,
                )
            )
            await db.commit()
    except Exception:
        logger.exception(
            "Failed to persist review result for word_id=%s, game_type=%s",
            word_id,
            game_type,
        )


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
"""Short-lived game sessions, kept in Redis.

A game session is the set of questions for one play-through, with the
expected answers, so the answers never have to be sent to the client. A
running session expires `GAME_SESSION_TTL_SECONDS` after its last activity
(being created or answered); Redis then deletes it, so an expired session
looks exactly like one that never existed. Sessions are looked up by id; the
stored `user_id` lets callers check that the session belongs to whoever is
answering.

A session is finished once every question is answered, or earlier when the
player asks for the result (`finish_game_session`). A finished session is kept
for `GAME_RESULT_TTL_SECONDS` from then on, so its result can still be read.

Session data is a plain dict:
`{"user_id": int, "game_id": int, "game_type": str, "finished": bool (set once
finished), "questions": [{"word_id": int, "answer": str, "grade": str (the
AnswerGrade value, set once answered)}, ...]}`

Updates are read-modify-write, so two simultaneous answers to the same session
can overwrite each other's "answered" flag. A single player is not expected to
do that.
"""

import json
import uuid

from core.redis import redis_client

GAME_SESSION_TTL_SECONDS = 20 * 60
GAME_RESULT_TTL_SECONDS = 60 * 60


class GameSessionNotFound(Exception):
    """The session has no Redis entry (missing or expired), or the word is not part of it."""


def _game_session_key(session_id: str) -> str:
    return f"game_session:{session_id}"


async def create_game_session(user_id: int, game_id: int, game_type: str, questions: list[dict]) -> str:
    """Store a new session for `user_id` and return its id."""
    session_id = str(uuid.uuid4())
    session_data = {
        "user_id": user_id,
        "game_id": game_id,
        "game_type": game_type,
        "questions": questions,
    }
    await redis_client.set(
        _game_session_key(session_id),
        json.dumps(session_data),
        ex=GAME_SESSION_TTL_SECONDS,
    )
    return session_id


async def get_game_session(session_id: str) -> dict:
    """Return the session data.

    Raises:
        GameSessionNotFound: the session is missing or has expired.
    """
    raw = await redis_client.get(_game_session_key(session_id))
    if raw is None:
        raise GameSessionNotFound(session_id)
    return json.loads(raw)


def get_question(session_data: dict, word_id: int) -> dict:
    """Return the question for `word_id` from already-loaded session data.

    Raises:
        GameSessionNotFound: the word is not part of the session.
    """
    question = next((q for q in session_data["questions"] if q["word_id"] == word_id), None)
    if question is None:
        raise GameSessionNotFound(f"word_id {word_id} not in session")
    return question


def is_answered(question: dict) -> bool:
    return "grade" in question


async def mark_question_answered(session_id: str, session_data: dict, word_id: int, grade: str) -> bool:
    """Record `grade` for the question and return True if every question is now answered.

    `session_data` is updated in place and saved back to Redis. Answering the
    last question finishes the session (see `finish_game_session`); otherwise
    the session's lifetime starts again from now.
    """
    for question in session_data["questions"]:
        if question["word_id"] == word_id:
            question["grade"] = grade
            break

    complete = all(is_answered(q) for q in session_data["questions"])
    if complete:
        await finish_game_session(session_id, session_data)
    else:
        await redis_client.set(
            _game_session_key(session_id),
            json.dumps(session_data),
            ex=GAME_SESSION_TTL_SECONDS,
        )
    return complete


async def finish_game_session(session_id: str, session_data: dict) -> None:
    """Mark the session finished and keep it for `GAME_RESULT_TTL_SECONDS`.

    `session_data` is updated in place and saved back to Redis. Unanswered
    questions stay unanswered. Does nothing if the session is already finished,
    so reading a result repeatedly does not extend its lifetime.
    """
    if session_data.get("finished"):
        return
    session_data["finished"] = True
    await redis_client.set(
        _game_session_key(session_id),
        json.dumps(session_data),
        ex=GAME_RESULT_TTL_SECONDS,
    )

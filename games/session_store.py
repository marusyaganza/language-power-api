import json
import uuid
from core.redis import redis_client

GAME_SESSION_TTL_SECONDS = 20 * 60


class GameSessionNotFound(Exception):
    """Raised when a session_id has no corresponding Redis entry (missing or expired),
    or a word_id isn't part of that session."""


def _game_session_key(session_id: str) -> str:
    return f"game_session:{session_id}"


def create_game_session(game_id: int, game_type: str, questions: list[dict]) -> str:
    session_id = str(uuid.uuid4())
    session_data = {
        "game_id": game_id,
        "game_type": game_type,
        "questions": questions,
    }
    redis_client.set(_game_session_key(session_id), json.dumps(session_data), ex=GAME_SESSION_TTL_SECONDS)
    return session_id


def get_game_session(session_id: str) -> dict:
    raw = redis_client.get(_game_session_key(session_id))
    if raw is None:
        raise GameSessionNotFound(session_id)
    return json.loads(raw)


def get_question(session_data: dict, word_id: int) -> dict:
    question = next((q for q in session_data["questions"] if q["word_id"] == word_id), None)
    if question is None:
        raise GameSessionNotFound(f"word_id {word_id} not in session")
    return question


def mark_question_answered(session_id: str, session_data: dict, word_id: int) -> bool:
    """Marks the question answered in-place and returns True if the whole session is now complete."""
    for question in session_data["questions"]:
        if question["word_id"] == word_id:
            question["answered"] = True
            break

    redis_client.set(_game_session_key(session_id), json.dumps(session_data), keepttl=True)
    return all(q.get("answered") for q in session_data["questions"])
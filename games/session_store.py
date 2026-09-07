import json
import uuid
from core.redis import redis_client

GAME_SESSION_TTL_SECONDS = 20 * 60

def _game_session_key(session_id: str) -> str:
    return f"game_session:{session_id}"

def create_game_session(answers: list[dict]) -> str:
    session_id = str(uuid.uuid4())
    redis_client.set(_game_session_key(session_id), json.dumps(answers), ex=GAME_SESSION_TTL_SECONDS)
    return session_id
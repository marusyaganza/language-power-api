import secrets

from core.redis import redis_client
from settings import settings


def create_session(user_id: int) -> str:
    session_id = secrets.token_urlsafe(32)
    redis_client.set(
        f"session:{session_id}",
        str(user_id),
        ex=settings.session_ttl_seconds,
    )
    return session_id


def get_user_id_for_session(session_id: str) -> int | None:
    user_id = redis_client.get(f"session:{session_id}")
    return int(user_id) if user_id is not None else None

def refresh_session_if_needed(session_id: str) -> None:
    ttl = redis_client.ttl(f"session:{session_id}")
    if ttl <= 0:
        return  # key doesn't exist or has no TTL — nothing to refresh

    half_life = settings.session_ttl_seconds / 2
    if ttl < half_life:
        redis_client.expire(f"session:{session_id}", settings.session_ttl_seconds)


def destroy_session(session_id: str) -> None:
    redis_client.delete(f"session:{session_id}")
"""Generated files waiting for their word to be saved, held in Redis.

Generating costs no bucket write: the file waits here under a random token,
and only saving the word uploads it (one write). A file that is regenerated,
or whose word is never saved, simply expires after `PENDING_TTL_SECONDS`.

The key includes the user's id, so a token only works for the user it was
made for: anyone else's lookup misses, exactly like an expired token.

A held file is a JSON string `{"data": <base64 of the bytes>, "meta": {...}}`.
Base64 keeps it in the app's text Redis client (no second connection pool);
the files are small (an MP3 word is 5–15 KB), so the extra third doesn't matter.
`meta` is what the save needs to know besides the bytes, e.g. the engine and
voice of an audio file.
"""

import base64
import json
import secrets
from dataclasses import dataclass

from core.redis import redis_client

PENDING_TTL_SECONDS = 24 * 60 * 60
# 32 random bytes: 43 URL-safe characters.
_TOKEN_BYTES = 32


@dataclass(frozen=True)
class HeldFile:
    data: bytes
    meta: dict[str, str]


def _key(kind: str, user_id: int, token: str) -> str:
    return f"pending:{kind}:{user_id}:{token}"


async def hold(kind: str, user_id: int, data: bytes, meta: dict[str, str]) -> str:
    """Keep `data` for `PENDING_TTL_SECONDS` and return the token to fetch it with.

    `kind` separates audio from images, so a token of one can't be used as the other.
    """
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    value = json.dumps({"data": base64.b64encode(data).decode("ascii"), "meta": meta})
    await redis_client.set(_key(kind, user_id, token), value, ex=PENDING_TTL_SECONDS)
    return token


async def get(kind: str, user_id: int, token: str) -> HeldFile | None:
    """The file held under `token` for this user, or None if it expired or never existed.

    It stays held, so a save that fails afterwards can be tried again (uploads
    are idempotent: same bytes, same name). Call `discard` once it's saved.
    """
    value = await redis_client.get(_key(kind, user_id, token))
    if value is None:
        return None
    held = json.loads(value)
    return HeldFile(data=base64.b64decode(held["data"]), meta=held["meta"])


async def discard(kind: str, user_id: int, token: str) -> None:
    """Stop holding the file: it's saved, or no longer wanted."""
    await redis_client.delete(_key(kind, user_id, token))

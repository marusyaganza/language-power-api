"""Image search results kept in Redis for 24 hours.

Pixabay's terms require it ("requests must be cached for 24 hours"), and it
means paging back and forth, or searching the same word again, makes no new
request. Only successful answers are kept; errors are retried next time.

The query is hashed in the key, so a key's length doesn't depend on it.
"""

import hashlib
import json
from dataclasses import asdict

from core.redis import redis_client
from images.results import ImageHit, ImageResults

CACHE_TTL_SECONDS = 24 * 60 * 60


def key(source: str, variant: str, query: str, page: int, image_type: str) -> str:
    """The Redis key of one page of results. The query's case doesn't matter."""
    query_hash = hashlib.sha256(query.casefold().encode()).hexdigest()
    return f"image-search:{source}:{variant}:{image_type}:{page}:{query_hash}"


async def get(cache_key: str) -> ImageResults | None:
    value = await redis_client.get(cache_key)
    if value is None:
        return None
    data = json.loads(value)
    items = [ImageHit(**item) for item in data["items"]]
    return ImageResults(items=items, total=data["total"], page=data["page"])


async def put(cache_key: str, results: ImageResults) -> None:
    await redis_client.set(cache_key, json.dumps(asdict(results)), ex=CACHE_TTL_SECONDS)

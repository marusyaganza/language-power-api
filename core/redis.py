"""The shared Redis client.

It is an asyncio client: every command must be awaited. Auth sessions
(`auth.service`) and game sessions (`games.session_store`) both use it, so
they must stay async together.
"""

from redis import asyncio as aioredis

from settings import settings

redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

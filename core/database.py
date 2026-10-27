"""The database engine and session factory. Everything here is async."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from settings import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# The only session factory. expire_on_commit=False keeps loaded values usable
# after commit, so returning an object to the router never triggers a lazy
# load (which an async session cannot do).
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. Uncommitted work is rolled back on close."""
    async with AsyncSessionLocal() as session:
        yield session

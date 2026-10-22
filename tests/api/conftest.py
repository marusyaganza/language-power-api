# tests/api/conftest.py
"""Fixtures for tests that go through HTTP, with a real Postgres and Redis.

* Database: `settings.database_url`, which tests/conftest.py points at
  `language_app_test`. It is dropped, recreated and migrated with
  `alembic upgrade head` once per run, so the migrations are tested too.
* Every test runs inside one outer transaction that is rolled back afterwards.
  The app's sessions join it through savepoints, so service code commits
  normally and nothing is left behind.
* Redis: database 15, flushed after each test, so dev keys are never touched.
"""
import functools
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from redis import asyncio as aioredis
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import auth.service
import games.service
import games.session_store
from core.database import AsyncSessionLocal, get_db
from main import app
from settings import settings

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
TEST_REDIS_DB = 15
PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def _migrated_database():
    """Recreate the test database from scratch and run every migration on it."""
    url = make_url(settings.database_url)
    if not url.database.endswith("_test"):
        raise RuntimeError(f"Refusing to recreate non-test database {url.database!r}")

    admin_url = url.set(drivername="postgresql", database="postgres")
    try:
        conn = psycopg.connect(
            admin_url.render_as_string(hide_password=False), autocommit=True, connect_timeout=5
        )
    except psycopg.OperationalError as exc:
        pytest.fail(
            f"Postgres is not reachable at {url.host}:{url.port} "
            f"(start it with `docker compose up -d`): {exc}",
            pytrace=False,
        )
    with conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{url.database}"')

    # alembic/env.py reads the URL from `settings`, i.e. the test database.
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


@pytest.fixture
async def db(_migrated_database, monkeypatch) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back after the test.

    Sessions the app opens itself (background tasks) join the same transaction.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        factory = functools.partial(
            AsyncSessionLocal, bind=conn, join_transaction_mode="create_savepoint"
        )
        monkeypatch.setattr(games.service, "AsyncSessionLocal", factory)
        session = factory()
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
    await engine.dispose()


@pytest.fixture
async def redis(monkeypatch):
    client = aioredis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=TEST_REDIS_DB,
        decode_responses=True,
    )
    monkeypatch.setattr(auth.service, "redis_client", client)
    monkeypatch.setattr(games.session_store, "redis_client", client)
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.fixture
async def make_client(db, redis, monkeypatch):
    """A factory for HTTP clients that talk to the app in-process.

    Each client keeps its own cookies, so two clients are two users.
    """
    monkeypatch.setattr(settings, "signup_enabled", True)

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    clients = []

    def _make() -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        clients.append(client)
        return client

    try:
        yield _make
    finally:
        for client in clients:
            await client.aclose()
        app.dependency_overrides.clear()


@pytest.fixture
async def client(make_client) -> httpx.AsyncClient:
    """An HTTP client logged in as a freshly signed-up user."""
    client = make_client()
    await signup(client)
    return client


async def signup(client: httpx.AsyncClient) -> dict:
    """Sign up a new user with a unique email; the client keeps the session cookie."""
    response = await client.post(
        "/auth/signup",
        json={"email": f"user-{uuid.uuid4().hex}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def save_word(client: httpx.AsyncClient, name: str, *, language: str = "es", **fields) -> dict:
    """Save a word through the API and return it. `fields` override the defaults."""
    payload = {
        "uuid": f"uuid-{name}",
        "name": name,
        "language": language,
        "fl": "noun",
        "defs": [f"definition of {name}"],
        **fields,
    }
    response = await client.post("/words/save", json=payload)
    assert response.status_code == 201, response.text
    return response.json()

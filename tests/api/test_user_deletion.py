# tests/api/test_user_deletion.py
"""Deleting a user removes everything they own, so the demo can purge old accounts.

The database does it (ON DELETE CASCADE down the whole chain), so a plain SQL
DELETE works as well as deleting through the ORM.
"""

import pytest
from sqlalchemy import delete, func, select

from games.models import GameSettings, ReviewLog, WordProgress
from games.seed import sync_games
from tests.api.conftest import save_word, signup
from users.models import User
from words.models import Example, Word

pytestmark = pytest.mark.anyio

OWNED = [Word, Example, WordProgress, ReviewLog, GameSettings]
SETTINGS = {"learning_steps_minutes": [5, 60], "graduating_interval_days": 2, "strict_mode": False}


@pytest.fixture
async def games(db):
    await sync_games(db)


async def _give_user_everything(client) -> int:
    """Through the API: a word with an example, an answered game, custom settings."""
    word = await save_word(client, "casa", examples=[{"text": "mi casa"}])
    listed = (await client.get("/games", params={"language": "es"})).json()
    game = next(g for g in listed if g["game_type"] == "type_word")
    session = (await client.post(f"/games/{game['id']}/sessions", json={"language": "es"})).json()
    answered = await client.post(
        f"/games/sessions/{session['session_id']}/answers",
        json={"word_id": word["id"], "answer": "casa"},
    )
    assert answered.status_code == 200, answered.text
    assert (await client.put("/users/me/game-settings", json=SETTINGS)).status_code == 200
    return (await client.get("/auth/me")).json()["id"]


async def _counts(db) -> dict[str, int]:
    return {m.__name__: await db.scalar(select(func.count()).select_from(m)) for m in OWNED}


async def test_sql_delete_removes_everything_the_user_owns(client, make_client, db, games):
    user_id = await _give_user_everything(client)
    other = make_client()
    await signup(other)
    await save_word(other, "perro")  # another user's data must survive
    assert all((await _counts(db)).values())

    await db.execute(delete(User).where(User.id == user_id))

    assert await _counts(db) == {
        "Word": 1,
        "Example": 0,
        "WordProgress": 0,
        "ReviewLog": 0,
        "GameSettings": 0,
    }


async def test_orm_delete_removes_everything_the_user_owns(client, db, games):
    user_id = await _give_user_everything(client)

    await db.delete(await db.get(User, user_id))
    await db.flush()

    assert await _counts(db) == {m.__name__: 0 for m in OWNED}

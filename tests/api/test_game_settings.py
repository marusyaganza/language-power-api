# tests/api/test_game_settings.py
import pytest
from sqlalchemy import select

from games.models import WordProgress
from games.seed import sync_games
from tests.api.conftest import save_word, signup

pytestmark = pytest.mark.anyio

URL = "/users/me/game-settings"
INTENSIVE = {"learning_steps_minutes": [15, 240, 1440], "graduating_interval_days": 3, "strict_mode": True}


async def test_new_user_gets_the_recommended_preset(client):
    presets = (await client.get(f"{URL}/presets")).json()
    assert presets[0]["id"] == "recommended"

    settings = (await client.get(URL)).json()
    assert settings == {**presets[0]["settings"], "preset": "recommended"}


async def test_update_settings(client):
    chosen = (await client.put(URL, json=INTENSIVE)).json()
    assert chosen == {**INTENSIVE, "preset": "intensive"}
    assert (await client.get(URL)).json() == chosen

    custom = {"learning_steps_minutes": [5, 60], "graduating_interval_days": 2, "strict_mode": False}
    assert (await client.put(URL, json=custom)).json()["preset"] == "custom"


async def test_invalid_settings_are_rejected(client):
    bad = {"learning_steps_minutes": [60, 15], "graduating_interval_days": 3, "strict_mode": False}
    assert (await client.put(URL, json=bad)).status_code == 422
    assert (await client.get(URL)).json()["preset"] == "recommended"


async def test_settings_belong_to_one_user(client, make_client):
    await client.put(URL, json=INTENSIVE)
    other = make_client()
    await signup(other)
    assert (await other.get(URL)).json()["preset"] == "recommended"


async def test_settings_change_the_schedule(client, db):
    await sync_games(db)
    # One learning step of 60 minutes: a correct first answer graduates the
    # word straight away, to the 2-day graduating interval.
    await client.put(URL, json={"learning_steps_minutes": [60], "graduating_interval_days": 2, "strict_mode": False})
    word = await save_word(client, "casa")
    games = (await client.get("/games", params={"language": "es"})).json()
    gid = next(g["id"] for g in games if g["game_type"] == "type_word")
    session = (await client.post(f"/games/{gid}/sessions", json={"language": "es"})).json()
    await client.post(
        f"/games/sessions/{session['session_id']}/answers",
        json={
            "word_id": word["id"],
            "answer": "casa",
        },
    )

    progress = await db.scalar(select(WordProgress).where(WordProgress.word_id == word["id"]))
    assert progress.is_learning is False
    assert progress.interval_days == 2.0

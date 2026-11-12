# tests/api/test_audio.py
"""Generating a word's audio by hand: POST /audio/generate and GET /audio/voices."""

import base64

import pytest

from audio import synthesizers
from audio.base import SpeechError, SpeechTimeoutError
from audio.mock import mock_audio
from core import pending_media
from settings import settings

pytestmark = pytest.mark.anyio


@pytest.fixture
def audio_on(monkeypatch):
    monkeypatch.setattr(settings, "audio_engines", ["google"])


def preview_bytes(body: dict) -> bytes:
    prefix = "data:audio/mpeg;base64,"
    assert body["preview"].startswith(prefix)
    return base64.b64decode(body["preview"].removeprefix(prefix))


async def generate(client, **fields):
    return await client.post("/audio/generate", json={"language": "en", "text": "wheel", **fields})


async def user_id(client) -> int:
    return (await client.get("/auth/me")).json()["id"]


# --------------------------------------------------------------------------- #
# Off by default
# --------------------------------------------------------------------------- #


async def test_both_routes_are_404_where_audio_is_off(client):
    assert (await generate(client)).status_code == 404
    assert (await client.get("/audio/voices", params={"language": "en"})).status_code == 404


async def test_off_means_404_even_before_signing_in(make_client):
    assert (await generate(make_client())).status_code == 404


# --------------------------------------------------------------------------- #
# Generating
# --------------------------------------------------------------------------- #


async def test_generating_returns_a_playable_preview_with_the_default_voice(client, audio_on):
    response = await generate(client)

    assert response.status_code == 200
    body = response.json()
    assert (body["engine"], body["voice"]) == ("google", "Achernar")
    assert preview_bytes(body) == mock_audio("en", "wheel", "Achernar")


async def test_the_audio_is_held_for_the_user_until_the_word_is_saved(client, audio_on):
    body = (await generate(client, language="ko", text="바퀴", voice="Puck")).json()

    held = await pending_media.get("audio", await user_id(client), body["token"])

    assert held.data == preview_bytes(body)
    assert held.meta == {"engine": "google", "voice": "Puck", "language": "ko", "text": "바퀴"}


async def test_the_text_is_trimmed(client, audio_on):
    body = (await generate(client, text="  wheel \n")).json()

    assert preview_bytes(body) == mock_audio("en", "wheel", "Achernar")


async def test_a_chosen_voice_is_used(client, audio_on):
    body = (await generate(client, voice="Charon")).json()

    assert body["voice"] == "Charon"
    assert preview_bytes(body) == mock_audio("en", "wheel", "Charon")


async def test_every_generation_gets_its_own_token(client, audio_on):
    first, second = (await generate(client)).json(), (await generate(client)).json()

    assert first["token"] != second["token"]


@pytest.mark.parametrize(
    "fields",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "x" * 41},
        {"voice": "Nobody"},
        {"engine": "gtts"},
        {"language": "fr"},
    ],
)
async def test_bad_requests_are_422(client, audio_on, fields):
    assert (await generate(client, **fields)).status_code == 422


async def test_40_characters_are_enough(client, audio_on):
    assert (await generate(client, text="가" * 40)).status_code == 200


async def test_a_language_the_deployment_doesnt_offer_is_422(client, audio_on, monkeypatch):
    monkeypatch.setattr(settings, "enabled_languages", ["en", "es"])

    response = await generate(client, language="ko", text="바퀴")

    assert response.status_code == 422
    assert "isn't available" in response.text


async def test_signing_in_is_required(make_client, audio_on):
    assert (await generate(make_client())).status_code == 401


@pytest.mark.parametrize(("error", "status"), [(SpeechTimeoutError("slow"), 504), (SpeechError("down"), 502)])
async def test_engine_failures_are_502_or_504_and_hold_nothing(client, audio_on, monkeypatch, redis, error, status):
    async def fail(*args):
        raise error

    monkeypatch.setattr(synthesizers.SYNTHESIZERS["google"], "_synthesize_raw", fail)

    response = await generate(client)

    assert response.status_code == status
    assert "try again" in response.json()["detail"]
    assert await redis.keys("pending:*") == []


# --------------------------------------------------------------------------- #
# Voices
# --------------------------------------------------------------------------- #


async def test_voices_lists_each_engines_voices_and_default(client, audio_on):
    response = await client.get("/audio/voices", params={"language": "es"})

    assert response.status_code == 200
    [google] = response.json()
    assert google["engine"] == "google"
    assert google["default"] == "Achernar"
    assert google["default"] in google["voices"] and len(google["voices"]) == 8


async def test_voices_need_an_offered_language(client, audio_on, monkeypatch):
    monkeypatch.setattr(settings, "enabled_languages", ["en", "es"])

    assert (await client.get("/audio/voices", params={"language": "ko"})).status_code == 422

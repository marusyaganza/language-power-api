# tests/api/test_audio.py
"""Generating a word's audio by hand: POST /audio/generate and GET /audio/voices."""

import base64
import hashlib

import pytest

from audio import synthesizers
from audio.base import SpeechError, SpeechTimeoutError
from audio.mock import mock_audio
from core import pending_media
from core.media_storage import StorageError
from settings import settings
from tests.api.conftest import InMemoryStorage, save_word, signup

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


# --------------------------------------------------------------------------- #
# Saving a word with its generated audio (PATCH /words/{id} with audio_token)
# --------------------------------------------------------------------------- #


def stored_path(language: str, engine: str, audio: bytes) -> str:
    return f"audio/{language}/{engine}/{hashlib.sha256(audio).hexdigest()}.mp3"


async def edit(client, word_id, **fields):
    return await client.patch(f"/words/{word_id}", json=fields)


async def test_saving_with_the_token_stores_the_audio_and_sets_the_url(client, audio_on, media_storage):
    word = await save_word(client, "wheel", language="en")
    body = (await generate(client)).json()

    response = await edit(client, word["id"], audio_token=body["token"])

    assert response.status_code == 200
    audio = preview_bytes(body)
    path = stored_path("en", "google", audio)
    assert response.json()["audio_url"] == f"{InMemoryStorage.BASE_URL}/{path}"
    assert media_storage.files == {path: (audio, "audio/mpeg")}


async def test_the_audio_url_is_kept_with_the_word(client, audio_on):
    word = await save_word(client, "wheel", language="en")
    token = (await generate(client)).json()["token"]
    audio_url = (await edit(client, word["id"], audio_token=token)).json()["audio_url"]

    vocabulary = (await client.get("/words/vocabulary", params={"language": "en"})).json()

    assert [w["audio_url"] for w in vocabulary["items"]] == [audio_url]


async def test_a_saved_token_is_let_go(client, audio_on):
    word = await save_word(client, "wheel", language="en")
    token = (await generate(client)).json()["token"]

    await edit(client, word["id"], audio_token=token)

    assert await pending_media.get("audio", await user_id(client), token) is None
    assert (await edit(client, word["id"], audio_token=token)).status_code == 409


async def test_only_the_chosen_generation_is_stored(client, audio_on, media_storage, redis):
    word = await save_word(client, "wheel", language="en")
    tried = (await generate(client, voice="Puck")).json()
    chosen = (await generate(client, voice="Charon")).json()

    await edit(client, word["id"], audio_token=chosen["token"])

    assert list(media_storage.files) == [stored_path("en", "google", preview_bytes(chosen))]
    # The other one is still only in Redis, until it expires.
    assert await pending_media.get("audio", await user_id(client), tried["token"]) is not None


async def test_other_fields_are_saved_with_the_audio(client, audio_on):
    word = await save_word(client, "wheel", language="en")
    token = (await generate(client)).json()["token"]

    saved = (await edit(client, word["id"], audio_token=token, defs=["a round thing"])).json()

    assert saved["defs"] == ["a round thing"]
    assert saved["audio_url"].endswith(".mp3")


async def test_an_unknown_or_expired_token_is_409_and_changes_nothing(client, audio_on, media_storage):
    word = await save_word(client, "wheel", language="en", audio_url="https://example.com/old.mp3")

    response = await edit(client, word["id"], audio_token="expired-token", defs=["changed"])

    assert response.status_code == 409
    assert "generate it again" in response.json()["detail"]
    [saved] = (await client.get("/words/vocabulary", params={"language": "en"})).json()["items"]
    assert (saved["audio_url"], saved["defs"]) == ("https://example.com/old.mp3", word["defs"])
    assert media_storage.files == {}


async def test_another_users_token_doesnt_work(make_client, audio_on):
    owner, other = make_client(), make_client()
    await signup(owner)
    await signup(other)
    token = (await generate(owner)).json()["token"]
    word = await save_word(other, "wheel", language="en")

    assert (await edit(other, word["id"], audio_token=token)).status_code == 409


@pytest.mark.parametrize(("name", "language"), [("whale", "en"), ("wheel", "es")])
async def test_audio_made_for_another_word_is_422(client, audio_on, media_storage, name, language):
    word = await save_word(client, name, language=language)
    token = (await generate(client, language="en", text="wheel")).json()["token"]

    response = await edit(client, word["id"], audio_token=token)

    assert response.status_code == 422
    assert "another word" in response.json()["detail"]
    assert media_storage.files == {}


@pytest.mark.parametrize("audio_url", ["https://example.com/a.mp3", None])
async def test_a_token_and_an_audio_url_together_are_422(client, audio_on, audio_url):
    word = await save_word(client, "wheel", language="en")
    token = (await generate(client)).json()["token"]

    assert (await edit(client, word["id"], audio_token=token, audio_url=audio_url)).status_code == 422


@pytest.mark.parametrize("token", ["not a token!", "x" * 65])
async def test_a_malformed_token_is_422(client, audio_on, token):
    word = await save_word(client, "wheel", language="en")

    assert (await edit(client, word["id"], audio_token=token)).status_code == 422


async def test_a_token_where_audio_is_off_is_422(client, audio_on, monkeypatch):
    word = await save_word(client, "wheel", language="en")
    token = (await generate(client)).json()["token"]
    monkeypatch.setattr(settings, "audio_engines", [])

    assert (await edit(client, word["id"], audio_token=token)).status_code == 422


async def test_a_failed_upload_is_503_and_saving_again_works(client, audio_on, media_storage, monkeypatch):
    word = await save_word(client, "wheel", language="en")
    token = (await generate(client)).json()["token"]

    upload = media_storage.upload
    attempts = []

    async def fail_once(*args):
        attempts.append(args)
        if len(attempts) == 1:
            raise StorageError("bucket unreachable")
        return await upload(*args)

    monkeypatch.setattr(media_storage, "upload", fail_once)
    failed = await edit(client, word["id"], audio_token=token)
    retried = await edit(client, word["id"], audio_token=token)

    assert failed.status_code == 503
    assert "try saving again" in failed.json()["detail"]
    assert retried.status_code == 200
    assert retried.json()["audio_url"].endswith(".mp3")
    assert len(media_storage.files) == 1


async def test_audio_url_can_still_be_set_by_hand(client):
    word = await save_word(client, "wheel", language="en")

    response = await edit(client, word["id"], audio_url="https://example.com/wheel.mp3")

    assert response.json()["audio_url"] == "https://example.com/wheel.mp3"

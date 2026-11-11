# tests/api/test_pending_media.py
"""Generated files held in Redis until their word is saved, and the local /media folder."""

import uuid

import pytest

from core import pending_media
from core.media_storage import LOCAL_MEDIA_DIR, LOCAL_MEDIA_URL, LocalFolderStorage

pytestmark = pytest.mark.anyio

MP3 = b"\xff\xf3 not text \x00\x01"


async def test_a_held_file_comes_back_as_it_was(redis):
    token = await pending_media.hold("audio", 1, MP3, {"engine": "google", "voice": "Achernar"})

    held = await pending_media.get("audio", 1, token)

    assert (held.data, held.meta) == (MP3, {"engine": "google", "voice": "Achernar"})


async def test_a_held_file_expires_after_a_day(redis):
    token = await pending_media.hold("audio", 1, MP3, {})

    [key] = await redis.keys("pending:*")
    assert token in key
    assert 24 * 60 * 60 - 5 < await redis.ttl(key) <= 24 * 60 * 60


async def test_a_held_file_can_be_read_again_until_discarded(redis):
    token = await pending_media.hold("audio", 1, MP3, {})

    assert await pending_media.get("audio", 1, token) is not None
    assert await pending_media.get("audio", 1, token) is not None
    await pending_media.discard("audio", 1, token)
    assert await pending_media.get("audio", 1, token) is None


async def test_a_token_works_only_for_its_user_and_kind(redis):
    token = await pending_media.hold("audio", 1, MP3, {})

    assert await pending_media.get("audio", 2, token) is None
    assert await pending_media.get("image", 1, token) is None
    # Someone else's discard doesn't touch it either.
    await pending_media.discard("audio", 2, token)
    assert await pending_media.get("audio", 1, token) is not None


async def test_every_hold_gets_a_new_unguessable_token(redis):
    tokens = {await pending_media.hold("audio", 1, MP3, {}) for _ in range(3)}

    assert len(tokens) == 3
    assert all(len(token) >= 43 for token in tokens)


async def test_an_unknown_token_is_none(redis):
    assert await pending_media.get("audio", 1, "no-such-token") is None


# --------------------------------------------------------------------------- #
# The local folder, served under /media (local development)
# --------------------------------------------------------------------------- #


async def test_a_locally_stored_file_is_served_at_its_url(make_client):
    path = f"test/{uuid.uuid4().hex}.mp3"
    url = await LocalFolderStorage().upload(MP3, path, "audio/mpeg")
    try:
        response = await make_client().get(url.removeprefix(LOCAL_MEDIA_URL.removesuffix("/media")))

        assert response.status_code == 200
        assert response.content == MP3
    finally:
        (LOCAL_MEDIA_DIR / path).unlink()
        (LOCAL_MEDIA_DIR / "test").rmdir()


async def test_a_missing_local_file_is_a_404(make_client):
    assert (await make_client().get(f"/media/test/{uuid.uuid4().hex}.mp3")).status_code == 404

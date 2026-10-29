# tests/api/test_mock_dictionary.py
"""The mock dictionaries: made-up fixtures, and their sample audio and pictures."""

import json

import pytest

from core.language import Language
from dictionary.mock import FIXTURES_DIR, SAMPLE_MEDIA_DIR, SAMPLE_MEDIA_PATH
from settings import settings

pytestmark = pytest.mark.anyio

FIXTURE_WORDS = {
    language: sorted(path.stem for path in (FIXTURES_DIR / language).glob("*.json")) for language in Language
}


async def search(client, query, language):
    response = await client.get("/words/search", params={"query": query, "language": language})
    assert response.status_code == 200, response.text
    return response.json()["words"]


def test_every_media_file_belongs_to_a_fixture_word():
    for language in Language:
        for path in (SAMPLE_MEDIA_DIR / language).iterdir():
            assert path.suffix in (".mp3", ".svg"), path
            assert path.stem in FIXTURE_WORDS[language], path


def test_the_fixtures_link_to_no_merriam_webster_media():
    # The parser would turn `sound.audio` and `art.artid` into MW URLs.
    for language in Language:
        for path in (FIXTURES_DIR / language).glob("*.json"):
            for entry in json.loads(path.read_text(encoding="utf-8")):
                assert "art" not in entry, path
                assert all("sound" not in pr for pr in entry["hwi"].get("prs", [])), path


@pytest.mark.parametrize("language", list(Language))
async def test_every_fixture_word_is_found_and_its_media_is_served(client, language):
    media_urls = []
    for query in FIXTURE_WORDS[language]:
        words = await search(client, query, language)
        assert words, query
        assert all(word["defs"] and word["fl"] for word in words), query
        media_urls += [url for word in words for url in (word["audio_url"], word["img_url"]) if url]

    assert media_urls  # each language has some
    for url in media_urls:
        response = await client.get(url)
        assert response.status_code == 200, url
        assert response.headers["content-type"].startswith(("audio/mpeg", "image/svg+xml")), url


async def test_words_with_sample_media_get_their_urls(client):
    [wheel] = await search(client, "wheel", "en")
    assert wheel["audio_url"] == f"{SAMPLE_MEDIA_PATH}/en/wheel.mp3"
    assert wheel["img_url"] == f"{SAMPLE_MEDIA_PATH}/en/wheel.svg"

    journeys = await search(client, "journey", "en")
    assert [(w["fl"], w["audio_url"], w["img_url"]) for w in journeys] == [("noun", None, None), ("verb", None, None)]

    [ballena] = await search(client, "ballena", "es")
    assert (ballena["gender"], ballena["audio_url"]) == ("feminine", f"{SAMPLE_MEDIA_PATH}/es/ballena.mp3")


async def test_media_urls_include_the_root_path(client, monkeypatch):
    monkeypatch.setattr(settings, "root_path", "/api")
    [wheel] = await search(client, "wheel", "en")
    assert wheel["audio_url"] == "/api/sample-media/en/wheel.mp3"

    saved = await client.post("/words/save", json={**wheel, "language": "en"})
    assert saved.status_code == 201, saved.text


async def test_a_mock_word_is_saved_with_its_media(client):
    [ballena] = await search(client, "ballena", "es")
    response = await client.post("/words/save", json={**ballena, "language": "es"})
    assert response.status_code == 201, response.text
    assert response.json()["img_url"] == f"{SAMPLE_MEDIA_PATH}/es/ballena.svg"


async def test_the_fixture_words_cover_every_game(client):
    """Each language has 4 words (choice games need 4), and Spanish has all three genders."""
    assert [len(words) for words in FIXTURE_WORDS.values()] == [4, 4]
    genders = set()
    for query in FIXTURE_WORDS[Language.ES]:
        genders |= {word["gender"] for word in await search(client, query, "es")}
    assert genders == {"masculine", "feminine", "both", None}

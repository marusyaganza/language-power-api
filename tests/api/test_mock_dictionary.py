# tests/api/test_mock_dictionary.py
"""The mock dictionaries: made-up fixtures, and their sample audio and pictures."""

import json

import pytest

from core.language import Language
from dictionary.mock import FIXTURES_DIR, SAMPLE_MEDIA

pytestmark = pytest.mark.anyio

FIXTURE_WORDS = {
    language: sorted(path.stem for path in (FIXTURES_DIR / language).glob("*.json")) for language in Language
}


async def search(client, query, language):
    response = await client.post("/words/search", json={"query": query, "language": language})
    assert response.status_code == 200, response.text
    return response.json()["words"]


def test_every_sample_media_word_has_a_fixture():
    for language, name in SAMPLE_MEDIA:
        assert name in FIXTURE_WORDS[language], (language, name)


def test_the_fixtures_link_to_no_merriam_webster_media():
    # The parser would turn `sound.audio` and `art.artid` into MW URLs.
    for language in (Language.EN, Language.ES):  # the Merriam-Webster languages
        for path in (FIXTURES_DIR / language).glob("*.json"):
            for entry in json.loads(path.read_text(encoding="utf-8")):
                assert "art" not in entry, path
                assert all("sound" not in pr for pr in entry["hwi"].get("prs", [])), path


@pytest.mark.parametrize("language", list(Language))
async def test_every_fixture_word_is_found(client, language):
    for query in FIXTURE_WORDS[language]:
        words = await search(client, query, language)
        assert words, query
        assert all(word["defs"] and word["fl"] for word in words), query


async def test_words_with_sample_media_get_their_urls(client):
    [cat] = await search(client, "cat", "en")
    assert (cat["audio_url"], cat["img_url"]) == (
        SAMPLE_MEDIA["en", "cat"]["audio_url"],
        SAMPLE_MEDIA["en", "cat"]["img_url"],
    )

    journeys = await search(client, "journey", "en")
    assert [(w["fl"], w["audio_url"], w["img_url"]) for w in journeys] == [("noun", None, None), ("verb", None, None)]

    [gato] = await search(client, "gato", "es")
    assert (gato["gender"], gato["audio_url"]) == ("masculine", SAMPLE_MEDIA["es", "gato"]["audio_url"])


async def test_a_mock_word_is_saved_with_its_media(client):
    [gato] = await search(client, "gato", "es")
    response = await client.post("/words/save", json={**gato, "language": "es"})
    assert response.status_code == 201, response.text
    assert response.json()["img_url"] == SAMPLE_MEDIA["es", "gato"]["img_url"]


async def test_the_fixture_words_cover_every_game(client):
    """Each language has at least 4 words (choice games need 4), and Spanish has all three genders."""
    assert all(len(words) >= 4 for words in FIXTURE_WORDS.values())
    genders = set()
    for query in FIXTURE_WORDS[Language.ES]:
        genders |= {word["gender"] for word in await search(client, query, "es")}
    assert genders == {"masculine", "feminine", "both", None}

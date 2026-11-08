# tests/api/test_enabled_languages.py
"""A deployment offers only its `enabled_languages`: the demo leaves Korean out while it's in beta."""

import pytest

from settings import settings
from tests.api.conftest import save_word

pytestmark = pytest.mark.anyio


@pytest.fixture
def demo_languages(monkeypatch):
    monkeypatch.setattr(settings, "enabled_languages", ["en", "es"])


def rejected_language(response):
    """Whether the response is the 422 for a language the deployment doesn't offer."""
    return response.status_code == 422 and "isn't available" in response.text


async def test_every_language_is_offered_by_default(make_client):
    config = (await make_client().get("/auth/config")).json()

    assert config["languages"] == ["en", "es", "ko"]


async def test_the_config_lists_only_the_offered_languages(make_client, demo_languages):
    config = (await make_client().get("/auth/config")).json()

    assert config["languages"] == ["en", "es"]


async def test_requests_in_a_language_not_offered_are_rejected(client, demo_languages):
    word = {"name": "가게", "language": "ko", "fl": "noun", "defs": ["shop"]}
    responses = {
        "search": await client.post("/words/search", json={"query": "가게", "language": "ko"}),
        "save": await client.post("/words/save", json=word),
        "vocabulary": await client.get("/words/vocabulary", params={"language": "ko"}),
        "games": await client.get("/games", params={"language": "ko"}),
        "game session": await client.post("/games/1/sessions", json={"language": "ko"}),
    }

    assert {name: rejected_language(response) for name, response in responses.items()} == dict.fromkeys(responses, True)


async def test_offered_languages_still_work(client, demo_languages):
    await save_word(client, "perro", language="es")

    search = await client.post("/words/search", json={"query": "wheel", "language": "en"})
    vocabulary = await client.get("/words/vocabulary", params={"language": "es"})

    assert search.status_code == 200
    assert [w["name"] for w in vocabulary.json()["items"]] == ["perro"]


async def test_search_limits_cover_only_the_offered_languages(client, demo_languages, monkeypatch):
    monkeypatch.setattr(settings, "searches_per_language", 10)

    limits = (await client.get("/words/search-limits")).json()

    assert limits["searches_left"] == {"en": 10, "es": 10}

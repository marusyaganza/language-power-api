# tests/api/test_words.py
import pytest

from dictionary.base import DictionaryError, DictionaryProvider, SearchResult
from dictionary.entry import DictionaryEntry
from dictionary.providers import PROVIDERS
from tests.api.conftest import save_word, signup

pytestmark = pytest.mark.anyio

EXAMPLE = {"text": "mi casa", "translation": "my house"}


async def test_saved_word_comes_back_with_examples(client):
    # Regression: after commit the examples used to be expired, and
    # serializing them raised MissingGreenlet (a 500 after the word was saved).
    saved = await save_word(client, "casa", examples=[EXAMPLE])
    assert saved["examples"] == [EXAMPLE]

    page = (await client.get("/words/vocabulary", params={"language": "es"})).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == saved["id"]
    assert page["items"][0]["examples"] == [EXAMPLE]


async def test_saving_the_same_word_twice_conflicts(client):
    await save_word(client, "casa")
    response = await client.post(
        "/words/save",
        json={
            "uuid": "uuid-casa",
            "name": "casa",
            "language": "es",
            "fl": "noun",
            "defs": ["house"],
        },
    )
    assert response.status_code == 409


# --------------------------------------------------------------------------- #
# Editing
# --------------------------------------------------------------------------- #


async def test_edit_replaces_examples_and_accepts_null_translations(client):
    word = await save_word(client, "casa", examples=[EXAMPLE])
    response = await client.patch(
        f"/words/{word['id']}",
        json={
            "examples": [{"text": "a", "translation": None}, {"text": "b", "translation": ""}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["examples"] == [
        {"text": "a", "translation": None},
        {"text": "b", "translation": None},
    ]


async def test_edit_changes_only_the_fields_sent(client):
    word = await save_word(
        client,
        "casa",
        defs=["house"],
        audio_url="https://a/casa.mp3",
        img_url="https://i/casa.png",
        img_desc="a house",
        examples=[EXAMPLE],
    )
    edited = (await client.patch(f"/words/{word['id']}", json={"audio_url": None})).json()
    assert edited["audio_url"] is None
    assert edited["defs"] == ["house"]
    assert edited["img_url"] == "https://i/casa.png"
    assert edited["img_desc"] == "a house"
    assert edited["examples"] == [EXAMPLE]


async def test_new_image_clears_the_old_description(client):
    word = await save_word(client, "casa", img_url="https://i/old.png", img_desc="the old image")
    edited = (await client.patch(f"/words/{word['id']}", json={"img_url": "https://i/new.png"})).json()
    assert edited["img_url"] == "https://i/new.png"
    assert edited["img_desc"] is None

    described = (
        await client.patch(
            f"/words/{word['id']}",
            json={
                "img_url": "https://i/newer.png",
                "img_desc": "the newer image",
            },
        )
    ).json()
    assert described["img_desc"] == "the newer image"


async def test_edit_cannot_remove_every_definition(client):
    word = await save_word(client, "casa")
    response = await client.patch(f"/words/{word['id']}", json={"defs": [" "]})
    assert response.status_code == 422


async def test_delete_word(client):
    word = await save_word(client, "casa", examples=[EXAMPLE])
    assert (await client.delete(f"/words/{word['id']}")).status_code == 204
    assert (await client.delete(f"/words/{word['id']}")).status_code == 404
    assert (await client.get("/words/vocabulary", params={"language": "es"})).json()["total"] == 0


async def test_other_users_words_are_invisible(client, make_client):
    word = await save_word(client, "casa")

    other = make_client()
    await signup(other)
    assert (await other.patch(f"/words/{word['id']}", json={"defs": ["x"]})).status_code == 404
    assert (await other.delete(f"/words/{word['id']}")).status_code == 404
    assert (await other.get("/words/vocabulary", params={"language": "es"})).json()["total"] == 0

    # The owner still has it, unchanged.
    page = (await client.get("/words/vocabulary", params={"language": "es"})).json()
    assert page["items"][0]["defs"] == word["defs"]


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #


async def test_vocabulary_search_sort_and_pages(client):
    names = [f"palabra{i:02}" for i in range(11)] + ["casa"]
    for name in names:
        await save_word(client, name)
    await save_word(client, "house", language="en")

    first = (await client.get("/words/vocabulary", params={"language": "es", "sort_by": "name"})).json()
    assert (first["total"], first["total_pages"], first["page_size"]) == (12, 2, 10)
    assert [w["name"] for w in first["items"]] == sorted(names)[:10]

    second = (
        await client.get(
            "/words/vocabulary",
            params={
                "language": "es",
                "sort_by": "name",
                "sort_order": "desc",
                "page": 2,
            },
        )
    ).json()
    assert [w["name"] for w in second["items"]] == sorted(names, reverse=True)[10:]

    found = (await client.get("/words/vocabulary", params={"language": "es", "query": "CAS"})).json()
    assert [w["name"] for w in found["items"]] == ["casa"]

    empty = (await client.get("/words/vocabulary", params={"language": "es", "query": "zzz"})).json()
    assert (empty["total"], empty["total_pages"], empty["items"]) == (0, 0, [])


# --------------------------------------------------------------------------- #
# Dictionary search (mock providers, see tests/conftest.py)
# --------------------------------------------------------------------------- #


async def test_search_marks_saved_words(client):
    results = (await client.get("/words/search", params={"query": "vivir", "language": "es"})).json()
    entries = results["words"]
    assert {w["name"] for w in entries} >= {"vivir"}
    assert not any(w["saved"] for w in entries)

    first = entries[0]
    await save_word(client, first["name"], uuid=first["uuid"], defs=first["defs"])

    again = (await client.get("/words/search", params={"query": "vivir", "language": "es"})).json()
    saved = {w["uuid"]: w["saved"] for w in again["words"]}
    assert saved.pop(first["uuid"]) is True
    assert not any(saved.values())


async def test_search_without_mock_data_lists_the_queries_that_have_it(client):
    response = await client.get("/words/search", params={"query": "zzz", "language": "en"})
    assert response.status_code == 200
    assert response.json()["words"] == []
    assert "heart" in response.json()["mock_queries"]


async def test_an_unsupported_language_is_rejected_before_the_service(client):
    search = await client.get("/words/search", params={"query": "x", "language": "xx"})
    vocabulary = await client.get("/words/vocabulary", params={"language": "xx"})
    save = await client.post("/words/save", json={"name": "x", "language": "xx", "fl": "noun", "defs": ["x"]})
    assert [search.status_code, vocabulary.status_code, save.status_code] == [422, 422, 422]


class _AnoProvider(DictionaryProvider):
    """MW's order for "año": it is searched as "ano", so "ano" comes first."""

    async def _fetch_raw(self, query):
        return ["ano", "año", "bisiesto", "Año Nuevo"]

    def _parse(self, raw):
        entry = {"language": "es", "fl": "noun", "stems": [], "defs": ["x"]}
        return SearchResult(words=[DictionaryEntry(uuid=name, name=name, **entry) for name in raw])


async def test_search_lists_the_exact_word_first(client, monkeypatch):
    monkeypatch.setitem(PROVIDERS, "es", _AnoProvider())
    response = await client.get("/words/search", params={"query": "Año", "language": "es"})
    assert [w["name"] for w in response.json()["words"]] == ["año", "ano", "bisiesto", "Año Nuevo"]


class _BrokenProvider(DictionaryProvider):
    async def _fetch_raw(self, query):
        raise DictionaryError("MW answered with status 500")

    def _parse(self, raw):
        raise AssertionError("never reached")


async def test_search_when_the_dictionary_fails_is_a_503(client, monkeypatch):
    monkeypatch.setitem(PROVIDERS, "en", _BrokenProvider())
    response = await client.get("/words/search", params={"query": "heart", "language": "en"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Dictionary is unavailable, try again later"}

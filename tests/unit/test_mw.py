# tests/unit/test_mw.py
import asyncio

import httpx
import pytest

from dictionary.base import DictionaryError
from dictionary.merriam_webster.api import extract_gender, fetch_entries

API_URL = "https://mw-api.invalid/api/v3/references/collegiate/json"


@pytest.mark.parametrize(
    ("fl", "expected"),
    [
        ("masculine noun", "masculine"),
        ("feminine noun", "feminine"),
        # "el/la ecologista": one entry, both genders.
        ("masculine or feminine noun", "both"),
        ("noun", None),
        ("transitive verb", None),
        ("Masculine Noun", "masculine"),
        (None, None),
    ],
)
def test_extract_gender(fl, expected):
    assert extract_gender(fl) == expected


@pytest.fixture
def serve(monkeypatch):
    """Answer `fetch_entries`' requests with a handler instead of the network."""
    real_client = httpx.AsyncClient

    def _serve(handler):
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    return _serve


@pytest.fixture
def requests(serve):
    """Record the requests `fetch_entries` sends, answering each with `[]`."""
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=[])

    serve(handler)
    return sent


# Regression: the query was pasted into the URL unencoded, so "#" pushed the
# key into the fragment and "../" sent the key to another MW endpoint.
@pytest.mark.parametrize(
    ("query", "segment"),
    [
        ("casa", "casa"),
        ("cat#x", "cat%23x"),
        ("a?key=other", "a%3Fkey%3Dother"),
        ("../thesaurus/v3/references/x", "..%2Fthesaurus%2Fv3%2Freferences%2Fx"),
        ("ice cream", "ice%20cream"),
        # Regression: MW answers accented queries with suggestions only.
        ("cariño", "carino"),
        ("jamás", "jamas"),
        ("pingüino", "pinguino"),
        ("carin\u0303o", "carino"),  # "n" + a combining tilde
    ],
)
def test_query_is_one_encoded_path_segment(requests, query, segment):
    asyncio.run(fetch_entries(API_URL, "secret", query))
    [request] = requests
    assert request.url.raw_path.decode() == f"/api/v3/references/collegiate/json/{segment}?key=secret"


@pytest.mark.parametrize("query", ["", ".", "..", "..."])
def test_query_of_only_dots_makes_no_request(requests, query):
    assert asyncio.run(fetch_entries(API_URL, "secret", query)) == []
    assert requests == []


def _raise(exc_type):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("boom", request=request)

    return handler


# Regression: every one of these was an unhandled 500.
@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500, text="Internal Server Error"),
        lambda request: httpx.Response(403, text="Forbidden"),
        # What MW sends for a bad key: status 200, plain text.
        lambda request: httpx.Response(200, text="Invalid API key. Not subscribed for this reference."),
        lambda request: httpx.Response(200, json={"error": "unexpected"}),
        _raise(httpx.ReadTimeout),
        _raise(httpx.ConnectError),
    ],
    ids=["500", "403", "plain-text", "json-object", "timeout", "connect-error"],
)
def test_mw_failures_raise_dictionary_error_without_the_key(serve, handler):
    serve(handler)
    with pytest.raises(DictionaryError) as excinfo:
        asyncio.run(fetch_entries(API_URL, "secret", "casa"))
    # httpx's own messages contain the URL, and the URL contains the key.
    assert "secret" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


# --------------------------------------------------------------------------- #
# Entries with an unexpected shape
# --------------------------------------------------------------------------- #

from dictionary.en.en import EnglishDictionaryProvider  # noqa: E402
from dictionary.es.es import SpanishDictionaryProvider  # noqa: E402

PROVIDERS = [EnglishDictionaryProvider, SpanishDictionaryProvider]


def entry(name="casa", **fields):
    """A minimal well-formed MW entry."""
    return {
        "meta": {"id": f"{name}:1", "uuid": f"uuid-{name}", "stems": [name]},
        "hwi": {"hw": name, "prs": [{"mw": name, "sound": {"audio": name}}]},
        "fl": "noun",
        "shortdef": [f"definition of {name}"],
        **fields,
    }


def search(provider_class, monkeypatch, raw_items):
    """Run the provider's real `fetch` on `raw_items` instead of an MW response."""
    provider = provider_class()

    async def fake_fetch_raw(query):
        return raw_items

    monkeypatch.setattr(provider, "_fetch_raw", fake_fetch_raw)
    return asyncio.run(provider.fetch("casa"))


# Regression: one malformed entry made the whole search a 500.
@pytest.mark.parametrize("provider_class", PROVIDERS)
def test_a_malformed_entry_is_skipped_and_logged(provider_class, monkeypatch, caplog):
    broken = {k: v for k, v in entry("roto").items() if k != "meta"}
    result = search(provider_class, monkeypatch, [entry("casa"), broken])
    assert [w.name for w in result.words] == ["casa"]
    assert "Skipped a malformed MW entry" in caplog.text


@pytest.mark.parametrize("provider_class", PROVIDERS)
def test_an_entry_without_pronunciation_is_still_a_word(provider_class, monkeypatch):
    without_hwi = {k: v for k, v in entry("casa").items() if k != "hwi"}
    [word] = search(provider_class, monkeypatch, [without_hwi]).words
    assert word.name == "casa"
    assert word.audio_url is None


@pytest.mark.parametrize("provider_class", PROVIDERS)
@pytest.mark.parametrize(
    ("meta_id", "headword", "name"),
    [
        ("jamas", "jamás", "jamás"),  # the id has no accents
        ("Stark:b1", "Stark", "Stark"),  # a person; the id ends in ":b1"
        ("Borrow:b", "Bor*row", "Borrow"),  # "*" marks syllables
    ],
)
def test_the_name_is_the_headword(provider_class, monkeypatch, meta_id, headword, name):
    raw = entry("casa")
    raw["meta"]["id"] = meta_id
    raw["hwi"]["hw"] = headword
    [word] = search(provider_class, monkeypatch, [raw]).words
    assert word.name == name


@pytest.mark.parametrize("provider_class", PROVIDERS)
@pytest.mark.parametrize(("label", "offensive"), [(True, True), (False, False), (None, False)])
def test_the_offensive_label_is_read_from_meta(provider_class, monkeypatch, label, offensive):
    raw = entry("casa")
    if label is not None:
        raw["meta"]["offensive"] = label
    [word] = search(provider_class, monkeypatch, [raw]).words
    assert word.offensive is offensive


# Regression: MW's Spanish dictionary is bilingual, and English headwords
# were saved as Spanish words with a broken audio URL.
def test_spanish_search_keeps_only_spanish_headwords(monkeypatch):
    dog, perro = entry("dog"), entry("perro")
    dog["meta"]["lang"], perro["meta"]["lang"] = "en", "es"
    result = search(SpanishDictionaryProvider, monkeypatch, [dog, perro])
    assert [w.name for w in result.words] == ["perro"]


def test_a_spanish_search_with_only_english_headwords_finds_nothing(monkeypatch):
    dog = entry("dog")
    dog["meta"]["lang"] = "en"
    assert search(SpanishDictionaryProvider, monkeypatch, [dog]).is_empty


@pytest.mark.parametrize("provider_class", PROVIDERS)
def test_strings_mixed_into_entries_are_skipped(provider_class, monkeypatch):
    result = search(provider_class, monkeypatch, ["casas", entry("casa")])
    assert [w.name for w in result.words] == ["casa"]


@pytest.mark.parametrize("provider_class", PROVIDERS)
def test_only_malformed_entries_is_a_dictionary_error(provider_class, monkeypatch):
    meta_not_an_object = entry("casa", meta="casa:1")
    no_meta = {k: v for k, v in entry("perro").items() if k != "meta"}
    with pytest.raises(DictionaryError, match="malformed"):
        search(provider_class, monkeypatch, [meta_not_an_object, no_meta, 42])


@pytest.mark.parametrize("provider_class", PROVIDERS)
def test_entries_without_definitions_are_no_error(provider_class, monkeypatch):
    # Nothing to learn from them, but not malformed: an empty result ("not found").
    no_defs = {k: v for k, v in entry("casa").items() if k != "shortdef"}
    assert search(provider_class, monkeypatch, [no_defs]).words == []

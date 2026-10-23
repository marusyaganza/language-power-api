# tests/unit/test_mw.py
import asyncio

import httpx
import pytest

from dictionary.base import DictionaryError
from dictionary.helpers.mw import extract_gender, fetch_entries

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

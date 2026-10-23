# tests/unit/test_mw.py
import asyncio

import httpx
import pytest

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
def requests(monkeypatch):
    """Record the requests `fetch_entries` sends, answering each with `[]`."""
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=[])

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda: real_client(transport=httpx.MockTransport(handler))
    )
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

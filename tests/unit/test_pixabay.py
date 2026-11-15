# tests/unit/test_pixabay.py
"""Pixabay image search: what is sent, how answers are read, and failures (HTTP faked)."""

import logging

import httpx
import pytest

from images.base import (
    ImageSearchBusyError,
    ImageSearchError,
    ImageSearchTimeoutError,
    ImageType,
    clean_query,
)
from images.mock import mock_hit
from images.pixabay import PixabayImageSearch
from images.results import ImageResults

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def serve(monkeypatch):
    """Answer Pixabay's requests with a handler instead of the network."""
    real_client = httpx.AsyncClient

    def _serve(handler):
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    return _serve


@pytest.fixture
def answer(serve):
    """Answer every request with this JSON; returns the list of requests sent."""
    sent: list[httpx.Request] = []

    def _answer(data):
        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return httpx.Response(200, json=data)

        serve(handler)
        return sent

    return _answer


def pixabay(safe_search=True) -> PixabayImageSearch:
    return PixabayImageSearch("secret", safe_search=safe_search)


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("safe_search", "sent"), [(True, "true"), (False, "false")])
async def test_a_search_sends_the_query_page_type_and_safe_search(answer, safe_search, sent):
    requests = answer({"totalHits": 0, "hits": []})

    await pixabay(safe_search)._search_raw("ice cream", 2, ImageType.ILLUSTRATION)

    [request] = requests
    assert request.url.host == "pixabay.com"
    assert dict(request.url.params) == {
        "key": "secret",
        "q": "ice cream",
        "page": "2",
        "per_page": "12",
        "image_type": "illustration",
        "safesearch": sent,
        "lang": "en",
    }


async def test_get_asks_for_one_image_by_id(answer):
    requests = answer({"totalHits": 1, "hits": [mock_hit(3) | {"id": 195893}]})

    hit = await pixabay().get("195893")

    assert dict(requests[0].url.params) == {"key": "secret", "id": "195893"}
    assert hit.id == "195893"


@pytest.mark.parametrize("image_id", ["", "abc", "12 3", "1/../2", "١٢٣"])
async def test_get_with_an_id_that_isnt_a_number_makes_no_request(answer, image_id):
    requests = answer({"totalHits": 0, "hits": []})

    assert await pixabay().get(image_id) is None
    assert requests == []


async def test_get_of_an_image_pixabay_doesnt_have_is_none(answer):
    answer({"totalHits": 0, "hits": []})

    assert await pixabay().get("42") is None


# --------------------------------------------------------------------------- #
# Answers
# --------------------------------------------------------------------------- #


async def test_hits_are_read_into_image_hits(answer):
    raw = {
        "id": 195893,
        "previewURL": "https://cdn.pixabay.com/photo/a_150.jpg",
        "webformatURL": "https://pixabay.com/get/a_640.jpg",
        "webformatWidth": 640,
        "webformatHeight": 426,
        "largeImageURL": "https://pixabay.com/get/a_1280.jpg",
        "pageURL": "https://pixabay.com/en/dog-195893/",
        "user": "Josch13",
        "tags": "dog, puppy",
    }
    answer({"total": 4692, "totalHits": 500, "hits": [raw]})

    results = await pixabay()._search_raw("dog", 1, ImageType.ALL)

    assert results.total == 500  # what paging can reach, not every match
    [hit] = results.items
    assert (hit.id, hit.thumb_url, hit.preview_url, hit.download_url) == (
        "195893",
        "https://cdn.pixabay.com/photo/a_150.jpg",
        "https://pixabay.com/get/a_640.jpg",
        "https://pixabay.com/get/a_1280.jpg",
    )
    assert (hit.width, hit.height, hit.page_url, hit.author) == (
        640,
        426,
        "https://pixabay.com/en/dog-195893/",
        "Josch13",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"id": None},
        {"previewURL": None},
        {"largeImageURL": "http://pixabay.com/insecure.jpg"},
        {"webformatURL": "javascript:alert(1)"},
        {"webformatWidth": 0},
        {"webformatHeight": "426"},
    ],
    ids=["no-id", "no-thumb", "http", "javascript", "zero-width", "text-height"],
)
async def test_a_hit_with_an_unexpected_shape_is_skipped_and_logged(answer, caplog, change):
    answer({"totalHits": 2, "hits": [mock_hit(1) | change, mock_hit(2)]})

    with caplog.at_level(logging.WARNING, logger="images.pixabay"):
        results = await pixabay()._search_raw("dog", 1, ImageType.ALL)

    assert [hit.id for hit in results.items] == [str(mock_hit(2)["id"])]
    assert "Skipped a Pixabay hit" in caplog.text


async def test_a_missing_total_counts_as_no_more_results(answer):
    answer({"hits": [mock_hit(1)]})

    results = await pixabay()._search_raw("dog", 1, ImageType.ALL)

    assert (results.total, results.has_more) == (0, False)


@pytest.mark.parametrize(("page", "total", "more"), [(1, 13, True), (1, 12, False), (2, 30, True), (3, 30, False)])
def test_has_more_says_whether_another_page_exists(page, total, more):
    assert ImageResults(items=[], total=total, page=page).has_more is more


# --------------------------------------------------------------------------- #
# Failures
# --------------------------------------------------------------------------- #


def _raise(exc_type):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("boom", request=request)

    return handler


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (lambda request: httpx.Response(429, text="API rate limit exceeded"), ImageSearchBusyError),
        (_raise(httpx.ReadTimeout), ImageSearchTimeoutError),
        (_raise(httpx.ConnectTimeout), ImageSearchTimeoutError),
        (_raise(httpx.ConnectError), ImageSearchError),
        # What Pixabay sends for a bad key: an error status, plain text.
        (lambda request: httpx.Response(400, text="[ERROR 400] Invalid or missing API key"), ImageSearchError),
        (lambda request: httpx.Response(500, text="Internal Server Error"), ImageSearchError),
        (lambda request: httpx.Response(200, text="not json"), ImageSearchError),
        (lambda request: httpx.Response(200, json=[]), ImageSearchError),
        (lambda request: httpx.Response(200, json={"totalHits": 3}), ImageSearchError),
    ],
    ids=["429", "read-timeout", "connect-timeout", "connect-error", "400", "500", "text", "list", "no-hits"],
)
async def test_failures_raise_image_search_errors_without_the_key(serve, handler, error):
    serve(handler)

    with pytest.raises(error) as excinfo:
        await pixabay()._search_raw("dog", 1, ImageType.ALL)

    # httpx's own messages contain the URL, and the URL contains the key.
    assert "secret" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


# --------------------------------------------------------------------------- #
# Arguments checked before any request (or cache lookup)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("query", "cleaned"), [("dog", "dog"), ("  ice   cream ", "ice cream"), ("a" * 100, "a" * 100)]
)
def test_a_query_is_trimmed_and_its_spaces_collapsed(query, cleaned):
    assert clean_query(query) == cleaned


@pytest.mark.parametrize("query", ["", "   ", "a" * 101])
async def test_an_empty_or_too_long_query_is_rejected(answer, query):
    requests = answer({"totalHits": 0, "hits": []})

    with pytest.raises(ValueError):
        await pixabay().search(query)
    assert requests == []


@pytest.mark.parametrize("page", [0, -1, 43])
async def test_a_page_beyond_what_pixabay_lets_you_reach_is_rejected(answer, page):
    requests = answer({"totalHits": 0, "hits": []})

    with pytest.raises(ValueError):
        await pixabay().search("dog", page)
    assert requests == []


def test_the_last_page_holds_the_500th_result():
    assert pixabay().max_page == 42  # 41 full pages of 12, then results 493–500

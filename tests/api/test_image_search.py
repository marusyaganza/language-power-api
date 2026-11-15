# tests/api/test_image_search.py
"""Image search through the mock: the 24-hour Redis cache, and the mock's own answers."""

import pytest

from core.image_source import ImageSource
from images import searches
from images.base import ImageSearchBusyError, ImageType
from images.mock import ID_BASE, MOCK_RESULTS, MockPixabayImageSearch
from images.search_cache import CACHE_TTL_SECONDS
from settings import settings

pytestmark = pytest.mark.anyio


# --------------------------------------------------------------------------- #
# The cache
# --------------------------------------------------------------------------- #


async def test_the_same_search_is_answered_from_the_cache(redis):
    search = MockPixabayImageSearch()

    first = await search.search("dog")
    again = await search.search("dog")

    assert again == first
    assert len(search.requests) == 1


async def test_the_cache_ignores_case_and_extra_spaces(redis):
    search = MockPixabayImageSearch()

    await search.search("ice cream")
    await search.search("  Ice   CREAM ")

    assert len(search.requests) == 1


async def test_the_cache_is_shared_by_every_instance(redis):
    """The app makes one instance per source, but a restart makes new ones."""
    await MockPixabayImageSearch().search("dog")
    search = MockPixabayImageSearch()

    await search.search("dog")

    assert search.requests == []


@pytest.mark.parametrize(
    "other",
    [
        {"query": "cat"},
        {"page": 2},
        {"image_type": ImageType.ILLUSTRATION},
        {"safe_search": False},
    ],
    ids=["query", "page", "type", "safe-search"],
)
async def test_a_search_that_differs_in_anything_is_asked_again(redis, other):
    await MockPixabayImageSearch().search("dog")
    search = MockPixabayImageSearch(safe_search=other.get("safe_search", True))

    await search.search(other.get("query", "dog"), other.get("page", 1), other.get("image_type", ImageType.ALL))

    assert len(search.requests) == 1


async def test_cached_results_expire_after_a_day(redis):
    await MockPixabayImageSearch().search("dog")

    [key] = await redis.keys("image-search:*")
    assert key.startswith("image-search:pixabay:safesearch-on:all:1:")
    assert CACHE_TTL_SECONDS - 5 < await redis.ttl(key) <= CACHE_TTL_SECONDS == 24 * 60 * 60


async def test_a_failed_search_isnt_cached(redis):
    class FailsOnce(MockPixabayImageSearch):
        async def _request(self, params):
            if not self.requests:
                self.requests.append(params)
                raise ImageSearchBusyError("too many requests")
            return await super()._request(params)

    search = FailsOnce()

    with pytest.raises(ImageSearchBusyError):
        await search.search("dog")
    results = await search.search("dog")

    assert len(results.items) == 12
    assert len(search.requests) == 2


async def test_get_is_never_cached(redis):
    search = MockPixabayImageSearch()
    image_id = (await search.search("dog")).items[0].id

    await search.get(image_id)
    await search.get(image_id)

    assert len(search.requests) == 3
    assert len(await redis.keys("*")) == 1  # the search's page only


# --------------------------------------------------------------------------- #
# The mock
# --------------------------------------------------------------------------- #


async def test_the_mock_pages_through_its_results(redis):
    search = MockPixabayImageSearch()

    pages = [await search.search("dog", page) for page in (1, 2, 3)]

    assert [len(page.items) for page in pages] == [12, 12, MOCK_RESULTS - 24]
    assert [page.has_more for page in pages] == [True, True, False]
    ids = [hit.id for page in pages for hit in page.items]
    assert len(set(ids)) == MOCK_RESULTS


async def test_the_mock_finds_different_images_for_different_queries(redis):
    search = MockPixabayImageSearch()

    dog, cat = await search.search("dog"), await search.search("cat")

    assert dog.items[0].id != cat.items[0].id


@pytest.mark.parametrize("query", ["although", "Nothing"])
async def test_the_mock_finds_nothing_for_some_queries(redis, query):
    results = await MockPixabayImageSearch().search(query)

    assert (results.items, results.total, results.has_more) == ([], 0, False)


async def test_the_mock_gets_a_found_image_by_its_id(redis):
    search = MockPixabayImageSearch()
    found = (await search.search("dog")).items[3]

    assert await search.get(found.id) == found


@pytest.mark.parametrize("image_id", [str(ID_BASE - 1), str(ID_BASE + 85), "12"])
async def test_the_mock_has_no_image_for_other_ids(redis, image_id):
    assert await MockPixabayImageSearch().get(image_id) is None


def test_the_app_uses_the_mock_with_mocks_on_and_safe_search_from_the_settings(monkeypatch):
    monkeypatch.setattr(settings, "image_safe_search", False)

    search = searches.build_image_searches()[ImageSource.PIXABAY]

    assert type(search) is MockPixabayImageSearch
    assert search.cache_variant() == "safesearch-off"


def test_the_app_uses_pixabay_with_its_key_when_mocks_are_off(monkeypatch):
    from pydantic import SecretStr

    from images.pixabay import PixabayImageSearch

    monkeypatch.setattr(settings, "use_mocks", False)
    monkeypatch.setattr(settings, "pixabay_api_key", SecretStr("the-key"))

    search = searches.build_image_searches()[ImageSource.PIXABAY]

    assert type(search) is PixabayImageSearch
    assert search._api_key == "the-key"

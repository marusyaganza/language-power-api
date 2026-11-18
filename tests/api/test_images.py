# tests/api/test_images.py
"""Finding a word's image: GET /images/search and GET /images/suggestions (mock Pixabay)."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from core.image_source import ImageSource
from images import searches
from images.base import ImageSearchBusyError, ImageSearchError, ImageSearchTimeoutError
from settings import settings
from tests.api.conftest import save_word, signup

pytestmark = pytest.mark.anyio

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def images_on(monkeypatch):
    monkeypatch.setattr(settings, "image_search_providers", ["pixabay"])


async def search(client, **params):
    return await client.get("/images/search", params={"q": "dog", **params})


# --------------------------------------------------------------------------- #
# Off by default
# --------------------------------------------------------------------------- #


async def test_both_routes_are_404_where_image_search_is_off(client):
    word = await save_word(client, "perro", defs=["dog"])

    assert (await search(client)).status_code == 404
    assert (await client.get("/images/suggestions", params={"word_id": word["id"]})).status_code == 404


async def test_off_means_404_even_before_signing_in(make_client):
    assert (await search(make_client())).status_code == 404


async def test_on_needs_signing_in(make_client, images_on):
    assert (await search(make_client())).status_code == 401


# --------------------------------------------------------------------------- #
# Searching
# --------------------------------------------------------------------------- #


async def test_a_search_returns_a_page_of_twelve_without_download_urls(client, images_on):
    response = await search(client)

    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["total"], body["page"], body["has_more"]) == ("pixabay", 30, 1, True)
    assert len(body["items"]) == 12
    assert set(body["items"][0]) == {"id", "thumb_url", "preview_url", "width", "height", "page_url", "author"}


async def test_paging_and_the_image_type_are_passed_on(client, images_on):
    body = (await search(client, page=3, type="illustration")).json()

    assert (body["page"], len(body["items"]), body["has_more"]) == (3, 6, False)
    assert searches.IMAGE_SEARCHES[ImageSource.PIXABAY].requests[-1]["image_type"] == "illustration"


async def test_nothing_found_is_an_empty_page_not_an_error(client, images_on):
    response = await search(client, q="although")

    assert response.status_code == 200
    assert (response.json()["items"], response.json()["total"]) == ([], 0)


@pytest.mark.parametrize(
    "params",
    [{"q": ""}, {"q": "   "}, {"q": "a" * 101}, {"page": 0}, {"page": 43}, {"type": "vector"}],
    ids=["empty", "spaces", "too-long", "page-0", "past-the-last-page", "unknown-type"],
)
async def test_a_search_that_cant_be_made_is_422(client, images_on, params):
    assert (await search(client, **params)).status_code == 422


@pytest.mark.parametrize(
    ("error", "status"),
    [(ImageSearchBusyError("429"), 503), (ImageSearchTimeoutError("slow"), 504), (ImageSearchError("down"), 502)],
    ids=["busy", "timeout", "failed"],
)
async def test_search_api_failures_are_clear_statuses(client, images_on, monkeypatch, error, status):
    async def fail(params):
        raise error

    monkeypatch.setattr(searches.IMAGE_SEARCHES[ImageSource.PIXABAY], "_request", fail)

    response = await search(client)

    assert response.status_code == status
    assert "try again" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Suggestions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "language", "defs", "query"),
    [
        ("perro", "es", ["dog, bitch"], "dog"),
        ("wheel", "en", ["a circular frame"], "wheel"),
        ("가게", "ko", ["shop; store"], "shop"),
    ],
)
async def test_suggestions_start_with_the_words_english_meaning(client, images_on, name, language, defs, query):
    word = await save_word(client, name, language=language, defs=defs)

    response = await client.get("/images/suggestions", params={"word_id": word["id"]})

    assert response.status_code == 200
    assert response.json() == {"query": query, "used_before": []}


async def test_suggestions_for_someone_elses_word_are_404(client, make_client, images_on):
    word = await save_word(client, "perro", defs=["dog"])
    other = make_client()
    await signup(other)

    assert (await other.get("/images/suggestions", params={"word_id": word["id"]})).status_code == 404


async def test_suggestions_for_a_missing_word_are_404(client, images_on):
    assert (await client.get("/images/suggestions", params={"word_id": 999_999})).status_code == 404


# --------------------------------------------------------------------------- #
# Docs
# --------------------------------------------------------------------------- #


def _schema_paths(**env: str) -> list[str]:
    """The /docs paths of an app imported fresh with these env vars (routes are listed once, at import)."""
    script = "import json, main\nprint(json.dumps(sorted(main.app.openapi()['paths'])))\n"
    with tempfile.TemporaryDirectory() as empty_dir:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=empty_dir,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT), **env},
            capture_output=True,
            text=True,
            check=True,
        )
    return json.loads(result.stdout)


def test_the_image_routes_are_listed_in_the_docs_only_where_image_search_is_on():
    off = _schema_paths(IMAGE_SEARCH_PROVIDERS="[]")
    on = _schema_paths(IMAGE_SEARCH_PROVIDERS='["pixabay"]', USE_MOCKS="true")

    assert not any(path.startswith("/images") for path in off)
    assert {"/images/search", "/images/suggestions"} <= set(on)

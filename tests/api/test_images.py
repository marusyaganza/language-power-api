# tests/api/test_images.py
"""Finding a word's image (GET /images/search, GET /images/suggestions) and saving it (mock Pixabay)."""

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from core.image_source import ImageSource
from core.media_storage import StorageError
from images import mock, picks, searches
from images.base import ImageSearchBusyError, ImageSearchError, ImageSearchTimeoutError
from images.processing import ImageProcessingError
from settings import settings
from tests.api.conftest import InMemoryStorage, save_word, signup

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


# --------------------------------------------------------------------------- #
# Saving a word with a picked image (PATCH /words/{id} with img_pick)
# --------------------------------------------------------------------------- #


def jpeg_for(url: str) -> bytes:
    """A small JPEG of its own colour for each URL, as a real download would differ."""
    digest = hashlib.sha256(url.encode()).digest()
    output = io.BytesIO()
    Image.new("RGB", (640, 427), tuple(digest[:3])).save(output, format="JPEG")
    return output.getvalue()


@pytest.fixture
def downloads(monkeypatch):
    """Downloads answer with `jpeg_for(url)`; returns the URLs downloaded."""
    urls: list[str] = []

    async def fake_download(url):
        urls.append(url)
        return jpeg_for(url)

    monkeypatch.setattr(picks, "download_image", fake_download)
    return urls


async def found(client, query="dog", index=0) -> dict:
    return (await search(client, q=query)).json()["items"][index]


async def edit(client, word_id, **fields):
    return await client.patch(f"/words/{word_id}", json=fields)


async def vocabulary_word(client, language="es") -> dict:
    [word] = (await client.get("/words/vocabulary", params={"language": language})).json()["items"]
    return word


async def test_saving_with_a_pick_stores_a_webp_and_sets_the_url(client, images_on, downloads, media_storage):
    word = await save_word(client, "perro", defs=["dog"])
    hit = await found(client)

    response = await edit(client, word["id"], img_pick={"source": "pixabay", "id": hit["id"]})

    assert response.status_code == 200
    [(path, (data, content_type))] = media_storage.files.items()
    assert path == f"images/pixabay/{hashlib.sha256(data).hexdigest()}.webp"
    assert content_type == "image/webp"
    stored = Image.open(io.BytesIO(data))
    # The 640×427 download, shrunk to fit 512 px (427 × 0.8 = 341.6, rounded).
    assert (stored.format, stored.size) == ("WEBP", (512, 342))
    assert response.json()["img_url"] == f"{InMemoryStorage.BASE_URL}/{path}"
    assert (await vocabulary_word(client))["img_url"] == response.json()["img_url"]


async def test_the_large_image_is_downloaded_not_a_url_from_the_client(client, images_on, downloads):
    word = await save_word(client, "perro", defs=["dog"])
    hit = await found(client)

    await edit(client, word["id"], img_pick={"source": "pixabay", "id": hit["id"]})

    picsum_id = int(hit["id"]) - mock.ID_BASE
    assert downloads == [f"https://picsum.photos/id/{picsum_id}/1280/853"]


async def test_the_same_pick_for_two_words_is_stored_once(client, images_on, downloads, media_storage):
    hit = await found(client)
    for name in ("perro", "can"):
        word = await save_word(client, name, defs=["dog"])
        await edit(client, word["id"], img_pick={"source": "pixabay", "id": hit["id"]})

    assert len(media_storage.files) == 1


async def test_a_new_pick_clears_the_old_description_unless_one_is_sent(client, images_on, downloads):
    word = await save_word(client, "perro", defs=["dog"], img_url="https://example.com/old.jpg", img_desc="old")
    first, second = await found(client, index=0), await found(client, index=1)

    cleared = (await edit(client, word["id"], img_pick={"source": "pixabay", "id": first["id"]})).json()
    described = (
        await edit(client, word["id"], img_pick={"source": "pixabay", "id": second["id"]}, img_desc="a dog")
    ).json()

    assert cleared["img_desc"] is None
    assert described["img_desc"] == "a dog"


async def test_picking_the_same_image_again_keeps_its_description(client, images_on, downloads):
    word = await save_word(client, "perro", defs=["dog"])
    pick = {"source": "pixabay", "id": (await found(client))["id"]}
    await edit(client, word["id"], img_pick=pick, img_desc="a dog")

    again = (await edit(client, word["id"], img_pick=pick)).json()

    assert again["img_desc"] == "a dog"


async def test_other_fields_are_saved_with_the_pick(client, images_on, downloads):
    word = await save_word(client, "perro", defs=["dog"])
    hit = await found(client)

    saved = (await edit(client, word["id"], img_pick={"source": "pixabay", "id": hit["id"]}, defs=["hound"])).json()

    assert saved["defs"] == ["hound"]
    assert saved["img_url"].endswith(".webp")


@pytest.mark.parametrize(
    "fields",
    [
        {"img_pick": {"source": "pixabay", "id": "1000001"}, "img_url": "https://example.com/a.jpg"},
        {"img_pick": {"source": "pixabay", "id": "1000001"}, "img_url": None},
        {"img_pick": {"source": "unsplash", "id": "1000001"}},
        {"img_pick": {"source": "pixabay", "id": "../1"}},
        {"img_pick": {"source": "pixabay", "id": ""}},
        {"img_pick": {"source": "pixabay"}},
    ],
    ids=["with-img-url", "with-img-url-null", "unknown-source", "bad-id", "empty-id", "no-id"],
)
async def test_a_pick_that_cant_be_read_is_422(client, images_on, downloads, fields):
    word = await save_word(client, "perro", defs=["dog"])

    assert (await edit(client, word["id"], **fields)).status_code == 422
    assert downloads == []


async def test_a_pick_where_image_search_is_off_is_422(client, downloads):
    word = await save_word(client, "perro", defs=["dog"])

    response = await edit(client, word["id"], img_pick={"source": "pixabay", "id": "1000001"})

    assert response.status_code == 422
    assert downloads == []


async def unchanged(client, word):
    saved = await vocabulary_word(client)
    return (saved["img_url"], saved["defs"]) == (word["img_url"], word["defs"])


async def test_an_image_gone_from_its_source_is_409_and_changes_nothing(client, images_on, downloads, media_storage):
    word = await save_word(client, "perro", defs=["dog"], img_url="https://example.com/old.jpg")

    response = await edit(client, word["id"], img_pick={"source": "pixabay", "id": "12"}, defs=["changed"])

    assert response.status_code == 409
    assert "pick another" in response.json()["detail"]
    assert await unchanged(client, word)
    assert (downloads, media_storage.files) == ([], {})


async def test_a_failed_lookup_is_503_and_changes_nothing(client, images_on, downloads, media_storage, monkeypatch):
    word = await save_word(client, "perro", defs=["dog"], img_url="https://example.com/old.jpg")
    hit = await found(client)

    async def fail(params):
        raise ImageSearchTimeoutError("slow")

    monkeypatch.setattr(searches.IMAGE_SEARCHES[ImageSource.PIXABAY], "_request", fail)

    response = await edit(client, word["id"], img_pick={"source": "pixabay", "id": hit["id"]}, defs=["changed"])

    assert response.status_code == 503
    assert "try saving again" in response.json()["detail"]
    assert await unchanged(client, word)
    assert media_storage.files == {}


async def test_a_failed_download_is_503_and_changes_nothing(client, images_on, media_storage, monkeypatch):
    word = await save_word(client, "perro", defs=["dog"], img_url="https://example.com/old.jpg")
    hit = await found(client)

    async def fail(url):
        raise ImageProcessingError("The image download timed out")

    monkeypatch.setattr(picks, "download_image", fail)

    response = await edit(client, word["id"], img_pick={"source": "pixabay", "id": hit["id"]}, defs=["changed"])

    assert response.status_code == 503
    assert await unchanged(client, word)
    assert media_storage.files == {}


async def test_a_download_that_isnt_an_image_is_503(client, images_on, monkeypatch):
    word = await save_word(client, "perro", defs=["dog"])
    hit = await found(client)

    async def not_an_image(url):
        return b"<html>"

    monkeypatch.setattr(picks, "download_image", not_an_image)

    assert (await edit(client, word["id"], img_pick={"source": "pixabay", "id": hit["id"]})).status_code == 503


async def test_a_failed_upload_is_503_and_changes_nothing(client, images_on, downloads, media_storage, monkeypatch):
    word = await save_word(client, "perro", defs=["dog"], img_url="https://example.com/old.jpg")
    hit = await found(client)

    async def fail(data, path, content_type):
        raise StorageError("Cloud Storage upload failed: ServiceUnavailable")

    monkeypatch.setattr(media_storage, "upload", fail)

    response = await edit(client, word["id"], img_pick={"source": "pixabay", "id": hit["id"]}, defs=["changed"])

    assert response.status_code == 503
    assert "couldn't be stored" in response.json()["detail"]
    assert await unchanged(client, word)

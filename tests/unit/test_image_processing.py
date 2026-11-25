# tests/unit/test_image_processing.py
"""Downloading, converting and storing an image (images made in memory, HTTP faked)."""

import io

import httpx
import pytest
from PIL import Image, ImageFile

from core import media_storage
from core.media_storage import LocalFolderStorage, StorageError
from images import processing
from images.processing import (
    MAX_DOWNLOAD_BYTES,
    MAX_REDIRECTS,
    MAX_SIDE,
    ImageProcessingError,
    convert_to_webp,
    download_image,
    store_image,
    to_webp,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def make_image(size=(1280, 853), mode="RGB", fmt="JPEG", **save) -> bytes:
    color = (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)
    image = Image.new(mode, size, color[: len(mode)] if mode != "P" else 1)
    output = io.BytesIO()
    image.save(output, format=fmt, **save)
    return output.getvalue()


def opened(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


# --------------------------------------------------------------------------- #
# Converting
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("size", "expected"),
    [((1280, 853), (512, 341)), ((853, 1280), (341, 512)), ((1024, 1024), (512, 512)), ((300, 200), (300, 200))],
    ids=["landscape", "portrait", "square", "small-isnt-enlarged"],
)
def test_an_image_becomes_a_webp_that_fits_the_largest_side(size, expected):
    result = opened(to_webp(make_image(size)))

    assert (result.format, result.size) == ("WEBP", expected)
    assert max(expected) <= MAX_SIDE


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP", "GIF"])
def test_every_allowed_format_is_converted(fmt):
    assert opened(to_webp(make_image((600, 400), mode="P" if fmt == "GIF" else "RGB", fmt=fmt))).format == "WEBP"


def test_transparency_is_kept():
    result = opened(to_webp(make_image((600, 400), mode="RGBA", fmt="PNG")))

    assert result.mode == "RGBA"
    assert result.getpixel((10, 10))[3] < 255


def test_a_photo_without_transparency_has_none():
    assert opened(to_webp(make_image())).mode == "RGB"


def test_the_exif_orientation_is_applied_and_the_metadata_dropped():
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise to display
    exif[0x010F] = "Camera maker"  # Make
    sideways = make_image((800, 400), exif=exif.tobytes())

    result = opened(to_webp(sideways))

    assert result.size == (256, 512)  # upright: portrait
    assert not result.getexif()
    assert "icc_profile" not in result.info


def test_an_animated_gif_becomes_its_first_frame():
    frames = [Image.new("P", (300, 200), color) for color in (1, 2, 3)]
    output = io.BytesIO()
    frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:], duration=100)

    result = Image.open(io.BytesIO(to_webp(output.getvalue())))

    assert getattr(result, "n_frames", 1) == 1


def test_the_same_image_converts_to_the_same_bytes():
    """The stored name is the hash of the converted file, so the same pick is stored once."""
    data = make_image()

    assert to_webp(data) == to_webp(data)


@pytest.mark.parametrize(
    "data",
    [b"", b"not an image at all", make_image(fmt="BMP"), make_image(fmt="TIFF"), b"<svg xmlns='x'/>"],
    ids=["empty", "text", "bmp", "tiff", "svg"],
)
def test_anything_but_an_allowed_image_is_rejected(data):
    with pytest.raises(ImageProcessingError, match="isn't an image the app accepts"):
        to_webp(data)


def test_a_damaged_image_is_rejected():
    data = make_image()

    with pytest.raises(ImageProcessingError, match="damaged"):
        to_webp(data[: len(data) // 2])


def test_an_image_with_too_many_pixels_is_rejected_before_it_is_decoded(monkeypatch):
    """A small file can decode into a huge image: the header's size is checked first."""
    data = make_image((1001, 1000), fmt="PNG")
    monkeypatch.setattr(processing, "MAX_PIXELS", 1000 * 1000)
    decoded = []
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self: decoded.append(self))

    with pytest.raises(ImageProcessingError, match="too many pixels"):
        to_webp(data)
    assert decoded == []


async def test_the_conversion_runs_off_the_event_loop(monkeypatch):
    calls = []

    async def fake_to_thread(function, *args):
        calls.append(function)
        return function(*args)

    monkeypatch.setattr(processing.asyncio, "to_thread", fake_to_thread)

    assert opened(await convert_to_webp(make_image())).format == "WEBP"
    assert calls == [to_webp]


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #

IMAGE_URL = "https://pixabay.com/get/a_1280.jpg"


@pytest.fixture
def serve(monkeypatch):
    """Answer downloads with a handler instead of the network; returns the requests sent."""
    real_client = httpx.AsyncClient
    sent: list[httpx.Request] = []

    def _serve(handler):
        def recording(request):
            sent.append(request)
            return handler(request)

        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=httpx.MockTransport(recording), **kwargs),
        )
        return sent

    return _serve


def jpeg_response(request, body=None, **headers):
    body = make_image() if body is None else body
    return httpx.Response(200, content=body, headers={"content-type": "image/jpeg", **headers})


async def test_an_image_is_downloaded(serve):
    serve(jpeg_response)

    assert await download_image(IMAGE_URL) == make_image()


async def test_redirects_are_followed(serve):
    sent = serve(
        lambda request: (
            httpx.Response(302, headers={"location": "https://cdn.example/a.jpg"})
            if request.url.host == "pixabay.com"
            else jpeg_response(request)
        )
    )

    assert await download_image(IMAGE_URL) == make_image()
    assert [request.url.host for request in sent] == ["pixabay.com", "cdn.example"]


async def test_a_redirect_to_plain_http_isnt_followed(serve):
    sent = serve(lambda request: httpx.Response(302, headers={"location": "http://cdn.example/a.jpg"}))

    with pytest.raises(ImageProcessingError, match="https"):
        await download_image(IMAGE_URL)
    assert len(sent) == 1


async def test_endless_redirects_stop(serve):
    sent = serve(lambda request: httpx.Response(302, headers={"location": IMAGE_URL}))

    with pytest.raises(ImageProcessingError, match="TooManyRedirects"):
        await download_image(IMAGE_URL)
    assert len(sent) == 1 + MAX_REDIRECTS


@pytest.mark.parametrize("url", ["http://pixabay.com/a.jpg", "file:///etc/passwd", "ftp://x/a.jpg", "/a.jpg"])
async def test_only_https_urls_are_downloaded(serve, url):
    sent = serve(jpeg_response)

    with pytest.raises(ImageProcessingError, match="https"):
        await download_image(url)
    assert sent == []


@pytest.mark.parametrize(
    ("handler", "message"),
    [
        (lambda request: httpx.Response(404, text="Not Found"), "status 404"),
        (lambda request: httpx.Response(200, text="<html>", headers={"content-type": "text/html"}), "isn't an image"),
        (lambda request: httpx.Response(200, content=b"x"), "isn't an image"),  # no content type
        (
            lambda request: jpeg_response(request, b"x", **{"content-length": str(MAX_DOWNLOAD_BYTES + 1)}),
            "too large",
        ),
    ],
    ids=["404", "html", "no-type", "declared-too-large"],
)
async def test_a_bad_answer_is_rejected(serve, handler, message):
    serve(handler)

    with pytest.raises(ImageProcessingError, match=message):
        await download_image(IMAGE_URL)


async def test_a_download_that_grows_too_large_is_stopped(serve):
    """No content-length, or a wrong one: the bytes are counted as they arrive."""
    chunk = b"\0" * 64 * 1024

    async def just_over_the_limit():
        # Finite, so a broken size check fails this test instead of using up memory.
        for _ in range(MAX_DOWNLOAD_BYTES // len(chunk) + 1):
            yield chunk

    serve(lambda request: httpx.Response(200, content=just_over_the_limit(), headers={"content-type": "image/jpeg"}))

    with pytest.raises(ImageProcessingError, match="too large"):
        await download_image(IMAGE_URL)


@pytest.mark.parametrize(
    ("error", "message"),
    [(httpx.ReadTimeout, "timed out"), (httpx.ConnectTimeout, "timed out"), (httpx.ConnectError, "ConnectError")],
)
async def test_network_failures_become_processing_errors(serve, error, message):
    def handler(request):
        raise error("boom", request=request)

    serve(handler)

    with pytest.raises(ImageProcessingError, match=message) as excinfo:
        await download_image(IMAGE_URL)
    assert excinfo.value.__cause__ is None


# --------------------------------------------------------------------------- #
# Storing
# --------------------------------------------------------------------------- #


async def test_an_image_is_stored_under_its_source_and_hash(monkeypatch, tmp_path):
    monkeypatch.setattr(media_storage, "STORAGE", LocalFolderStorage(tmp_path, "https://media.test"))
    webp = to_webp(make_image())

    url = await store_image(webp, "pixabay")

    path = media_storage.hashed_path("images/pixabay", webp, "webp")
    assert url == f"https://media.test/{path}"
    assert (tmp_path / path).read_bytes() == webp


async def test_storing_without_storage_fails(monkeypatch):
    monkeypatch.setattr(media_storage, "STORAGE", None)

    with pytest.raises(StorageError):
        await store_image(b"webp", "pixabay")

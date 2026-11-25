"""Turning a picked or generated image into the file the app stores.

Three steps, used by the save (I5) and later by generation:
1. `download_image`: fetch the image an image search API pointed to.
2. `to_webp`: shrink it to fit `MAX_SIDE` and convert it to WebP. A
   flashcard needs no more, and a 512 px WebP is 30–60 KB.
3. `store_image`: upload it to `images/<source>/<sha256>.webp`, so the
   client can tell where an image came from by its path.

The bytes come from another site, so every step has a limit: the download's
size and type, the image's format and its number of pixels (a small file can
decode into a huge image). Nothing about the original survives the conversion
except its pixels: no EXIF (camera, location), no colour profile.
"""

import asyncio
import io

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from core import media_storage
from core.media_storage import StorageError

# Pixabay's largeImageURL is at most 1280 px; its JPEGs are well under 1 MB.
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 15
MAX_REDIRECTS = 3
# The longest side of a stored image.
MAX_SIDE = 512
# More than any image we ask for (1280×1280 is 1.6 million), far less than
# what would exhaust the server's memory once decoded.
MAX_PIXELS = 25_000_000
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF"})
WEBP_QUALITY = 80


class ImageProcessingError(Exception):
    """The image couldn't be downloaded or isn't one the app accepts.

    The message is safe to log and show.
    """


async def download_image(url: str) -> bytes:
    """The bytes of the image at `url`, an https URL an image search API returned.

    Redirects are followed (image hosts use them), at most `MAX_REDIRECTS`.
    Every request, the first and each redirect, must be https (`_require_https`).

    Raises:
        ImageProcessingError: a URL isn't https, the download failed or
            timed out, the answer isn't an image, or it's larger than
            `MAX_DOWNLOAD_BYTES`.
    """
    try:
        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            event_hooks={"request": [_require_https]},
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise ImageProcessingError(f"The image download answered with status {resp.status_code}")
                content_type = resp.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    raise ImageProcessingError("The download isn't an image")
                declared = resp.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > MAX_DOWNLOAD_BYTES:
                    raise ImageProcessingError("The image is too large to download")
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise ImageProcessingError("The image is too large to download")
                    chunks.append(chunk)
    except httpx.TimeoutException:
        raise ImageProcessingError("The image download timed out") from None
    except httpx.HTTPError as exc:
        raise ImageProcessingError(f"The image download failed: {type(exc).__name__}") from None
    return b"".join(chunks)


async def _require_https(request: httpx.Request) -> None:
    """Refuse any request that isn't https (plain http, a redirect to it, no scheme) before it is sent."""
    if request.url.scheme != "https":
        raise ImageProcessingError("Images are only downloaded over https")


def to_webp(data: bytes) -> bytes:
    """`data` as a WebP image whose longest side is at most `MAX_SIDE` (never enlarged).

    The EXIF orientation is applied first, so a photo taken sideways stays
    upright once its metadata is gone. Transparency is kept; an animated GIF
    becomes its first frame. Blocking (CPU): call it through `convert_to_webp`.

    Raises:
        ImageProcessingError: not an image, not one of `ALLOWED_FORMATS`, or
            more than `MAX_PIXELS` pixels.
    """
    try:
        # `open` reads only the header, so the size is checked before decoding.
        with Image.open(io.BytesIO(data), formats=sorted(ALLOWED_FORMATS)) as image:
            width, height = image.size
            if width * height > MAX_PIXELS:
                raise ImageProcessingError("The image has too many pixels")
            image = ImageOps.exif_transpose(image)
            has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
            image = image.convert("RGBA" if has_alpha else "RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=WEBP_QUALITY)
    except (UnidentifiedImageError, Image.DecompressionBombError):
        raise ImageProcessingError("The file isn't an image the app accepts") from None
    except (OSError, ValueError, SyntaxError):
        # Pillow's errors for a truncated or corrupt file.
        raise ImageProcessingError("The image file is damaged") from None
    return output.getvalue()


async def convert_to_webp(data: bytes) -> bytes:
    """`to_webp`, in a thread, off the event loop."""
    return await asyncio.to_thread(to_webp, data)


async def store_image(webp: bytes, source: str) -> str:
    """Upload a WebP from `to_webp` to `images/<source>/<sha256>.webp`; return its URL.

    `source` is where it came from: an image search source (`pixabay`) or
    `generated`. The same bytes always get the same name, so storing an image
    twice writes it once.

    Raises:
        StorageError: there is no storage, or the upload failed.
    """
    storage = media_storage.STORAGE
    if storage is None:
        raise StorageError("No media storage is configured")
    return await storage.upload(webp, media_storage.hashed_path(f"images/{source}", webp, "webp"), "image/webp")

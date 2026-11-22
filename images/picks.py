"""Storing an image picked from the search results, when its word is saved.

Its own module, apart from `images.service`: the words service calls it, and
`images.service` calls the words service (for the suggestions), so keeping
this free of `words` imports avoids a cycle, as `audio.service` does.
"""

import logging

from images import searches
from images.base import ImageSearchError
from images.processing import ImageProcessingError, convert_to_webp, download_image, store_image
from settings import settings

logger = logging.getLogger(__name__)


class PickError(Exception):
    """Base of the errors below. The message is safe to show."""


class ImageSearchOffError(PickError):
    """The pick names a source this deployment doesn't offer (or image search is off)."""


class PickedImageGoneError(PickError):
    """The search API no longer has the picked image."""


class PickedImageUnavailableError(PickError):
    """The picked image couldn't be fetched right now (the API or the download failed)."""


async def store_pick(source: str, image_id: str) -> str:
    """Download the picked image, convert it to WebP, store it, and return its URL.

    The image is looked up again by its id rather than trusting a URL from the
    client: the server only downloads what the API itself points to, and the
    API's URLs expire (Pixabay's after 24 hours), so a fresh one is needed.

    Raises:
        ImageSearchOffError: `source` isn't offered here.
        PickedImageGoneError: the API doesn't have the image anymore.
        PickedImageUnavailableError: the API or the download failed, or the
            file isn't an image the app accepts.
        StorageError: the image couldn't be stored.
    """
    if source not in settings.image_search_providers:
        raise ImageSearchOffError("Image search isn't available")
    try:
        hit = await searches.IMAGE_SEARCHES[source].get(image_id)
    except ImageSearchError as exc:
        logger.warning("Looking up picked image %s:%s failed: %s", source, image_id, exc)
        raise PickedImageUnavailableError("The image couldn't be fetched right now, try saving again") from exc
    if hit is None:
        raise PickedImageGoneError("This image is no longer available, pick another")
    try:
        webp = await convert_to_webp(await download_image(hit.download_url))
    except ImageProcessingError as exc:
        logger.warning("Downloading picked image %s:%s failed: %s", source, image_id, exc)
        raise PickedImageUnavailableError("The image couldn't be fetched right now, try saving again") from exc
    return await store_image(webp, source)

from core.image_source import ImageSource
from images.base import ImageSearch
from images.mock import MockPixabayImageSearch
from images.pixabay import PixabayImageSearch
from settings import settings


def build_image_searches() -> dict[ImageSource, ImageSearch]:
    """An image search for every source, mocked when `use_mocks` is on.

    Every source gets one, cheap to make (nothing connects until the first
    search): whether a source is offered is `settings.image_search_providers`,
    checked by the routes. The settings refuse to start with Pixabay on, real
    APIs and no key, so an empty key here only reaches the mock.
    """
    api_key = settings.pixabay_api_key.get_secret_value() if settings.pixabay_api_key else ""
    pixabay = MockPixabayImageSearch if settings.use_mocks else PixabayImageSearch
    return {ImageSource.PIXABAY: pixabay(api_key, safe_search=settings.image_safe_search)}


IMAGE_SEARCHES = build_image_searches()

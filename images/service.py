"""Image search for a word's image: the rules between the routes and the search APIs.

Domain errors only; `images.router` turns them into HTTP statuses.
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from images import searches
from images.base import ImageSearch, ImageSearchBusyError, ImageSearchError, ImageSearchTimeoutError, ImageType
from images.meaning import image_meaning
from images.results import ImageResults
from settings import settings
from words import service as words_service


class ImagesError(Exception):
    """Base of the errors below. The message is safe to show."""


class InvalidSearchError(ImagesError):
    """The query or page can't be searched (empty, too long, out of range)."""


class SearchBusyError(ImagesError):
    """The search API is refusing requests for now (too many); worth retrying in a minute."""


class SearchTimeoutError(ImagesError):
    """The search API didn't answer in time; worth retrying."""


class SearchFailedError(ImagesError):
    """The search API failed or is unreachable; worth retrying."""


class WordNotFoundError(ImagesError):
    """No such word, or it belongs to another user."""


@dataclass(frozen=True)
class UsedImage:
    """An image already saved with another of the user's words of the same meaning (I9)."""

    word_id: int
    img_url: str


@dataclass(frozen=True)
class Suggestions:
    query: str
    used_before: list[UsedImage] = field(default_factory=list)


def search_source() -> ImageSearch:
    """The image search the routes use: the first source the deployment offers."""
    return searches.IMAGE_SEARCHES[settings.image_search_providers[0]]


async def search(query: str, page: int, image_type: ImageType) -> ImageResults:
    """One page of images for `query`, from the search source (cached for 24 hours).

    Raises:
        InvalidSearchError, SearchBusyError, SearchTimeoutError, SearchFailedError.
    """
    try:
        return await search_source().search(query, page, image_type)
    except ValueError as exc:
        raise InvalidSearchError(str(exc)) from exc
    except ImageSearchBusyError as exc:
        raise SearchBusyError("The image search is busy, try again in a minute") from exc
    except ImageSearchTimeoutError as exc:
        raise SearchTimeoutError("The image search didn't answer in time, try again") from exc
    except ImageSearchError as exc:
        raise SearchFailedError("The image search isn't available right now, try again") from exc


async def suggestions(db: AsyncSession, user_id: int, word_id: int) -> Suggestions:
    """What the picker starts with for one of the user's words: the query (its English meaning).

    `used_before` stays empty until "Used before" is built (I9).

    Raises:
        WordNotFoundError: no such word, or it belongs to another user.
    """
    try:
        word = await words_service.get_word(db, user_id, word_id)
    except words_service.WordNotFoundError as exc:
        raise WordNotFoundError("Word not found") from exc
    return Suggestions(query=image_meaning(word.language, word.name, word.defs))

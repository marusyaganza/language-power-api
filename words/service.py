"""The user's saved vocabulary, and the dictionary lookups that feed it.

This is the only part of `words` that other modules (the router, games) should
import from. Callers never touch the `Word` table directly.

Rules that apply to every function below:

* Everything is scoped to `user_id`. A word that exists but belongs to another
  user is reported exactly like a word that does not exist, so ids of other
  users' words cannot be probed.
* Functions that modify data commit before returning. Call them one at a time
  rather than as part of a larger transaction.
* Failures are raised as subclasses of `WordsError`. This module knows nothing
  about HTTP; the router decides how each error is presented.
* `db` must be an `AsyncSession`. An async session cannot lazy-load, so
  `Word.examples` is always loaded eagerly. Anything that returns a `Word`
  returns it with its examples already available.
* Nothing here knows about games. Filters are phrased in terms of what a word
  has (audio, image, gender), and callers decide which of those they need.
"""

import logging
from dataclasses import dataclass
from math import ceil

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dictionary.base import DictionaryError, SearchResult
from dictionary.providers import PROVIDERS
from words import repository
from words.models import Example, Word
from words.schemas import (
    SortOrder,
    VocabularyPage,
    VocabularySortBy,
    WordCreate,
    WordOut,
    WordUpdate,
)

logger = logging.getLogger(__name__)

__all__ = [
    "WordsError",
    "UnsupportedLanguageError",
    "DefinitionNotFoundError",
    "DictionaryUnavailableError",
    "WordNotFoundError",
    "WordAlreadySavedError",
    "VOCABULARY_PAGE_SIZE",
    "search_words",
    "save_word",
    "update_word",
    "delete_word",
    "get_vocabulary_page",
    "get_word_ids",
    "get_words_by_ids",
    "WordSummary",
    "get_word_summaries",
]

VOCABULARY_PAGE_SIZE = 10


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class WordsError(Exception):
    """Base class for every error this module raises on purpose."""


class UnsupportedLanguageError(WordsError):
    """No dictionary provider is configured for the requested language."""


class DefinitionNotFoundError(WordsError):
    """The dictionary has no entry at all for the searched text."""


class DictionaryUnavailableError(WordsError):
    """The dictionary could not be used right now; the search may work later."""


class WordNotFoundError(WordsError):
    """The user has no saved word with the given id."""


class WordAlreadySavedError(WordsError):
    """Saving the word violated a uniqueness constraint."""


# --------------------------------------------------------------------------- #
# Dictionary search
# --------------------------------------------------------------------------- #


async def search_words(db: AsyncSession, user_id: int, *, query: str, language: str) -> SearchResult:
    """Look `query` up in the dictionary for `language`.

    Each returned word has `saved=True` if the user already has a saved word
    with the same dictionary uuid. Words the dictionary returns without a uuid
    are never marked as saved.

    A response that contains no words but spelling suggestions, or (with
    mocks on) the queries that have mock data, is a normal result and is
    returned unchanged.

    Raises:
        UnsupportedLanguageError: there is no provider for `language`.
        DefinitionNotFoundError: the dictionary returned nothing at all.
        DictionaryUnavailableError: the dictionary failed (unreachable, timed
            out, or an error response). The cause is logged, not returned.
    """
    provider = PROVIDERS.get(language)
    if provider is None:
        raise UnsupportedLanguageError(f"Unsupported language: {language}")

    try:
        results = await provider.fetch(query)
    except DictionaryError as exc:
        logger.warning("Dictionary lookup failed for language=%s: %s", language, exc)
        raise DictionaryUnavailableError("Dictionary is unavailable, try again later") from exc
    if results.is_empty:
        raise DefinitionNotFoundError("Word not found")
    if not results.words:
        return results

    uuids = [w.uuid for w in results.words if w.uuid]
    saved_uuids = await repository.get_saved_uuids(db, user_id, uuids)
    words = [WordOut.model_validate(w).model_copy(update={"saved": w.uuid in saved_uuids}) for w in results.words]
    return SearchResult(words=words)


# --------------------------------------------------------------------------- #
# Saved vocabulary: writes
# --------------------------------------------------------------------------- #


async def save_word(db: AsyncSession, user_id: int, payload: WordCreate) -> Word:
    """Add `payload` to the user's vocabulary and return the stored word.

    Raises:
        WordAlreadySavedError: the database rejected the insert as a
            duplicate. Nothing is stored and the session is rolled back.
    """
    word = Word(
        user_id=user_id,
        uuid=payload.uuid,
        name=payload.name,
        language=payload.language,
        stems=payload.stems,
        defs=payload.defs,
        fl=payload.fl,
        audio_url=payload.audio_url,
        transcription=payload.transcription,
        img_url=payload.img_url,
        img_desc=payload.img_desc,
        gender=payload.gender,
        examples=_to_examples(payload.examples),
    )
    db.add(word)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # TODO: every integrity error is currently reported as "already
        # saved". Inspect `exc.orig` to tell a duplicate from other violations.
        raise WordAlreadySavedError("Word already saved") from exc
    # No refresh: it would expire `examples` and the router would then
    # lazy-load them. The id and created_at come back from the INSERT.
    return word


async def update_word(db: AsyncSession, user_id: int, word_id: int, payload: WordUpdate) -> Word:
    """Apply a partial edit to one of the user's saved words.

    Only `defs`, `audio_url`, `img_url`, `img_desc` and `examples` can be
    edited. A field missing from the request is left unchanged. Sent as null
    (or an empty string), `audio_url`, `img_url` and `img_desc` are cleared,
    while `defs` and `examples` are left unchanged: a word always has
    definitions. `examples`, when given, replaces the whole list (an empty
    list removes every example).

    Changing `img_url` without sending `img_desc` clears the old description,
    which described the previous image.

    Raises:
        WordNotFoundError: the user has no saved word with this id.
    """
    word = await _get_owned_word(db, user_id, word_id)
    sent = payload.model_fields_set

    if payload.defs is not None:
        word.defs = payload.defs
    if "audio_url" in sent:
        word.audio_url = payload.audio_url
    if "img_url" in sent and payload.img_url != word.img_url:
        word.img_url = payload.img_url
        if "img_desc" not in sent:
            word.img_desc = None
    if "img_desc" in sent:
        word.img_desc = payload.img_desc
    if payload.examples is not None:
        # The old rows are deleted by cascade="all, delete-orphan" on
        # Word.examples (models.py), so reassigning the list is enough.
        word.examples = _to_examples(payload.examples)

    await db.commit()
    return word


async def delete_word(db: AsyncSession, user_id: int, word_id: int) -> None:
    """Delete one of the user's saved words, including its examples.

    Raises:
        WordNotFoundError: the user has no saved word with this id.
    """
    word = await _get_owned_word(db, user_id, word_id)
    await db.delete(word)
    await db.commit()


# --------------------------------------------------------------------------- #
# Saved vocabulary: reads
# --------------------------------------------------------------------------- #


async def get_vocabulary_page(
    db: AsyncSession,
    user_id: int,
    *,
    language: str,
    query: str | None,
    page: int,
    sort_by: VocabularySortBy,
    sort_order: SortOrder | None = None,
) -> VocabularyPage:
    """Return one page of the user's saved words in `language`.

    `page` is 1-based and pages hold `VOCABULARY_PAGE_SIZE` words. `query` is
    an optional search text; how it is matched is decided by
    `repository.get_vocabulary`. `total` counts every matching word across all
    pages, and `total_pages` is 0 when nothing matches.

    `sort_order` defaults to ascending for `name` and descending (newest
    first) for `created_at`.
    """
    items, total = await repository.get_vocabulary(
        db,
        user_id,
        language=language,
        query=query,
        page=page,
        page_size=VOCABULARY_PAGE_SIZE,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return VocabularyPage(
        items=[WordOut.model_validate(w) for w in items],
        page=page,
        page_size=VOCABULARY_PAGE_SIZE,
        total=total,
        total_pages=ceil(total / VOCABULARY_PAGE_SIZE) if total else 0,
    )


async def get_word_ids(
    db: AsyncSession,
    user_id: int,
    language: str,
    *,
    requires_audio: bool = False,
    requires_image: bool = False,
    requires_gender: bool = False,
) -> list[int]:
    """Return the ids of the user's saved words in `language`, in no particular order.

    Each `requires_*` flag, when True, restricts the result to words that have
    that field filled in: an audio URL, an image URL, or a grammatical gender.
    Flags that are False do not exclude anything.
    """
    return await repository.get_word_ids(
        db,
        user_id,
        language,
        requires_audio=requires_audio,
        requires_image=requires_image,
        requires_gender=requires_gender,
    )


@dataclass(frozen=True)
class WordSummary:
    """The fields of a saved word needed to compare it with others, nothing more."""

    id: int
    name: str
    stems: list[str]
    defs: list[str]


async def get_word_summaries(db: AsyncSession, user_id: int, word_ids: list[int]) -> list[WordSummary]:
    """Summaries of the user's saved words with these ids, in no particular order.

    Much lighter than `get_words_by_ids`: four columns and no examples, for
    when many words are compared and few are shown. Ids that do not exist or
    belong to another user are skipped.
    """
    rows = await repository.get_word_summary_rows(db, user_id, word_ids)
    return [WordSummary(*row) for row in rows]


async def get_words_by_ids(db: AsyncSession, user_id: int, word_ids: list[int]) -> list[Word]:
    """Load the user's saved words with these ids, in no particular order.

    Ids that do not exist or belong to another user are skipped.
    """
    return await repository.get_words_by_ids(db, user_id, word_ids)


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


async def _get_owned_word(db: AsyncSession, user_id: int, word_id: int) -> Word:
    """Load a saved word together with its examples.

    Raises:
        WordNotFoundError: no such word, or it belongs to another user.
    """
    word = await repository.get_word(db, user_id, word_id)
    if word is None:
        raise WordNotFoundError("Word not found")
    return word


def _to_examples(items) -> list[Example]:
    """Build new `Example` rows from schema objects with `text` and `translation`."""
    return [Example(text=e.text, translation=e.translation) for e in items]

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
from math import ceil

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dictionary.base import SearchResult
from dictionary.providers import PROVIDERS
from words.models import Example, Word
from words.repository import get_saved_uuids, get_vocabulary
from words.schemas import (
    VocabularyPage,
    VocabularySortBy,
    WordCreate,
    WordOut,
    WordUpdate,
)

__all__ = [
    "WordsError",
    "UnsupportedLanguageError",
    "DefinitionNotFoundError",
    "WordNotFoundError",
    "WordAlreadySavedError",
    "VOCABULARY_PAGE_SIZE",
    "search_words",
    "save_word",
    "update_word",
    "delete_word",
    "get_vocabulary_page",
    "get_random_words",
    "count_words",
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


class WordNotFoundError(WordsError):
    """The user has no saved word with the given id."""


class WordAlreadySavedError(WordsError):
    """Saving the word violated a uniqueness constraint."""


# --------------------------------------------------------------------------- #
# Dictionary search
# --------------------------------------------------------------------------- #

async def search_words(
    db: AsyncSession, user_id: int, *, query: str, language: str
) -> SearchResult:
    """Look `query` up in the dictionary for `language`.

    Each returned word has `saved=True` if the user already has a saved word
    with the same dictionary uuid. Words the dictionary returns without a uuid
    are never marked as saved.

    A non-empty response that contains no words (for example, spelling
    suggestions) is a normal result and is returned unchanged.

    Raises:
        UnsupportedLanguageError: there is no provider for `language`.
        DefinitionNotFoundError: the dictionary returned nothing at all.
    """
    provider = PROVIDERS.get(language)
    if provider is None:
        raise UnsupportedLanguageError(f"Unsupported language: {language}")

    results = await provider.fetch(query)
    if not results:
        raise DefinitionNotFoundError("Word not found")
    if not results.words:
        return results

    uuids = [w.uuid for w in results.words if w.uuid]
    saved_uuids = await get_saved_uuids(db, user_id, uuids)
    words = [
        WordOut.model_validate(w).model_copy(update={"saved": w.uuid in saved_uuids})
        for w in results.words
    ]
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


async def update_word(
    db: AsyncSession, user_id: int, word_id: int, payload: WordUpdate
) -> Word:
    """Apply a partial edit to one of the user's saved words.

    Only `defs`, `audio_url`, `img_url` and `examples` can be edited. A field
    that is `None` in `payload` is left unchanged, so these edits cannot set
    `defs`, `audio_url` or `img_url` back to `None`. `examples`, when given,
    replaces the whole list (an empty list removes every example).

    Raises:
        WordNotFoundError: the user has no saved word with this id.
    """
    word = await _get_owned_word(db, user_id, word_id)

    if payload.defs is not None:
        word.defs = payload.defs
    if payload.audio_url is not None:
        word.audio_url = payload.audio_url
    if payload.img_url is not None:
        word.img_url = payload.img_url
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
) -> VocabularyPage:
    """Return one page of the user's saved words in `language`.

    `page` is 1-based and pages hold `VOCABULARY_PAGE_SIZE` words. `query` is
    an optional search text; how it is matched is decided by
    `repository.get_vocabulary`. `total` counts every matching word across all
    pages, and `total_pages` is 0 when nothing matches.
    """
    items, total = await get_vocabulary(
        db,
        user_id,
        language=language,
        query=query,
        page=page,
        page_size=VOCABULARY_PAGE_SIZE,
        sort_by=sort_by,
    )
    return VocabularyPage(
        items=[WordOut.model_validate(w) for w in items],
        page=page,
        page_size=VOCABULARY_PAGE_SIZE,
        total=total,
        total_pages=ceil(total / VOCABULARY_PAGE_SIZE) if total else 0,
    )


async def get_random_words(
    db: AsyncSession,
    user_id: int,
    language: str,
    limit: int,
    *,
    requires_audio: bool = False,
    requires_image: bool = False,
    requires_gender: bool = False,
) -> list[Word]:
    """Pick up to `limit` of the user's saved words in `language`, at random.

    Each `requires_*` flag, when True, restricts the pool to words that have
    that field filled in: an audio URL, an image URL, or a grammatical gender.
    Flags that are False do not exclude anything.

    Returns fewer than `limit` words when fewer match. Use `count_words` with
    the same arguments to find out beforehand.
    """
    query = (
        select(Word)
        .options(selectinload(Word.examples))
        .where(Word.user_id == user_id, Word.language == language)
    )
    query = _require_fields(
        query, requires_audio=requires_audio, requires_image=requires_image, requires_gender=requires_gender
    )
    # random() sorts every matching row, which is fine for a personal
    # vocabulary. Revisit if lists grow to tens of thousands of words.
    query = query.order_by(func.random()).limit(limit)
    result = await db.scalars(query)
    return list(result.all())


async def count_words(
    db: AsyncSession,
    user_id: int,
    language: str,
    *,
    requires_audio: bool = False,
    requires_image: bool = False,
    requires_gender: bool = False,
) -> int:
    """Count the user's saved words in `language` that match the filters.

    The flags mean the same as in `get_random_words`.
    """
    query = (
        select(func.count())
        .select_from(Word)
        .where(Word.user_id == user_id, Word.language == language)
    )
    query = _require_fields(
        query, requires_audio=requires_audio, requires_image=requires_image, requires_gender=requires_gender
    )
    return await db.scalar(query) or 0


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #

async def _get_owned_word(db: AsyncSession, user_id: int, word_id: int) -> Word:
    """Load a saved word together with its examples.

    Raises:
        WordNotFoundError: no such word, or it belongs to another user.
    """
    word = await db.scalar(
        select(Word)
        .options(selectinload(Word.examples))
        .where(Word.id == word_id, Word.user_id == user_id)
    )
    if word is None:
        raise WordNotFoundError("Word not found")
    return word


def _to_examples(items) -> list[Example]:
    """Build new `Example` rows from schema objects with `text` and `translation`."""
    return [Example(text=e.text, translation=e.translation) for e in items]


def _require_fields(
    query: Select, *, requires_audio: bool, requires_image: bool, requires_gender: bool
) -> Select:
    """Narrow a query on `Word` to rows where each requested field is set."""
    if requires_audio:
        query = query.where(Word.audio_url.is_not(None))
    if requires_image:
        query = query.where(Word.img_url.is_not(None))
    if requires_gender:
        query = query.where(Word.gender.is_not(None))
    return query
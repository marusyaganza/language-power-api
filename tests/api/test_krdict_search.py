# tests/api/test_krdict_search.py
"""Searching the imported Korean dictionary in the database.

The rows are made up for these tests. The provider opens its own sessions,
so its tests hand it the test session instead.
"""

import unicodedata
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.exc import OperationalError

from dictionary.base import DictionaryError
from dictionary.ko import ko
from dictionary.ko.ko import KoreanDictionaryProvider
from dictionary.ko.models import KrdictEntry
from dictionary.ko.repository import find_entries, suggest_words

pytestmark = pytest.mark.anyio


def entry(key, word, *, homonym_number=0, level=None, forms=()):
    return KrdictEntry(
        key=key,
        id=int(key.split(":")[0]),
        word=word,
        unit="단어" if ":" not in key else "관용구",
        homonym_number=homonym_number,
        pos="명사",
        level=level,
        forms=list(forms),
        senses=[{"en": f"made-up meaning of {word}", "en_def": None, "examples": []}],
    )


@pytest.fixture
async def words(db):
    db.add_all(
        [
            entry("1", "가다", homonym_number=2, forms=["가", "가서"]),
            entry("2", "가다", homonym_number=1, forms=["가", "갔다"]),
            # Sorts after 가다 by homonym number and key; first only as the exact match.
            entry("3", "가", homonym_number=1, level="고급"),
            entry("4", "가게", level="초급"),
            entry("5", "가계", level="고급"),
            entry("6:눈(이) 높다", "눈(이) 높다", forms=["눈이 높다", "눈 높다"]),
        ]
    )
    await db.flush()


@pytest.fixture
def provider(db, monkeypatch):
    @asynccontextmanager
    async def test_session():
        yield db

    monkeypatch.setattr(ko, "AsyncSessionLocal", test_session)
    return KoreanDictionaryProvider()


async def test_homonyms_come_in_dictionary_order(db, words):
    assert [(r["key"], r["homonym_number"]) for r in await find_entries(db, "가다")] == [("2", 1), ("1", 2)]


async def test_a_word_is_found_by_its_forms_after_words_written_that_way(db, words):
    assert [r["key"] for r in await find_entries(db, "가")] == ["3", "2", "1"]
    assert [r["key"] for r in await find_entries(db, "가서")] == ["1"]
    assert [r["key"] for r in await find_entries(db, "눈 높다")] == ["6:눈(이) 높다"]


async def test_suggestions_count_letters_so_a_one_letter_typo_in_a_short_word_is_close(db, words):
    # 가개 vs 가게: one vowel apart. Compared by syllables they share too
    # little to count as similar; compared by letters they do.
    suggestions = await suggest_words(db, "가개")

    assert "가게" in suggestions
    assert len(suggestions) == len(set(suggestions))


async def test_the_provider_returns_entries_or_else_suggestions(provider, words):
    found = await provider.fetch("가게")
    typo = await provider.fetch("가개")

    assert ([w.uuid for w in found.words], found.suggestions) == (["4"], [])
    assert typo.words == [] and "가게" in typo.suggestions


async def test_a_decomposed_query_finds_the_word(provider, words):
    # Some keyboards send each syllable as separate letters.
    result = await provider.fetch(unicodedata.normalize("NFD", " 가게 "))

    assert [w.uuid for w in result.words] == ["4"]


async def test_an_empty_query_returns_nothing_without_querying(provider, monkeypatch):
    monkeypatch.setattr(ko, "AsyncSessionLocal", None)  # would fail if used

    assert (await provider.fetch("  ")).is_empty


async def test_a_database_failure_is_a_dictionary_error(monkeypatch):
    async def failing(*args):
        raise OperationalError("SELECT", {}, Exception("connection refused"))

    monkeypatch.setattr(ko, "find_entries", failing)

    with pytest.raises(DictionaryError, match="OperationalError"):
        await KoreanDictionaryProvider().fetch("가게")

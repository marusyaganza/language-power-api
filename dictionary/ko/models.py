"""Tables for the Korean dictionary, which is imported data rather than an API.

The data is the Korean Learners' Dictionary (한국어기초사전) of the National
Institute of Korean Language, CC BY-SA 2.0 KR. The import script fills these
tables from its XML download; the Korean provider only reads them.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base

# The kinds of entry (the dictionary's `lexicalUnit`): word, phrase or
# compound, idiom, proverb, grammar pattern. The last one is spelled with
# U+2027 (‧), as in the download.
UNITS = ("단어", "구", "관용구", "속담", "문법‧표현")


class KrdictEntry(Base):
    """One headword with its English meanings. Never edited by the app.

    `senses` holds the meanings in dictionary order, each
    `{"en": "shop; store", "en_def": "A place where...", "examples": ["과일 가게.", ...]}`.
    For a grammar pattern, `en` is only a romanization ("-geodeunnyo"); the
    meaning is in `en_def`.
    """

    __tablename__ = "krdict_entries"
    __table_args__ = (
        CheckConstraint("level IN ('초급', '중급', '고급')", name="ck_krdict_entries_level"),
        CheckConstraint("unit IN ({})".format(", ".join(f"'{u}'" for u in UNITS)), name="ck_krdict_entries_unit"),
        # Suggestions for misspelled queries (similarity search, pg_trgm).
        Index("ix_krdict_entries_word_trgm", "word", postgresql_using="gin", postgresql_ops={"word": "gin_trgm_ops"}),
        # Lookups by another way of writing the headword (`query = ANY(forms)`).
        Index("ix_krdict_entries_forms", "forms", postgresql_using="gin"),
    )

    # Unique and stable across releases: the id for a single word ("16391"),
    # the id and headword for anything else ("16391:가난이 죄다"), since idioms
    # and proverbs share the id of the word they're built on.
    key: Mapped[str] = mapped_column(primary_key=True)
    # The dictionary's own entry id; not unique (see `key`), not generated here.
    id: Mapped[int] = mapped_column(index=True, autoincrement=False)
    word: Mapped[str] = mapped_column(index=True)
    unit: Mapped[str]  # kind of entry, one of UNITS
    homonym_number: Mapped[int] = mapped_column(server_default="0")  # 0: the word has no homonyms
    pos: Mapped[str]  # part of speech, in Korean (명사, 동사, ...); 품사 없음 (none) for most non-words
    level: Mapped[str | None]  # 초급 / 중급 / 고급 (beginner / intermediate / advanced)
    pronunciation: Mapped[str | None]  # in Hangul, e.g. 가ː게
    # Other ways of writing the headword, to search by: conjugated and
    # contracted forms, and spellings of idioms and proverbs without their
    # optional or alternative parts.
    forms: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    senses: Mapped[list[dict]] = mapped_column(JSONB)


class DictionaryImport(Base):
    """One run of a dictionary import: which release the tables hold, and since when."""

    __tablename__ = "dictionary_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]  # "krdict"
    release: Mapped[str]  # the source's release date, e.g. "2026-06-19"
    commit: Mapped[str | None]  # the mirror commit the files came from, if any
    file_hashes: Mapped[dict] = mapped_column(JSONB)  # file name -> SHA-256
    entries: Mapped[int]
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

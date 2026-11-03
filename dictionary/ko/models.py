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


class KrdictEntry(Base):
    """One headword with its English meanings. Never edited by the app.

    `senses` holds the meanings in dictionary order, each
    `{"en": "shop; store", "en_def": "A place where...", "examples": ["과일 가게.", ...]}`.
    """

    __tablename__ = "krdict_entries"
    __table_args__ = (
        CheckConstraint("level IN ('초급', '중급', '고급')", name="ck_krdict_entries_level"),
        # Suggestions for misspelled queries (similarity search, pg_trgm).
        Index("ix_krdict_entries_word_trgm", "word", postgresql_using="gin", postgresql_ops={"word": "gin_trgm_ops"}),
        # Lookups by a conjugated form (`query = ANY(forms)`).
        Index("ix_krdict_entries_forms", "forms", postgresql_using="gin"),
    )

    # The dictionary's own entry id, stable across releases; not generated here.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    word: Mapped[str] = mapped_column(index=True)
    homonym_number: Mapped[int] = mapped_column(server_default="0")  # 0: the word has no homonyms
    pos: Mapped[str]  # part of speech, in Korean (명사, 동사, ...)
    level: Mapped[str | None]  # 초급 / 중급 / 고급 (beginner / intermediate / advanced)
    pronunciation: Mapped[str | None]  # in Hangul, e.g. 가ː게
    forms: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")  # conjugated forms
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

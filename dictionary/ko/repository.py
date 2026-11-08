"""Queries on the imported Korean dictionary. Read only: the import script writes."""

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dictionary.ko.models import KrdictEntry, decomposed

# What the provider formats an entry from; also the shape of the mock fixtures.
ENTRY_COLUMNS = (
    KrdictEntry.key,
    KrdictEntry.word,
    KrdictEntry.unit,
    KrdictEntry.homonym_number,
    KrdictEntry.pos,
    KrdictEntry.level,
    KrdictEntry.pronunciation,
    KrdictEntry.forms,
    KrdictEntry.senses,
)
MAX_ENTRIES = 20
MAX_SUGGESTIONS = 5


async def find_entries(db: AsyncSession, query: str) -> list[dict]:
    """Entries written `query`, then entries `query` is another form of (a conjugation, an idiom's variant).

    Homonyms come in the dictionary's order. A form can belong to several
    entries (가 is a word and a form of 가다), so both kinds are returned.
    """
    exact = KrdictEntry.word == query
    stmt = (
        select(*ENTRY_COLUMNS)
        # `@>` rather than `= ANY`: only containment uses the GIN index on forms.
        .where(or_(exact, KrdictEntry.forms.contains([query])))
        .order_by(exact.desc(), KrdictEntry.homonym_number, KrdictEntry.key)
        .limit(MAX_ENTRIES)
    )
    result = await db.execute(stmt)
    return [dict(row) for row in result.mappings()]


async def suggest_words(db: AsyncSession, query: str) -> list[str]:
    """Headwords spelled like `query`, closest first, each once.

    Compared letter by letter (`decomposed`), so a typo in one letter of a
    short word still counts as close. `%` is pg_trgm's "similar enough"
    (similarity above 0.3), which the index serves. Equally close words come
    easiest level first.
    """
    word, typed = decomposed(KrdictEntry.word), decomposed(literal(query))
    level_rank = case({"초급": 1, "중급": 2, "고급": 3}, value=KrdictEntry.level, else_=4)
    stmt = (
        select(KrdictEntry.word)
        .where(word.op("%")(typed))
        .group_by(KrdictEntry.word)
        .order_by(func.max(func.similarity(word, typed)).desc(), func.min(level_rank), KrdictEntry.word)
        .limit(MAX_SUGGESTIONS)
    )
    return list(await db.scalars(stmt))

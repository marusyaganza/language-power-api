"""Import the Korean Learners' Dictionary (한국어기초사전) into `krdict_entries`.

Run with `python -m dictionary.ko.import_krdict <folder> --release 2026-06-19 [--commit 009b480a]`,
with `DATABASE_URL` pointing at the database to fill. The folder holds the
dictionary's full XML download (`001.xml`, `002.xml`, ...), from the National
Institute of Korean Language or the GitHub mirror spellcheck-ko/korean-dict-nikl.
Safe to run again: entries are updated in place, and entries missing from the
release are deleted. Everything happens in one transaction, so the app sees
either the old release or the new one.

Every kind of entry is kept (words, phrases, idioms, proverbs, grammar
patterns) if it has an English meaning, without its media (pictures and
recordings are not openly licensed). The text is CC BY-SA 2.0 KR.
"""

import argparse
import asyncio
import hashlib
import itertools
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import String, all_, bindparam, delete, or_
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, engine
from dictionary.ko.models import UNITS, DictionaryImport, KrdictEntry

SOURCE = "krdict"
LEVELS = ("초급", "중급", "고급")
NO_PART_OF_SPEECH = "품사 없음"
MAX_EXAMPLES = 3  # per meaning: enough for a learner, and well within quotation
MAX_SPELLINGS = 32  # per headword; the longest proverbs combine several alternatives
BATCH_SIZE = 1000

# Control characters XML 1.0 doesn't allow. A few appear in the download (a
# backspace inside an Arabic translation), and a strict parser stops at them.
_INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Example kinds, most useful first: sentences, then short phrases. Dialogues
# (대화) are several lines from different speakers, so they're left out.
_EXAMPLE_KINDS = ("문장", "구")
# Headword notation in idioms and proverbs: a space-separated token, kept
# whole when it has a bracketed alternative with spaces ("한강에서[한강에 가서]").
_TOKEN = re.compile(r"\S*\[[^\]]*\]\S*|\S+")
_BRACKET = re.compile(r"(?P<base>[^\[]*)\[(?P<alternatives>[^\]]*)\](?P<rest>.*)")
_OPTIONAL = re.compile(r"\(([^)]*)\)")


class KrdictFormatError(ValueError):
    """The download isn't shaped as expected (an entry without id or word, a repeated key)."""


@dataclass
class ImportStats:
    entries: int = 0
    deleted: int = 0
    levels: Counter = field(default_factory=Counter)  # imported entries per level ("none" without one)
    skipped: Counter = field(default_factory=Counter)  # entries left out, per reason
    invalid_chars: int = 0  # characters removed before parsing


def read_entries(path: Path, stats: ImportStats) -> Iterator[dict]:
    """The `krdict_entries` rows in one XML file, in file order.

    The file is parsed in chunks, and each entry is cleared once read, so a
    35 MB file never sits in memory as a tree.
    """
    parser = ET.XMLPullParser(events=("end",))
    with path.open(encoding="utf-8") as file:
        while chunk := file.read(1 << 20):
            chunk, removed = _INVALID_XML_CHARS.subn("", chunk)
            stats.invalid_chars += removed
            parser.feed(chunk)
            for _, element in parser.read_events():
                if element.tag == "LexicalEntry":
                    row = _entry_row(element, stats)
                    element.clear()
                    if row is not None:
                        yield row
    parser.close()


def _entry_row(entry: ET.Element, stats: ImportStats) -> dict | None:
    """One entry as a row, or None (counted in `stats.skipped`) if it isn't kept."""
    if entry.get("att") != "id" or not (entry.get("val") or "").isdigit():
        raise KrdictFormatError(f"Entry without an id: {entry.attrib}")
    entry_id = int(entry.get("val"))
    feats = _feats(entry)

    unit = feats.get("lexicalUnit")
    if unit not in UNITS:  # a kind a later release might add
        stats.skipped[f"unknown kind {unit!r}"] += 1
        return None
    # A second Lemma, when there is one, only lists spelling variants.
    lemma = entry.find("Lemma")
    word = _feats(lemma).get("writtenForm") if lemma is not None else None
    if not word:
        raise KrdictFormatError(f"Entry {entry_id} has no word")

    senses = [sense for s in entry.findall("Sense") if (sense := _sense(s)) is not None]
    if not senses:
        stats.skipped["no English meaning"] += 1
        return None

    level = feats.get("vocabularyLevel")
    return {
        # Idioms and proverbs share the id of the word they're built on.
        "key": str(entry_id) if unit == "단어" else f"{entry_id}:{word}",
        "id": entry_id,
        "word": word,
        "unit": unit,
        "homonym_number": int(feats.get("homonym_number") or 0),
        "pos": feats.get("partOfSpeech") or NO_PART_OF_SPEECH,
        "level": level if level in LEVELS else None,  # 없음 (none) or missing
        "pronunciation": _pronunciation(entry),
        "forms": _forms(entry, word),
        "senses": senses,
    }


def _feats(element: ET.Element) -> dict[str, str]:
    """The element's own `<feat att=... val=...>` children, as a dict; empty values left out."""
    return {f.get("att"): f.get("val").strip() for f in element.findall("feat") if (f.get("val") or "").strip()}


def _sense(sense: ET.Element) -> dict | None:
    """A meaning with its English translation, or None if it has no English."""
    translations = (_feats(equivalent) for equivalent in sense.findall("Equivalent"))
    english = next((t for t in translations if t.get("language") == "영어"), {})
    if not english.get("lemma"):
        return None
    examples = []
    for kind in _EXAMPLE_KINDS:
        for example in sense.findall("SenseExample"):
            feats = _feats(example)
            if feats.get("type") == kind and feats.get("example"):
                examples.append(feats["example"])
    return {"en": english["lemma"], "en_def": english.get("definition"), "examples": examples[:MAX_EXAMPLES]}


def _pronunciation(entry: ET.Element) -> str | None:
    """The first pronunciation of the word itself (not of a conjugated form)."""
    for form in entry.findall("WordForm"):
        feats = _feats(form)
        if feats.get("type") == "발음" and feats.get("pronunciation"):
            return feats["pronunciation"]
    return None


def _forms(entry: ET.Element, word: str) -> list[str]:
    """Other ways of writing `word`, to search by, without repeats or the word itself.

    Conjugated forms (활용) and their contractions (준말), then the headword's
    spellings without its notation (`spellings`).
    """
    forms = []
    for form in entry.findall("WordForm"):
        if _feats(form).get("type") != "활용":
            continue
        for element in (form, *form.findall("FormRepresentation")):
            if written := _feats(element).get("writtenForm"):
                forms.append(written)
    forms.extend(spellings(word))
    return [form for form in dict.fromkeys(forms) if form != word]


def spellings(headword: str, *, keep_hyphens: bool = False) -> list[str]:
    """The ways to type `headword` without the dictionary's notation, at most MAX_SPELLINGS.

    - `(을)` is optional: with and without it (`진땀(을) 빼다`: 진땀을 빼다, 진땀 빼다).
    - `[B/C]` lists alternatives for the word just before it
      (`빼다[뽑다/흘리다]`: 빼다, 뽑다, 흘리다).
    - A leading or trailing `-` (grammar patterns, affixes) is left out
      (`-거든요`: 거든요), unless `keep_hyphens`.

    The first spelling keeps every optional part and the first alternative.
    """
    text = headword if keep_hyphens else headword.strip("-")
    choices = [_token_spellings(token) for token in _TOKEN.findall(text)]
    combined = (" ".join(parts) for parts in itertools.product(*choices))
    return list(itertools.islice(dict.fromkeys(combined), MAX_SPELLINGS))


def _token_spellings(token: str) -> list[str]:
    """One token's spellings: its bracketed alternatives, each with and without its optional parts."""
    match = _BRACKET.fullmatch(token)
    if match is None:
        written = [token]
    else:
        rests = _token_spellings(match["rest"]) if match["rest"] else [""]
        bases = [match["base"], *(a.strip() for a in match["alternatives"].split("/") if a.strip())]
        written = [base + rest for base in bases for rest in rests]
    return list(dict.fromkeys(spelling for text in written for spelling in _optional_spellings(text)))


def _optional_spellings(text: str) -> list[str]:
    """`text` with each `(...)` part both kept (without the parentheses) and left out."""
    match = _OPTIONAL.search(text)
    if match is None:
        return [text]
    before, after = text[: match.start()], text[match.end() :]
    return [spelling for middle in (match[1], "") for spelling in _optional_spellings(before + middle + after)]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


async def import_release(db: AsyncSession, files: list[Path], *, release: str, commit: str | None) -> ImportStats:
    """Replace the Korean dictionary with the entries in `files`, and record the import.

    Commits once, at the end.

    Raises:
        KrdictFormatError: an entry has no id or word, or two entries have the same key.
    """
    if not files:
        raise ValueError("No XML files to import")
    stats = ImportStats()
    seen: set[str] = set()
    batch: list[dict] = []
    for path in files:
        for row in read_entries(path, stats):
            if row["key"] in seen:
                raise KrdictFormatError(f"Entry {row['key']} appears twice")
            seen.add(row["key"])
            stats.entries += 1
            stats.levels[row["level"] or "none"] += 1
            batch.append(row)
            if len(batch) == BATCH_SIZE:
                await _upsert(db, batch)
                batch = []
    if batch:
        await _upsert(db, batch)

    # One array parameter rather than one per key: a release has ~55,000 keys,
    # and a statement can have at most 65,535 parameters.
    keys = bindparam("keys", list(seen), type_=ARRAY(String))
    result = await db.execute(delete(KrdictEntry).where(KrdictEntry.key != all_(keys)))
    stats.deleted = result.rowcount

    db.add(
        DictionaryImport(
            source=SOURCE,
            release=release,
            commit=commit,
            file_hashes={path.name: file_sha256(path) for path in files},
            entries=stats.entries,
        )
    )
    await db.commit()
    return stats


async def _upsert(db: AsyncSession, rows: list[dict]) -> None:
    """Insert new rows and update changed ones. Unchanged rows aren't written at all.

    Postgres keeps the old copy of every updated row until vacuumed, and the
    table's file doesn't shrink afterwards: rewriting all ~55,000 unchanged
    rows on each re-import made the table three times its size.
    """
    stmt = insert(KrdictEntry).values(rows)
    table = KrdictEntry.__table__
    columns = ("id", "word", "unit", "homonym_number", "pos", "level", "pronunciation", "forms", "senses")
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[KrdictEntry.key],
            set_={column: stmt.excluded[column] for column in columns},
            where=or_(*(table.c[column].is_distinct_from(stmt.excluded[column]) for column in columns)),
        )
    )


def release_date(value: str) -> str:
    """A YYYY-MM-DD date, kept as text. argparse names this function in its error message."""
    date.fromisoformat(value)
    return value


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import the Korean Learners' Dictionary into the database.")
    parser.add_argument("folder", type=Path, help="folder with the dictionary's XML files")
    parser.add_argument("--release", type=release_date, required=True, help="release date, e.g. 2026-06-19")
    parser.add_argument("--commit", help="the mirror commit the files came from")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = _arguments(argv)
    files = sorted(args.folder.glob("*.xml"))
    if not files:
        sys.exit(f"No .xml files in {args.folder}")

    started = time.monotonic()
    try:
        async with AsyncSessionLocal() as db:
            stats = await import_release(db, files, release=args.release, commit=args.commit)
    finally:
        await engine.dispose()

    print(f"Imported {stats.entries} entries from {len(files)} files in {time.monotonic() - started:.0f} s.")
    print("Per level: " + ", ".join(f"{level} {count}" for level, count in sorted(stats.levels.items())))
    print("Skipped: " + (", ".join(f"{reason} {count}" for reason, count in stats.skipped.items()) or "none"))
    print(f"Deleted (not in this release): {stats.deleted}. Invalid characters removed: {stats.invalid_chars}.")


if __name__ == "__main__":
    asyncio.run(main())

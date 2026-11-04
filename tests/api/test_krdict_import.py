# tests/api/test_krdict_import.py
"""Importing the Korean dictionary into the database: updates, deletions, the import record.

The XML is made up for these tests (see tests/unit/test_krdict_import.py).
"""

import hashlib

import pytest
from sqlalchemy import select, text

from dictionary.ko.import_krdict import KrdictFormatError, import_release
from dictionary.ko.models import DictionaryImport, KrdictEntry
from tests.unit.test_krdict_import import FOOTER, HEADER, english, entry, sense

pytestmark = pytest.mark.anyio


def write(folder, name, *entries):
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(HEADER + "".join(entries) + FOOTER, encoding="utf-8")
    return path


async def stored(db):
    rows = await db.scalars(select(KrdictEntry).order_by(KrdictEntry.key))
    return {row.key: (row.word, [s["en"] for s in row.senses]) for row in rows}


async def test_an_import_stores_every_file_and_records_the_release(db, tmp_path):
    files = [
        write(tmp_path, "001.xml", entry(1, "가게", sense(english("shop")))),
        write(tmp_path, "002.xml", entry(2, "나무", sense(english("tree")), level="중급")),
    ]

    stats = await import_release(db, files, release="2026-06-19", commit="009b480a")

    assert await stored(db) == {"1": ("가게", ["shop"]), "2": ("나무", ["tree"])}
    assert (stats.entries, stats.levels) == (2, {"초급": 1, "중급": 1})
    record = await db.scalar(select(DictionaryImport))
    assert (record.source, record.release, record.commit, record.entries) == ("krdict", "2026-06-19", "009b480a", 2)
    assert record.file_hashes == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


async def test_a_new_release_updates_entries_and_deletes_the_ones_it_no_longer_has(db, tmp_path):
    old = write(
        tmp_path / "old", "001.xml", entry(1, "가게", sense(english("shop"))), entry(2, "나무", sense(english("tree")))
    )
    await import_release(db, [old], release="2025-12-19", commit=None)

    new = write(
        tmp_path / "new", "001.xml", entry(1, "가게", sense(english("store"))), entry(3, "물", sense(english("water")))
    )
    stats = await import_release(db, [new], release="2026-06-19", commit=None)

    assert await stored(db) == {"1": ("가게", ["store"]), "3": ("물", ["water"])}
    assert stats.deleted == 1
    releases = await db.scalars(select(DictionaryImport.release).order_by(DictionaryImport.id))
    assert list(releases) == ["2025-12-19", "2026-06-19"]


async def test_importing_the_same_release_again_rewrites_no_row(db, tmp_path):
    # xmin is the transaction that last wrote the row; an update changes it.
    async def row_versions():
        rows = await db.execute(text("SELECT key, xmin::text FROM krdict_entries"))
        return dict(rows.all())

    path = write(
        tmp_path, "001.xml", entry(1, "가게", sense(english("shop"))), entry(2, "나무", sense(english("tree")))
    )
    await import_release(db, [path], release="2026-06-19", commit=None)
    before = await row_versions()

    await import_release(db, [path], release="2026-06-19", commit=None)

    assert await row_versions() == before


async def test_idioms_and_proverbs_are_stored_next_to_the_word_whose_id_they_share(db, tmp_path):
    # As in the download: an idiom has the id of the word it's built on.
    path = write(
        tmp_path,
        "001.xml",
        entry(1, "가게", sense(english("shop"))),
        entry(1, "가게(를) 보다", sense(english("mind the shop")), unit="관용구", pos=None, level=None, homonym=None),
        entry(1, "가게가 크다", sense(english("a made-up proverb")), unit="속담", pos=None, level=None, homonym=None),
    )

    await import_release(db, [path], release="2026-06-19", commit=None)

    assert await stored(db) == {
        "1": ("가게", ["shop"]),
        "1:가게(를) 보다": ("가게(를) 보다", ["mind the shop"]),
        "1:가게가 크다": ("가게가 크다", ["a made-up proverb"]),
    }


async def test_a_word_id_in_two_files_stops_the_import_and_changes_nothing(db, tmp_path):
    first = write(tmp_path, "001.xml", entry(1, "가게", sense(english("shop"))))
    second = write(tmp_path, "002.xml", entry(1, "나무", sense(english("tree"))))

    with pytest.raises(KrdictFormatError):
        await import_release(db, [first, second], release="2026-06-19", commit=None)
    await db.rollback()

    assert await stored(db) == {}
    assert await db.scalar(select(DictionaryImport)) is None

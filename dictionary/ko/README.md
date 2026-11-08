# Korean dictionary

Korean words come from the [Korean Learners' Dictionary (한국어기초사전)](https://krdict.korean.go.kr) of the National Institute of Korean Language: about 55,000 entries written for learners, each with English translations and definitions, and a level (초급 beginner, 중급 intermediate, 고급 advanced).

Unlike English and Spanish, Korean doesn't call an API. The dictionary has an Open API, but neither it nor the site is reachable through the VPN I use, and I don't go online without it while travelling. So its full download is imported into PostgreSQL and searched there, and searches don't depend on the site at all. Korean is in **beta**, on the private deployment only.

## Files

- `models.py`: the `krdict_entries` table (one row per entry) and `dictionary_imports` (one row per import: release, source commit, file hashes).
- `import_krdict.py`: reads the XML download into `krdict_entries`.
- `repository.py`: the searches, by headword, by another form of it, and spelling suggestions.
- `ko.py`: `KoreanDictionaryProvider`, which turns rows into `DictionaryEntry` objects.
- `mock.py`: the mock provider, which reads made-up rows from `dictionary/fixtures/ko/`.

## The data and its license

- **Source:** the dictionary's own "full download" (사전 전체 내려받기), XML, mirrored on GitHub at [spellcheck-ko/korean-dict-nikl](https://github.com/spellcheck-ko/korean-dict-nikl) (folder `krdict/`, 11 files of about 35 MB). The mirror belongs to the `spellcheck-ko` project and says it isn't run by the National Institute of Korean Language. Its [`update.py`](https://github.com/spellcheck-ko/korean-dict-nikl/blob/009b480a924c5c4b7ed83635769da6c519fc7ab3/krdict/update.py) only unzips the official download and renames its files (`1_5000_<date>.xml` becomes `001.xml`); the XML itself isn't changed. The release currently imported is 2026-06-19, mirror commit `009b480a`.
- **License:** the text is [CC BY-SA 2.0 KR](https://creativecommons.org/licenses/by-sa/2.0/kr/), as the dictionary's [copyright policy](https://krdict.korean.go.kr/kor/kboardPolicy/copyRightTermsInfo) says of everything on the site not marked otherwise: free to use, commercially too, with credit to the author, and adapted work under the same license. The client credits the dictionary wherever Korean entries are shown, and says they're adapted.
- **Not used:** the same policy says pictures, video, sound and pronunciation recordings have their own terms, set file by file. So they're neither imported nor linked.
- **Never in this repository:** the repository is MIT, so the data lives only in the databases. The fixtures in `dictionary/fixtures/ko/` are made up.

## What is imported

- Every kind of entry with an English meaning: words, phrases, idioms, proverbs and grammar patterns (`unit`). Entries without English (about 1,700) are left out.
- Per meaning: the short English translation (`en`), the English definition (`en_def`) and up to 3 Korean examples (sentences first, then phrases; dialogues are left out).
- `forms`: other ways the headword is written, so searches find them: conjugated and contracted forms, and idioms or proverbs without their notation (`진땀(을) 빼다[뽑다/흘리다]` is also found as 진땀 빼다, 진땀을 흘리다, ...).
- `key`: the entry's id for a single word, the id and headword for anything else (`16391:가난이 죄다`), because idioms and proverbs reuse the id of the word they're built on. Saved words keep it as their `uuid`.
- The import strips a few control characters the download contains (they stop an XML parser), and only rewrites rows that changed.

## Importing

The tables are created by the migrations; the data is loaded by hand, once per database:

```bash
# The XML files of one release, at a pinned commit of the mirror.
COMMIT=009b480a924c5c4b7ed83635769da6c519fc7ab3
mkdir -p ~/krdict-2026-06-19 && cd ~/krdict-2026-06-19
for n in 001 002 003 004 005 006 007 008 009 010 011; do
  curl -fsSO "https://raw.githubusercontent.com/spellcheck-ko/korean-dict-nikl/$COMMIT/krdict/$n.xml"
done

# Back in the repository, with DATABASE_URL pointing at the database to fill
# (local by default, from .env).
python -m dictionary.ko.import_krdict ~/krdict-2026-06-19 --release 2026-06-19 --commit 009b480a
```

It takes about half a minute, prints the entries per level and what it skipped, and runs in one transaction: the app sees the old release or the new one, never a mix. Running it again is safe. Without an import, Korean searches simply find nothing.

The table takes about 45 MB.

## Updating to a new release

The mirror is updated a few times a year; its commits are named after the release they contain.

1. Download the new files at the new commit (as above), and keep a copy outside the repository.
2. Import them locally and look at the summary: entries per level and skipped counts should be close to the last release's (54,870 entries; 1,685 skipped without English).
3. Search a few known words (가게, 나무, 가다) and an idiom (진땀 빼다).
4. Import into the private deployment's database: run the same command with that database's `DATABASE_URL`.
5. Update the release and commit at the top of this file.

Entries that a release removes are deleted. Words users already saved are copies and don't change.

## Search

- A query finds the entries written that way, then those it's another form of (가 finds the word 가, then 가다).
- When nothing matches, up to 5 spelling suggestions, compared letter by letter (`normalize(word, NFD)` with a pg_trgm index): a 2-syllable word has too few syllables for a one-letter typo to look similar otherwise.
- Queries are NFC-normalized, since some keyboards send Hangul decomposed.
- **Not yet:** conjugated forms the dictionary doesn't list (먹었어요 → 먹다). The dictionary lists only 3–4 forms per verb.

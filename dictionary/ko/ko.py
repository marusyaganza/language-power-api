"""Korean: the Korean Learners' Dictionary (한국어기초사전), imported into our database.

Unlike the other languages, it doesn't call an API: the dictionary's Open API
and site aren't reachable through the VPN I use (see README.md), so its full
download is imported (`python -m dictionary.ko.import_krdict`) and searched here.
"""

import unicodedata

from sqlalchemy.exc import SQLAlchemyError

from core.database import AsyncSessionLocal
from core.language import Language
from dictionary.base import DictionaryError, DictionaryProvider, SearchResult
from dictionary.entry import DictionaryEntry, DictionaryExample, unique_definitions
from dictionary.ko.import_krdict import spellings
from dictionary.ko.repository import find_entries, suggest_words

# Parts of speech in English. Values not listed are shown as they are.
PARTS_OF_SPEECH = {
    "명사": "noun",
    "동사": "verb",
    "형용사": "adjective",
    "부사": "adverb",
    "관형사": "determiner",
    "대명사": "pronoun",
    "수사": "numeral",
    "조사": "particle",
    "감탄사": "interjection",
    "의존 명사": "dependent noun",
    "보조 동사": "auxiliary verb",
    "보조 형용사": "auxiliary adjective",
    "어미": "ending",
    "접사": "affix",
    "품사 없음": "other",  # no part of speech
}
# Anything but a single word shows its kind instead: its part of speech is
# 품사 없음 (none) or missing.
KINDS = {"구": "phrase", "관용구": "idiom", "속담": "proverb", "문법‧표현": "grammar pattern"}
GRAMMAR = "문법‧표현"


class KoreanDictionaryProvider(DictionaryProvider):
    language = Language.KO

    async def _fetch_raw(self, query: str) -> dict:
        """The matching entries as rows, and spelling suggestions when none match.

        The query is NFC-normalized: the data is, and some keyboards send
        Hangul decomposed. The provider opens its own session, so `fetch`
        keeps the signature every provider has.
        """
        query = unicodedata.normalize("NFC", query.strip())
        if not query:
            return {"entries": [], "suggestions": []}
        try:
            async with AsyncSessionLocal() as db:
                entries = await find_entries(db, query)
                suggestions = [] if entries else await suggest_words(db, query)
        except SQLAlchemyError as exc:
            raise DictionaryError(f"Korean dictionary query failed: {type(exc).__name__}") from None
        return {"entries": entries, "suggestions": suggestions}

    def _parse(self, raw: dict) -> SearchResult:
        return SearchResult(words=[self._format(row) for row in raw["entries"]], suggestions=raw["suggestions"])

    def _format(self, row: dict) -> DictionaryEntry:
        senses = row["senses"]
        grammar = row["unit"] == GRAMMAR
        return DictionaryEntry(
            uuid=row["key"],
            name=_name(row["word"]),
            language=self.language,
            fl=KINDS.get(row["unit"]) or PARTS_OF_SPEECH.get(row["pos"], row["pos"]),
            # The headword as the dictionary writes it, for hiding the word in hints.
            stems=list(dict.fromkeys([row["word"], *row["forms"]])),
            # A grammar pattern's short English is only a romanization ("-geodeunnyo").
            defs=unique_definitions([(s.get("en_def") or s["en"]) if grammar else s["en"] for s in senses]),
            transcription=senses[0]["en"] if grammar else row["pronunciation"],
            examples=[DictionaryExample(text=text) for s in senses for text in s["examples"]],
        )


def _name(headword: str) -> str:
    """The headword as one can type it: `진땀(을) 빼다[뽑다/흘리다]` becomes 진땀을 빼다.

    Idioms and proverbs mark optional parts and alternatives, which nobody
    would type in a game; the first spelling keeps the optional parts and the
    first alternative. The others stay searchable (the entry's forms).
    """
    return spellings(headword, keep_hyphens=True)[0]

"""The base for every language served by a Merriam-Webster reference.

It holds what all MW references share; a subclass per language sets its API
URL, key and audio path, and adds the fields only its reference has.
"""

from abc import abstractmethod
from typing import Any

from dictionary.base import DictionaryProvider, SearchResult
from dictionary.entry import DictionaryEntry, unique_definitions
from dictionary.merriam_webster.api import (
    extract_audio,
    extract_definitions,
    extract_examples,
    fetch_entries,
    format_entries,
    format_name,
    is_suggestion_response,
)


class MerriamWebsterProvider(DictionaryProvider):
    api_url: str
    # Country code in MW's audio URLs ("us", or "me" for Spanish).
    audio_country: str

    @abstractmethod
    def _api_key(self) -> str:
        """This reference's key; each MW reference has its own."""

    def _keep(self, raw_items: list) -> list:
        """The entries to show, before parsing. All of them unless overridden."""
        return raw_items

    def _extra_fields(self, entry: dict) -> dict[str, Any]:
        """`DictionaryEntry` fields only this language's reference provides."""
        return {}

    async def _fetch_raw(self, query: str) -> list:
        return await fetch_entries(self.api_url, self._api_key(), query)

    def _parse(self, raw: list) -> SearchResult:
        if is_suggestion_response(raw):
            return SearchResult(suggestions=raw)
        return SearchResult(words=format_entries(self._keep(raw), self._format))

    def _format(self, entry: dict) -> DictionaryEntry:
        meta = entry["meta"]
        return DictionaryEntry(
            uuid=meta["uuid"],
            name=format_name(entry),
            language=self.language,
            fl=entry.get("fl", ""),  # cross-reference entries have none
            stems=meta["stems"],
            defs=unique_definitions(extract_definitions(entry)),
            audio_url=extract_audio(entry, self.language, self.audio_country),
            examples=extract_examples(entry),
            **self._extra_fields(entry),
        )

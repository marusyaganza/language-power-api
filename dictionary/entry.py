"""What a dictionary lookup returns, whichever dictionary answered it."""

from dataclasses import dataclass, field

from words.language import Language


@dataclass(frozen=True)
class DictionaryExample:
    text: str
    translation: str | None = None


@dataclass(frozen=True)
class DictionaryEntry:
    """One entry of a dictionary response. Saving it is up to the user.

    What every provider must fill in, whatever its API calls it:

    * `uuid`: the API's own id for the entry, stable across searches. Saved
      words are matched to search results by it.
    * `defs`: meanings in English, whatever the language; the games rely on it.
    * `fl`: the part of speech, shown as is.
    * `stems`: forms of the word, used to hide it in hints; may be empty.
    * `gender`: only for languages with grammatical gender.
    """

    uuid: str
    name: str
    language: Language
    fl: str  # part of speech
    stems: list[str]
    defs: list[str]
    audio_url: str | None = None
    transcription: str | None = None
    img_url: str | None = None
    img_desc: str | None = None  # caption of img_url
    examples: list[DictionaryExample] = field(default_factory=list)
    gender: str | None = None  # "masculine" | "feminine" | "both" | None


def unique_definitions(defs: list[str]) -> list[str]:
    """Strip each definition and drop repeats, keeping the first of each.

    Definitions that differ only in case or spacing count as repeats. The
    dictionary returns some (e.g. "ser": "to be" three times).
    """
    seen = set()
    result = []
    for definition in defs:
        definition = definition.strip()
        key = " ".join(definition.lower().split())
        if key not in seen:
            seen.add(key)
            result.append(definition)
    return result

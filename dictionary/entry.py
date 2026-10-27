"""What a dictionary lookup returns, whichever dictionary answered it."""

from dataclasses import dataclass, field

from words.language import Language


@dataclass(frozen=True)
class DictionaryExample:
    text: str
    translation: str | None = None


@dataclass(frozen=True)
class DictionaryEntry:
    """One entry of a dictionary response. Saving it is up to the user."""

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

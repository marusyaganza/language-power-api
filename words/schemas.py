from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, field_validator

from core.language import Language
from dictionary.entry import unique_definitions

# Limits on what a client can store, in characters (or items, for lists). They
# keep one account from filling the database; real dictionary entries are far
# below them (checked 2026-10-28 against the recorded entries: names up to 25
# characters, definitions 307, examples 243, at most 9 stems and 3
# definitions). Only input is checked: words already stored are returned as
# they are.
MAX_NAME_LENGTH = 100
MAX_UUID_LENGTH = 64
MAX_FL_LENGTH = 100
MAX_STEMS = 100  # common words have dozens of inflected forms
MAX_STEM_LENGTH = 100
MAX_DEFINITIONS = 10
MAX_DEFINITION_LENGTH = 1000
MAX_EXAMPLES = 50
MAX_EXAMPLE_LENGTH = 500  # the text and the translation each
MAX_TRANSCRIPTION_LENGTH = 100
MAX_IMG_DESC_LENGTH = 1000
MAX_URL_LENGTH = 2048
# The search text of /words/search and /words/vocabulary.
MAX_QUERY_LENGTH = 100


def _empty_str_to_none(value):
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _web_url(value: str | None) -> str | None:
    # The frontend puts these in <audio src> and <img src>: no javascript:,
    # data: or other schemes.
    if value is not None and not value.lower().startswith(("http://", "https://")):
        raise ValueError("Must be an http:// or https:// URL")
    return value


OptionalStr = Annotated[str | None, BeforeValidator(_empty_str_to_none)]
OptionalUrl = Annotated[str | None, BeforeValidator(_empty_str_to_none), AfterValidator(_web_url)]
# "both": the noun takes either gender (el/la ecologista).
Gender = Literal["masculine", "feminine", "both"]
OptionalGender = Annotated[Gender | None, BeforeValidator(_empty_str_to_none)]
Definition = Annotated[str, Field(max_length=MAX_DEFINITION_LENGTH)]
Stem = Annotated[str, Field(max_length=MAX_STEM_LENGTH)]


class ExampleItem(BaseModel):
    text: str
    translation: OptionalStr = None
    model_config = {"from_attributes": True}


class ExampleIn(BaseModel):
    """An example sent by the client, for a new word or an edit."""

    text: str = Field(max_length=MAX_EXAMPLE_LENGTH)
    translation: OptionalStr = Field(default=None, max_length=MAX_EXAMPLE_LENGTH)


class WordCreate(BaseModel):
    uuid: str | None = Field(default=None, max_length=MAX_UUID_LENGTH)
    name: str = Field(max_length=MAX_NAME_LENGTH)
    language: Language
    stems: list[Stem] = Field(default=[], max_length=MAX_STEMS)
    defs: list[Definition] = Field(min_length=1, max_length=MAX_DEFINITIONS)
    fl: str = Field(max_length=MAX_FL_LENGTH)
    audio_url: OptionalUrl = Field(default=None, max_length=MAX_URL_LENGTH)
    transcription: OptionalStr = Field(default=None, max_length=MAX_TRANSCRIPTION_LENGTH)
    img_url: OptionalUrl = Field(default=None, max_length=MAX_URL_LENGTH)
    img_desc: OptionalStr = Field(default=None, max_length=MAX_IMG_DESC_LENGTH)
    gender: OptionalGender = None
    offensive: bool = False
    examples: list[ExampleIn] = Field(default=[], max_length=MAX_EXAMPLES)

    @field_validator("defs")
    @classmethod
    def defs_must_be_non_blank(cls, value: list[str]) -> list[str]:
        cleaned = [d.strip() for d in value]
        if any(not d for d in cleaned):
            raise ValueError("Definitions cannot be empty or blank")
        return unique_definitions(cleaned)


class WordOut(BaseModel):
    id: int | None = None
    uuid: str | None = None
    name: str
    language: str
    stems: list[str]
    defs: list[str] = Field(min_length=1)
    fl: str
    audio_url: OptionalStr
    transcription: OptionalStr
    img_url: OptionalStr
    img_desc: OptionalStr
    examples: list[ExampleItem]
    saved: bool = False
    gender: Gender | None = None
    offensive: bool = False

    model_config = {"from_attributes": True}


class VocabularySortBy(str, Enum):
    created_at = "created_at"
    name = "name"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class VocabularyPage(BaseModel):
    items: list[WordOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class WordUpdate(BaseModel):
    defs: list[Definition] | None = Field(default=None, min_length=1, max_length=MAX_DEFINITIONS)
    examples: list[ExampleIn] | None = Field(default=None, max_length=MAX_EXAMPLES)
    audio_url: OptionalUrl = Field(default=None, max_length=MAX_URL_LENGTH)
    img_url: OptionalUrl = Field(default=None, max_length=MAX_URL_LENGTH)
    img_desc: OptionalStr = Field(default=None, max_length=MAX_IMG_DESC_LENGTH)

    @field_validator("defs")
    @classmethod
    def defs_must_be_non_blank(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("Definitions must contain at least one non-empty string")
        return unique_definitions(cleaned)


class WordSearchResponse(BaseModel):
    words: list[WordOut]
    suggestions: list[str] = []  # spelling suggestions from the dictionary
    # Mock mode only, when the query has no mock data: the queries that do.
    mock_queries: list[str] = []

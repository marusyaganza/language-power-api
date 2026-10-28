from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, field_validator

from core.language import Language
from dictionary.entry import unique_definitions


def _empty_str_to_none(value):
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


OptionalStr = Annotated[str | None, BeforeValidator(_empty_str_to_none)]
# "both": the noun takes either gender (el/la ecologista).
Gender = Literal["masculine", "feminine", "both"]
OptionalGender = Annotated[Gender | None, BeforeValidator(_empty_str_to_none)]


class ExampleItem(BaseModel):
    text: str
    translation: OptionalStr = None
    model_config = {"from_attributes": True}


class WordCreate(BaseModel):
    uuid: str | None = None
    name: str
    language: Language
    stems: list[str] = []
    defs: list[str] = Field(min_length=1)
    fl: str
    audio_url: OptionalStr = None
    transcription: OptionalStr = None
    img_url: OptionalStr = None
    img_desc: OptionalStr = None
    gender: OptionalGender = None
    offensive: bool = False
    examples: list[ExampleItem] = []

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


class ExampleUpdate(BaseModel):
    text: str
    translation: OptionalStr = None


class WordUpdate(BaseModel):
    defs: list[str] | None = Field(default=None, min_length=1)
    examples: list[ExampleUpdate] | None = None
    audio_url: OptionalStr = None
    img_url: OptionalStr = None
    img_desc: OptionalStr = None

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

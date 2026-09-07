from pydantic import BaseModel, Field, field_validator
from enum import Enum

class ExampleCreate(BaseModel):
    text: str
    translation: str


class WordCreate(BaseModel):
    uuid: str | None = None
    name: str
    language: str
    stems: list[str] = []
    defs: list[str] = Field(min_length=1)
    fl: str
    audio_url: str | None = None
    transcription: str | None = None
    img_url: str | None = None
    gender: str | None = None
    examples: list[ExampleCreate] = []

    @field_validator("defs")
    @classmethod
    def defs_must_be_non_blank(cls, value: list[str]) -> list[str]:
        cleaned = [d.strip() for d in value]
        if any(not d for d in cleaned):
            raise ValueError("Definitions cannot be empty or blank")
        return cleaned


class ExampleOut(BaseModel):
    text: str
    translation: str

    model_config = {"from_attributes": True}


class WordOut(BaseModel):
    id: int | None = None
    uuid: str | None = None
    name: str
    language: str
    stems: list[str]
    defs: list[str] = Field(min_length=1)
    fl: str
    audio_url: str | None
    transcription: str | None
    img_url: str | None
    examples: list[ExampleOut]
    saved: bool = False
    gender: str | None = None

    model_config = {"from_attributes": True}

class VocabularySortBy(str, Enum):
    created_at = "created_at"
    name = "name"


class VocabularyPage(BaseModel):
    items: list[WordOut]
    page: int
    page_size: int
    total: int
    total_pages: int

class ExampleUpdate(BaseModel):
    text: str
    translation: str


class WordUpdate(BaseModel):
    defs: list[str] | None = Field(default=None, min_length=1)
    examples: list[ExampleUpdate] | None = None
    audio_url: str | None = None
    img_url: str | None = None

    @field_validator("defs")
    @classmethod
    def defs_must_be_non_blank(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned = [d.strip() for d in value]
        if any(not d for d in cleaned):
            raise ValueError("Definitions cannot be empty or blank")
        return cleaned

class WordSearchResponse(BaseModel):
    words: list[WordOut]
    suggestions: list[str] = []
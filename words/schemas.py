from pydantic import BaseModel


class ExampleCreate(BaseModel):
    text: str
    translation: str


class WordCreate(BaseModel):
    uuid: str | None = None
    name: str
    language: str
    stems: list[str] = []
    defs: list[str] = []
    fl: str
    audio_url: str | None = None
    transcription: str | None = None
    img_url: str | None = None
    examples: list[ExampleCreate] = []


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
    defs: list[str]
    fl: str
    audio_url: str | None
    transcription: str | None
    img_url: str | None
    examples: list[ExampleOut]
    saved: bool = False

    model_config = {"from_attributes": True}
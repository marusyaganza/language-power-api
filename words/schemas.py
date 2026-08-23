from pydantic import BaseModel

from word.language import Language

class WordOut(BaseModel):
    model_config = {"from_attributes": True}
    name: str
    stems: list[str]
    defs: list[str]
    language: Language
    uuid: str
    fl: str
    audio_url: str
    transcription:str
from pydantic import BaseModel

from words.language import Language
from words.example import Example

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
    examples: list[Example]
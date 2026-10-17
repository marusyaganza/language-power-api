from words.language import Language
from words.example import Example
import json


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

class Word: 
    name: str
    stems: list[str]
    defs: list[str]
    language: Language
    uuid: str
    fl: str
    audio_url: str | None
    transcription:str
    img_url: str | None
    examples: list[Example]
    gender: str | None

    def __init__(self, *, name, defs, language, stems, uuid, fl, audio_url=None, transcription=None, examples=[], img_url=None, gender=None):
        self.name = name
        self.stems = stems
        self.defs = defs
        self.language = language
        self.uuid = uuid
        self.fl = fl
        self.audio_url = audio_url
        self.transcription = transcription
        self.examples = examples
        self.img_url = img_url
        self.gender = gender
    def __repr__(self):
        # data = {k:v for k,v in self.__dict__.items()}
        return json.dumps(self.__dict__)

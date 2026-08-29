from words.language import Language
from words.example import Example
import json

class Word: 
    name: str
    stems: list[str]
    defs: list[str]
    language: Language
    uuid: str
    fl: str
    audio_url: str
    transcription:str
    img_url: str
    examples: list[Example]

    def __init__(self, *, name, defs, language, stems, uuid, fl, audio_url='', transcription='', examples=[], img_url=''):
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
    def __repr__(self):
        # data = {k:v for k,v in self.__dict__.items()}
        return json.dumps(self.__dict__)

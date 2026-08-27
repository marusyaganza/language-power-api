from words.language import Language
import json

class Word: 
    def __init__(self, *, name, defs, language, stems, uuid, fl, audio_url, transcription='', examples=[]):
        self.name = name
        self.stems = stems
        self.defs = defs
        self.language = language
        self.uuid = uuid
        self.fl = fl
        self.audio_url = audio_url
        self.transcription = transcription
        self.examples = examples
    def __repr__(self):
        # data = {k:v for k,v in self.__dict__.items()}
        return json.dumps(self.__dict__)

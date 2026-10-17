import re
from words.example import Example
from settings import settings

import re

TAG_RE = re.compile(r'\{[^}]*\}')

def strip_mw_markup(raw: str) -> str:
    return TAG_RE.sub('', raw).strip()

def extract_examples(data):
    sseq = data.get('def')[0].get('sseq')[0]
    examples = [] 
    for item in sseq:
        dt = item[1].get('dt')
        if not dt:
            continue
        for d in dt:
            if 'vis' in d:
                examples.extend(d[1])
    return [_format_example(example) for example in examples]

def _format_example(example):
    t = strip_mw_markup(example.get('t'))
    tr = example.get('tr', None)
    print(Example(text=t, translation=tr))
    return Example(text=t, translation=tr)

def extract_audio(word, language, countryCode): 
    """
    if audio begins with "bix", the subdirectory should be "bix",
    if audio begins with "gg", the subdirectory should be "gg",
    if audio begins with a number or punctuation (eg, "_"), the subdirectory should be "number",
    """
    prs = word.get('hwi').get('prs')
    audio_url = None
    audio = ''
    if prs:
        audio = prs[0].get('sound').get('audio')
        if audio:
            subdir = audio[0]
            if audio.startswith('gg'):
                subdir = 'gg'
            if audio.startswith('bix'):
                subdir = 'bix'
            if not subdir.isalpha():
                subdir = 'number'

            audio_url = f'{settings.audio_endpoint}/{language}/{countryCode}/mp3/{subdir}/{audio}.mp3'
    return audio_url

def format_name(str):
    return ''.join(c for c in str if c != ':' and not c.isnumeric())

def extract_transcription(word):
    transcription = None
    prs = word.get('hwi').get('prs')
    if prs:
        transcription = prs[0].get('ipa', '')
    return transcription

def is_suggestion_response(raw_items: list) -> bool:
    """
    MW-family APIs return a flat list of plain suggestion strings
    (instead of entry objects) when the query doesn't match a
    headword closely enough. This is specific to this API family,
    not to any particular language.
    """
    return bool(raw_items) and all(isinstance(item, str) for item in raw_items)

def extract_gender(fl: str | None) -> str | None:
    if fl is None:
        return None
    fl_lower = fl.lower()
    masculine, feminine = "masculine" in fl_lower, "feminine" in fl_lower
    if masculine and feminine:  # e.g. "masculine or feminine noun" (el/la ecologista)
        return "both"
    if feminine:
        return "feminine"
    if masculine:
        return "masculine"
    return None
import re
from words.example import Example
from settings import settings

TAG_RE = re.compile(r'\{[^}]*\}')
# Direct link to an illustration, by the `art.artid` of an entry (MW API docs, "art").
ART_URL = 'https://www.merriam-webster.com/assets/mw/static/art/dict'

def strip_mw_markup(raw: str) -> str:
    return TAG_RE.sub('', raw).strip()

# Cross-reference notes inside a definition ("compare waterfowl"), dropped.
_NOTE_RE = re.compile(r'\{(dx|dx_def|dx_ety|ma)\}.*?\{/\1\}')
# Tokens that carry a word ({sx|fellow||}, {d_link|craniate|craniate}), kept as the word.
_LINK_RE = re.compile(r'\{(?:sx|a_link|d_link|i_link|et_link|mat|dxt)\|([^|}]*)[^}]*\}')
MAX_DEFINITIONS_FROM_SENSES = 3

def extract_definitions(entry) -> list[str]:
    """The entry's definitions.

    `shortdef` when the dictionary provides it. Otherwise the text of the
    first senses in `def`, and for a cross-reference entry (no senses, e.g.
    "murther") the reference itself: "chiefly dialectal variant of murder".
    """
    if entry.get('shortdef'):
        return entry['shortdef']
    from_senses = [
        text
        for group in _sense_groups(entry)
        for sense in _senses(group)
        if (text := _sense_text(sense))
    ]
    if from_senses:
        return from_senses[:MAX_DEFINITIONS_FROM_SENSES]
    return [
        f"{cx.get('cxl', '')} {', '.join(t['cxt'].split(':')[0] for t in cx.get('cxtis', []) if t.get('cxt'))}".strip()
        for cx in entry.get('cxs', [])
    ]

def has_definitions(entry) -> bool:
    """Whether the entry has anything to learn (see `extract_definitions`)."""
    return bool(extract_definitions(entry))

def _sense_groups(entry):
    for definition in entry.get('def') or []:
        yield from definition.get('sseq') or []

def _sense_text(sense) -> str:
    raw = ' '.join(d[1] for d in sense.get('dt') or [] if d[0] == 'text')
    return _definition_text(raw)

def _definition_text(raw: str) -> str:
    text = _LINK_RE.sub(r'\1', _NOTE_RE.sub('', raw))
    return ' '.join(strip_mw_markup(text).split())

def extract_examples(data):
    """The usage examples of the entry's first sense group."""
    definitions = data.get('def') or []
    sseq = definitions[0].get('sseq') if definitions else None
    if not sseq:
        return []
    examples = []
    for sense in _senses(sseq[0]):
        for d in sense.get('dt') or []:
            if d[0] == 'vis':
                examples.extend(d[1])
    return [_format_example(example) for example in examples]

def _senses(items):
    """Yield each sense's data from an `sseq` group.

    A group mixes plain senses ["sense", {...}], binding senses
    ["bs", {"sense": {...}}] and parenthesized groups ["pseq", [...]].
    """
    for kind, data in items:
        if kind == 'sense':
            yield data
        elif kind == 'bs':
            yield data.get('sense', {})
        elif kind == 'pseq':
            yield from _senses(data)

def extract_image(word) -> str | None:
    """The URL of the entry's illustration, if it has one."""
    artid = (word.get('art') or {}).get('artid')
    return f'{ART_URL}/{artid}.gif' if artid else None

def _format_example(example):
    t = strip_mw_markup(example.get('t'))
    tr = example.get('tr', None)
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
        audio = (prs[0].get('sound') or {}).get('audio')
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
    """IPA where the dictionary gives it (Learner's), else MW's own respelling
    (Collegiate, e.g. "ˈhärt")."""
    transcription = None
    prs = word.get('hwi').get('prs')
    if prs:
        transcription = prs[0].get('ipa') or prs[0].get('mw')
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
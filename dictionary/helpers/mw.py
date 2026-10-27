import logging
import re
from collections.abc import Callable
from urllib.parse import quote

import httpx

from dictionary.base import DictionaryError
from dictionary.entry import DictionaryEntry, DictionaryExample

logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"\{[^}]*\}")
# Seconds to wait for MW; well under the frontend proxy's own timeout.
REQUEST_TIMEOUT_SECONDS = 10

# Pronunciation audio, by the `sound.audio` of an entry (MW API docs, "prs").
AUDIO_URL = "https://media.merriam-webster.com/audio/prons"
# Direct link to an illustration, by the `art.artid` of an entry (MW API docs, "art").
ART_URL = "https://www.merriam-webster.com/assets/mw/static/art/dict"


async def fetch_entries(api_url: str, api_key: str, query: str) -> list:
    """Request one MW reference's JSON for `query`.

    The query is one path segment, so it is percent-encoded completely: "/",
    "?" and "#" in a search must not change which URL is called or push the
    key out of the query string. A query of only dots would still be read as
    "." or ".." in the path, and nothing else is a word, so it returns no
    entries without a request.

    MW answers an unknown word with an empty list or spelling suggestions,
    so anything other than a JSON list is a failure. A bad key, for example,
    comes back as plain text.

    Raises:
        DictionaryError: MW is unreachable, timed out, or answered with an
            error status or something other than a JSON list. The error
            names only the kind of failure: httpx's own messages include the
            URL, and the URL includes the API key.
    """
    if not query.strip("."):
        return []
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.get(f"{api_url}/{quote(query, safe='')}", params={"key": api_key})
    except httpx.HTTPError as exc:
        raise DictionaryError(f"MW request failed: {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise DictionaryError(f"MW answered with status {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise DictionaryError("MW answered with something other than JSON") from None
    if not isinstance(data, list):
        raise DictionaryError(f"MW answered with a JSON {type(data).__name__}, not a list")
    return data


def format_entries(raw_items: list, format_entry: Callable[[dict], DictionaryEntry]) -> list[DictionaryEntry]:
    """Format the entries of an MW response, skipping any with an unexpected shape.

    `format_entry` is the language's own formatter. Entries without
    definitions are left out, as there is nothing to learn from them. An entry
    that isn't a dict, or that `format_entry` can't handle (a missing key, a
    value of the wrong type), is skipped and logged, so one odd entry doesn't
    fail the whole search.

    Raises:
        DictionaryError: every entry was skipped as malformed. Returning no
            words would read as "word not found"; this is MW answering in a
            shape the code doesn't know, so it is reported as a failure.
    """
    words: list[DictionaryEntry] = []
    malformed = 0
    for item in raw_items:
        try:
            if not isinstance(item, dict):
                raise TypeError(f"entry is a {type(item).__name__}, not an object")
            if has_definitions(item):
                words.append(format_entry(item))
        except (KeyError, TypeError, AttributeError, ValueError, IndexError) as exc:
            malformed += 1
            logger.warning("Skipped a malformed MW entry %r: %s: %s", _entry_id(item), type(exc).__name__, exc)
    if raw_items and malformed == len(raw_items):
        raise DictionaryError(f"MW answered with {malformed} malformed entries")
    return words


def _entry_id(item) -> str | None:
    """The entry's `meta.id` ("casa:1"), if it has one, for log messages."""
    meta = item.get("meta") if isinstance(item, dict) else None
    return meta.get("id") if isinstance(meta, dict) else None


def strip_mw_markup(raw: str) -> str:
    return TAG_RE.sub("", raw).strip()


# Cross-reference notes inside a definition ("compare waterfowl"), dropped.
_NOTE_RE = re.compile(r"\{(dx|dx_def|dx_ety|ma)\}.*?\{/\1\}")
# Tokens that carry a word ({sx|fellow||}, {d_link|craniate|craniate}), kept as the word.
_LINK_RE = re.compile(r"\{(?:sx|a_link|d_link|i_link|et_link|mat|dxt)\|([^|}]*)[^}]*\}")
MAX_DEFINITIONS_FROM_SENSES = 3


def extract_definitions(entry) -> list[str]:
    """The entry's definitions.

    `shortdef` when the dictionary provides it. Otherwise the text of the
    first senses in `def`, and for a cross-reference entry (no senses, e.g.
    "murther") the reference itself: "chiefly dialectal variant of murder".
    """
    if entry.get("shortdef"):
        return entry["shortdef"]
    from_senses = [text for group in _sense_groups(entry) for sense in _senses(group) if (text := _sense_text(sense))]
    if from_senses:
        return from_senses[:MAX_DEFINITIONS_FROM_SENSES]
    return [
        f"{cx.get('cxl', '')} {', '.join(t['cxt'].split(':')[0] for t in cx.get('cxtis', []) if t.get('cxt'))}".strip()
        for cx in entry.get("cxs", [])
    ]


def has_definitions(entry) -> bool:
    """Whether the entry has anything to learn (see `extract_definitions`)."""
    return bool(extract_definitions(entry))


def _sense_groups(entry):
    for definition in entry.get("def") or []:
        yield from definition.get("sseq") or []


def _sense_text(sense) -> str:
    raw = " ".join(d[1] for d in sense.get("dt") or [] if d[0] == "text")
    return _definition_text(raw)


def _definition_text(raw: str) -> str:
    text = _LINK_RE.sub(r"\1", _NOTE_RE.sub("", raw))
    return " ".join(strip_mw_markup(text).split())


def extract_examples(data):
    """The usage examples of the entry's first sense group."""
    definitions = data.get("def") or []
    sseq = definitions[0].get("sseq") if definitions else None
    if not sseq:
        return []
    examples = []
    for sense in _senses(sseq[0]):
        for d in sense.get("dt") or []:
            if d[0] == "vis":
                examples.extend(d[1])
    return [_format_example(example) for example in examples]


def _senses(items):
    """Yield each sense's data from an `sseq` group.

    A group mixes plain senses ["sense", {...}], binding senses
    ["bs", {"sense": {...}}] and parenthesized groups ["pseq", [...]].
    """
    for kind, data in items:
        if kind == "sense":
            yield data
        elif kind == "bs":
            yield data.get("sense", {})
        elif kind == "pseq":
            yield from _senses(data)


def extract_image(word) -> str | None:
    """The URL of the entry's illustration, if it has one."""
    artid = (word.get("art") or {}).get("artid")
    return f"{ART_URL}/{artid}.gif" if artid else None


def extract_image_desc(word) -> str | None:
    """The caption of the entry's illustration ("wheel 1: 1 hub, 2 spoke, ..."),
    or None if it has no illustration or an empty caption."""
    art = word.get("art") or {}
    if not art.get("artid"):
        return None
    return _definition_text(art.get("capt") or "") or None


def _format_example(example):
    t = strip_mw_markup(example.get("t"))
    tr = example.get("tr", None)
    return DictionaryExample(text=t, translation=tr)


def extract_audio(word, language, countryCode):
    """
    if audio begins with "bix", the subdirectory should be "bix",
    if audio begins with "gg", the subdirectory should be "gg",
    if audio begins with a number or punctuation (eg, "_"), the subdirectory should be "number",
    """
    prs = (word.get("hwi") or {}).get("prs")  # some entries have no pronunciation
    audio_url = None
    audio = ""
    if prs:
        audio = (prs[0].get("sound") or {}).get("audio")
        if audio:
            subdir = audio[0]
            if audio.startswith("gg"):
                subdir = "gg"
            if audio.startswith("bix"):
                subdir = "bix"
            if not subdir.isalpha():
                subdir = "number"

            audio_url = f"{AUDIO_URL}/{language}/{countryCode}/mp3/{subdir}/{audio}.mp3"
    return audio_url


def format_name(word) -> str:
    """The headword as MW displays it: "jamás", "Stark", "borrow".

    `hwi.hw` marks syllable breaks with "*" ("Bor*row"), which are removed.
    `meta.id` is only a fallback for an entry without `hwi`: it has no accents
    and ends in a homograph suffix after ":" ("jamas", "Stark:b1").
    """
    headword = (word.get("hwi") or {}).get("hw")
    if headword:
        return headword.replace("*", "")
    return word["meta"]["id"].split(":")[0]


def extract_transcription(word):
    """IPA where the dictionary gives it (Learner's), else MW's own respelling
    (Collegiate, e.g. "ˈhärt")."""
    transcription = None
    prs = (word.get("hwi") or {}).get("prs")  # some entries have no pronunciation
    if prs:
        transcription = prs[0].get("ipa") or prs[0].get("mw")
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

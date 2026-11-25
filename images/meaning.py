"""A word's meaning in a few English words: what to search an image for.

It fills the image search box, and later the generation prompt and the
"Used before" key (I9), so the rules live here only, on the server.

- English: the headword (`wheel`). Its dictionary definitions are long
  sentences, and the word itself is already English.
- Every other language: the first definition, since definitions are always
  English glosses (Spanish `rueda` → "wheel", Korean `바퀴` → "wheel").

Each text is cleaned: parentheses dropped, cut at the first `;` or `,`
(Spanish `perro` "dog, bitch" and Korean `개` "dog" both become "dog"),
lowercased, a leading "to", "a", "an" or "the" dropped. When a text has
nothing left, e.g. krdict's "(no equivalent expression)", the next
definition is tried. A word with nothing usable gets "" and the user types
the query.
"""

import re
import unicodedata

from core.language import Language
from images.base import MAX_QUERY_LENGTH

_BRACKETED = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_FIRST_ITEM = re.compile(r"[;,]")
_LEADING_WORD = re.compile(r"^(?:to|a|an|the)\s+")
_EDGE_PUNCTUATION = " .:!?¡¿\"'“”‘’-–—"


def image_meaning(language: str, name: str, defs: list[str]) -> str:
    """The English meaning to search an image for; "" if the word has none usable."""
    texts = [name, *defs] if language == Language.EN else defs
    for text in texts:
        meaning = clean_meaning(text)
        if meaning:
            return meaning
    return ""


def clean_meaning(text: str) -> str:
    """One definition (or headword) cleaned as described above, at most `MAX_QUERY_LENGTH` characters."""
    text = unicodedata.normalize("NFKC", text)
    text = _BRACKETED.sub(" ", text)
    text = _FIRST_ITEM.split(text, maxsplit=1)[0]
    text = " ".join(text.lower().split()).strip(_EDGE_PUNCTUATION)
    # Needs a word after it ("to live"), so "to" alone stays.
    text = _LEADING_WORD.sub("", text)
    return _shorten(text)


def _shorten(text: str) -> str:
    """Cut at the last whole word that fits `MAX_QUERY_LENGTH`."""
    if len(text) <= MAX_QUERY_LENGTH:
        return text
    cut = text[: MAX_QUERY_LENGTH + 1].rsplit(" ", 1)[0]
    return cut[:MAX_QUERY_LENGTH].rstrip()

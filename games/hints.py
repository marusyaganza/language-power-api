"""Hide the answer where a question's text gives it away.

Dictionary definitions often contain the word they define ("heart": "the
heart thought of as the place where emotions are felt"). Before a definition
is shown as a clue or an option, every form of its word (the name and the
dictionary stems, e.g. "hearts", "by heart") is replaced with `BLANK`.
"""

import re

BLANK = "___"


def hide_word(text: str, name: str, stems: list[str]) -> str:
    """Replace every whole-word occurrence of `name` or a stem in `text`, ignoring case.

    Longer forms are matched first, so a phrase stem ("by heart") becomes a
    single blank rather than "by ___".
    """
    forms = sorted({f.strip() for f in [name, *stems] if f and f.strip()}, key=len, reverse=True)
    if not forms:
        return text
    # Lookarounds instead of \b, which fails next to non-word characters
    # such as the "¡" in "¡sea!".
    pattern = r"(?<!\w)(?:" + "|".join(re.escape(f) for f in forms) + r")(?!\w)"
    return re.sub(pattern, BLANK, text, flags=re.IGNORECASE)


def hidden_definitions(name: str, stems: list[str], defs: list[str]) -> list[str]:
    """`defs` with the word hidden in each."""
    return [hide_word(d, name, stems) for d in defs]

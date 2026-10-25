"""Answer options for the multiple-choice games, drawn from the user's own words.

The wrong options are other saved words, in random order, skipping any that
would make a second option correct or repeat one already chosen. If too few
words qualify, the question gets fewer options; it always has at least the
answer.

Texts are compared ignoring case and spacing.
"""
import random
from typing import Protocol

from games.hints import hidden_definitions


class OptionWord(Protocol):
    """What option picking reads from a word: a saved `Word` or a `WordSummary`."""

    id: int
    name: str
    stems: list[str]
    defs: list[str]


def definition_options(
    target: OptionWord, pool: list[OptionWord], count: int
) -> tuple[str, list[str]]:
    """select_def: return the answer (the target's first definition) and the shuffled options.

    Every definition is shown with its own word hidden, so blanks do not
    single out the answer. A wrong option comes from a word with a different
    name, and is never any meaning of the target or of another entry with
    its name ("ser" the verb and "ser" the noun): the player only sees the
    name, so each of those would be correct. If a word's first definition
    does not qualify (or is only a blank), its next one is tried.
    """
    answer = hidden_definitions(target.name, target.stems, target.defs[:1])[0]
    options = [answer]
    used = {_key(answer)}
    same_name = [w for w in [target, *pool] if _key(w.name) == _key(target.name)]
    correct_meanings = {_key(d) for w in same_name for d in w.defs}
    for word in _others(target, pool):
        if len(options) == count:
            break
        if _key(word.name) == _key(target.name):
            continue
        for raw, definition in zip(word.defs, hidden_definitions(word.name, word.stems, word.defs)):
            if (
                _key(raw) not in correct_meanings
                and _key(definition) not in used
                and any(c.isalpha() for c in definition)
            ):
                options.append(definition)
                used.add(_key(definition))
                break
    random.shuffle(options)
    return answer, options


def word_options(target: OptionWord, pool: list[OptionWord], count: int) -> list[str]:
    """select_word: return the shuffled options, one of which is the target's name.

    A word is skipped if its name is already an option (e.g. "ser" the verb
    and "ser" the noun), or if any entry with its name shares a definition
    with the target: the player only sees the name, and a synonym would fit
    the clues as well as the answer.
    """
    options = [target.name]
    used = {_key(target.name)}
    target_defs = {_key(d) for d in target.defs}
    synonyms = {_key(w.name) for w in pool if target_defs & {_key(d) for d in w.defs}}
    for word in _others(target, pool):
        if len(options) == count:
            break
        if _key(word.name) in used or _key(word.name) in synonyms:
            continue
        options.append(word.name)
        used.add(_key(word.name))
    random.shuffle(options)
    return options


def _others(target: OptionWord, pool: list[OptionWord]) -> list[OptionWord]:
    others = [w for w in pool if w.id != target.id]
    random.shuffle(others)
    return others


def _key(text: str) -> str:
    return " ".join(text.lower().split())

# tests/unit/test_options.py
"""The options are shuffled, so these tests check properties, not positions."""
from types import SimpleNamespace

from games.hints import BLANK
from games.options import definition_options, word_options


def word(id, name, *defs, stems=()):
    return SimpleNamespace(id=id, name=name, stems=list(stems), defs=list(defs))


POOL = [
    word(1, "perro", "dog"),
    word(2, "gato", "cat"),
    word(3, "casa", "house"),
    word(4, "mesa", "table"),
    word(5, "libro", "book"),
]


# --------------------------------------------------------------------------- #
# select_def: pick the definition
# --------------------------------------------------------------------------- #

def test_definition_options_include_the_answer_once():
    target = POOL[0]
    answer, options = definition_options(target, POOL, 4)
    assert answer == "dog"
    assert len(options) == 4
    assert options.count("dog") == 1
    assert len(set(options)) == 4
    assert set(options) <= {"dog", "cat", "house", "table", "book"}


def test_definition_options_are_fewer_when_the_pool_is_small():
    answer, options = definition_options(POOL[0], POOL[:2], 4)
    assert sorted(options) == ["cat", "dog"]


def test_definition_options_hide_the_word_in_every_definition():
    target = word(1, "ser", "to be")
    pool = [target, word(2, "estar", "to estar somewhere")]
    answer, options = definition_options(target, pool, 4)
    assert set(options) == {"to be", f"to {BLANK} somewhere"}


def test_definition_options_skip_another_meaning_of_the_target():
    # The answer is "to be", but "to exist" is also a meaning of "ser": as an
    # option from "existir" it would be a second correct one.
    target = word(1, "ser", "to be", "to exist")
    pool = [target, word(2, "existir", "to exist", "to live"), word(3, "gato", "cat")]
    answer, options = definition_options(target, pool, 4)
    assert answer == "to be"
    assert "to exist" not in options
    assert set(options) == {"to be", "to live", "cat"}


def test_definition_options_skip_meanings_of_other_entries_with_the_same_name():
    # "ser" the verb and "ser" the noun: the player sees only "ser", so the
    # noun's meaning "being" is correct too, even coming from "ente".
    verb = word(1, "ser", "to be")
    noun = word(2, "ser", "being")
    pool = [verb, noun, word(3, "ente", "being", "entity"), word(4, "gato", "cat")]
    _answer, options = definition_options(verb, pool, 4)
    assert "being" not in options
    assert set(options) == {"to be", "entity", "cat"}


# --------------------------------------------------------------------------- #
# select_word: pick the word
# --------------------------------------------------------------------------- #

def test_word_options_include_the_answer_once():
    options = word_options(POOL[0], POOL, 4)
    assert len(options) == 4
    assert options.count("perro") == 1
    assert len(set(options)) == 4


def test_word_options_never_repeat_a_name():
    pool = [word(1, "ser", "to be"), word(2, "ser", "being"), word(3, "gato", "cat")]
    assert sorted(word_options(pool[0], pool, 4)) == ["gato", "ser"]


def test_word_options_skip_synonyms():
    # "can" and "may" share a definition: both would fit the clues.
    target = word(1, "can", "to be able")
    pool = [target, word(2, "may", "To  be able"), word(3, "dog", "an animal")]
    assert sorted(word_options(target, pool, 4)) == ["can", "dog"]

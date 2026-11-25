# tests/unit/test_image_meaning.py
"""A word's English meaning, the starting query for its image search."""

import pytest

from images.base import MAX_QUERY_LENGTH
from images.meaning import clean_meaning, image_meaning


@pytest.mark.parametrize(
    ("language", "name", "defs", "meaning"),
    [
        # English: the headword, not its long definition.
        ("en", "wheel", ["a circular frame of hard material that may be solid"], "wheel"),
        ("en", "take into account", ["to consider"], "take into account"),
        # Spanish and Korean: the first English gloss.
        ("es", "ballena", ["whale"], "whale"),
        ("es", "vivir", ["to live", "to be alive"], "live"),
        ("es", "perro", ["dog, bitch"], "dog"),
        ("ko", "개", ["dog"], "dog"),
        ("ko", "가게", ["shop; store"], "shop"),
        ("ko", "티셔츠", ["T-shirt"], "t-shirt"),
        ("ko", "전혀", ["(not) at all; completely"], "at all"),
        # krdict's grammar words have no gloss: the next definition is used.
        ("ko", "그것", ["(no equivalent expression)", "that thing"], "that thing"),
        # Nothing usable: the user types the query.
        ("ko", "그", ["(no equivalent expression)"], ""),
        ("es", "x", [], ""),
    ],
)
def test_the_meaning_of_a_word(language, name, defs, meaning):
    assert image_meaning(language, name, defs) == meaning


def test_an_english_word_with_an_unusable_name_falls_back_to_its_definitions():
    assert image_meaning("en", "(…)", ["a small round fruit"]) == "small round fruit"


@pytest.mark.parametrize(
    ("text", "cleaned"),
    [
        ("  An   Apple. ", "apple"),
        ("the sea", "sea"),
        ("to", "to"),  # nothing would be left: kept
        ("a", "a"),
        ("tomato", "tomato"),  # "to" only as a word
        ("another day", "another day"),
        ("[informal] guy", "guy"),
        ("“quote”", "quote"),
        ("ｆｕｌｌ　ｗｉｄｔｈ", "full width"),  # NFKC
        ("¿qué?", "qué"),
        ("—", ""),
    ],
)
def test_cleaning_one_text(text, cleaned):
    assert clean_meaning(text) == cleaned


def test_a_long_meaning_is_cut_at_a_whole_word():
    # The 100-character limit falls inside the 21st "word" ("x" shifts it off a boundary).
    text = "x " + " ".join(["word"] * 40)

    cleaned = clean_meaning(text)

    assert len(cleaned) <= MAX_QUERY_LENGTH
    assert cleaned == "x " + " ".join(["word"] * 19)


def test_a_long_meaning_without_spaces_is_cut_at_the_limit():
    assert clean_meaning("x" * 150) == "x" * MAX_QUERY_LENGTH

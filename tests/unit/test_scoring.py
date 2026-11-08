# tests/unit/test_scoring.py
import unicodedata

import pytest

from games.scoring import (
    AnswerGrade,
    classify_choice_answer,
    classify_gender_answer,
    classify_typed_answer,
)

CORRECT, CLOSE, WRONG = AnswerGrade.CORRECT, AnswerGrade.CLOSE, AnswerGrade.WRONG


@pytest.mark.parametrize(
    ("answer", "expected", "grade"),
    [
        ("house", "house", CORRECT),
        ("  House ", "house", CORRECT),  # case and surrounding spaces ignored
        ("houses", "house", CLOSE),  # similarity 0.91
        ("camion", "camión", CLOSE),  # missing accent, 0.92 (the accent is a separate mark when decomposed)
        ("housx", "house", CLOSE),  # exactly the 0.8 threshold
        ("cosa", "casa", WRONG),  # 0.75, just below it
        ("dog", "house", WRONG),
        ("", "casa", WRONG),
        # Korean is compared letter by letter, not syllable by syllable.
        ("조용하다", "조용하다", CORRECT),
        ("조영하다", "조용하다", CLOSE),  # one vowel off: 0.89 (by syllables 0.75, WRONG)
        ("도서간", "도서관", CLOSE),  # 0.86 (by syllables 0.67)
        ("가개", "가게", WRONG),  # one letter of four: 0.75, like "cosa" for "casa"
        ("나무", "바다", WRONG),
    ],
)
def test_classify_typed_answer(answer, expected, grade):
    assert classify_typed_answer(answer, expected) == grade


def test_the_same_text_typed_composed_or_decomposed_is_correct():
    # Some keyboards send é, or a Hangul syllable, as separate letters.
    decomposed = unicodedata.normalize("NFD", "camión 가게")

    assert decomposed != "camión 가게"
    assert classify_typed_answer(decomposed, "camión 가게") == CORRECT


@pytest.mark.parametrize(
    ("answer", "expected", "grade"),
    [
        ("house", "house", CORRECT),
        ("House", "house", WRONG),  # choices are picked, not typed: exact match only
        ("dog", "house", WRONG),
    ],
)
def test_classify_choice_answer(answer, expected, grade):
    assert classify_choice_answer(answer, expected) == grade


@pytest.mark.parametrize(
    ("answer", "expected", "grade"),
    [
        ("masculine", "masculine", CORRECT),
        ("feminine", "feminine", CORRECT),
        ("both", "both", CORRECT),
        ("masculine", "both", CLOSE),  # half of a "both" noun
        ("feminine", "both", CLOSE),
        ("feminine", "masculine", WRONG),
        ("both", "masculine", WRONG),  # hedging is not knowing the gender
    ],
)
def test_classify_gender_answer(answer, expected, grade):
    assert classify_gender_answer(answer, expected) == grade

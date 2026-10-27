# tests/unit/test_scoring.py
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
        ("camion", "camión", CLOSE),  # missing accent, 0.83
        ("housx", "house", CLOSE),  # exactly the 0.8 threshold
        ("cosa", "casa", WRONG),  # 0.75, just below it
        ("dog", "house", WRONG),
        ("", "casa", WRONG),
    ],
)
def test_classify_typed_answer(answer, expected, grade):
    assert classify_typed_answer(answer, expected) == grade


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

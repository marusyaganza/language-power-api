# games/scoring.py
import difflib
import unicodedata
from enum import Enum


class AnswerGrade(str, Enum):
    WRONG = "wrong"
    CLOSE = "close"  # a near-miss: a typo, or half of a "both" gender
    CORRECT = "correct"


def classify_typed_answer(user_answer: str, correct_answer: str) -> AnswerGrade:
    """CORRECT if equal ignoring case and surrounding spaces, CLOSE for a near-miss (similarity of 0.8 or more).

    Both are compared decomposed (NFD): a Hangul syllable is one character
    made of 2 or 3 letters (가 = ᄀ + ᅡ), so a one-letter typo would otherwise
    cost a whole syllable, and 조영하다 for 조용하다 would be WRONG. Decomposed,
    similarity counts letters, as for other languages; accents become their
    own marks (é = e + ́), and the same text typed composed or decomposed is
    equal.
    """
    normalized_user = unicodedata.normalize("NFD", user_answer.strip().lower())
    normalized_correct = unicodedata.normalize("NFD", correct_answer.strip().lower())

    if normalized_user == normalized_correct:
        return AnswerGrade.CORRECT

    similarity = difflib.SequenceMatcher(None, normalized_user, normalized_correct).ratio()
    if similarity >= 0.8:
        return AnswerGrade.CLOSE

    return AnswerGrade.WRONG


def classify_choice_answer(user_answer: str, correct_answer: str) -> AnswerGrade:
    return AnswerGrade.CORRECT if user_answer == correct_answer else AnswerGrade.WRONG


def classify_gender_answer(user_answer: str, correct_answer: str) -> AnswerGrade:
    """Answers are "masculine", "feminine" or "both".

    One gender for a "both" noun is half right (CLOSE). "both" for a noun with
    one gender is WRONG: it shows the gender is not known.
    """
    if user_answer == correct_answer:
        return AnswerGrade.CORRECT
    if correct_answer == "both" and user_answer in ("masculine", "feminine"):
        return AnswerGrade.CLOSE
    return AnswerGrade.WRONG

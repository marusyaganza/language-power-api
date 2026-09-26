# games/scoring.py
import difflib
from enum import Enum


class AnswerGrade(str, Enum):
    WRONG = "wrong"
    CLOSE = "close"      # typed games only — a near-miss/typo
    CORRECT = "correct"


def classify_typed_answer(user_answer: str, correct_answer: str) -> AnswerGrade:
    normalized_user = user_answer.strip().lower()
    normalized_correct = correct_answer.strip().lower()

    if normalized_user == normalized_correct:
        return AnswerGrade.CORRECT

    similarity = difflib.SequenceMatcher(None, normalized_user, normalized_correct).ratio()
    if similarity >= 0.8:
        return AnswerGrade.CLOSE

    return AnswerGrade.WRONG


def classify_choice_answer(user_answer: str, correct_answer: str) -> AnswerGrade:
    return AnswerGrade.CORRECT if user_answer == correct_answer else AnswerGrade.WRONG
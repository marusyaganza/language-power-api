from typing import Literal

from pydantic import BaseModel
from words.schemas import ExampleItem
from games.scoring import AnswerGrade

class GameOut(BaseModel):
    id: int
    slug: str
    title: str
    description: str
    game_type: str
    available_word_count: int
    is_enabled: bool

    class Config:
        from_attributes = True

class QuestionAdditionalInfo(BaseModel):
    audio_url: str | None = None
    img_url: str | None = None
    examples: list[ExampleItem] | None = None

    model_config = {"from_attributes": True}

class QuestionOut(BaseModel):
    id: int
    question: list[str]
    additional_info: QuestionAdditionalInfo

class GameSessionOut(BaseModel):
    task: str
    session_id: str
    questions: list[QuestionOut]
    questions: list[QuestionOut]


class AnswerRequest(BaseModel):
    session_id: str
    word_id: int
    answer: str


class AnswerResponse(BaseModel):
    grade: AnswerGrade
    correct_answer: str | None = None  # populated when grade != CORRECT
    session_complete: bool


class QuestionResult(BaseModel):
    word_id: int
    answer: str
    grade: AnswerGrade | Literal["unanswered"]


class GameResultOut(BaseModel):
    """The result of a finished game session.

    `score_percent` is (correct + close) / total_words, rounded half up;
    unanswered questions count against it.
    """

    total_words: int
    correct: int
    close: int
    wrong: int
    unanswered: int
    score_percent: int
    questions: list[QuestionResult]

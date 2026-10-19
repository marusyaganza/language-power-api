from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field
from words.schemas import ExampleItem
from games.scoring import AnswerGrade

class GameMode(str, Enum):
    SPACED = "spaced"  # only words that are due
    REVIEW = "review"  # every word, least recently practiced first


class GameOut(BaseModel):
    id: int
    slug: str
    title: str
    description: str
    game_type: str
    total_word_count: int
    due_word_count: int  # includes words never practiced in this game
    next_due_at: datetime | None  # earliest due date of words not due yet
    min_word_count: int  # words needed to start the game

    class Config:
        from_attributes = True

class QuestionAdditionalInfo(BaseModel):
    audio_url: str | None = None
    img_url: str | None = None
    examples: list[ExampleItem] | None = None
    definition: str | None = Field(default=None, alias="def")

    model_config = {"from_attributes": True, "populate_by_name": True}

class QuestionOut(BaseModel):
    id: int
    # A word (select_def), definitions (type_word, select_word), or an audio
    # (audio) or image (image) URL.
    question: list[str] | str
    options: list[str] | None = None  # multiple-choice games only
    alt: str | None = None  # image game only: a text clue if the image fails to load
    additional_info: QuestionAdditionalInfo

class GameSessionOut(BaseModel):
    task: str
    session_id: str
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

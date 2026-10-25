from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from words.schemas import ExampleItem
from games.scoring import AnswerGrade
from games.spaced_repetition import DEFAULT_CONFIG

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

    model_config = {"from_attributes": True}

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

class GameSessionCreate(BaseModel):
    language: str
    mode: GameMode = GameMode.SPACED
    new_words_first: bool = False  # words never practiced in this game first


class GameSessionOut(BaseModel):
    task: str
    session_id: str
    questions: list[QuestionOut]


class AnswerRequest(BaseModel):
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


MAX_LEARNING_STEPS = 5
# Fixed, not a user setting: no interval, including a learning step, is longer.
MAX_INTERVAL_DAYS = int(DEFAULT_CONFIG.max_interval_days)


class GameSettingsUpdate(BaseModel):
    """The spaced-repetition settings a user can change."""

    learning_steps_minutes: list[int] = Field(min_length=1, max_length=MAX_LEARNING_STEPS)
    graduating_interval_days: int = Field(ge=1, le=MAX_INTERVAL_DAYS)
    strict_mode: bool

    @field_validator("learning_steps_minutes")
    @classmethod
    def steps_must_increase(cls, steps: list[int]) -> list[int]:
        if any(step < 1 or step > MAX_INTERVAL_DAYS * 24 * 60 for step in steps):
            raise ValueError(f"Each learning step must be between 1 minute and {MAX_INTERVAL_DAYS} days")
        if any(later <= earlier for earlier, later in zip(steps, steps[1:])):
            raise ValueError("Learning steps must get longer each time")
        return steps

    @model_validator(mode="after")
    def graduating_not_shorter_than_last_step(self) -> "GameSettingsUpdate":
        if self.graduating_interval_days * 24 * 60 < self.learning_steps_minutes[-1]:
            raise ValueError("The graduating interval cannot be shorter than the last learning step")
        return self


class GameSettingsOut(GameSettingsUpdate):
    preset: str  # id of the preset these values match, or "custom"


class GameSettingsPreset(BaseModel):
    id: str
    title: str
    description: str
    settings: GameSettingsUpdate

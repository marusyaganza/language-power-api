from pydantic import BaseModel
from words.schemas import ExampleOut

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
    examples: list[ExampleOut] | None = None

    model_config = {"from_attributes": True}

class QuestionOut(BaseModel):
    id: int
    question: str
    additional_info: QuestionAdditionalInfo

class GameSessionOut(BaseModel):
    task: str
    session_id: str
    questions: list[QuestionOut]
    questions: list[QuestionOut]
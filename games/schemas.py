from pydantic import BaseModel

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
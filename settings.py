from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    spanish_api_key: str
    spanish_api_url: str
    english_api_key: str
    english_api_url: str
    audio_endpoint: str
    img_endpoint: str

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()  # automatically loads and validates from .env

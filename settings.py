from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    spanish_api_key: str
    spanish_api_url: str
    english_api_key: str
    english_api_url: str
    audio_endpoint: str
    img_endpoint: str
    use_mocks: str
    database_url: str = "postgresql+psycopg://app_user:dev_password@localhost:5432/language_app"
    signup_enabled: bool = True

    # rediss://user:password@host:port for TLS with a password (Upstash);
    # the trailing number is the Redis database.
    redis_url: str = "redis://localhost:6379/0"

    session_cookie_name: str = "session_id"
    session_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days
    cookie_secure: bool = False  

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()  # automatically loads and validates from .env

from pydantic import SecretStr
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
    cookie_secure: bool = False  # True in production: the cookie only travels over HTTPS

    # /docs, /redoc and /openapi.json. Off in production.
    docs_enabled: bool = True
    # Browser origins allowed to call the API from another site, as JSON in the
    # environment: CORS_ORIGINS='["https://example.com"]'. Empty in production,
    # where the frontend reaches the API through its own proxy (same origin),
    # and then no CORS middleware is installed.
    cors_origins: list[str] = ["http://localhost:5173"]
    # Secret shared with the Netlify proxy, which signs every request it
    # forwards (core.proxy_signature). Unset: requests aren't checked.
    proxy_signature_secret: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()  # automatically loads and validates from .env

from typing import Self

from pydantic import PositiveInt, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # True: dictionary lookups read recorded responses (dictionary/fixtures)
    # and need no keys. False: they call Merriam-Webster with the keys below.
    use_mocks: bool = False
    english_api_key: SecretStr | None = None
    spanish_api_key: SecretStr | None = None

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

    # Rate limits, counted in memory (auth.rate_limit). Every login attempt
    # counts, per email; a successful login starts the count over.
    login_attempt_limit: int = 5
    login_attempt_window_seconds: int = 15 * 60
    # All signups together, from anyone: only matters where signup is open.
    signup_limit: int = 30
    signup_window_seconds: int = 60 * 60

    # Limits for a public deployment, where strangers sign up. Unset (the
    # default) turns each one off. Days are UTC days.
    # Dictionary searches per language: per account, and per day for everyone
    # together (Merriam-Webster's free plan allows 1,000 a day per dictionary).
    searches_per_language: PositiveInt | None = None
    daily_searches_per_language: PositiveInt | None = None
    # New accounts per day.
    daily_signup_limit: PositiveInt | None = None
    # Accounts older than this are logged out, and deleted at the next signup.
    account_ttl_hours: PositiveInt | None = None
    # Saved words per account.
    max_words_per_user: PositiveInt | None = None

    # Error reporting (core.sentry). No DSN: nothing is sent.
    sentry_dsn: SecretStr | None = None
    sentry_environment: str = "local"  # "demo" on the demo, the only deployment with a DSN
    # The commit the image was built from; the Dockerfile sets it from GIT_SHA.
    sentry_release: str | None = None

    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="after")
    def keys_required_without_mocks(self) -> Self:
        missing = [name.upper() for name in ("english_api_key", "spanish_api_key") if getattr(self, name) is None]
        if not self.use_mocks and missing:
            raise ValueError(f"{', '.join(missing)} must be set when USE_MOCKS is off")
        return self


settings = Settings()  # automatically loads and validates from .env

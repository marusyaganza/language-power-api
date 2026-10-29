from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from auth.dependencies import limit_requests_per_ip
from auth.router import auth_router
from core.database import engine
from core.proxy_signature import require_proxy_signature
from core.redis import redis_client
from core.sentry import init_sentry
from dictionary.mock import SAMPLE_MEDIA_DIR, SAMPLE_MEDIA_PATH
from games.router import router as games_router
from games.router import settings_router as game_settings_router
from settings import settings
from words.router import router as words_router

# Before the app is created, so Sentry's FastAPI integration sees all of it.
init_sentry(settings)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """On shutdown, close the Redis connections and the database pool."""
    yield
    await redis_client.aclose()
    await engine.dispose()


# Shown at the top of /docs and /redoc.
_DESCRIPTION = """\
Backend of [Language Power](https://github.com/marusyaganza/language-power-api), a vocabulary trainer
for English and Spanish: dictionary search, a personal vocabulary, and games scheduled by spaced
repetition.

Authentication is a session cookie set by `POST /auth/login` or `POST /auth/signup`. Opened from the
app's own site, "Try it out" uses the session of the app open in the same browser.
"""
_app_info = {"title": "Language Power API", "version": "3.0.0", "description": _DESCRIPTION}

if settings.docs_enabled:
    app = FastAPI(lifespan=lifespan, root_path=settings.root_path, **_app_info)
else:
    app = FastAPI(
        lifespan=lifespan, root_path=settings.root_path, docs_url=None, redoc_url=None, openapi_url=None, **_app_info
    )

# Every API route only answers requests from the frontend's proxy, and only so
# many from one IP. In this order: the IP is only known once the signature is
# checked, and route dependencies (the session lookup) run after these.
_from_proxy = [Depends(require_proxy_signature), Depends(limit_requests_per_ip)]
app.include_router(words_router, dependencies=_from_proxy)
app.include_router(auth_router, dependencies=_from_proxy)
app.include_router(games_router, dependencies=_from_proxy)
app.include_router(game_settings_router, dependencies=_from_proxy)


# The mock dictionaries' audio and pictures. Mock mode only, so never in
# production; not behind the proxy signature, like any static file.
if settings.use_mocks:
    app.mount(SAMPLE_MEDIA_PATH, StaticFiles(directory=SAMPLE_MEDIA_DIR), name="sample-media")


@app.get("/health", include_in_schema=False)
async def health():
    """For uptime checks and the deploy smoke test: the process is serving.

    Not behind the proxy signature, and checks nothing else, so it reveals
    nothing and costs no database or Redis calls.
    """
    return {"status": "ok"}


if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

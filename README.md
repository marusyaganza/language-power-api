# py-lp

[![CI](https://github.com/marusyaganza/py-lp/actions/workflows/ci.yml/badge.svg)](https://github.com/marusyaganza/py-lp/actions/workflows/ci.yml)

Third version of the Language Power application: a vocabulary trainer for English and Spanish. This repository is its backend, a FastAPI service with PostgreSQL, Redis and session-based authentication. Users look up words in Merriam-Webster dictionaries, save them to a personal vocabulary, and practise them in games scheduled by spaced repetition. The React frontend lives in a separate repository.

## Status

- In active development
- Deployed privately for my own daily use, with signup closed
- No public demo yet; a separate demo deployment with mock dictionary data is planned
- Not a public production service

## Features

- Search English and Spanish words in Merriam-Webster dictionaries, with spelling suggestions when nothing matches
- Save words to a personal vocabulary with their definitions, examples, pronunciation audio, illustrations and, for Spanish nouns, grammatical gender
- Edit saved words, and browse the vocabulary with search, sorting and pagination
- Practise saved words in six games: pick the meaning, pick the word, type the word, listen and type, name the picture, and noun gender (Spanish only)
- Spaced-repetition scheduling per word and per game, with three presets or custom settings

The spaced repetition is a simplified scheduler inspired by Anki's learning steps and intervals, not a reproduction of its algorithm. The games, their rules and the scheduling are described in [docs/games.md](docs/games.md).

## Architecture

![Architecture diagram: a React client calls the FastAPI app over HTTPS with a session cookie; the app stores auth and game sessions in Redis, users, words and learning progress in PostgreSQL, and looks words up in the Merriam-Webster Dictionary API, which can be replaced by recorded fixtures in mock mode.](docs/architecture.png)

Each feature module (`auth`, `words`, `games`) is split the same way:

- **Routers** handle HTTP only: they read the request, pass the logged-in user to a service, and map the service's errors to status codes.
- **Services** hold the rules, raise domain errors that know nothing about HTTP, and own the transaction: each write ends in a single commit.
- **Repositories** (`repository.py`) build the queries and never commit. Services only call `db.get` for a lookup by primary key. The exception is `users`, whose service is just two one-line lookups.

Some rules hold everywhere:

- Everything is async: SQLAlchemy 2.0 with psycopg 3, and the asyncio Redis client. CPU-bound work (bcrypt) runs in a thread so it does not block the event loop.
- One database session per request. Relationships are never lazy-loaded: queries load what they need explicitly, and a missing load fails loudly instead of running a hidden query.
- Data belongs to a user. A word or game session that belongs to someone else is reported exactly like one that does not exist.
- Dictionary providers sit behind one interface, so the real Merriam-Webster clients and the mock ones are interchangeable.

## Tech stack

- Python 3.12
- FastAPI, Pydantic 2 and pydantic-settings, served by Uvicorn
- SQLAlchemy 2.0 (async) with psycopg 3, and Alembic for migrations
- PostgreSQL 18
- Redis 7 for auth sessions and game sessions
- httpx for the Merriam-Webster API
- bcrypt for password hashing
- pytest and pytest-cov, ruff
- Docker, GitHub Actions and Google Cloud Run

## Project structure

| Path | Responsibility |
| --- | --- |
| `main.py` | Creates the FastAPI app and includes the routers |
| `settings.py` | All configuration, read from environment variables and `.env` |
| `core/` | Database engine and session factory, Redis client, and the `Language` enum shared by every module |
| `auth/` | Signup, login, logout, server-side sessions and the `get_current_user` dependency |
| `users/` | User model, password hashing and user lookups |
| `words/` | Dictionary search and the saved vocabulary |
| `games/` | Game sessions, answer grading, spaced repetition and per-user settings |
| `dictionary/` | One provider per language (`en/`, `es/`), the shared Merriam-Webster code (`merriam_webster/`), and the mock providers. [dictionary/README.md](dictionary/README.md) lists the steps for adding a language |
| `dictionary/fixtures/` | Recorded Merriam-Webster responses used in mock mode |
| `alembic/` | Database migrations |
| `tests/` | Unit tests (`tests/unit`) and API tests against real Postgres and Redis (`tests/api`) |
| `docs/` | Games API documentation and the diagrams |
| `deploy/`, `Dockerfile`, `docker-entrypoint.sh` | Container image and Cloud Run settings |
| `.github/workflows/` | CI and the deploy workflow |

## Requirements

- Python 3.12
- [Docker](https://docs.docker.com/get-docker/), for PostgreSQL and Redis through the included `docker-compose.yml` (or servers of your own)
- _(Optional)_ [Merriam-Webster API](https://dictionaryapi.com) keys for the Collegiate and Spanish-English dictionaries. In mock mode the app uses recorded responses instead, so no keys are needed.

## Local development setup

1. Create a virtual environment and install the dependencies:

   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r requirements-dev.txt
   ```

   `requirements-dev.txt` includes `requirements.txt` and adds the test tools.

2. Start PostgreSQL and Redis:

   ```bash
   docker compose up -d
   ```

3. Create `.env` from the example:

   ```bash
   cp .env.example .env
   ```

   Its values work with `docker-compose.yml` and mock mode, so no API keys are needed. Every setting is described in [Environment variables](#environment-variables).

4. Create the tables and the games:

   ```bash
   alembic upgrade head
   python -m games.seed
   ```

   The seed script is safe to run repeatedly. Run it again after changing `games/seed_data.py`.

5. Start the API:

   ```bash
   uvicorn main:app --reload
   ```

   The API runs on `http://localhost:8000`, with interactive documentation at `http://localhost:8000/docs`. Sign up through `POST /auth/signup` or the frontend, then search for one of the mocked words, for example `heart` or `wheel` in English, or `hola` or `idioma` in Spanish. A search for any other word returns the list of mocked ones.

### Database migrations

After changing a model, generate a migration, read it before applying it (autogenerate misses some changes, such as data updates), then apply it. [alembic/README.md](alembic/README.md) describes the setup and the conventions.

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

To connect to the local databases:

```bash
docker exec -it postgres-dev psql -U app_user -d language_app
docker exec -it redis-dev redis-cli
```

## Environment variables

Settings are read from the environment, then from `.env`. Names are case-insensitive.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local `docker-compose.yml` database | PostgreSQL URL; must use the `postgresql+psycopg://` driver |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL; `rediss://user:password@host:port` for TLS |
| `USE_MOCKS` | `false` | `true` serves recorded dictionary responses; `false` calls the real Merriam-Webster API |
| `ENGLISH_API_KEY`, `SPANISH_API_KEY` | none | Merriam-Webster keys; required when `USE_MOCKS` is `false` |
| `SIGNUP_ENABLED` | `true` | Whether `POST /auth/signup` creates accounts |
| `COOKIE_SECURE` | `false` | Send the session cookie over HTTPS only; `true` in production |
| `SESSION_TTL_SECONDS` | 30 days | Session lifetime |
| `DOCS_ENABLED` | `true` | Serve `/docs`, `/redoc` and `/openapi.json`; `false` in production |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON list of browser origins allowed to call the API; `[]` turns CORS off |
| `SEARCHES_PER_LANGUAGE` | none | Dictionary searches per language an account may make; unset: unlimited |
| `DAILY_SEARCHES_PER_LANGUAGE` | none | Dictionary searches per language per UTC day, for everyone together |
| `DAILY_SIGNUP_LIMIT` | none | New accounts per UTC day |
| `ACCOUNT_TTL_HOURS` | none | Accounts older than this are logged out and deleted at the next signup |
| `MAX_WORDS_PER_USER` | none | Saved words per account |
| `SENTRY_DSN` | none | Report errors to Sentry; unset sends nothing |
| `SENTRY_ENVIRONMENT` | `local` | Environment name on Sentry events |

The production values that are not secret are in [deploy/personal.env.yaml](deploy/personal.env.yaml) and [deploy/demo.env.yaml](deploy/demo.env.yaml). Secrets are kept in Google Secret Manager and are never part of the repository or the image.

## Testing

```bash
pytest                 # all tests
pytest tests/unit      # unit tests only, no database or Redis needed
pytest --cov           # with a coverage report (configured in .coveragerc)
```

- **Unit tests** cover the pure logic: scoring, spaced repetition, hints, multiple-choice options, word selection, schemas and the Merriam-Webster parsing.
- **API tests** call the app over HTTP and need PostgreSQL and Redis from `docker compose up -d`. They create a separate `language_app_test` database and run every migration on it, so the migrations are tested too. Each test runs in a transaction that is rolled back afterwards, and Redis database 15 is flushed after each test, so the development data is never touched.
- Tests always use the mock dictionaries, whatever `.env` says, and need no API keys.

Linting and formatting use [ruff](https://docs.astral.sh/ruff/), configured in `pyproject.toml`:

```bash
ruff check .           # lint
ruff format .          # format
```

New migrations are linted and formatted by ruff as Alembic writes them.

CI runs ruff and then the whole suite against PostgreSQL and Redis containers on every push and pull request. No type checker is configured yet.

## API overview

- **Authentication:** server-side sessions. Logging in stores a random session id in Redis and sends it in an `HttpOnly`, `SameSite=Lax` cookie. Sessions last 30 days and are extended while the user is active. Passwords are hashed with bcrypt.
- **Documentation:** OpenAPI at `/docs` and `/redoc` when `DOCS_ENABLED` is on.
- **Resource groups:**

  | Prefix | Purpose |
  | --- | --- |
  | `/auth` | Signup, login, logout, the current user, and public settings for the frontend |
  | `/words` | Dictionary search and the user's saved vocabulary |
  | `/games` | Listing games, and starting, answering and finishing game sessions |
  | `/users/me/game-settings` | Spaced-repetition settings and presets |

- **Errors:** services raise domain errors, and each router maps them to a status code, for example 404 for a word that does not exist, 409 for a word already saved, and 503 when the dictionary is unavailable. Request validation errors are 422.

The API is built for the Language Power frontend only. [docs/games.md](docs/games.md) documents the games endpoints from a client's point of view.

## Deployment

![Deployment diagram: the browser loads the React build from Netlify, which proxies /api/* to the API container on Google Cloud Run; the API uses Neon for PostgreSQL, Upstash for Redis, and the Merriam-Webster API.](docs/deployment.png)

The browser only ever talks to the Netlify origin, so the session cookie stays first-party (`SameSite=Lax`) and the API needs no CORS in production. Running a single instance keeps migrations on startup safe.

- The `Dockerfile` builds a slim Python 3.12 image that runs as a non-root user. On start, `docker-entrypoint.sh` applies the migrations, syncs the games and starts Uvicorn.
- `.github/workflows/ci.yml` runs ruff and the tests on every push and pull request.
- `.github/workflows/deploy.yml` is started by hand. It runs the tests, builds and pushes the image, deploys it to Cloud Run, and checks that the new revision answers. GitHub authenticates to Google Cloud through Workload Identity Federation, so no service account key is stored anywhere.
- The same image runs as two deployments, each in its own Google Cloud project with its own database, Redis and secrets: a private one (signup closed) and the public demo (open signup, `/docs` on, errors reported to Sentry). The workflow's `target` input picks one, and `deploy/<target>.env.yaml` holds its settings.

## Related projects

- Frontend: TODO add link
- [lp-monorepo](https://github.com/marusyaganza/lp-monorepo): second version, a TypeScript monorepo with a GraphQL server and a Storybook design system
- [language-power](https://github.com/marusyaganza/language-power) and [language-power-backend](https://github.com/marusyaganza/language-power-backend): first version, an English-only app with an Express REST API

## Limitations

- The deployment is private and signup is closed, so there are no demo credentials.
- Real dictionary lookups need your own Merriam-Webster API keys; mock mode only knows the recorded words.
- Hardening such as rate limiting and a health endpoint is planned but not done yet.
- The data model may still change.

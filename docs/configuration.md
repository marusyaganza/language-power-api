# Configuration

Settings are read from the environment, then from `.env`. Names are case-insensitive.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local `docker-compose.yml` database | PostgreSQL URL; must use the `postgresql+psycopg://` driver |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL; `rediss://user:password@host:port` for TLS |
| `USE_MOCKS` | `false` | `true` serves made-up dictionary entries (tests and local development); `false` calls the real Merriam-Webster API |
| `ENGLISH_API_KEY`, `SPANISH_API_KEY` | none | Merriam-Webster keys; required when `USE_MOCKS` is `false` |
| `SIGNUP_ENABLED` | `true` | Whether `POST /auth/signup` creates accounts |
| `COOKIE_SECURE` | `false` | Send the session cookie over HTTPS only; `true` in production |
| `SESSION_TTL_SECONDS` | 30 days | Session lifetime |
| `SESSION_COOKIE_NAME` | `session_id` | Name of the session cookie |
| `DOCS_ENABLED` | `true` | Serve `/docs`, `/redoc` and `/openapi.json`; `false` in production |
| `ROOT_PATH` | empty | The prefix a proxy strips before forwarding (`/api` behind Netlify), so `/docs` works through it |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON list of browser origins allowed to call the API; `[]` turns CORS off |
| `PROXY_SIGNATURE_SECRET` | none | Secret shared with the Netlify proxy: every route except `/health` then requires its `X-Nf-Sign` signature. Unset: nothing is checked (local development) |
| `LOGIN_ATTEMPT_LIMIT`, `LOGIN_ATTEMPT_WINDOW_SECONDS` | 5, 15 minutes | Login attempts per email (per IP and email where the IP is known); a successful login starts the count over |
| `SIGNUP_LIMIT`, `SIGNUP_WINDOW_SECONDS` | 30, 1 hour | Signups from everyone together |
| `SIGNUP_IP_LIMIT`, `LOGIN_IP_LIMIT` | 5, 30 | Signups and login attempts from one IP, in `SIGNUP_WINDOW_SECONDS` and `LOGIN_ATTEMPT_WINDOW_SECONDS`, where the IP is known (behind the signed proxy) |
| `REQUEST_IP_LIMIT`, `REQUEST_IP_WINDOW_SECONDS` | 300, 5 minutes | Requests from one IP to any route except `/health`, where the IP is known |
| `SEARCHES_PER_LANGUAGE` | none | Dictionary searches per language an account may make; unset: unlimited |
| `DAILY_SEARCHES_PER_LANGUAGE` | none | Dictionary searches per language per UTC day, for everyone together |
| `DAILY_SIGNUP_LIMIT` | none | New accounts per UTC day |
| `ACCOUNT_TTL_HOURS` | none | Accounts older than this are logged out and deleted at the next signup |
| `MAX_WORDS_PER_USER` | none | Saved words per account |
| `SENTRY_DSN` | none | Report errors to Sentry; unset sends nothing |
| `SENTRY_ENVIRONMENT` | `local` | Environment name on Sentry events |
| `SENTRY_RELEASE` | none | The release on Sentry events; the Docker image sets it to the commit it was built from |

The production values that are not secret are in [deploy/personal.env.yaml](../deploy/personal.env.yaml) and [deploy/demo.env.yaml](../deploy/demo.env.yaml). Secrets are kept in Google Secret Manager and are never part of the repository or the image.

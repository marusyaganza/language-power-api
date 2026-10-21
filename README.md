# py-lp

run the server

```
uvicorn main:app --reload
source venv/bin/activate
docker run -d --name redis-dev -p 6379:6379 redis:7-alpine
docker stop redis-dev
docker start redis-dev
docker rm -f redis-dev
docker compose up -d
docker exec -it postgres-dev psql -U app_user -d language_app
```

Seed games DB (run each time after changing `seed_data.py`):

```
python3 -m games.seed
```

```bash
# generate a migration by diffing your models against the current DB schema
alembic revision --autogenerate -m "add games and game_languages tables"

# review the generated file in alembic/versions/ before applying —
# autogenerate is good but not infallible (enums, JSONB defaults, etc. are worth a glance)

# then apply it
alembic upgrade head
```

Running DB locally for development (Postgres and Redis):

```
docker compose up
```

Connect to the DB:

```
docker exec -it postgres-dev psql -U app_user -d language_app
```

docker exec -it <your-redis-container-name> redis-cli

> KEYS game_session:\*
> GET game_session:<the-session-id-you're-testing-with>

## Tests

```
pip install -r requirements-dev.txt
pytest                 # run all tests
pytest tests/unit      # unit tests only (no DB or Redis needed)
pytest --cov           # with a coverage report (config in .coveragerc)
```

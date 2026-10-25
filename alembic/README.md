# Migrations

Alembic migrations for the PostgreSQL schema. Commands run from the project root.

## How it is configured

- `env.py` takes the database URL from `settings.database_url`, so migrations always run against the same database as the app. The `sqlalchemy.url` in `alembic.ini` is a placeholder and is never used.
- Migrations run through the same async driver as the app (`postgresql+psycopg`).
- `env.py` imports every module that defines models (`users.models`, `words.models`, `games.models`). A new model module must be added there too. Otherwise autogenerate does not see its tables and writes a migration that drops them.

## Adding a migration

```bash
alembic revision --autogenerate -m "describe the change"
```

Read the generated file before applying it. Autogenerate compares the models with the database schema, so it does not write data changes, and it does not detect check constraints. Then apply it:

```bash
alembic upgrade head
alembic check   # reports any difference left between the models and the database
```

## Conventions

- One change per migration, with a message that says what it does.
- Data fixes are written in SQL inside the migration, next to the schema change that needs them. For example, `a974a89d47e4` corrects existing genders before it adds the constraint that requires valid ones.
- `downgrade()` undoes the schema change. When a data fix cannot be undone, its docstring says so.
- Constraints declared in `__table_args__` are named (`ck_...`, `uq_...`), so a later migration can drop them by name.

## Where migrations run

- **Locally:** `alembic upgrade head` by hand, then `python -m games.seed`.
- **Tests:** the API tests create an empty `language_app_test` database and run every migration on it, so a broken migration fails the test run.
- **Production:** `docker-entrypoint.sh` runs `alembic upgrade head` each time the container starts. This is safe because the service runs as a single instance.

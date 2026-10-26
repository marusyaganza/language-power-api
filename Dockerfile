# The API image. Configuration comes from environment variables (see
# settings.py); the image itself holds no secrets.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# psycopg (without the [binary] extra) loads the system libpq at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# The commit the image is built from, reported to Sentry as the release.
# deploy.yml passes it; a local build without it reports no release.
ARG GIT_SHA=""
ENV SENTRY_RELEASE=$GIT_SHA

RUN useradd --system --uid 10001 --no-create-home app
USER app

# Cloud Run sets PORT; 8080 is its default and the fallback for local runs.
ENV PORT=8080
EXPOSE 8080

CMD ["./docker-entrypoint.sh"]

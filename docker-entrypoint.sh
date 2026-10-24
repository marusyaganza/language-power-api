#!/bin/sh
# Bring the database up to date, then serve the API.
#
# Migrations run on every start. That is safe because there is only ever one
# instance (Cloud Run --max-instances=1); with more, two could migrate at once.
set -e

alembic upgrade head
python -m games.seed

# --proxy-headers with any forwarding IP: only the platform's own proxy can
# reach the container, so X-Forwarded-For/-Proto can be trusted.
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8080}" \
    --proxy-headers \
    --forwarded-allow-ips='*'

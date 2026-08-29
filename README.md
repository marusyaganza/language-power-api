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
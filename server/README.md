# Homing server

FastAPI API (and, soon, the worker that runs the agents). See the [architecture](../docs/01-architecture.md) and [API](../docs/07-api.md) docs.

```bash
python -m pip install uv          # once
cp .env.example .env              # fill in DATABASE_URL and PROXY_SECRET
python -m uv sync
python -m uv run alembic upgrade head
python -m uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
python -m uv run pytest
python -m uv run ruff check . && python -m uv run ruff format --check .
```

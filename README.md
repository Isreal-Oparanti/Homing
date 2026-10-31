# Homing

**Save anything to use now or later.**

Homing answers four questions about every save: *What is it? Is it true? What's it for? When will you need it?* Then it brings the save back when it's needed.

Built for the Meta Global AI Developer Hackathon (Indie track) on Meta's Muse Spark, Muse Voice Transcribe and Muse Spark Open.

> This README is a placeholder. The judges' version (what it does, how to run it, how well it works, limits) is written on Tue 3 Nov.

## Run it locally

```bash
# server (needs Postgres with pgvector: docker compose up -d db, or a Supabase dev database)
cd server
python -m pip install uv
cp .env.example .env
python -m uv sync
python -m uv run alembic upgrade head
python -m uv run uvicorn app.main:app --reload --timeout-graceful-shutdown 3

# web
cd web
npm install
cp .env.example .env.local
npm run dev
```

## For developers

- What we're building and why: [docs/PLAN.md](docs/PLAN.md)
- How it's built: [docs/README.md](docs/README.md)

## Origin

Homing is built by Crowscap. The idea comes from Crowscap, Isreal Oparanti's personal memory product. This repository is new code written during the hackathon. No code was copied from the original Crowscap.

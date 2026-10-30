# ADR 0001: Stack

**Status:** accepted · 30 Oct 2026

## Context
We're one developer with four and a half days. We need a clean UI, Python for AI and ingestion work, and something Isreal is already fast in.

## Decision
- **Web:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui, deployed on Vercel.
- **Server:** Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 (sync) + Alembic + psycopg 3. One Docker image, run as two processes (`api`, `worker`).
- **Data:** Postgres (Supabase) and object storage (Supabase Storage).
- **Tooling:** `uv` for Python dependencies, npm for web. Exact pins everywhere.

## Consequences
- Two languages, but each does what it's best at.
- Sync SQLAlchemy is simpler to debug. We get concurrency from worker threads, since agents mostly wait on the network.

## Rejected
- **Full-stack Next.js only:** weaker for PDF, audio and HTML extraction, and the Python AI libraries.
- **Async SQLAlchemy:** more failure modes, and no real benefit at our scale.

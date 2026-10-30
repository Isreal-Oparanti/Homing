# 12 · Dev workflow

## Repository layout

```
crowscap-hackathon/
  README.md                  # for judges: what, how to run, Meta models, limits (written Tue)
  Makefile                   # dev, test, lint, fmt, migrate, seed
  docker-compose.yml         # local Postgres
  docs/                      # this folder
  web/                       # Next.js app
    app/                     # routes (see 08)
    components/              # SaveCard, TodayCard, TeamFeed, … ; ui/ = shadcn copies
    lib/                     # api.ts (typed client + case mapping), auth.ts, events.ts, dates.ts
    public/manifest.webmanifest
  server/
    pyproject.toml           # uv-managed, exact pins in uv.lock
    Dockerfile
    alembic.ini
    app/
      main.py                # FastAPI app factory, routers, lifespan (optional in-process worker)
      worker.py              # job runner + scheduler entry
      core/                  # config (pydantic-settings), logging, errors, auth (proxy check), rate_limit
      db/
        models/              # one file per table group
        repo/                # user-scoped data access
        session.py
        migrations/
      schemas/               # api.py (request/response), agents.py (Reading, ProposedCheck…), common.py
      api/v1/                # health, me, uploads, saves, imports, threads, today, cards, moments, team, events, search, asks, audits, feedback, admin
      agents/                # what_is_it.py, is_it_true.py, whats_it_for.py, when_needed.py, base.py
      search/                # embed.py (local ONNX model), hybrid.py (words + meaning + RRF)
      ask/                   # answer.py (candidates → pick → answer → verify)
      audit/                 # run.py, items.py
      ingest/                # fetch.py (SafeFetcher), urls.py, youtube.py, x.py, meta_embed.py, tiktok.py, web.py, pdf.py, image.py, audio.py, video.py
        whatsapp/            # parser.py, importer.py
      verify/                # quotes.py, dates.py, status.py, eligibility.py, verdict.py, sources.py, secrets.py, timestamps.py, citations.py, data/
      llm/                   # gateway.py, providers.py, cache.py, budget.py, video.py, search.py, prompts/
      jobs/                  # queue.py, runner.py, scheduler.py, kinds.py
      storage/               # base.py, local.py, supabase.py
      events/                # emitter.py, stream.py
      scripts/               # seed_demo.py, export_user.py, ops.sql
    tests/                   # see 11
```

**Module rules:**
- **Dependencies run one way:** `api → agents/ask/audit → search/verify/ingest/llm → db/repo`. `verify/` imports nothing from the app except schemas.
- **Small files.** If a file passes about 400 lines, split it.
- **One public function per job kind** in `agents/`. Helpers stay private (`_name`).

## Local setup

```bash
# once
cp server/.env.example server/.env      # fill META_*, YOUTUBE_API_KEY…
cp web/.env.example web/.env.local
docker compose up -d db                 # Postgres 16 on :5432
cd server && uv sync && uv run alembic upgrade head
cd ../web && npm ci

# every day
make dev        # api :8000 (with in-process worker) + web :3000
make test-unit  # fast
```

## Conventions

**Python:**
- 3.12, type hints everywhere.
- `ruff` (lint + format, line length 100) and `mypy --strict` on `verify/` and `ingest/whatsapp/` only. Those modules must be fully correct; elsewhere strictness would slow us down.
- Pydantic v2 for every boundary: API, model outputs and JSON columns.
- SQLAlchemy 2.0 typed `Mapped[]` models; sync sessions; `psycopg` 3.
- No `print`. Use `log.info("event_name", key=value)` with structured logging.

**TypeScript:**
- `strict: true`, ESLint + Prettier. Server components by default; `"use client"` only where needed.
- API types live in `web/lib/api.ts`, hand-written to mirror `schemas/api.py`. Keep them in sync in the same commit.

**Naming:** use the [vocabulary](01-architecture.md#vocabulary). The agent IDs are `what`, `true`, `for` and `when`.

**Errors:**
- Python: raise `AppError(code, message, status)`, where `message` is plain language for the user.
- TypeScript: show `error.message` from the API, never a stack trace.

**Feature flags:** read from config; checked in agents and the UI; documented in [10](10-deployment-ops.md#environment-variables).

## Git

- **Branch:** work on `main`. We're solo and the deadline is short.
- **Commits:** small, with conventional prefixes: `feat(agents): …`, `fix(verify): …`, `docs: …`, `test: …`, `chore: …`.
- **Commit locally. Push only when Isreal says so.**
- **Commit trailers:** commits are Isreal's own, so no `Co-Authored-By` lines.
- **Before each commit:** `make lint test-unit`, and update the docs touched by the change.

## Definition of done (per feature)

1. It works end to end on the demo user, in the browser.
2. The unit tests for its pure logic exist and pass.
3. The UI states are all handled: empty, loading, partial, error and private.
4. It emits `agent_events` with evidence (for agent work).
5. The docs are updated, and PLAN.md if scope changed.

## What we kept and changed from today's Crowscap

We reuse *approaches*, not code. This repo is new code written during the event.

| Area | Kept (approach) | Changed |
|---|---|---|
| Auth | Next.js session + proxy route + shared secret + user headers | Constant-time comparison; demo login provider |
| Background work | Job rows in Postgres + worker loops | A proper claim with `SKIP LOCKED`, priorities, dedupe keys and a separate worker process |
| Model output | JSON output + Pydantic validation + label normalisers | One gateway with cache, budget and purposes |
| Link previews | oEmbed providers (YouTube, X, TikTok) + Open Graph fallback via trafilatura | Instagram and Facebook embeds only, never scraped |
| Fetching | Public-IP checks, size caps, robots, retries | Re-check on every redirect; re-check after connect |
| Privacy | PII masking (emails, phones, IDs, Luhn) | Secret screen makes saves private and keeps them away from models |
| Live updates | SSE relayed through a Next.js route with a long timeout | Resume with `Last-Event-ID` from a stored events table |
| YouTube | Data API + oEmbed metadata | **Dropped** `yt-dlp` and `youtube-transcript-api` (platform rules) |
| Dependencies | — | **Exact pins.** No `"latest"` |
| Code size | — | **Small modules.** No 5,800-line service files |
| Chat | Asking about your saves, and auditing them (the belief-audit idea) | **No chat thread or router.** Ask gives one verified answer page per question; Audit is a job that produces a report |
| Search | Meaning-based search (Crowscap used pgvector) | Hybrid words + meaning; a local open embedding model instead of a cloud embeddings API |

# Homing server

The API and the agents behind [Homing](../README.md). Python 3.13, FastAPI, SQLAlchemy 2, Postgres (with pgvector) as both the database and the job queue. Every model call goes to Meta's models (Muse Spark, Muse Wonder, Muse Voice Transcribe) through one gateway.

Two processes run from this folder:

| Process | Command | Does |
|---|---|---|
| **API** | `uvicorn app.main:app` | HTTP API for the web app, live agent steps over Server-Sent Events, the calendar feed |
| **Worker** | `python -m app.worker` | Runs the agents: takes jobs from the Postgres queue, three threads, one long web job at a time |

## Quickstart

```bash
python -m pip install uv                  # once
cp .env.example .env                      # set DATABASE_URL, PROXY_SECRET, META_API_KEY
python -m uv sync
python -m uv run alembic upgrade head     # create the tables
python -m uv run uvicorn app.main:app --reload --timeout-graceful-shutdown 3   # http://127.0.0.1:8000/docs
python -m uv run python -m app.worker     # in a second terminal: the agents
```

Postgres with pgvector: `docker compose up -d db` from the repo root, or a Supabase project (use the Session pooler URI).

## Layout

```
app/
  main.py            FastAPI app: routers, error handling, CORS
  worker.py          the worker process: job runner + Keep watching schedule
  api/v1/            HTTP endpoints (saves, threads, today, finds, search, team, me, calendar)
  agents/            the agents, one module each
    what_is_it.py      reads a save (Muse Spark, Voice Transcribe)
    is_it_true.py      checks it against its source; code judges eligibility
    source_agent.py    Muse Wonder finds the official page (tools + code gate)
    whats_it_for.py    places a save in a goal
    finds_more.py      Muse Wonder looks on the web for more for a goal (plan, memory, gate)
    goal_memory.py     what a goal's runs remember: searches, refusals, keeps, dismissals, lessons
    web_tools.py       web_search / open_page tools: refs only, ranked links, trimmed context
    when_needed.py     when a save comes back
    today.py           Today's cards and moments
    prep.py            prep sheets from saved videos, each point at its second
    keep_watching.py   5 am and 5 pm: re-read pages that can change; find more for active goals
  verify/            code that checks the models: quotes, numbers, dates, eligibility, closed pages
  llm/               the model gateway (budgets, cache, credits) and versioned prompts
  ingest/            safe fetching (public addresses only, robots.txt), page and file reading
  search/            hybrid search (full text + pgvector) and Ask (Muse Wonder agent)
  jobs/              the Postgres job queue (SKIP LOCKED), runner, retries
  db/                models and Alembic migrations
  scripts/           one-off tools (below)
evals/               the evaluation: fixed test sets and real runs -> REPORT.md
tests/               pytest suite (unit and integration)
```

## How a save moves through the agents

```
POST /api/v1/saves
  -> save.read     What is it?        Muse Spark (and Voice Transcribe)
  -> save.check    Is it true?        Muse Wonder finds the source, Muse Spark compares, code verifies
  -> save.place    What's it for?     Muse Spark places it; an opportunity queues goal.find
  -> save.when     When will you need it?   code reads the deadline in the person's time zone
goal.find          Muse Wonder: plan, search, open, propose; code keeps only what it can prove
watch.tick         5 am / 5 pm Lagos: queues watch.user for active people, then the next tick
```

Every step is written to `agent_events` with the models that did it, and streamed live to the web app.

## Configuration

All settings are environment variables (see `.env.example`; full meanings in [docs/10-deployment-ops.md](../docs/10-deployment-ops.md)).

| Variable | What it's for |
|---|---|
| `DATABASE_URL` | Postgres with pgvector |
| `TEST_DATABASE_URL` | Integration tests: each run uses a throwaway schema |
| `PROXY_SECRET` | Shared with the web app's server-side proxy (the only caller) |
| `META_API_KEY`, `META_API_BASE` | Meta's model API |
| `META_SPARK_MODEL`, `META_TRANSCRIBE_MODEL` | Model ids (defaults: `muse-spark-1.3`, `muse-voice-transcribe-1.0`) |
| `SEARCH_PROVIDER`, `SEARCH_API_KEY` | Web search for the web agents (Serper) |
| `YOUTUBE_API_KEY` | Video titles and descriptions (YouTube Data API) |
| `STORAGE_BACKEND`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `STORAGE_BUCKET` | Where uploaded files live (`local` or a private Supabase bucket) |
| `MODEL_DAILY_TOKEN_BUDGET`, `MODEL_USER_DAILY_TOKEN_BUDGET` | Daily token caps, in total and per person |
| `WORKER_THREADS`, `SPARK_MAX_CONCURRENCY` | Worker threads; concurrent model calls |

The shared demo account and the web agents have their own smaller budgets (`app/core/config.py`), so a busy day can never pause reading or Ask.

## Tests and checks

```bash
python -m uv run pytest                          # 250+ tests; integration tests need TEST_DATABASE_URL
python -m uv run ruff check . && python -m uv run ruff format --check .
python -m uv run python -m evals.run             # writes evals/REPORT.md
```

Tests never call the real models or the web: the agents' factories are swapped for fakes in `tests/conftest.py`. CI runs the whole suite against a pgvector Postgres service on every push ([.github/workflows/ci.yml](../.github/workflows/ci.yml)).

## Scripts

| Command | Does |
|---|---|
| `python -m app.scripts.reset_demo --snapshot` / `--reset` | Record the demo account's clean state / put it back (removes what visitors added, adds a moment for tomorrow) |
| `python -m app.scripts.smoke_meta` | Check what Meta's models can read, and in which request shape (images, PDFs, video, JSON output) |
| `python -m app.scripts.setup_storage` | Create the private storage bucket and copy in files saved locally |
| `python -m app.scripts.embed_pile <user_id \| all>` | Embed saves for search by meaning (new saves are embedded as they're read) |
| `python -m app.scripts.fetch_captions` | Fetch YouTube captions from a home connection (YouTube blocks cloud servers) |
| `python -m app.scripts.reread_kept <user_id>` | Read again the files that were only kept (videos, voice notes, documents), then organise the pile again |
| `python -m evals.record_pages` | Record the real pages the finds-gate eval uses |

## Deploy

The live API and worker run on one EC2 instance behind Caddy, as two systemd services; `deploy/ec2/update.sh` pulls and installs, and the API runs `alembic upgrade head` as it starts. See [deploy/](../deploy) and [docs/10-deployment-ops.md](../docs/10-deployment-ops.md).

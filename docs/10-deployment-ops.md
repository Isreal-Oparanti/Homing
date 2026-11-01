# 10 · Deployment and operations

## Environments

| Env | Web | API + worker | Database and storage | Notes |
|---|---|---|---|---|
| `local` | `npm run dev` on :3000 | `uvicorn` on :8000, worker inside the API (`RUN_WORKER_IN_API=true`) | Postgres (Docker or a Supabase dev database); storage on the local disk (`STORAGE_BACKEND=local`) | see [12-dev-workflow.md](12-dev-workflow.md#local-setup) |
| `prod` | Vercel (functions in Paris) | AWS `eu-west-3` (Paris): one container with the worker inside (`RUN_WORKER_IN_API=true`); split into `api` and `worker` later if needed | Supabase (Postgres + Storage) | See [ADR 0007](adr/0007-hosting.md) |

There's no staging environment, because there's no time. Use feature flags and the demo user instead.

## Hosting (from ADR 0007)

- **Web:** Vercel, linked to the GitHub repo, root `web/`.
- **API and worker:** AWS in `eu-west-3` (Paris, next to Supabase), one container from `server/Dockerfile`, worker inside the API. Two containers (`api`, and `worker` started with `python -m app.worker`) remain an option.
  - **Fallback:** a VM with Docker Compose and Caddy (for example the existing Crowscap server, if it's still running and has room).
- **Postgres and Storage:** Supabase project `crowscap-hack` (free tier). Bucket `saves`, private.
- **Muse Spark Open:** a Baseten (or Modal) deployment of `meta-models/muse-spark-open-1026`, using partner credits **(confirm)**.

## Environment variables

**Web (`web/.env.example`):**
```
NEXTAUTH_URL=
NEXTAUTH_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
DEMO_LOGIN_ENABLED=true
HOMING_API_URL=            # https://api.<domain>
HOMING_PROXY_SECRET=
```

**Server (`server/.env.example`):**
```
ENV=prod
DATABASE_URL=                # Supabase Session pooler URI, pasted as shown (postgresql://… is converted)
TEST_DATABASE_URL=           # same project; tests create and drop their own schema
DB_POOL_SIZE=5               # per process; the free tier has few pooled connections
DB_MAX_OVERFLOW=2
PROXY_SECRET=
ADMIN_TOKEN=
STORAGE_BACKEND=supabase     # local|supabase
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
STORAGE_BUCKET=saves
RUN_WORKER_IN_API=false
WORKER_THREADS=3             # each thread holds a DB connection, so keep below DB_POOL_SIZE

META_API_BASE=https://api.meta.ai/v1
META_API_KEY=
META_SPARK_MODEL=muse-spark-1.3
META_TRANSCRIBE_MODEL=muse-voice-transcribe-1.0
SPARK_OPEN_BASE=
SPARK_OPEN_KEY=
SPARK_OPEN_MODEL=
VIDEO_MODE=chapters_only
SEARCH_PROVIDER=
SEARCH_API_KEY=
YOUTUBE_API_KEY=
EMBED_MODEL=intfloat/multilingual-e5-small
EMBED_DIM=384

MODEL_DAILY_TOKEN_BUDGET=5000000
MODEL_USER_DAILY_TOKEN_BUDGET=1500000
STORAGE_DIR=data/storage        # local backend only
SUPABASE_URL=                    # supabase backend: project URL
SUPABASE_SERVICE_KEY=            # supabase backend: service role key (server only)
STORAGE_BUCKET=saves             # private bucket
SEARCH_PROVIDER=serper
SEARCH_API_KEY=                  # serper.dev key (rotate before launch)

# Feature flags (kill switches)
FEATURE_CHECKS=true
FEATURE_SEARCH_FOR_SOURCES=true
FEATURE_VOICE=true
FEATURE_VIDEO=true
FEATURE_RECHECK=true
FEATURE_PREP=true
FEATURE_ASK=true
FEATURE_AUDIT=true
```

## Docker image (`server/Dockerfile`)

- Base `python:3.12-slim`, plus `ffmpeg` (voice notes) and `libmagic` (type sniffing).
- Dependencies installed with `uv` from a lock file. Runs as a non-root user.
- The embedding model (`EMBED_MODEL`, ONNX) is downloaded **at build time** into `/models`, adding about 200 MB. Both `api` (query embeddings for search) and `worker` (save embeddings) load it once at startup.
- **Start commands:**
  - `api`: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2 --timeout-graceful-shutdown 10`
  - `worker`: `python -m app.worker`
- Healthcheck: `GET /health`.

## First deploy, as done (1 Nov)
- **Settings files:** `server/.env.production` and `web/.env.vercel` (git-ignored) hold every production variable, with production's own `PROXY_SECRET`, `ADMIN_TOKEN` and `NEXTAUTH_SECRET`. The first goes to the AWS container, the second into Vercel's variable editor.
- **One database:** development and production share the Supabase database, so the demo pile is already there. Files must therefore live in the bucket in both: run `python -m app.scripts.setup_storage` once (creates the private `saves` bucket, copies local files in, reads each back), then set `STORAGE_BACKEND=supabase` locally too.
- **While the local server runs,** its worker also takes jobs from production's queue. Stop it once judging starts.
- **Uploads** skip Vercel with an upload ticket ([07](07-api.md#conventions)), so Vercel's 4.5 MB limit doesn't apply.

## Deploy steps

1. Push to `main`. Vercel builds `web/`; the API image is built from `server/` and deployed to AWS. **Only when Isreal says push.**
2. The `api` service runs `alembic upgrade head` before starting. Migrations must be backwards-compatible with the running worker: add columns first, use them later.
3. `worker` restarts. Running jobs are picked up again after 15 minutes if they were cut off ([03](03-agents.md#job-catalogue)).
4. Smoke test after deploy:
   - `GET /health/deep`;
   - sign in as the demo user;
   - add one link;
   - watch four answers arrive in the save card;
   - check that The team shows events;
   - search "YC" and confirm a "Y Combinator" save comes up;
   - ask one question and confirm the answer page has verified citations.

**First-time setup:**
- Supabase (project **Homing**, `eu-west-3`, free tier):
  - **Connection:** use **Connect → Session pooler** for `DATABASE_URL` and `TEST_DATABASE_URL`. The direct connection is IPv6-only on the free tier and fails on many Nigerian networks. If the password has `@`, `:` or `/`, URL-encode it.
  - **Later, for production:** the Transaction pooler (port 6543) also works, because the server turns off prepared statements.
  - **Extensions:** the first migration enables `vector` and `pg_trgm`.
  - **Storage:** create the private `saves` bucket (S7).
  - **Data API:** turn it off in project settings, or at least make sure every table has RLS on. Every migration enables RLS ([02](02-data-model.md)), because we never use Supabase's REST API.
- Google OAuth: add the redirect URL `https://<web>/api/auth/callback/google`.
- AWS: one container in `eu-west-3` (Paris) from `server/Dockerfile`, with HTTPS.
- Vercel: create the project and set the env vars.
- Seed the demo data with `python -m app.scripts.seed_demo --from <export.zip>`.

## Observability

- **Logs:** JSON lines with `ts, level, event, request_id, job_id, user_id, purpose, latency_ms`. No content (see [09](09-security-privacy.md#secret-screen)).
- **`/health/deep`** reports DB latency, storage reachability, the oldest queued job's age (`queue_lag_s`), jobs failed in the last hour, and model spend today.
- **Admin queries** (`server/app/scripts/ops.sql`):
  - stuck jobs;
  - failures by kind;
  - spend by purpose;
  - events per user over the last hour.
- **Errors:** Sentry free tier on web and server if set up in under 20 minutes. Otherwise, logs only.

## Runbook

| Symptom | Check | Fix |
|---|---|---|
| Save card stuck on "Working on it…" | `queue_lag_s` in `/health/deep`; jobs `running` > 15 min | Restart `worker`; stuck jobs requeue themselves. If `queue_lag_s` keeps growing, lower `WORKER_THREADS` (rate limits) or pause imports. |
| Many `invalid_output` model calls | `model_calls` grouped by purpose and status | Look at one failing output; bump the prompt version with a clearer schema; redeploy. |
| 429s from Meta | `model_calls.error` | Lower `SPARK_MAX_CONCURRENCY`. Backoff already applies. |
| Budget exceeded | A "Paused reading" line in The team; save cards say "Paused until tomorrow" | Raise `MODEL_DAILY_TOKEN_BUDGET` or `MODEL_USER_DAILY_TOKEN_BUDGET` if credits allow; otherwise paused reads carry on just after midnight UTC. |
| Checks all `couldnt_confirm` | Search provider errors; official pages 403 | Set `FEATURE_SEARCH_FOR_SOURCES=false` and rely on post links; tell the user plainly. |
| Live feed not updating | Browser devtools EventSource; `/api/stream` status | Vercel function timeout (reconnect is automatic); check `HOMING_API_URL`. |
| Upload fails | Signed URL expired; bucket policy | Re-sign; check the bucket is private and the service key is set. |
| Voice notes fail | ffmpeg present? Transcribe endpoint errors | Set `FEATURE_VOICE=false` for the demo; note it in the README. |
| Demo user looks wrong | Seed version | `POST /api/v1/admin/demo/reset` |
| Search misses obvious saves | `save_embeddings` count vs ready saves; `save.embed` failures | Re-enqueue `save.embed` for missing rows (`scripts/reembed.py`); check that `EMBED_MODEL` loaded at startup |
| Answer pages come back nearly empty | `model_calls` dropped-citation counts for `ask.answer` | The prompt isn't quoting exactly: tighten it (new prompt version). Check that the candidates actually contain the relevant saves. |

## Backups

The Supabase daily backup is enough. Before recording the demo, export the demo user's data (`scripts/export_user.py`), so the recording can be redone exactly.

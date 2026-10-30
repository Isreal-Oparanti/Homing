# 10 · Deployment and operations

## Environments

| Env | Web | API + worker | Database and storage | Notes |
|---|---|---|---|---|
| `local` | `npm run dev` on :3000 | `uvicorn` on :8000, worker inside the API (`RUN_WORKER_IN_API=true`) | Postgres in Docker; storage on the local disk (`STORAGE_BACKEND=local`) | `make dev` starts everything |
| `prod` | Vercel | One Docker image, two services: `api` and `worker` | Supabase (Postgres + Storage) | See [ADR 0007](adr/0007-hosting.md) |

There's no staging environment, because there's no time. Use feature flags and the demo user instead.

## Hosting (from ADR 0007)

- **Web:** Vercel, linked to the GitHub repo, root `web/`.
- **API and worker:** Railway, two services from `server/Dockerfile` with different start commands.
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
CROWSCAP_API_URL=            # https://api.<domain>
CROWSCAP_PROXY_SECRET=
```

**Server (`server/.env.example`):**
```
ENV=prod
DATABASE_URL=                # postgresql+psycopg://…  (Supabase pooled, port 6543 for api; direct 5432 for migrations)
PROXY_SECRET=
ADMIN_TOKEN=
STORAGE_BACKEND=supabase     # local|supabase
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
STORAGE_BUCKET=saves
RUN_WORKER_IN_API=false
WORKER_THREADS=8

META_API_BASE=
META_API_KEY=
META_SPARK_MODEL=
META_TRANSCRIBE_MODEL=
SPARK_OPEN_BASE=
SPARK_OPEN_KEY=
SPARK_OPEN_MODEL=
VIDEO_MODE=chapters_only
SEARCH_PROVIDER=
SEARCH_API_KEY=
YOUTUBE_API_KEY=

MODEL_DAILY_BUDGET_USD=10
MODEL_USER_DAILY_BUDGET_USD=3

# Feature flags (kill switches)
FEATURE_CHECKS=true
FEATURE_SEARCH_FOR_SOURCES=true
FEATURE_VOICE=true
FEATURE_VIDEO=true
FEATURE_RECHECK=true
FEATURE_PREP=true
```

## Docker image (`server/Dockerfile`)

- Base `python:3.12-slim`, plus `ffmpeg` (voice notes) and `libmagic` (type sniffing).
- Dependencies installed with `uv` from a lock file. Runs as a non-root user.
- **Start commands:**
  - `api`: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`
  - `worker`: `python -m app.worker`
- Healthcheck: `GET /health`.

## Deploy steps

1. Push to `main`. Vercel builds `web/`, and Railway builds `server/`. **Only when Isreal says push.**
2. The `api` service runs `alembic upgrade head` before starting. Migrations must be backwards-compatible with the running worker: add columns first, use them later.
3. `worker` restarts. Running jobs are picked up again after 15 minutes if they were cut off ([03](03-agents.md#job-catalogue)).
4. Smoke test after deploy:
   - `GET /health/deep`;
   - sign in as the demo user;
   - add one link;
   - watch four answers arrive in the save card;
   - check that The team shows events.

**First-time setup:**
- Supabase: create the project and the private `saves` bucket.
- Google OAuth: add the redirect URL `https://<web>/api/auth/callback/google`.
- Railway: create two services from the repo.
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
| Budget exceeded | `/health/deep` spend | Raise `MODEL_DAILY_BUDGET_USD` if credits allow; otherwise imports wait until tomorrow. |
| Checks all `couldnt_confirm` | Search provider errors; official pages 403 | Set `FEATURE_SEARCH_FOR_SOURCES=false` and rely on post links; tell the user plainly. |
| Live feed not updating | Browser devtools EventSource; `/api/stream` status | Vercel function timeout (reconnect is automatic); check `CROWSCAP_API_URL`. |
| Upload fails | Signed URL expired; bucket policy | Re-sign; check the bucket is private and the service key is set. |
| Voice notes fail | ffmpeg present? Transcribe endpoint errors | Set `FEATURE_VOICE=false` for the demo; note it in the README. |
| Demo user looks wrong | Seed version | `POST /api/v1/admin/demo/reset` |

## Backups

The Supabase daily backup is enough. Before recording the demo, export the demo user's data (`scripts/export_user.py`), so the recording can be redone exactly.

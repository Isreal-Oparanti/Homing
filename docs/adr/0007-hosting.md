# ADR 0007: Hosting

**Status:** accepted · 1 Nov 2026. Isreal chose AWS for the API, for speed.

## Context
We need a live URL for judges, an always-on worker, no cold starts during the demo, and minimal setup time.

## Decision (proposed)
- **Web:** Vercel.
- **API and worker:** Railway, two services from one Docker image.
- **Postgres and Storage:** Supabase (free tier, already familiar from Crowscap).
- **Muse Spark Open:** Baseten or Modal with partner credits.

## Fallbacks
1. A VM (for example the existing Crowscap server, if it's still running) with Docker Compose (`api`, `worker`) and Caddy for HTTPS.
2. Render (paid background worker).
3. A single service with `RUN_WORKER_IN_API=true`, if only one service is possible.

## As built (1 Nov 2026)
- **API on AWS, not Railway** (Isreal, 1 Nov: for speed), in `eu-west-3` (Paris), the same region as the Supabase database. Every request makes several database round trips, so this is where most of the speed comes from.
- **Plain EC2, no Docker** (Isreal, 1 Nov): Python and `uv`, `ffmpeg`, two systemd services (`homing-api`, `homing-worker`) and Caddy for HTTPS at `homing-api.crowscap.xyz`. On one small server Docker would only add memory and slower deploys. Separate services mean restarting the API never cuts off a job. Files: `deploy/ec2/`.
- **Vercel functions** run in `cdg1` (Paris, `web/vercel.json`), next to the database.

## Consequences
Three or four vendors, each on a free or credit tier. Document every account in `docs/10-deployment-ops.md`.

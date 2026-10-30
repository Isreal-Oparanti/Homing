# ADR 0007: Hosting

**Status:** proposed · 30 Oct 2026. **Confirm with Isreal: payment cards and existing servers.**

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

## Consequences
Three or four vendors, each on a free or credit tier. Document every account in `docs/10-deployment-ops.md`.

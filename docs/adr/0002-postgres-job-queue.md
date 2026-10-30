# ADR 0002: Job queue in Postgres

**Status:** accepted · 30 Oct 2026

## Context
Agents run as background jobs with retries, priorities, delays and schedules. The current Crowscap planned Redis + Celery, but in practice ran job rows plus loops inside the process.

## Decision
A `jobs` table, claimed with `SELECT … FOR UPDATE SKIP LOCKED`. It has priorities, `run_after` for delays and backoff, `dedupe_key` (unique while queued or running), stuck-job recovery, and a scheduler loop that enqueues timed jobs idempotently.

## Consequences
- **Gains:** no extra service, transactional enqueue (save and job in one commit), and easy to inspect with SQL.
- **Costs:** polling (1s) and a ceiling of roughly hundreds of jobs a second. That's far above our needs.

## Rejected
- **Celery + Redis:** another service to host and pay for.
- **RQ, arq:** still need Redis.

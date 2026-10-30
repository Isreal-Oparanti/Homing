# ADR 0006: One model gateway

**Status:** accepted · 30 Oct 2026

## Context
There's $150 of credits, three model endpoints (Spark, Voice Transcribe, Spark Open), privacy routing rules, and a need to measure accuracy and cost.

## Decision
All calls go through `llm/gateway.py`, by **purpose**. Each purpose fixes the model, the versioned prompt, the Pydantic output schema and the timeout. The gateway enforces:
- the private-save and profile routing rules;
- caching by input hash;
- daily budgets;
- concurrency limits;
- retries and one repair call;
- a `model_calls` record for every call.

## Consequences
- **Gains:** re-running a job costs nothing; prompts are traceable; tests can replay recorded outputs.
- **Costs:** a little ceremony when adding a new call.

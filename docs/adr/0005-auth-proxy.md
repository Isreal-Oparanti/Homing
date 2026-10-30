# ADR 0005: Auth through the Next.js proxy

**Status:** accepted · 30 Oct 2026

## Context
This approach worked in the current Crowscap: Next.js owns the Google session, and the API trusts signed headers from the Next.js server only.

## Decision
- NextAuth (Google, plus a demo credentials provider).
- `/api/backend/[...path]` forwards requests with `X-Crowscap-Proxy-Secret` and the user headers.
- The API compares the secret in constant time and scopes every query by user ID.
- `/api/stream` relays SSE the same way.

## Consequences
- **Gains:** one auth system, no tokens in the browser, and no CORS.
- **Costs:** the proxy adds a hop, and Vercel's body and time limits apply. So uploads go direct to storage, and SSE reconnects with `Last-Event-ID`.

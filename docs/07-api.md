# 07 · API

FastAPI. Base path `/api/v1`. The API is called only by the Next.js server ([ADR 0005](adr/0005-auth-proxy.md)). Interactive docs are at `/docs` in development only.

## Conventions

- **Auth headers** (set by the Next.js proxy):
  - `X-Homing-Proxy-Secret`: must equal `PROXY_SECRET`, else 401;
  - `X-Homing-User-Id`, `X-Homing-User-Email`, `X-Homing-User-Name`.
- **JSON:** request and response bodies are Pydantic models in `server/app/schemas/api.py`. Field names are `snake_case`; the web app maps them to camelCase in `web/lib/api.ts`.
- **Slow work** returns `202 Accepted` with the created resource. Progress arrives over SSE.
- **Pagination** is cursor-based: `?cursor=<opaque>&limit=<≤100>` → `{items, next_cursor}`.
- **Errors** always look like this:
  ```json
  {"error": {"code": "save_not_found", "message": "That save doesn't exist.", "details": {}}}
  ```
  `message` is plain language and safe to show to the user.
- **Idempotency:** `POST /saves`, `POST /saves/file` and `POST /imports/whatsapp` accept an `Idempotency-Key` header (stored for 24h).
- **Rate limits** are per user (see [09](09-security-privacy.md#rate-limits)). Going over returns 429 with `Retry-After`.

## Endpoints

### Health
| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{status: "ok"}` (no auth) |
| GET | `/health/deep` | DB, storage and job-queue lag (proxy secret only) |

### Me and profile
| Method | Path | Body or query | Returns |
|---|---|---|---|
| GET | `/me` | — | `{id, email, name, tz, is_demo}` |
| PATCH | `/me` | `{tz?}` | user |
| GET | `/me/profile` | — | `Profile` |
| PUT | `/me/profile` | `Profile` | `Profile` |
| DELETE | `/me` | — | `204`, deletes all user data |

### Uploads
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/uploads/sign` | `{filename, mime, bytes}` | `{storage_key, upload_url, expires_at}` (signed PUT URL, 15 min) |

### Saves
| Method | Path | Body or query | Returns |
|---|---|---|---|
| POST | `/saves` | `{text}` (may contain links) | `202 Save` |
| POST | `/saves/file` | `{storage_key, note?}` | `202 Save` |
| GET | `/saves` | `?thread_id&status&cursor&limit` | `{items: SaveSummary[], next_cursor}` |
| GET | `/saves/{id}` | — | `SaveCard` |
| DELETE | `/saves/{id}` | — | `204` (also deletes snapshots and media) |
| PUT | `/saves/{id}/when` | `{kind: "date", at} \| {kind: "moment", moment_id} \| {kind: "none"}` | `When` (user override, `source=user`) |
| POST | `/saves/{id}/answer` | `{answer}` | `202`, re-runs the verdict with the answer stored on the profile or check |
| GET | `/saves/{id}/calendar.ics` | — | `text/calendar`: one event at `due_at`, with an alarm at `bring_back_at`. Description: title, next step, link back to the save card. |

`SaveCard`, the main read model behind the four answers:
```json
{
  "save": {"id": "…", "kind": "link", "platform": "web", "url": "…", "label": null, "saved_at": "…", "status": "ready", "visibility": "normal"},
  "what":  {"title": "Afreximbank internship call", "what": "Internship programme in Cairo for students aged 20–32.", "key_facts": {"…": "…"}} ,
  "true":  {"verdict": "needs_your_answer", "official_url": "…", "deadline": {"at": "…", "display": "Sat 31 Oct, 23:59 Lagos time", "tz_stated": false},
            "findings": [{"point": "It's on-site in Cairo.", "quote": "…", "kind": "left_out", "source_url": "…"}],
            "question": "Do you have a working knowledge of French?"},
  "for":   {"threads": [{"id": "…", "title": "Funding and opportunities", "position": 26}], "duplicate_of": null},
  "when":  {"kind": "date", "due_at": "…", "bring_back_at": "…", "explanation": "Closes tomorrow if the post is right."},
  "pending": ["true"]
}
```

`pending` lists the answers still being worked on, so the UI shows a skeleton for each. Until S4 ships, `true`, `for` and `when` are `null` and stay in `pending`. `save.text` is `null` for private saves, and `save.error` holds a plain message when reading failed.

### Imports
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/imports/whatsapp` | `{storage_key}` | `202 Import` |
| GET | `/imports/{id}` | — | `Import` with `counts` and `status` |

### Threads
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/threads` | — | `ThreadSummary[]` (title, count, last_saved_at, next_due) |
| GET | `/threads/{id}` | `?cursor` | `{thread, saves: SaveSummary[], next_cursor}` |
| PATCH | `/threads/{id}` | `{title?, summary?, archived?}` | `Thread` (sets `locked_by_user`) |
| POST | `/threads/{id}/merge` | `{into_thread_id}` | `Thread` |
| PUT | `/threads/{id}/saves/{save_id}` | — | add (user) |
| DELETE | `/threads/{id}/saves/{save_id}` | — | remove (remembered by **What's it for?**) |

### Today and cards
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/today` | — | `{cards: Card[], date}` (≤ 3 new, plus `later` cards that are due) |
| GET | `/cards/{id}` | — | `Card` (with `payload`, e.g. `PrepSheet`) |
| POST | `/cards/{id}/act` | `{action: "use" \| "dismiss" \| "later", later_until?}` | `Card` |

### Moments
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/moments` | `{text, at}` | `202 Moment` (matched by **When will you need it?**) |
| GET | `/moments` | — | upcoming moments |

### The team (feed)
| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/team` | `?cursor&limit&agent` | `{items: AgentEvent[], next_cursor}` |
| GET | `/events/stream` | header `Last-Event-ID` | SSE stream |

SSE format:
```
id: 18342
event: agent_event
data: {"id":18342,"agent":"true","action":"checked","summary":"Checked against apply.workable.com: 4 things the post left out.","save_id":"…","evidence":[…],"created_at":"…"}

event: save_updated
data: {"save_id":"…","answer":"true"}

event: card_new
data: {"card_id":"…"}

event: ask_ready          (also ask_progress {ask_id, step})
data: {"ask_id":"…"}

event: audit_ready
data: {"audit_id":"…"}

: keep-alive   (every 15s)
```

Server behaviour:
- The first frame is `id: <resume point>` plus `retry: 2000`, so the browser always has an id to resume from, even after a quiet stretch.
- Polls `agent_events WHERE user_id=? AND id>?` every 0.75s (cheap at our scale).
- Sends a keep-alive comment every 15s, and closes after 60 seconds. Long streams held up `uvicorn --reload` and deploys, which wait for open connections (found 31 Oct). Run uvicorn with `--timeout-graceful-shutdown` as well.
- The client reconnects with `Last-Event-ID` and gets everything after it. The web shows "Reconnecting" only if that takes more than 4s.

### Search (instant)
| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/search` | `?q&kind&thread_id&limit` | `SaveSummary[]` with `highlight` and `matched_by: ["words" \| "meaning"]` |

Hybrid search by words and meaning, merged with RRF ([02 · Search](02-data-model.md#search)). There's no model call, so it's fast enough for search as you type (debounce 250 ms).

### Ask (answer pages)
| Method | Path | Body or query | Returns |
|---|---|---|---|
| POST | `/asks` | `{question, follows_ask_id?, thread_id?}` | `202 Ask` (`status: queued`) |
| GET | `/asks/{id}` | — | `Ask` with `answer` once `ready` |
| GET | `/asks` | `?cursor` | your past questions |

`Ask.answer` uses the `Answer` shape in [02](02-data-model.md#asks). Each citation includes the save's title and a link to its save card. Progress events arrive over SSE (`ask_progress`, `ask_ready`).

### Audits
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/audits` | `{scope: "thread" \| "library", thread_id?}` | `202 Audit` |
| GET | `/audits/{id}` | — | `Audit` with `items` |
| POST | `/audits/{id}/items/{item_id}/act` | `{action: "merge" \| "archive" \| "recheck" \| "ignore"}` | `AuditItem` |

### Feedback (evals)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/feedback` | `{target, target_id, verdict, note?}` | `201` |
| GET | `/feedback/summary` | — | counts per target and verdict (used for the README numbers) |

### Dev (local only)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/dev/echo` | `{message?}` | `202 {job_id}`. Queues `system.echo`, whose event reaches `/events/stream` in about 1.3s (measured 31 Oct). Returns 404 unless `ENV=local`. |

### Demo (admin)
| Method | Path | Returns |
|---|---|---|
| POST | `/admin/demo/reset` | resets the demo user to the seed pile (needs `X-Admin-Token`) |

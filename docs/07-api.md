# 07 · API

FastAPI. Base path `/api/v1`. The API is called only by the Next.js server ([ADR 0005](adr/0005-auth-proxy.md)). Interactive docs are at `/docs` in development only.

## Conventions

- **Auth headers** (set by the Next.js proxy):
  - `X-Homing-Proxy-Secret`: must equal `PROXY_SECRET`, else 401;
  - `X-Homing-User-Id`, `X-Homing-User-Email`, `X-Homing-User-Name`.
  - **One exception, uploads (1 Nov):** `POST /saves/file` and `POST /imports/whatsapp` also take `Authorization: Bearer <upload ticket>`, so the browser can send files straight to the API (Vercel caps request bodies at about 4.5 MB). The web server's `POST /api/upload-ticket` signs `{uid, email, name?, exp}` with an HMAC key derived from `PROXY_SECRET`; a ticket lasts 5 minutes. CORS allows any origin for `POST` with `Authorization`, which gives nothing away because the API never reads cookies.
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
| GET | `/me/profile` | — | `Profile`: what Homing remembers from your answers |
| PUT | `/me/profile` | `{question_id, value}` (`value: null` forgets it) | `Profile`; every saved opportunity is re-judged |
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
| | | **As built (S7, ticket 1 Nov):** sent by the browser straight to the API with an upload ticket; multipart `files` (1–6 images, or one PDF, 10 MB each) plus an optional `note` | `202 Save`. The type is sniffed from the bytes (415 otherwise). Several images become one save read in order (screenshots of one thread). The same file twice is stored once (`media.sha256`). |
| GET | `/saves/{id}/files/{n}` | — | the owner's file `n` (image or PDF) for the card; 404 for anyone else |
| GET | `/saves` | `?thread_id&status&cursor&limit` | `{items: SaveSummary[], next_cursor}`. Each item also carries the reading's `title` and `what` when there is one. |
| GET | `/saves/{id}` | — | `SaveCard` |
| GET | `/saves/{id}/reveal` | — | `{text}`: the owner's own text, for a private save they tap to show. `Cache-Control: no-store`. Another user gets 404. |
| DELETE | `/saves/{id}` | — | `204` (also deletes snapshots and media) |
| PUT | `/saves/{id}/when` | `{kind: "date", at} \| {kind: "moment", moment_id} \| {kind: "none"}` | `When` (user override, `source=user`) |
| POST | `/saves/{id}/answer` | `{question_id, value}` | `{summary}`. The answer is stored on the profile (or on the check for `rule:N` questions), then every saved opportunity is re-judged by code. 422 if the answer doesn't fit the question. |
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

`pending` lists the answers still being worked on, so the UI shows a skeleton for each. Until S4 ships, `true`, `for` and `when` are `null` and stay in `pending`.

Also on the card:
- `copies`: our copy of the content, kept at save time: `[{id, kind, source_url, chars, excerpt}]`, with `kind` one of `page_text`, `post_text`, `transcript` or `metadata` and the excerpt capped at 1,500 characters. It's the proof behind "What is it?", and The team's evidence chips point here.
- For private saves, `save.text`, `save.url` and `save.label` are `null`. A key inside a link is one reason a save is private. The owner sees the text with `/reveal`.
- `save.error` holds a plain message when reading failed, or "Paused until tomorrow…" when the day's model budget is used up (`status` is then `received`).

As built in S4, the three answers differ slightly from the example above:
- **`true`:**
  - It adds `note` (plain words when there was nothing to check against), `deadline.source_text` and `checked_at`.
  - Findings are `{point, quote, kind}` with the source in `official_url`, and only verified findings are sent.
  - A save with nothing checkable gets `{"verdict": "nothing_to_check"}`.
- **`true` (S6):** it adds `rules` (`{rule, plain, quote, strength, result}`, verified only), `questions` (`{id, text, kind, options?}`, with `kind` one of `choice`, `yesno`, `year` or `country`) and `same_page` (the save is just a link to the official page).
- **`true` (S6 follow-ups, S7):**
  - `from_post`: no official page (or the link went to a different page), so `rules` quote the post itself and are marked "in the post, not confirmed".
  - `items`: for a save that lists several things, one entry per item: `{name, url, status, verdict, note, official_url, findings, rules, deadline, closed}`. Each item is checked on its own page, side by side.
  - `questions` on a list save are the profile questions its items need, asked once.
- **`save.files`:** how many images or PDFs the save has.
- **`for`:** each thread also has `count`, so the card can say "your 3rd save on this".
- **`when`:** it adds `source` (`check` or `reading`), `display` ("Sat 31 Oct, 23:59 Lagos time"), `source_text`, `tz_stated` and `time_stated`.
- **`pending`:** an answer is pending while its agent's job is queued or running. The "when" also waits on the check, because an official deadline beats a date in the post.

### Imports
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/imports/whatsapp` | `{storage_key}` | `202 Import` |
| GET | `/imports/{id}` | — | `Import` with `counts` and `status` |
| | | **As built (S8, 1 Nov):** `POST /imports/whatsapp` takes multipart `file` (the `.zip` or the chat `.txt`, up to 1 GB), sent by the browser straight to the API with an upload ticket. It waits in `IMPORT_DIR` on that machine until the job reads it, then it's deleted. `GET /imports` lists the latest 5. `counts`: `{messages, saves, media, private, duplicates, skipped, already, total, done}`. | |

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
| GET | `/today` | — | `{cards: Card[], date}` (≤ 3 new, plus `later` cards that are due). **Until S11:** dated saves due within 7 days, soonest first, as `{save_id, kind: "deadline", title, why_now, next_step, due_at, tz_stated, unconfirmed}`. `unconfirmed` means the date came from the post, not the official page. |
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

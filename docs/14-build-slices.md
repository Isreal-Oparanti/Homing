# 14 · Build slices

How we build Homing, piece by piece, in demo order. The day plan is in [PLAN §12](PLAN.md#12-build-plan); this doc breaks it into slices.

**A slice** is a piece of work that ends in something you can see working on real data. It's never "half the backend". Each slice lists:
- what it builds;
- **Done when**: the check we run on real data;
- **Proved by**: the tests that must pass;
- **If late**: what to drop first.

## How we work every slice

1. Read the slice and the docs it links.
2. Build the server part with its tests, then the web part.
3. Run the **Done when** check on real data. Not mocks.
4. Update the docs it touched, and remove any **(confirm)** marks we've now checked.
5. Commit with a conventional message. Push only when Isreal says so.

## Overview

| ID | Slice | Scene | Day | Hours | Priority |
|---|---|---|---|---|---|
| S0 | Model check | — | Fri | 1.5 | P0 |
| S1 | Foundations: tables, job queue, events, live stream | all | Fri–Sat | 4 | P0 |
| S2 | Sign-in, proxy and app shell | all | Sat | 3 | P0 |
| S3 | Add a save + **What is it?** (text and links) | Now | Sat | 5 | P0 |
| S4 | Rough answers for the other three questions + rough Today | all | Sat | 3 | P0 |
| S5 | First deploy | — | Sat | 2 | P0 |
| S6 | **Is it true?** in depth | Now | Sun | 7 | P0 |
| S7 | Files: images, flyers, PDFs, lists | Now | Sun | 2.5 | P0 |
| S8 | WhatsApp import | Past | Mon | 4 | P0 |
| S9 | **What's it for?** over the whole pile | Past | Mon | 3 | P0 |
| S10 | Search by meaning + **Ask** | anytime | Mon | 4 | P0 |
| S11 | **When will you need it?** + Today | Later | Tue | 4 | P0 |
| S12 | Prep sheet + reel | Later | Tue | 3.5 | P0 (reel P2) |
| S13 | Audit | anytime | Tue | 2 | P1 |
| S14 | Demo readiness | — | Tue | 2 | P0 |
| S15 | Polish and submit | — | Wed | — | P0 |
| X1 | Voice notes | Past | when ahead | 1.5 | P2 |
| X2 | Daily re-check | Later | when ahead | 1.5 | P2 |
| X3 | Android share-to-Homing | Now | when ahead | 1.5 | P2 |

About 60 hours of building in total. Friday night and Saturday are the heaviest, because the rough path through the whole demo has to exist before anything gets deep ([PLAN §15](PLAN.md#15-rules-to-come-back-to), rule 5).

## Checkpoints (go / no-go)

| When | Must be true | If not |
|---|---|---|
| **CP1 · Sat 23:00** | On the live URL: paste a link, and four rough answers appear on its save card while The team feed updates live | Drop Audit (S13) now; keep going on the demo path |
| **CP2 · Sun 23:00** | The "Now" scene works on at least 5 real opportunity posts, with verified quotes | Drop list checking from S7 and keep single posts |
| **CP3 · Mon 23:00** | The "Past" scene works on the full pile; Ask answers "How do I prepare for YC?" with verified points | Ask keeps only its answer points (no "disagree" or "out of date" sections) |
| **CP4 · Tue 18:00** | The "Later" scene works: deadline → Today → prep sheet | Prep sheet from chapters and titles only; no reel; record anyway |

---

## Phase A · The rough path (Fri–Sat)

### S0 · Model check
- **Day:** Fri evening · **Estimate:** 1.5h · **Depends on:** Meta API key and model IDs (Isreal)
- **Builds:** `server/app/scripts/smoke_meta.py`, a one-off script (not a test). It calls:
  - Muse Spark with text and JSON output;
  - Muse Spark with an image URL;
  - Muse Spark with a PDF;
  - Muse Spark with a **YouTube link** (one of the 16 demo videos);
  - Voice Transcribe on 5 real voice notes from the export with media.

  It prints the latency, tokens and output of each.
- **Done when:** we know:
  - the exact model IDs;
  - whether JSON schema output works;
  - how images, PDFs and videos are passed in (URL, base64 or Files API);
  - **whether YouTube links work**;
  - how the transcription endpoint behaves, and how well it handles Nigerian English and Pidgin.
- **Then:**
  - set `VIDEO_MODE`;
  - remove the **(confirm)** marks in [06-models.md](06-models.md);
  - note the per-call costs.
- **If late:** never skip it. Every later slice depends on these answers.

### S1 · Foundations: tables, job queue, events, live stream
- **Day:** Fri evening → Sat morning · **Estimate:** 4h · **Depends on:** a Postgres database (Supabase dev project)
- **Builds (server):**
  - **Migrations** for `saves`, `media`, `snapshots`, `readings`, `agent_events`, `agent_memory`, `jobs`, `imports` and `model_calls` ([02](02-data-model.md)).
  - **Data access:** `db/repo/` with user-scoped helpers.
  - **Job queue** (`jobs/`): `queue.py` (enqueue with a dedupe key, claim with `SKIP LOCKED`, complete, fail with backoff, requeue stuck jobs), `runner.py` (worker threads), `scheduler.py` (timed jobs) and `app/worker.py`. `RUN_WORKER_IN_API` starts the loops inside the API process for local runs.
  - **Events:** `events/emitter.py`, plus `GET /team` and the SSE endpoint `GET /events/stream` ([07](07-api.md#the-team-feed)).
  - A `system.echo` job kind, used only by tests and the S0–S2 checks.
- **Done when:** enqueueing `system.echo` leads to the runner running it, then an `agent_events` row, which `curl -N /api/v1/events/stream` shows within 2s. A second enqueue with the same dedupe key is ignored.
- **Proved by:**
  - unit tests: the backoff formula and the dedupe key rules;
  - integration tests against `TEST_DATABASE_URL`, covering claim and complete, a failure becoming a retry, a dead job after `max_attempts`, and stuck-job requeue ([11](11-testing-evals.md)).
- **If late:** leave the scheduler until S11. Timed jobs aren't needed before then.

### S2 · Sign-in, proxy and app shell
- **Day:** Sat · **Estimate:** 3h · **Depends on:** S1, and a Google OAuth client (Isreal)
- **Builds:**
  - **web:**
    - NextAuth: Google plus a "Try the demo" provider. Check which Auth.js version supports Next 16 **(confirm)**.
    - `app/api/backend/[...path]/route.ts`, the proxy that adds the secret and user headers.
    - `app/api/stream/route.ts`, the SSE relay that passes `Last-Event-ID` through.
    - `lib/api.ts` (typed client), `lib/events.ts` (`useEventStream`) and the TanStack Query provider.
    - The signed-in layout: glass bottom tabs (**Today · Threads · Ask · Team**) and a desktop sidebar.
    - Empty states for each screen, and a **Team** screen that renders events live.
  - **server:** create the user the first time we see them, in `/me`.
- **Done when:** signing in with Google, or with the demo login, lands on `/today`. Running `system.echo` makes an event appear live on `/team`. Signing out blocks `/today`.
- **Proved by:**
  - server: API test that `/me` creates the user once, and that user A can't read user B's events;
  - web: `npm run lint && npm run typecheck`.
- **If late:** the demo login only. Google sign-in moves to S14.

### S3 · Add a save + What is it? (text and links)
- **Day:** Sat · **Estimate:** 5h · **Depends on:** S1, S2, S0
- **Builds (server):**
  - **Endpoints:** `POST /saves`, `GET /saves`, and `GET /saves/{id}` returning the `SaveCard` view with `pending` ([07](07-api.md#saves)).
  - **Privacy:** `verify/secrets.py`, the secret screen, runs before anything is stored or sent.
  - **Fetching:** `ingest/urls.py` (canonical URLs) and `ingest/fetch.py` (`SafeFetcher`).
  - **Platform connectors:** `ingest/web.py`, `youtube.py`, `x.py`, `meta_embed.py` and `tiktok.py`.
  - **Model gateway** `llm/gateway.py` v1: purposes, cache, budget, `model_calls`, Pydantic validation plus one repair attempt. Purposes `read.text` and `read.batch_links`, with prompts v1.
  - `agents/what_is_it.py`: `read_one`, which writes a snapshot and a reading and emits `read`.
- **Builds (web):**
  - an **Add** sheet (paste);
  - the save card page `/saves/[id]` with four `AnswerRow`s, where "What is it?" fills in live and the others show skeletons.
- **Done when:** pasting the Afreximbank post text, a YouTube link and an X link shows "What is it?" on each save card within about 15s, and The team shows "Read …" lines with the snapshot as evidence. A note that looks like a backup code is marked private and never reaches the gateway.
- **Proved by:**
  - unit tests for URL canonicalisation, every secret-screen pattern, and `SafeFetcher` rejecting private IPs and redirects to them;
  - an agent test using `FakeModelGateway` (replays recorded output);
  - an API test that `POST /saves` returns 202 and enqueues `save.read` once.
- **If late:** TikTok and the Instagram/Facebook embed connectors wait. Those saves show the link only.

### S4 · Rough answers for the other three questions + rough Today
- **Day:** Sat · **Estimate:** 3h · **Depends on:** S3
- **Builds:** the simplest honest version of each remaining question.
  - **Is it true?:**
    - fetch the first link in the post and run `check.compare`;
    - `verify/quotes.py` runs **for real**, so the proof rule holds from day one;
    - no eligibility yet, and the verdict is `couldnt_confirm` or `nothing_to_check` until S6.
  - **What's it for?:** `place.assign` against the existing threads, creating new ones as needed.
  - **When will you need it?:** a date from the reading (`verify/dates.py`, first version), and `bring_back_at` by the rule in [03](03-agents.md#when-will-you-need-it).
  - **Today:** `GET /today` lists dated saves due within 7 days (a plain query, no tick yet). The Today screen shows them as `TodayCard`s.
- **Done when:** all four answers fill in on a pasted opportunity post. Only verified quotes are shown. The post shows up on Today when its date is within a week.
- **Proved by:** unit tests for `verify/quotes` (exact, fuzzy at 92 accepted and 91 rejected, short quote exact, offsets) and for the first `verify/dates` golden rows.
- **If late:** Today waits for S11. The save card's four answers don't.

### S5 · First deploy
- **Day:** Sat evening · **Estimate:** 2h · **Depends on:** S1–S4 and the accounts (Isreal)
- **Builds:**
  - **Supabase:** the project, with the `vector` and `pg_trgm` extensions and a private `saves` bucket.
  - **Server host:** Railway (`api` and `worker` services from `server/Dockerfile`), or the fallback from [ADR 0007](adr/0007-hosting.md).
  - **Vercel:** the `web/` project.
  - **Config:** every env var from [10](10-deployment-ops.md#environment-variables), and the Google redirect URL.
- **Done when:** **CP1** passes on the live URL ([10 · Deploy steps](10-deployment-ops.md#deploy-steps), smoke test).
- **If late:** keep going locally, but deploy before Sunday noon. Deploy surprises only get worse.

---

## Phase B · Make each scene deep (Sun–Tue)

### S6 · Is it true? in depth
- **Day:** Sun · **Estimate:** 7h · **Depends on:** S4 · **Scene:** Now
- **Builds:**
  - **`verify/`, complete** ([05](05-verification.md)): `dates` (all golden rows, time zones, the mismatch guard), `status` (closed signals), `eligibility` (every rule type, including "English or French plus the other"), `verdict`, `sources`.
  - **Finding the official source:** links in the post, then agent memory, then the search provider (`llm/search.py`).
  - **Profile:** `GET/PUT /me/profile` and the **Settings** page (eligibility profile form).
  - `check.eligibility_open` on **Muse Spark Open**, for free-text rules only.
  - `POST /saves/{id}/answer`, for the "needs your answer" question.
  - **Save card:** `VerdictBadge`, `EvidenceQuote` (serif quote, highlighted words, "verified on source"), `DeadlineText`, `AnswerQuestion`.
- **Done when:**
  - The **Afreximbank** post shows **Needs your answer** (French). Its 4 findings each carry a verified quote: on-site in Cairo, needs the other language too, full-time study only preferred, housing only if relocating. It also shows "no closing date on the official page".
  - At least **5 real opportunity posts** give sensible verdicts with only verified findings.
  - Answering the French question re-runs the verdict.
- **Proved by:**
  - unit tests for every row in [05](05-verification.md) and every verdict branch;
  - the golden Afreximbank agent test, using a recorded official page fixture.
- **If late:**
  - Muse Spark Open waits; free-text rules show as "needs your answer";
  - search waits; post links only.

### S7 · Files: images, flyers, PDFs, lists
- **Day:** Sun · **Estimate:** 2.5h · **Depends on:** S3, S5 (storage) · **Scene:** Now
- **Builds:**
  - **Uploads:** `POST /uploads/sign` (Supabase signed upload URL), and a direct browser upload with a progress bar.
  - `POST /saves/file`.
  - **Connectors:** `ingest/image.py` and `pdf.py` (text layer, or scanned).
  - **Purposes:** `read.image`, `read.pdf`, `read.list`. For list saves, **Is it true?** checks each item, up to 20.
- **Done when:** uploading screenshots of the **"18 opportunities" thread** gives a list save with its items read. Each item gets a verdict, and the card shows counts (fits you, closed, not for you, needs your answer, couldn't confirm). A flyer image gets a full save card.
- **Proved by:** a unit test for scanned-PDF detection, and an agent test for list items using recorded output.
- **If late:** check the first 10 list items only.

### S8 · WhatsApp import
- **Day:** Mon morning · **Estimate:** 4h · **Depends on:** S3, S7 · **Scene:** Past
- **Builds:**
  - `ingest/whatsapp/parser.py`: pure code. Android day-first and month-first dates, 12h and 24h times, iOS, multi-line messages, edits, system lines, media attached or omitted, labels within 180s, lists.
  - `ingest/whatsapp/importer.py`: zip safety; media to storage; saves keep their original time; the secret screen; content hashes; counts.
  - `POST /imports/whatsapp` and `GET /imports/{id}`.
  - Import reads run at **low priority**, with `read.batch_links` handling video links in batches of 20.
  - The **Import** page: drop zone, upload progress, then live counters from events, then a summary.
- **Done when:** Isreal's real export **with media** imports. The counts match the pile (about 624 messages). Every save is read within about 20 minutes. Private items appear blurred. Nothing is sent to the model twice: re-running the import is a cache hit.
- **Proved by:**
  - parser unit tests on synthetic fixtures (`tests/fixtures/whatsapp/`);
  - a zip-slip test;
  - an agent test checking the import counts.
- **If late:** media read as "kept, not read yet". Text and links still go through.

### S9 · What's it for? over the whole pile
- **Day:** Mon · **Estimate:** 3h · **Depends on:** S8 · **Scene:** Past
- **Builds:**
  - `place.rebuild` (long context, run once after import, then daily) and duplicate linking (`duplicate_of`).
  - **Thread endpoints:** list, get, rename (locks the thread), merge, add and remove a save ([07](07-api.md#threads)).
  - The **Threads** and **Thread** screens.
  - A validator that rejects titles describing the person, never their goals.
- **Done when:** after the import, threads like **"Getting into YC"** (7 saves) and **"Speaking better"** (10) exist. Repeats are linked ("You saved this before, on 8 Jul"). A renamed thread survives the next rebuild.
- **Proved by:** an agent test that rebuild respects locked threads, and a unit test for the title validator.
- **If late:** no merge or split UI. Rename only.

### S10 · Search by meaning + Ask
- **Day:** Mon · **Estimate:** 4h · **Depends on:** S8, S9 · **Scene:** anytime
- **Builds:**
  - **Embeddings:** `search/embed.py` (local ONNX model; check that `multilingual-e5-small` loads **(confirm)**), the `save.embed` job, the `save_embeddings` table and its HNSW index.
  - **Search:** `search/hybrid.py` (words plus meaning, merged with RRF) and `GET /search`.
  - **Ask:** `ask/answer.py` (candidates → `ask.select` → load → `ask.answer` → `verify/citations.py`), `POST /asks` and `GET /asks/{id}`.
  - **web:** `SearchAskBox` (instant results as you type, Ask button) and the `/ask/[id]` answer page, which fills in live.
- **Done when:**
  - searching **"YC"** returns the "Y Combinator" saves;
  - asking **"How do I prepare for YC?"** gives an answer page whose every point cites one of Isreal's saves with a verified quote, and which says plainly what isn't covered.
- **Proved by:**
  - unit tests for RRF merge and for `verify/citations`;
  - the golden Ask scenario ([11](11-testing-evals.md#agent-tests)).
- **Then:** **Isreal's grading hour.** Grade 40 save cards, and write 15 search and Ask questions with the saves he expects to see.
- **If late:** Ask keeps only "points" and "not in your saves".

### S11 · When will you need it? + Today
- **Day:** Tue morning · **Estimate:** 4h · **Depends on:** S6, S9 · **Scene:** Later
- **Builds:**
  - **The "when":** `when_needed.set_when` (from the check deadline, then reading dates, then a thread date, then a moment).
  - **Moments:** `POST /moments` and `MomentInput`.
  - **Timed work:** `tick.when` creates candidate cards, and `user.today` scores them in code and keeps at most 3 per day. This is where the scheduler from S1 gets finished.
  - **Card actions:** `POST /cards/{id}/act` (use, dismiss, later). Dismissed cards are remembered.
  - `GET /saves/{id}/calendar.ics`.
  - The **Today** screen, fully built.
- **Done when:** saving the **Meta hackathon page** gives "when = Thu 5 Nov, 03:00 Lagos time", and a **prep** card for the demo video appears on Today, because the related threads hold 16 saves. The actions work, a dismissed card never comes back, and there are never more than 3 new cards a day.
- **Proved by:** unit tests for the priority formula, the 3-a-day cap, and the `bring_back_at` rules; an API test that Today never returns more than 3 new cards.
- **If late:** no calendar file. Moments are typed only, with no date picker.

### S12 · Prep sheet + reel
- **Day:** Tue · **Estimate:** 3.5h · **Depends on:** S11, S0 (`VIDEO_MODE`) · **Scene:** Later
- **Builds:**
  - `llm/video.py` in the mode S0 chose.
  - `video.points` for each video, checked by `verify/timestamps.py`.
  - `prep.sheet` synthesis, with every citation checked against the per-video points.
  - `card.prep` job.
  - **web:** `PrepSheet` (5 points, each with chips like `Video · 4:12`, plus "they agree" and "they disagree") and `ReelPlayer` (YouTube embed playing start/end segments, at most 3 minutes).
- **Done when:** the demo-video prep card opens a sheet whose points cite exact seconds in Isreal's saved speaking and demo videos, and clicking a chip plays from that second.
- **If late:**
  - the reel goes first (PLAN cut order);
  - YouTube videos are read through their **captions** (Isreal's decision, 31 Oct); if captions are off or blocked, the sheet is built from chapters, titles and descriptions, and labelled "from chapters".

### S13 · Audit
- **Day:** Tue · **Estimate:** 2h · **Depends on:** S9 · **Priority:** P1, and the first thing cut at CP1 or CP3
- **Builds:**
  - **Found by code:** repeats and things that went bad.
  - **Contradictions:** `audit.contradictions`, kept only when two verified quotes back them.
  - **Suggestions:** gaps and let-go items from `audit.gaps`, labelled as suggestions.
  - `POST /audits`, `GET /audits/{id}`, and item actions.
  - The `/audit/[id]` report.
- **Done when:** a library audit shows the real repeats (the Elon video twice, the Jensen video twice) and any closed opportunities. Each item's action works.
- **If late:** repeats and went-bad only (PLAN cut order #2).

### S14 · Demo readiness
- **Day:** Tue afternoon · **Estimate:** 2h · **Depends on:** S11, S12
- **Builds:**
  - **Demo account:** the demo user seeded from Isreal's pile (`scripts/seed_demo.py`: private saves removed, phone numbers masked), and `POST /admin/demo/reset`.
  - **Google sign-in,** if S2 deferred it.
  - **README:** the judges' version, with real numbers from `/feedback/summary`.
  - The **demo-path check**: the Playwright test from [11](11-testing-evals.md#the-demo-path-test), or the same steps as a written checklist if time is short.
- **Done when:**
  - a stranger can open the live URL, press "Try the demo", and walk the three scenes;
  - the README numbers match the database;
  - the screen shows no personal numbers.
- **Then:** **record the video on Tuesday evening** ([PLAN §8](PLAN.md#8-the-3-minute-demo-past-now-later)).

## Phase C · Ship (Wed)

### S15 · Polish and submit
- **Builds:**
  - fixes found in the recording and the demo-path check;
  - a copy pass ([13](13-brand.md#voice));
  - loading and empty states;
  - the final deploy.
- **Then:** post on X (it counts for the viral prize until 8 Nov), and submit **before 03:00 Thu, Lagos time**. Isreal submits the form himself.

## Extras (only when ahead of the checkpoints)

| ID | Extra | What it adds | Depends on |
|---|---|---|---|
| X1 | Voice notes | `ingest/audio.py` (PyAV converts Opus to WAV, then `/v1/asr/transcribe`), transcript snapshots. A second Meta model visible in the product. | S0 result, S8 |
| X2 | Daily re-check | `user.recheck_open`: deadline moved, closed, dead link, then a `went_bad` card | S6, S11 |
| X3 | Android share-to-Homing | Web manifest `share_target` and `/share-target` | S3, S7 |

---

## Isreal's track (only Isreal can do these)

| When | Needed for | Item |
|---|---|---|
| **Fri** | S0 | Meta API key (as an env var) and the model IDs from the dashboard |
| **Fri** | S0, S8 | WhatsApp "message yourself" export **with media** |
| **Fri** | S1 | Supabase dev project (its connection string goes in `DATABASE_URL` and `TEST_DATABASE_URL`) |
| **Sat am** | S2, S5 | Google OAuth client; hosting decision ([ADR 0007](adr/0007-hosting.md)); Railway and Vercel accounts |
| **Sat am** | S3 | YouTube Data API key |
| **Sat 3–4 PM** | S0, S12 | Office hours questions: Can Spark take YouTube links? Can Spark Open read video? Is there web search? Are there embeddings? |
| **Sun am** | S6, S7 | Screenshots of the "18 opportunities" thread; 5–10 live opportunity posts; your eligibility profile; a search API key (Tavily or Brave) |
| **Mon eve** | S10 | 1 hour of grading, plus 15 search and Ask questions with the saves you expect |
| **Tue am** | S11 | Save the Meta hackathon page into Homing; re-pick posts that are still open |
| **Tue eve** | S14 | Record the video |
| **Wed** | S15 | Post on X; submit the hackathon form |

## Testing without Docker

There's no Docker on the dev machine. So:
- **Pure-logic tests** (`verify/`, the parser, URLs, priority) need no database and run in seconds.
- **Integration tests** use `TEST_DATABASE_URL`, pointing at the Supabase dev project. Each run creates its own schema (`test_<random>`) and drops it afterwards. The `vector` and `pg_trgm` extensions are already installed on the database.

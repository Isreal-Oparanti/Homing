# 11 · Testing and evals

Two different questions:
- **Tests:** does the code do what we meant? They run on every commit, without network access or models.
- **Evals:** are the answers actually right? They run on real data, graded by Isreal, and the numbers go in the README.

## Test layout

```
server/tests/
  unit/          # pure functions: verify/*, ingest/whatsapp/parser, ingest/urls, secrets, priority
  api/           # FastAPI TestClient against TEST_DATABASE_URL, a fresh schema per run (no Docker needed)
  agents/        # agent handlers with FakeModelGateway (recorded outputs) and FakeFetcher
  fixtures/
    whatsapp/    # synthetic exports: android_dmy.txt, android_mdy_12h.txt, ios.txt, with_media.zip
    pages/       # saved HTML or PDF of official pages, e.g. afreximbank_workable.json/html
    model/       # recorded model outputs per purpose (JSON), used by FakeModelGateway
web/
  tests/         # Vitest for lib/ (api mapping, date display); Playwright smoke for the demo path
```

**Run:**
- `python -m uv run pytest` (server) and `npm test` (web) run everything.
- `python -m uv run pytest tests/unit` takes under 5 seconds and is run constantly.

## Unit tests

These must exist before a feature counts as done.

| Module | Cases |
|---|---|
| `verify/quotes` | exact; whitespace and quote-mark differences; fuzzy at 92 accepted and 91 rejected; short quote must be exact; offsets map back to the original |
| `verify/dates` | every row of the golden table in [05](05-verification.md#dates-and-time-zones); "tomorrow" relative to message time; ET to Lagos; no time means 23:59; model/code mismatch flagged |
| `verify/eligibility` | the Afreximbank rules (age 20–32 by year, nationality group, English or French plus the other, student preferred); `preferred` never fails; missing profile field gives `unknown` |
| `verify/verdict` | each branch of the verdict order |
| `verify/secrets` | each pattern hits; dates and amounts don't false-positive; the matched value is never returned |
| `verify/timestamps` | out-of-range points dropped; segments trimmed; unknown citations dropped |
| `ingest/whatsapp/parser` | Android DMY and MDY, 12h and 24h, iOS; multi-line; edited; system lines; media attached vs omitted; label within 180s; lists |
| `ingest/urls` | YouTube Shorts, youtu.be and live normalised; tracking params stripped; X host normalised |
| `when_needed.priority` | priority formula; the 3-a-day cap; dismissed never comes back |
| `search.fusion` | RRF merge order; a word-only match and a meaning-only match both appear; private saves never returned |
| `verify/citations` | quote from the wrong save is rejected; one verified citation keeps a point; a contradiction needs both quotes; "out of date" needs a check or a past date |

## The test database

- **Schema per run:** integration tests (`@pytest.mark.integration`) create a schema `test_<random>` in `TEST_DATABASE_URL`, migrate it, and drop it at the end.
- **Version record:** Alembic keeps its version record inside that schema (`version_table_schema`). Without that, it finds the real `public.alembic_version` through the search path and marks the real database as migrated. That happened once on 31 Oct and was fixed.
- **Leak guard:** after migrating, the fixture checks that `users`, `jobs`, `saves` and `alembic_version` exist **in the test schema**, and fails otherwise.

## API tests

- Auth: a missing or wrong proxy secret gets 401.
- **Isolation:** user A gets 404 for user B's save, thread, card and event stream, on every endpoint.
- `POST /saves` returns 202 and creates a `save.read` job with the right dedupe key.
- `SaveCard` lists `pending` correctly as answers arrive.
- `/today` never returns more than 3 new cards.
- Errors always come back in the standard error shape.

## Agent tests

- `FakeModelGateway` replays recorded outputs per `(purpose, input_hash)` and fails the test if an unexpected call is made. That's how we catch accidental extra spend.
- **Golden scenario: Afreximbank.** The save text plus the recorded official page must give the findings:
  - on-site in Cairo;
  - both languages;
  - full-time study only preferred;
  - housing only if relocating;
  - no date on the official page.

  Each finding verified, verdict `needs_your_answer` (French), with a question set.
- **Golden scenario: private.** A code-like note is never sent to the gateway, which raises if it is.
- **Golden scenario: import.** The synthetic export gives the expected counts.
- **Golden scenario: ask.** With a fixture library holding an image save ("YC interview tips" screenshot) and a link save ("Y Combinator: how to apply"), asking "How do I prepare for YC?":
  - both saves are among the candidates (the real local embedding model is used in this test);
  - every point on the answer page cites one of them with a verified quote;
  - an unrelated save is never cited.

## Evals

Real data, graded by Isreal.

Grading uses the in-app **feedback** buttons (Right · Wrong · Nonsense) on save cards, plus a hidden `/eval` page that serves a random sample.

| Eval | Sample | Metric | Target to claim in the README |
|---|---|---|---|
| **What is it?** | 40 random saves from the real pile | % Right | measure, don't promise |
| **Is it true?** | ≥ 10 real opportunity posts | % of shown findings that are correct (precision); % of posts where we found the official page | precision ≥ 95%, because a wrong ✓ is the worst failure |
| **What's it for?** | all threads after rebuild | % of saves in a sensible thread | measure |
| **When will you need it?** | 20 saves with dates | % of correct dates and zones | 100% on parsed dates, which code guarantees once the quote is right |
| Prep sheet | the 16-video demo thread | % of points that are true at the cited second | measure |
| Search | 15 questions written by Isreal, each with the saves he expects | % of expected saves in the top 10 (recall@10), for words-only vs hybrid | hybrid beats words-only. Report both. |
| Ask | the same 15 questions | % of answer points graded Right; % of answers that wrongly say "not in your saves" | measure |

**Reporting:**
- `GET /feedback/summary` gives the counts. Copy them into the README "How well it works" table, with the sample size and date.
- **Never round up, and never drop a bad category.**

**When:** grading takes about 1 hour on Monday 2 Nov ([PLAN §12](PLAN.md#12-build-plan)), with a second pass after fixes if time allows.

### What is it? on the real pile (31 Oct)

This is a check by code and by reading the outputs, not Isreal's grading. It doesn't replace the Monday grade.

- **Sample:** 34 saves from the export, chosen by platform with a fixed seed, read through the real fetchers and Muse Spark, as the user `eval-s3`:
  - 8 YouTube, 4 Instagram, 4 Facebook, 9 web, 5 X, 2 TikTok;
  - 2 messages with several links.
- **The pile it came from:** 486 link saves, of which 217 are YouTube, 89 Instagram, 81 Facebook, 75 web, 17 X and 2 TikTok.

| Measure | `read_text.v1` | `read_text.v2` |
|---|---|---|
| Reads that failed | 0 / 34 | 0 / 34 |
| Saves we couldn't read that said so instead of guessing | 12 / 12 | 12 / 12 |
| Marked checkable (only 2–4 really are) | 15 | 5 |
| Opportunities found (both real ones) | 2 / 2 | 2 / 2 |
| Dates, amounts, requirements and places listed | 51 | 17 |
| Of those dates, amounts and requirements, found word for word in the save or our copy | 34 / 39 | 16 / 16 |

- **The 12 unreadable saves:**
  - all 8 Instagram and Facebook posts;
  - 3 web pages that refused us or were empty;
  - a TikTok short link.

  Instagram and Facebook are 35% of the pile's links, and we can't read them unless the user adds the file.
- **v1's 5 misses** were captions where the model added punctuation the raw captions lack. The quote check in S4 must match loosely on transcripts.
- **Re-run:** `eval/rerun_eval.py`, kept outside the repo because it reads the private export. The eval saves stay under `eval-s3` for S4 testing.

## The demo path test

Playwright, on the demo user's data.

`web/tests/demo.spec.ts`. This is the three scenes as a test:
1. Sign in as the demo user. `/today` renders.
2. Import the screen: counts appear (the seed is already imported, so it checks the summary).
3. Paste a link to a live opportunity. The save card shows four answers within 90s, with at least one verified finding.
4. `/today` shows the prep card. Opening it shows the prep sheet with at least one timestamp chip.

Run it before recording, and after every deploy on Tuesday and Wednesday.

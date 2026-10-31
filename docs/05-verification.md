# 05 · Verification

The **proof or silence** rule, written as code. Everything here lives in `server/app/verify/`. It's pure functions with no I/O and no model calls, and it's the most heavily tested part of the codebase ([11](11-testing-evals.md#unit-tests)).

**The rule:** models *propose*, code *decides*. A claim reaches the UI only if code has confirmed it against a stored source snapshot.

## Quotes

Code: `verify/quotes.py`

`match_quote(quote: str, source: str) -> QuoteMatch | None`

1. **Normalise both strings:**
   - Unicode NFKC, then lowercase;
   - unify quote marks (`“”‘’` → `"'`) and dashes (`–—` → `-`);
   - collapse all whitespace to single spaces;
   - remove soft hyphens and zero-width characters.
2. **Exact substring** → `score = 100` with offsets.
3. **Otherwise fuzzy:** find the best-matching stretch of the source with `rapidfuzz.fuzz.partial_ratio_alignment` (windows the length of the quote). Accept if the best score ≥ **92** and the quote is ≥ **12** characters. Shorter quotes must match exactly.
4. **Map offsets back** to the original (un-normalised) source, so the UI can highlight the exact text.

**Rejected outright:**
- quotes of fewer than 3 words (except dates and amounts that match exactly);
- quotes longer than 400 chars (the model is pasting, not quoting).

A finding with no accepted quote is **dropped**, and the count of dropped findings is logged to `model_calls` for evals.

## Dates and time zones

Code: `verify/dates.py`

`parse_deadline(source_text: str, *, base: datetime, user_tz: str, source_tz_hint: str | None) -> Deadline | None`

1. Parse the **verified quote text**, never the model's interpretation, with `dateparser`, using:
   - `RELATIVE_BASE = base` (the message's `saved_at` for relative words like "tomorrow", or `fetched_at` for official pages);
   - `PREFER_DATES_FROM = future`;
   - `DATE_ORDER = DMY` unless the source is clearly US-style.
2. **Time zone:**
   - If a zone is stated (`ET`, `EST`, `PT`, `GMT`, `WAT`, `CAT`, `UTC`, `+01:00`…), map it to IANA (`ET` → `America/New_York`) and attach it. `deadline_tz_stated = true`.
   - If no zone is stated, use `source_tz_hint` (country of the organiser) or else the user's zone, and mark `deadline_tz_stated = false`. The UI then says *"time zone not stated"*.
3. **No time given** → end of day, 23:59, in that zone. Mark it `time_stated = false`.
4. Convert to the user's zone for display: `"Thu 5 Nov, 03:00 Lagos time"`.
5. **Only real dates count:** a month with a day ("31 October", "Nov 4"), a full numeric date ("31/10/2026", ISO) or a relative word ("tomorrow", "demain"). "Early December" or "aged 20–32" give no date. Labels like "Date limite :" are tried with and without the label. Offsets need `UTC`/`GMT` or the `±hh:mm` form, so a bare "+1" isn't a zone.
6. **Mismatch guard:** if the model's proposed ISO date is more than 1 day away from the code's parse → `needs_your_answer` with *"The date is unclear: '…'. When does it close?"*

**Examples (golden tests):**

| Source text | Base | User tz | Result |
|---|---|---|---|
| `Deadline: 31 October 2026.` | — | Africa/Lagos | 31 Oct 2026 23:59 WAT, tz not stated |
| `Nov 4, 9 PM ET` | 2026-10-30 | Africa/Lagos | 5 Nov 2026 03:00 WAT, tz stated |
| `closes TOMORROW` | message 2026-10-30 14:05 | Africa/Lagos | 31 Oct 2026 23:59 WAT, relative |
| `Deadline: November 2, 2026` | — | Africa/Lagos | 2 Nov 2026 23:59 (organiser tz unknown) |

## Closed signals

Code: `verify/status.py`

`is_closed(snapshot, http_status) -> ClosedSignal | None`

- HTTP 404 or 410 on the official URL → `dead_link`.
- The page text matches one of these patterns (case-insensitive, in English and French):
  - `applications? (are |is )?(now )?closed`
  - `no longer accepting`
  - `this (position|opportunity|call) (has|is) (closed|expired)`
  - `deadline (has )?passed`
  - `candidatures? (sont )?closes?`
- `deadline_at < now` → `past_deadline`.

Each signal must carry the matched text as its quote.

## Eligibility

Code: `verify/eligibility.py`

The model proposes rules, each with a quote. Code checks the quotes, then evaluates.

| Rule | Params | How code evaluates it against `profiles` |
|---|---|---|
| `age` | `min`, `max`, `reference` (`year_of_application` · `on_deadline` · `unspecified`) | from `birth_year`. If `birth_year` is missing → `unknown` |
| `nationality` | `allowed: [ISO codes or groups]` | groups such as `afreximbank_members` or `african_union` expand from `verify/data/groups.json` **(fill from official lists; confirm)** |
| `residence` | `allowed` | `residence_country` |
| `student` | `required_status`, `strength` | `student_status` |
| `education` | `min_level` | `education_level` |
| `language` | `[{code, level}]`, with `any_of` / `all_of` | `languages`. "Fluent in English or French **and** working knowledge of the other" is `any_of(fluent en, fluent fr)` **and** `all_of(working en, working fr)` |
| `company` | `registered`, `stages` | `company_registered`, `company_stage` |
| `location` | `onsite_city`, `remote_ok` | not a pass/fail rule. It's always shown as a finding ("It's on-site in Cairo") |
| `other` | free text | → Muse Spark Open (`check.eligibility_open`) → `meets` / `fails` / `unknown` with a reason. `fails` only counts if the reason quotes the rule. |

**`strength`:**
- `required`: words like "must", "only", "eligible applicants are…".
- `preferred`: "preferred", "advantage", "ideally".

`preferred` rules never fail a user. They're shown as *"Preferred, not required."*

## Finding the official source

Code: `agents/is_it_true.py`, helpers in `verify/sources.py`

1. **Links in the post:** prefer links whose domain matches the organisation named in the reading (e.g. `afreximbank.com`, `apply.workable.com/afreximbank`), and known application hosts (`workable.com`, `greenhouse.io`, `lever.co`, `typeform.com`, `forms.gle`, `docs.google.com/forms`, `fluxx.io`, `submittable.com`).
2. **Agent memory** for the same canonical URL or organisation name.
3. **Search** (`SearchProvider`, see [06](06-models.md#web-search)): query `"{organisation} {programme name} {year} apply"`. Keep results whose domain matches the organisation or a known application host. Take the top 2 candidates.
4. **Aggregator sites** (opportunity blogs, X threads) are never treated as official. They can only lead to the official page. Nor are chat and social links (WhatsApp channels, Telegram, Instagram, YouTube, link shorteners). The list is in `verify/sources.py`.

If nothing passes → `couldnt_confirm`, with *"We couldn't find the official page. Here's what the post says, unconfirmed."*

## Verdict

Decided by code in `verify/verdict.py`. The order is set out in [03 · Is it true?](03-agents.md#is-it-true), step 6. The same inputs always give the same verdict.

## Video timestamps

Code: `verify/timestamps.py`

- Each point needs `0 ≤ t_start < t_end ≤ duration_s` (duration from the YouTube Data API or the file probe).
- Segments longer than 120s are trimmed to 120s around `t_start`.
- Prep sheet citations must reference a `(save_id, t_start)` that the per-video step produced. Anything else is dropped.

For video, the proof the user can check is the link to the exact second.

## Answers and audits

Code: `verify/citations.py`

The same proof rule applies to Ask answers and audit contradictions, but here the "source" is the user's own save.

- **Each citation** names a `save_id` the user owns, from the candidate set of that ask or audit. Its `quote` must match that save's snapshot text or reading text using `match_quote` (same thresholds as above).
- **Video citations** use `verify/timestamps.py` instead of text matching.
- **Points:** a point survives only if at least one of its citations verifies. Unverified citations are removed even when the point survives.
- **Contradictions:** a contradiction survives only if **both** quotes verify, and they come from two different saves.
- **"Out of date"** is shown only when backed by a check verdict (`closed`) or a stored `due_at` in the past. It's never taken from the model's text alone.
- **Counts:** dropped points and citations are counted in `model_calls`, for evals.

## What the UI is allowed to show

| Shown as | Requires |
|---|---|
| A fact with a ✓ | a verified quote, linked to the source snapshot, with the quote highlighted |
| "Unconfirmed" | it came from the user's own save, but has no official source |
| A date | `parse_deadline` result. The UI states whether the time and zone were given. |
| A verdict | `verify/verdict.py` output only |
| A point on an answer page | at least one citation verified by `verify/citations.py` |
| A contradiction in an audit | two verified quotes from two different saves |
| A gap or let-go item | shown as a suggestion ("You might be missing…"), never as fact |

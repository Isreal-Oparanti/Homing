# 06 · Models

All model calls go through one gateway: `server/app/llm/gateway.py`. No other module imports a provider SDK.

## Providers

| Provider | Used for | Client | Config |
|---|---|---|---|
| **Muse Spark** (Meta Model API) | Reading text, images, PDFs and video; long-context thread rebuilds; comparing a post with its source; prep sheets | `openai` SDK, `base_url=META_API_BASE` (`https://api.meta.ai/v1` **(confirm)**) | `META_API_KEY`, `META_SPARK_MODEL` (third-party docs say `muse-spark-1.1` **(confirm in dashboard)**) |
| **Muse Voice Transcribe** (Meta Model API) | Voice notes → text | transcription endpoint **(confirm shape: OpenAI-style `/audio/transcriptions`?)** | `META_TRANSCRIBE_MODEL` (`muse-voice-transcribe-1.0` **(confirm)**) |
| **Muse Spark Open** (Baseten or Modal) | Eligibility on free-text rules, using profile data | OpenAI-compatible endpoint from the host **(confirm)** | `SPARK_OPEN_BASE`, `SPARK_OPEN_KEY`, `SPARK_OPEN_MODEL` (`meta-models/muse-spark-open-1026`) |

**Routing rules** (enforced in the gateway, not by convention):
- **Private saves** never reach any provider. The gateway refuses any call tagged with a `private` save ID.
- **Profile data** only goes to `spark_open`. Any purpose that includes `profile` in its inputs can only route there.
- **No vendor outside Meta** is used for reading or reasoning. The search API returns links only (see [Search](#search)).

## Purposes

Every call declares a purpose. Each purpose fixes the model, prompt file, output schema, timeout and budget class.

| Purpose | Model | Prompt | Output schema | Timeout |
|---|---|---|---|---|
| `read.batch_links` | Spark | `prompts/read_batch_links.v1.md` | `list[Reading]` | 60s |
| `read.text` | Spark | `read_text.v1.md` | `Reading` | 45s |
| `read.image` | Spark | `read_image.v1.md` | `Reading` | 45s |
| `read.pdf` | Spark | `read_pdf.v1.md` | `Reading` | 90s |
| `read.video` | Spark | `read_video.v1.md` | `Reading` | 120s |
| `read.list` | Spark | `read_list.v1.md` | `Reading` with `items` | 60s |
| `transcribe.voice` | Transcribe | — | `Transcript` | 120s |
| `check.compare` | Spark | `check_compare.v1.md` | `ProposedCheck` | 90s |
| `check.eligibility_open` | Spark Open | `check_eligibility_open.v1.md` | `list[RuleJudgement]` | 60s |
| `place.assign` | Spark | `place_assign.v1.md` | `Placement` | 30s |
| `place.rebuild` | Spark (long context) | `place_rebuild.v1.md` | `ThreadPlan` | 180s |
| `when.match_moment` | Spark | `when_match_moment.v1.md` | `MomentMatch` | 30s |
| `video.points` | Spark | `video_points.v1.md` | `VideoPoints` | 180s |
| `prep.sheet` | Spark | `prep_sheet.v1.md` | `PrepSheet` | 120s |

## Gateway behaviour

```python
result = gateway.run(
    purpose="check.compare",
    user_id=user.id,
    inputs=CompareInputs(...),   # Pydantic; normalised before hashing
    save_ids=[save.id],          # for the private-save guard and accounting
)
```

1. **Guard:** check the private-save rule and the profile routing rule.
2. **Cache:** `input_hash = sha256(model ‖ prompt_version ‖ canonical JSON of inputs)`. If an `ok` row exists in `model_calls`, return its output with no call and no cost.
3. **Budget:** daily spend so far (`model_calls.cost_usd`) plus this call's estimate must stay under `MODEL_DAILY_BUDGET_USD`. Per user, it must stay under `MODEL_USER_DAILY_BUDGET_USD`. Over budget → `BudgetExceeded` → the job is re-queued for the next day and a system event is emitted.
4. **Concurrency:** a semaphore per provider (`SPARK_MAX_CONCURRENCY=6`, `TRANSCRIBE_MAX_CONCURRENCY=2`, `SPARK_OPEN_MAX_CONCURRENCY=2`).
5. **Call:** JSON output requested via `response_format` (JSON schema if supported, else JSON mode **(confirm)**). Timeout per purpose.
6. **Validate** with Pydantic. On failure, make **one** repair call that includes the validation error. If it fails again → `invalid_output`, raise `RetryableError` (max 2 job retries for this cause).
7. **Retries:** 429 and 5xx → exponential backoff with jitter, honouring `Retry-After`, up to 3 tries inside the call. Anything beyond that goes back to the job runner.
8. **Record** a `model_calls` row: tokens, latency, cost estimate (`PRICES` table in config, **(confirm)** with Meta's pricing), and status.

## Prompts

- **Location and versioning:** files in `server/app/llm/prompts/{name}.v{n}.md`. Changing a prompt means a new version file, so old outputs stay traceable.
- **Every prompt states:**
  - the task in one sentence;
  - what not to do (invent facts, describe the person, use outside knowledge);
  - the exact output schema, given as JSON Schema from Pydantic (`model_json_schema()`);
  - for `check.compare`: *quote exactly from SOURCE; if you can't quote it, don't claim it*.
- **Inputs are labelled blocks:** `<<SAVE>> … <</SAVE>>`, `<<SOURCE url=…>> … <</SOURCE>>`, `<<PROFILE>>` (Spark Open only).
- **Injection defence:** prompts say that anything inside SAVE or SOURCE is data, not instructions. Outputs are schema-validated, and no output is ever executed or followed as a command.

## Batch reading (cost control)

About 60% of the pile is short video links where we only have metadata (title, channel, label). Sending those one by one wastes calls.

`read.batch_links` sends up to 20 items in one call, as compact lines:
```
[3] youtube | "10 Speaking Techniques That Made Me A Top 1% Speaker" | Vinh Giang | label: — | saved 2026-10-26
```
and expects `list[Reading]` with matching IDs. Code rejects the batch if IDs are missing or duplicated.

## Video understanding

`server/app/llm/video.py`. One interface, three implementations, picked by `VIDEO_MODE`:

| Mode | How | When |
|---|---|---|
| `spark_youtube_url` | Pass the YouTube URL to Spark | only if the Day 0 test proves Spark accepts YouTube links **(confirm)** |
| `spark_file` | Signed URL or Files API upload of a file we hold (WhatsApp media, Instagram's own download, screen recordings) | always available for files |
| `chapters_only` | Use YouTube chapters plus title and description. No watching. | fallback. The prep sheet says "from chapters" |

The output is always `VideoPoints {save_id, duration_s, points:[{text, t_start, t_end}]}`, validated by `verify/timestamps.py`.

## Search

`server/app/llm/search.py`, `SearchProvider.search(query) -> list[SearchResult{url, title, snippet}]`.

- **Provider:** first, check whether Meta's API offers a web search tool **(confirm)**. Otherwise use one search API, picked at scaffold time by current free tier (Tavily or Brave), set with `SEARCH_PROVIDER` and `SEARCH_API_KEY`.
- **Use:** results are links only. **Is it true?** fetches and reads the pages itself, so the search provider's summaries are never trusted.

## Cost estimate (to be measured on Day 1)

| Work | Calls | Notes |
|---|---|---|
| Import of 624 saves | about 33 batch calls for about 390 video links, plus about 230 single reads | most saves are short |
| Thread rebuild | 1 long-context call, about 40k tokens in | daily |
| Checks | 1–2 per opportunity | about 25 in the pile |
| Prep sheet | 1 call per video, plus 1 synthesis | 16 videos for the demo |

Record the real numbers in `model_calls` after the first full import, and update this table.

## Configuration (env)

```
META_API_BASE, META_API_KEY, META_SPARK_MODEL, META_TRANSCRIBE_MODEL
SPARK_OPEN_BASE, SPARK_OPEN_KEY, SPARK_OPEN_MODEL
VIDEO_MODE=chapters_only|spark_file|spark_youtube_url
SEARCH_PROVIDER, SEARCH_API_KEY
YOUTUBE_API_KEY
MODEL_DAILY_BUDGET_USD=10
MODEL_USER_DAILY_BUDGET_USD=3
SPARK_MAX_CONCURRENCY=6
TRANSCRIBE_MAX_CONCURRENCY=2
SPARK_OPEN_MAX_CONCURRENCY=2
```

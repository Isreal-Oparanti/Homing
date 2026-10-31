# 06 · Models

All model calls go through one gateway: `server/app/llm/gateway.py`. No other module imports a provider SDK.

## Providers

| Provider | Used for | Client | Config |
|---|---|---|---|
| **Muse Spark** (Meta Model API) | Reading text, images, PDFs and video; long-context thread rebuilds; comparing a post with its source; prep sheets | `openai` SDK, `base_url=META_API_BASE` (`https://api.meta.ai/v1`, Bearer key; checked 30 Oct) | `META_API_KEY`, `META_SPARK_MODEL` = `muse-spark-1.3` (default; S0 compares it with 1.2, the `-contributor` builds and `muse-wonder-1.0`) |
| **Muse Voice Transcribe** (Meta Model API) | Voice notes → text | `POST /v1/asr/transcribe`, multipart (`request` JSON + `audio` **WAV**), up to 10 min / 32 MB. Returns `transcript`, `audioDurationMs`, `turns`. A realtime WebSocket (`/v1/asr/realtime`) also exists; we don't need it. | `META_TRANSCRIBE_MODEL` = `muse-voice-transcribe-1.0` (listed by `/v1/models`, 30 Oct) |
| **Muse Spark Open** (Baseten or Modal) | Eligibility on free-text rules, using profile data | OpenAI-compatible endpoint from the host **(confirm)** | `SPARK_OPEN_BASE`, `SPARK_OPEN_KEY`, `SPARK_OPEN_MODEL` (`meta-models/muse-spark-open-1026`) |

**Routing rules** (enforced in the gateway, not by convention):
- **Private saves** never reach any provider. The gateway refuses any call tagged with a `private` save ID.
- **Profile data** only goes to `spark_open`. Any purpose that includes `profile` in its inputs can only route there.
- **No vendor outside Meta** is used for reading or reasoning. The search API returns links only (see [Web search](#web-search)).

## Models on our key

`GET /v1/models` on 30 Oct listed:
- `muse-spark-1.1`, `muse-spark-1.2` and `muse-spark-1.3`, plus `-contributor` builds of 1.2 and 1.3;
- `muse-wonder-1.0`;
- `muse-voice-transcribe-1.0`;
- `muse-image-1.0`;
- `sam-3.1`.

We use Spark and Voice Transcribe. S0 checks whether `muse-wonder-1.0` is worth it for `check.compare`, the hardest call. Image generation and segmentation aren't needed.

## What the S0 check found (30 Oct)

| Input | Works? | How to send it |
|---|---|---|
| Text with structured output | Yes | `response_format={"type": "json_schema", ...}` (exact schema followed) |
| Images (JPEG, PNG, GIF, WebP) | Yes | **Base64 data URL** in `image_url`. Remote URLs can fail when the host blocks Meta's downloader, so always send bytes. |
| PDF | Yes | `{"type": "file", "file": {"filename": ..., "file_data": "data:application/pdf;base64,..."}}`. File URLs are rejected; `file_id` (upload first) also works. |
| Video | **MP4 only** | `{"type": "video_url", "video_url": {"url": <MP4 URL>}}`. Answers carry timestamps. 5s sample took about 23s. |
| **YouTube links** | **No** | Rejected (`text/html`, MP4 only), and Spark says it can't watch YouTube. |
| Voice notes (Opus → WAV) | **Yes** | Convert with PyAV to 16 kHz mono WAV, then `/v1/asr/transcribe`. A 145s Nigerian-English note was accurate and took 38s; a 24s Pidgin note worked too. |
| Muse Wonder | Yes | Same API, faster on simple JSON (3.7s vs 5.9s). Compare on `check.compare` in S6. |

**Latency:** Spark is a reasoning model. Most output tokens are reasoning (about 300–800 per call). Use `reasoning_effort="low"` for reading and placing (simple extraction took 2.8s instead of 5–6s), and leave the default for `check.compare`, `ask.answer` and `prep.sheet`.

**Decision for YouTube (Isreal, 31 Oct):** read YouTube's **captions** with `youtube-transcript-api` (timestamped text, no video download), behind `FEATURE_YT_CAPTIONS`. Spark reads the captions and cites exact seconds. Revisit after asking at office hours ([ADR 0008](adr/0008-platform-rules.md)). Tested on the saved "10 Speaking Techniques" video: 545 timestamped lines over 20 minutes.

**Known risk:** YouTube often blocks caption requests from cloud-server IPs. It works from Isreal's machine, but even there YouTube sometimes refuses a request (`RequestBlocked`, seen several times on 31 Oct). The worker tries 3 times with a short pause. If it's still blocked, or the video has no captions, Spark reads the title, description and chapters, and the card says which happened. Check it from the deployed worker in S5.

## Purposes

Every call declares a purpose. Each purpose fixes the model, prompt file, output schema, timeout and budget class.

| Purpose | Model | Prompt | Output schema | Timeout |
|---|---|---|---|---|
| `read.batch_links` | Spark | `prompts/read_batch_links.v1.md` | `list[Reading]` | 60s |
| `read.text` | Spark | `read_text.v2.md` (v2 since 31 Oct: only facts someone could act on, a narrower `is_checkable`) | `Reading` | 90s |
| `read.image` | Spark | `read_image.v1.md` | `Reading` | 45s |
| `read.pdf` | Spark | `read_pdf.v1.md` | `Reading` | 90s |
| `read.video` | Spark | `read_video.v1.md` | `Reading` | 120s |
| `read.list` | Spark | `read_list.v1.md` | `Reading` with `items` | 60s |
| `transcribe.voice` | Transcribe | — | `Transcript` | 120s |
| `check.compare` | Spark | `check_compare.v1.md` (default reasoning effort) | `ProposedCheck` | 120s. Measured 31 Oct on the real Afreximbank post: 17.1s, 1.6k tokens in, 4.8k out (mostly reasoning). Try `low` effort or Muse Wonder in S6. |
| `check.eligibility_open` | Spark Open | `check_eligibility_open.v1.md` | `list[RuleJudgement]` | 60s |
| `place.assign` | Spark | `place_assign.v1.md` (`low` effort) | `Placement` | 45s. Measured 2.9s. |
| `place.rebuild` | Spark (long context) | `place_rebuild.v1.md` | `ThreadPlan` | 180s |
| `when.match_moment` | Spark | `when_match_moment.v1.md` | `MomentMatch` | 30s |
| `video.points` | Spark | `video_points.v1.md` | `VideoPoints` | 180s |
| `prep.sheet` | Spark | `prep_sheet.v1.md` | `PrepSheet` | 120s |
| `ask.select` | Spark | `ask_select.v1.md` | `Selection` | 30s |
| `ask.answer` | Spark | `ask_answer.v1.md` | `Answer` | 90s |
| `audit.contradictions` | Spark (long context) | `audit_contradictions.v1.md` | `list[ProposedContradiction]` | 180s |
| `audit.gaps` | Spark | `audit_gaps.v1.md` | `list[ProposedGap]` | 60s |

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
3. **Budget, in tokens** (Meta hasn't published prices, so dollars can't be counted yet). Two checks, each on tokens in plus out since midnight UTC, plus this call's estimate (characters / 4 + 1,500 for the output):
   - everyone's total must stay under `MODEL_DAILY_TOKEN_BUDGET`;
   - this user's must stay under `MODEL_USER_DAILY_TOKEN_BUDGET`, halved for the demo user.

   Cached answers skip this check (they cost nothing). Over budget → `BudgetExceeded` → the job waits until just after midnight without using up an attempt. The save card says "Paused until tomorrow", and The team gets one "paused" line per user per day.
4. **Concurrency:** a semaphore per provider (`SPARK_MAX_CONCURRENCY=6`, `TRANSCRIBE_MAX_CONCURRENCY=2`, `SPARK_OPEN_MAX_CONCURRENCY=2`).
5. **Call:** JSON output requested via `response_format` (JSON schema if supported, else JSON mode **(confirm)**). Timeout per purpose.
6. **Validate** with Pydantic. On failure, make **one** repair call that includes the validation error. If it fails again → `invalid_output`, raise `RetryableError` (max 2 job retries for this cause).
7. **Retries:** 429 and 5xx → exponential backoff with jitter, honouring `Retry-After`, up to 3 tries inside the call. Anything beyond that goes back to the job runner.
8. **Record** a `model_calls` row: tokens, latency and status. `cost_usd` stays empty until Meta publishes prices.

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
| `youtube_captions` | Fetch YouTube captions (`youtube-transcript-api`), then Spark reads the timestamped text | **default for YouTube** (Isreal's decision, 31 Oct) |
| `spark_youtube_url` | Pass the YouTube URL to Spark | **ruled out**: the S0 check showed Spark rejects YouTube links |
| `spark_file` | MP4 by URL (signed storage URL) or Files API upload, for files we hold (WhatsApp media, Instagram's own download, screen recordings) | **default** for any video file |
| `chapters_only` | Use YouTube chapters plus title and description. No watching. | fallback when captions are off or blocked. The prep sheet says "from chapters" |

The output is always `VideoPoints {save_id, duration_s, points:[{text, t_start, t_end}]}`, validated by `verify/timestamps.py`.

## Embeddings (local)

`server/app/search/embed.py`. Used for meaning-based search ([ADR 0003](adr/0003-search-ask-audit.md)).

- **No Meta endpoint:** Meta's Model API shows no embeddings endpoint **(confirm in the official docs)**.
- **The model:** we run a small open multilingual model **inside the worker and API** on CPU, through ONNX Runtime (via `fastembed`, or `optimum` + `onnxruntime`). Default: `intfloat/multilingual-e5-small`, 384 dimensions **(confirm it loads at scaffold; fallback `paraphrase-multilingual-MiniLM-L12-v2`)**.
- **Why local:**
  - no new vendor or account;
  - saves never leave our servers for indexing;
  - free;
  - multilingual, because saves mix English, Pidgin and Yoruba words.
- **What gets embedded:** `passage: {title}. {what}. {label}. {key facts as text}. {first 1,000 chars of the snapshot}`. Queries are embedded as `query: {text}`, the e5 convention.
- **Not covered by the gateway rules:** this isn't a Meta model call, so it isn't budgeted or recorded in `model_calls`. The private-save rule still applies in `embed_save`, because private saves are never embedded.
- **Speed target:** about 10–30 ms per text on CPU; 624 saves in under a minute. Measure on Day 2.
- **Image:** the model files are downloaded at Docker build time into `/models`, so nothing is fetched at runtime.

## Web search

This is web search for **Is it true?**, not for searching saves.

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
| Ask | 2 calls per question (pick, then answer) | about 5k tokens to pick, up to 60k to answer |
| Audit (library) | 1 long-context call for contradictions, plus 1 for gaps | about 40–100k tokens |

Record the real numbers in `model_calls` after the first full import, and update this table.

## Configuration (env)

```
META_API_BASE, META_API_KEY, META_SPARK_MODEL, META_TRANSCRIBE_MODEL
SPARK_OPEN_BASE, SPARK_OPEN_KEY, SPARK_OPEN_MODEL
FEATURE_YT_CAPTIONS=true        # YouTube: captions, else chapters_only
# Video files we hold always use spark_file
SEARCH_PROVIDER, SEARCH_API_KEY
YOUTUBE_API_KEY
EMBED_MODEL=intfloat/multilingual-e5-small
EMBED_DIM=384
MODEL_DAILY_TOKEN_BUDGET=5000000        # everyone, per day
MODEL_USER_DAILY_TOKEN_BUDGET=1500000   # per user per day; the demo user gets half
SPARK_MAX_CONCURRENCY=6
TRANSCRIBE_MAX_CONCURRENCY=2
SPARK_OPEN_MAX_CONCURRENCY=2
```

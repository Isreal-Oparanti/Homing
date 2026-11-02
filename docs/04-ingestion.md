# 04 · Ingestion

How things come in, and how **What is it?** gets content to read. Code lives in `server/app/ingest/` (connectors) and `server/app/ingest/whatsapp/` (the export parser).

## Ways in

| Way | Flow | Limits |
|---|---|---|
| Paste text or a link | `POST /saves {text}`. Links in the text are detected. | 20k chars |
| Upload a file | `POST /uploads/sign` → browser uploads to storage → `POST /saves/file {storage_key}` | 100 MB per file |
| Share (Android installed web app) | Share sheet → `POST /share-target` (Next.js) → small files are forwarded, large ones redirect to the upload page | Vercel body limit of about 4.5 MB |
| WhatsApp export | `POST /uploads/sign` → upload the `.zip` or `.txt` → `POST /imports/whatsapp {storage_key}` | 1 GB zip, 50k messages |

## WhatsApp "message yourself" export

`server/app/ingest/whatsapp/parser.py`. This is pure code, with no model, and fully unit-tested ([11](11-testing-evals.md)).

### Formats to support

| Source | Line format | Media line |
|---|---|---|
| Android | `28/10/2026, 14:05 - Name: text` (also `10/28/26, 2:05 pm - …`) | without media: `<Media omitted>`. With media: `IMG-20261027-WA0001.jpg (file attached)` |
| iOS | `[28/10/2026, 14:05:33] Name: text` | `<attached: 00000012-PHOTO-2026-10-27-10-11-12.jpg>` |

**Parsing rules:**
- **Date order:** detect day-first vs month-first by scanning the whole file for a first or second field > 12. If it's still ambiguous, use the locale guess (day-first for NG), and record that the order was ambiguous on the import.
- **Lines without a timestamp** continue the previous message.
- **Skip:** system lines (encryption notice, "You deleted this message", "Messages and calls are end-to-end encrypted").
- **Edited messages:** strip the `<This message was edited>` suffix.
- **Time zone:** the export carries no zone, so timestamps are read in the user's `tz`.

### From messages to saves

1. **Several URLs in one message** → one `list` save, with `items` filled in later by the reader.
2. **One URL** → a `link` save. Any other text in the message becomes the save `text`.
3. **A label for the previous link:** a text-only message ≤ 60 chars, sent within 180s after a link save, becomes that save's `label`. This rule is from our pile analysis: only 13% of links have labels, and they arrive this way.
4. **Other text-only messages** → a `note` save. Empty or punctuation-only messages ("..") are skipped.
5. **Media** → a `media` row (stored once per sha256) plus a save of kind `image` / `voice` / `video` / `pdf` / `file`. **The type comes from the file's first bytes, not its name**: WhatsApp exports can drop extensions (Isreal's export has 3 Word docs and a PDF named `DOC-…WA0037.`). See the storage rules below.
6. **`<Media omitted>`** → no save. It's counted as `skipped` in `imports.counts`, and the import summary says how many were left out and how to re-export with media.
7. **Secret screen** ([09](09-security-privacy.md#secret-screen)) runs on every text. A match sets `visibility = private`.
8. **Dedupe:** compute `content_hash`. Duplicates are kept as saves and get linked by **What's it for?**, because re-saving is a signal.

**Import summary** (`imports.counts`): `{messages, saves, media, private, duplicates, skipped}`, shown to the user when the import finishes.

### As built (S8 step 1, 1 Nov)
- **Code:** `ingest/whatsapp/parser.py` (pure: `parse`, `plan`) and `ingest/whatsapp/importer.py` (job `import.whatsapp`). Tests on made-up Android 24h, Android 12h month-first and iOS exports in `tests/fixtures/whatsapp/`.
- **Isreal's real export:** 700 messages (28 Jun 2025 to 30 Oct 2026), day-first found from the dates, 6 system lines, 633 planned saves, 63 links labelled by the next message, all 64 attachments found, and each type found from its bytes (3 Word docs and a PDF have no extension).
- **Running the same export again adds nothing:** a save already imported with the same time and `content_hash` is counted as `already`.
- **Files:** photos and PDFs are read as in S7. Videos, voice notes and Office documents are stored and marked "kept, not read yet" (step 2 reads them with Meta's models). Videos are stored as they are for now; the 480p copy comes later (Isreal's videos total 185 MB, the largest 15 MB, under the bucket's 50 MB per-file limit).
- **Skipped and counted:** stickers (`STK-`), contact cards, zips inside the zip, files the export left out, empty and punctuation-only messages.
- **Zip safety:** paths with `..` or a drive or root are refused before anything is read; 2 GB and 20k entries at most; each file 50 MB at most.
- **Token budget for an import (1 Nov, Isreal: "we need to optimize for token management" while staying agentic):**
  - **Nothing to read, no model:** a link whose content can't be fetched (Instagram and Facebook posts, dead pages) and that carries no words of the person's own is kept with an honest note instead of a model's guess. With a label or text, the agent reads those words.
  - **Shorter input:** an imported save sends the reader at most 8,000 characters (fresh saves: 40,000). The first reading needs the gist; Is it true? reads the official page itself.
  - **Read together:** small saves are read 20 per call (`read.batch`). Measured on 20 of Isreal's saves with the real model: 40,703 tokens one at a time, 9,322 together (77% fewer), all 20 returned, the same opportunity call on 20 of 20, titles equivalent.
  - **Only open opportunities are checked:** an imported opportunity is checked when a date it names is still ahead, or when it names none and was saved in the last six months. Otherwise Is it true? says in The team why it held off ("Didn't check …: its date passed on …"), and the card offers **Check it now**.
  - **Low priority:** an import's checks, placements and dates wait behind anything saved by hand.
- **Videos, voice notes and documents (S8 step 2, 2 Nov):** read by What is it? (`_read_media`), never guessed:
  - **Voice notes:** PyAV turns the sound into 16 kHz mono WAV (`ingest/media.py`, first 10 minutes), Muse Voice Transcribe returns the words (`ModelGateway.transcribe`, cached by the sound, recorded in `model_calls` as `transcribe.voice`), and the reader reads them like text (snapshot `speech`). No words heard: kept, and the card says so.
  - **Videos:** the sound is transcribed first. With 40 words or more, the video is read from what's said: cheaper, and every fact can be checked against the words. With less, Spark watches it from a 15-minute signed link to the private bucket (`read.video`); what it sees goes in `what`, but facts must be words said or written by the person. On the local disk (no link), a quiet video is kept.
  - **Documents:** the words come out of the Word, PowerPoint or Excel file (`office_text`, no extra library) and are read like text (snapshot `doc_text`).
  - **A secret heard or written** keeps the save private before any reading.
  - **Measured on two of Isreal's videos:** a silent 0.5 MB clip, watched by Spark: 3,038 tokens, "A close-up of colorful notebooks personalized with names". A 5.2 MB clip with 91 words: transcribed (36s, no tokens) then read: 1,911 tokens, "A short comedy clip showing a demo of an app that tells hot dogs from not hot dogs." Spark watching that same clip cost 15,530 tokens.
  - **All of Isreal's kept files, read on the server (2 Nov):** 36 files, no errors. 17 videos read from their speech, 14 watched by Spark, 5 Word documents, 2 voice notes; 30 transcriptions. 231,854 tokens in all: Spark watching 13 videos 123,277 (about 9,500 each, more than the small clip measured), reading 53,966, and two rebuild calls 54,611. The rebuild then placed 356 saves into 24 goals.
  - **Muse Voice Transcribe's `turns` come back empty in PUSH_TO_TALK mode:** we get the words without timestamps.
- **Where the upload waits:** the API writes it to `IMPORT_DIR` on its own disk, and only a worker on the same machine can read it. That's why jobs have lanes ([03](03-agents.md)).

### Storage rules (approved by Isreal, 31 Oct)

The database holds **text only**: saves, readings, snapshots, captions and transcripts. That's a few MB for the whole pile. Files go to object storage (Supabase free tier: 1 GB). Isreal's export is about 200 MB, 93% of it 31 videos. These rules bring it to about 40–60 MB without losing anything useful.

| File | Rule |
|---|---|
| **Videos** (MP4, MOV) | Spark reads the **original** once. Keep the reading, its timestamped points and a thumbnail (JPEG, 480px wide). Store a **480p H.264 copy** (CRF 28, AAC 64k) instead of the original; the original isn't uploaded. Compression runs in the worker with ffmpeg (in the Docker image). If ffmpeg isn't available (local Windows dev), keep the original and log it. |
| **Photos** (JPEG, PNG, WebP not a sticker) | Store as is. |
| **Voice notes** (Opus) | Store as is; the transcript is the snapshot. |
| **PDFs, Word docs** | Store as is; the extracted text is the snapshot. |
| **Stickers** (`STK-*.webp`) | **Skip.** They're reactions, not saves. Counted as `skipped`. |
| **Contact cards** (`.vcf`) | **Skip.** They hold someone else's personal details. Counted as `skipped`. |
| **Archives inside the export** (`.zip`, `.rar`) | **Don't open or store them.** The save says "zip not imported". |
| **The same file twice** (same sha256) | Store once; both saves point to it. |

**Zip safety:**
- reject paths with `..` or absolute paths (zip slip);
- cap total uncompressed size at 2 GB and the file count at 20k;
- only extract the chat `.txt` and known media types (checked by first bytes, not by name);
- never extract nested archives.

## Connectors (one per platform or kind)

Each connector returns `Gathered(snapshots: list[Snapshot], media_urls: list[str], notes: list[str])`.

### Canonical URLs

`server/app/ingest/urls.py`. Pure code.
- Lowercase the host, strip `www.`, `m.`, and fragments.
- Strip tracking params: `utm_*`, `fbclid`, `igsh`, `si`, `s`, `t` (except YouTube `t`), `ref_src`.
- Normalise YouTube:
  - `youtu.be/ID`, `youtube.com/shorts/ID` and `youtube.com/live/ID` → `https://www.youtube.com/watch?v=ID`;
  - keep `kind=short` in snapshot meta when it was a Short.
- Normalise X: `twitter.com` → `x.com`, drop query.

### YouTube (`youtube.py`)
- **oEmbed** `https://www.youtube.com/oembed?format=json&url=…` gives title and channel.
- **YouTube Data API v3** `videos.list?part=snippet,contentDetails` gives description, `publishedAt` and duration (ISO 8601 → seconds). It needs `YOUTUBE_API_KEY`.
- **Chapters:** parsed by code from description lines like `0:00 Intro`, `12:30 How to…`. They're kept in `snapshot.meta.chapters`.
- Snapshot `metadata`: title, channel, description, chapters and duration.
- **Captions** (when `FEATURE_YT_CAPTIONS` is on): `youtube-transcript-api` gives the timestamped caption text, stored as a `transcript` snapshot with `meta.segments: [{t, text}]`. This is Isreal's decision, with the risk noted in [ADR 0008](adr/0008-platform-rules.md).
- **Never:** download video or audio (no `yt-dlp`).

### X (`x.py`)
- `https://publish.twitter.com/oembed?omit_script=1&url=https://x.com/i/status/{id}` gives author, text (from the HTML) and date.
- **Limit:** only the first post of a thread. For threads, the UI asks the user to add screenshots (read as images).

### Instagram and Facebook (`meta_embed.py`)
- Meta's tokenless oEmbed (`instagram_oembed`, and the Facebook equivalent) gives **only an embed shell**. We tested this on 29 Oct: no caption, author or thumbnail.
- We store the link and use the embed for display only.
- The reading says plainly: *"Instagram reel. We can't see inside it. Add the video or a screenshot if it matters."*
- **Never:** scrape the page or the CDN.

### TikTok (`tiktok.py`)
- `https://www.tiktok.com/oembed?url=…` gives `title` (the caption) and author. Use them **(confirm)** that the field is still the caption.

### Web pages (`web.py`)
- `SafeFetcher.get` (SSRF-safe, see [09](09-security-privacy.md#ssrf-and-fetching)).
  - **Timeouts:** connect 5s, read 15s.
  - **Size cap:** 5 MB.
  - **Redirects:** at most 5, each one re-checked.
  - **Robots:** robots.txt is respected.
- `trafilatura` extracts the main text and metadata. If it fails, fall back to the `<title>` and meta description.
- **Pages built in the browser** (2 Nov): when the main text is under 500 characters, the words inside the page's script data (Next.js `self.__next_f` and `__NEXT_DATA__`: rich-text and description fields) are used instead, each once. The Meta hackathon page on Cerebral Valley gave 75 characters before, 28,062 after.
- If the content type is PDF, hand over to the PDF connector.

### Files (`files.py`), as built in S7
- **Upload:** `POST /saves/file`: 1–6 images, or one PDF, 10 MB each. The browser sends the files straight to the API with a 5-minute upload ticket from the web server, because Vercel limits a request to about 4.5 MB ([07](07-api.md#conventions)).
- **Types** are sniffed from the bytes (PNG, JPEG, WebP, GIF, PDF), never from the name.
- **Storage:** `STORAGE_BACKEND=local` in development (git-ignored `server/data/`), `supabase` in production (private bucket `saves`). Keys are `u/{user_id}/{sha256}.{ext}`, so the same file is stored once.
- **Reading:**
  - a PDF with a text layer (at least 200 characters a page on average) is read as text (`pdf_text` snapshot, then `read.text`);
  - images and scanned or damaged PDFs go to Muse Spark (`read.file`), which returns every word on them as our copy (`ocr_text`) plus the reading. Images are shrunk to at most 1600 px first.
- **Lists:** when a save lists several things (screenshots of an "18 opportunities" thread, a numbered list of links), the reading has `items`. **Is it true?** then checks each item on its own page (`save.check_item`, up to 20, side by side).

### Application sites built by JavaScript (`ats.py`)
A plain fetch of a Workable job page returns only its one-line description (tested 31 Oct on the Afreximbank internship). Workable publishes the same data as JSON, and its robots.txt allows AI input (`Content-Signal: ai-input=yes`).
- `apply.workable.com/{account}/j/{code}` → `GET /api/v2/accounts/{account}/jobs/{code}`. The snapshot holds the title, location, workplace (`on-site`), description, requirements and benefits.
- `/j/{code}` alone is followed to the account's own path first.
- An account link with no job (`apply.workable.com/afreximbank/`) lists the account's jobs (`/api/v1/widget/accounts/{account}`). Code picks the only job, or the one whose title shares the most words with the save's title. If it's unclear, it gives up rather than guess.
- If the JSON can't be read, the plain page fetch is used.
- Greenhouse and Lever have similar public JSON; add them the same way when a real post needs it.

### PDF (`pdf.py`)
- PyMuPDF extracts the text layer, with page numbers kept (`[p. 3]` markers).
- If there are fewer than 200 chars of text per page on average → treat it as scanned and send the PDF to Muse Spark (`read.pdf`, with the OCR-style instruction). Store the result as `ocr_text`.

### Images (`image.py`)
- Store the original. Send a signed URL to Muse Spark (`read.image`).
- Flyers usually carry dates and requirements, so `is_checkable` is often true.

### Voice notes (`audio.py`)
- WhatsApp voice notes are `.opus`. Meta's endpoint takes **WAV only**, so convert with PyAV (bundled decoder, no system ffmpeg) to 16 kHz mono 16-bit WAV.
- Send to `POST /v1/asr/transcribe` (`transcribe.voice`) and store a `transcript` snapshot. The response has `transcript`, `audioDurationMs` and `turns`. Notes over 10 minutes are split.
- Pidgin and Yoruba are not validated languages. Mark `meta.language_validated = false` when detection says so.

### Video files (`video.py`)
- Store the file. Spark reads it through a signed URL or a Files API upload **(confirm)**.
- This only applies to files the user supplied: WhatsApp media, Instagram's own Download button, or screen recordings.

## Failure behaviour

| Failure | What the user sees | Retry? |
|---|---|---|
| Link unreachable or 404 | "Couldn't open this link. We kept what you saved." | 2 tries, then stop |
| Blocked by robots or 403 | "This site doesn't allow automated reading." | no |
| oEmbed unavailable | Fall back to the URL and label only | no |
| Transcription failed | "Couldn't transcribe this voice note." | 3 tries |
| Unsupported file | "We can't read this file type yet." | no |

Every failure writes a plain-language `saves.error` and an `agent_event`.

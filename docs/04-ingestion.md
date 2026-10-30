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
4. **Other text-only messages** → a `note` save.
5. **Media** → a `media` row (stored by sha256) plus a save of kind `image` / `voice` / `video` / `pdf` / `file`, by MIME type.
6. **`<Media omitted>`** → no save. It's counted as `skipped` in `imports.counts`, and the import summary says how many were left out and how to re-export with media.
7. **Secret screen** ([09](09-security-privacy.md#secret-screen)) runs on every text. A match sets `visibility = private`.
8. **Dedupe:** compute `content_hash`. Duplicates are kept as saves and get linked by **What's it for?**, because re-saving is a signal.

**Import summary** (`imports.counts`): `{messages, saves, media, private, duplicates, skipped}`, shown to the user when the import finishes.

**Zip safety:**
- reject paths with `..` or absolute paths (zip slip);
- cap total uncompressed size at 2 GB and the file count at 20k;
- only extract `.txt` and known media extensions.

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
- **Never:** download video or audio, or scrape transcripts. That breaks YouTube's rules ([ADR 0008](adr/0008-platform-rules.md)).

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
- If the content type is PDF, hand over to the PDF connector.

### PDF (`pdf.py`)
- PyMuPDF extracts the text layer, with page numbers kept (`[p. 3]` markers).
- If there are fewer than 200 chars of text per page on average → treat it as scanned and send the PDF to Muse Spark (`read.pdf`, with the OCR-style instruction). Store the result as `ocr_text`.

### Images (`image.py`)
- Store the original. Send a signed URL to Muse Spark (`read.image`).
- Flyers usually carry dates and requirements, so `is_checkable` is often true.

### Voice notes (`audio.py`)
- WhatsApp voice notes are `.opus`. Convert with ffmpeg to 16 kHz mono `.mp3` **(confirm the accepted formats)**.
- Send to Muse Voice Transcribe (`transcribe.voice`) and store a `transcript` snapshot, with segment timestamps if returned.
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

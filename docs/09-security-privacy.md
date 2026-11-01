# 09 · Security and privacy

People's saves are personal. Our own pile contains phone numbers, an account number and what look like backup codes. Treat everything as sensitive by default.

## Authentication

- **Sign-in:** NextAuth with Google, plus a **demo** credentials provider that signs into the shared demo user. The demo user is flagged `is_demo` and reset nightly.
- **The browser never calls the API,** except to send files: the Next.js server adds `X-Homing-Proxy-Secret` and the user headers ([ADR 0005](adr/0005-auth-proxy.md)). For uploads it signs a 5-minute ticket naming the user, and the browser sends the files to the API with it ([07](07-api.md#conventions)).
- **API checks:**
  - compares the secret in constant time (`hmac.compare_digest`);
  - creates the user on first sight (upsert by ID);
  - rejects requests without a user ID, except `/health`.
- **Network:** the API is HTTPS-only, and in production should accept traffic only from Vercel and our own IPs where the host allows it.

## User isolation

- **Repositories** (`server/app/db/repo/*.py`) take `user_id` as a required argument and always filter by it. Route handlers never write raw queries.
- **Jobs** carry `user_id`. Handlers load the save *through the repository with that user_id*. A job for another user's save fails as `PermanentError`.
- **Storage keys** are prefixed `u/{user_id}/`. Signed URLs are issued only for the caller's own keys.
- **Test:** every list and get endpoint has a test proving user A can't see user B's data ([11](11-testing-evals.md#api-tests)).

## Secret screen

`server/app/verify/secrets.py`. Pure code, run on every text before storage and before any model call.

| Pattern | Example shape | Action |
|---|---|---|
| Backup or recovery codes | a note made only of 4+ upper-case alphanumeric groups containing digits, e.g. `8XK2-9QPL` | private |
| Labelled codes | "backup codes", "recovery codes", "2FA codes" followed by 2+ code-like groups, any case, digits only allowed (Google's are digits, GitHub's lower-case) | private |
| Seed phrases | "seed phrase", "recovery phrase", "mnemonic" followed by 12+ words | private |
| Bare long numbers | a message that is only a number of 10+ digits, spaced or dashed (meter tokens, vouchers, PINs), unless it's a phone number | private |
| One-time codes | "code is 123456", "OTP" near 4–8 digits | private |
| Nigerian bank account (NUBAN) | 10 digits near a bank name or "acct", "account" | private |
| BVN or NIN | 11 digits near "BVN" or "NIN" | private |
| Card numbers | 13–19 digits passing a Luhn check | private |
| API keys and tokens | `sk-…`, `AKIA…`, `ghp_…`, `xox[bp]-…`, long high-entropy strings ≥ 32 chars | private |
| Passwords | "password", "pwd", "pass:" followed by a value, or "my password is …" | private |
| Phone numbers | `+234…`, `0[789]0…` (11 digits) | **not private**, but **masked** before any model call and in the demo UI |

**Images and scanned PDFs:** code can't read a picture before the model does, so a screenshot is sent to Muse Spark to be read. The words it returns are screened at once. If they look like a code, account number or key, the save becomes private, the words aren't stored, and nothing else is sent. A note typed with the upload is screened first, as usual, and a private note keeps the file from ever being sent. Say this plainly in the README.

**Private saves:**
- stored and shown blurred to the owner only. The text, link and label are left out of every API response; the owner taps **Show**, which calls `GET /saves/{id}/reveal` (`no-store`, owner only);
- never sent to any model (the gateway refuses, see [06](06-models.md#providers));
- never shown in The team or in exports;
- `private_reason` stores the *type*, never the matched value;
- never embedded, never returned by search, and never used in Ask answers or audits (audits only count them).

**Logs** never contain save text, snapshots, model inputs or model outputs. Only IDs, sizes and statuses. Two guards make this hold for errors too: the database engine runs with `hide_parameters=True`, so errors never quote query values, and the job runner logs only the error's type (the full message goes to `jobs.last_error` in the database).

## SSRF and fetching

`server/app/ingest/fetch.py` `SafeFetcher`:
- **Schemes:** only `http`/`https`, ports 80 and 443.
- **Addresses:** resolve DNS, then reject private, loopback, link-local, multicast and reserved IPs (IPv4 and IPv6). This re-runs on every redirect, with at most 5 redirects, and is re-checked after connect to stop DNS rebinding.
- **Limits:** 5 MB body cap (streamed), connect 5s, read 15s.
- **Robots:** respects robots.txt (cached per host for 1h).
- **Identity:** User-Agent `HomingBot/0.1 (+https://<site>/bot)`.
- **Blocks:** no cookies, no auth headers, never posts forms.

## Uploads

- Direct to storage with signed PUT URLs that last 15 minutes and are scoped to `u/{user_id}/uploads/{uuid}`.
- **The server re-checks after upload:**
  - size;
  - MIME type sniffed from the file's magic bytes, not trusted from the client;
  - allowed types: `txt`, `zip`, images, audio (`opus`, `ogg`, `m4a`, `mp3`, `wav`), video (`mp4`, `mov`, `webm`), `pdf`.
- **Zip:** zip-slip protection, 2 GB uncompressed cap, 20k files cap, allowed extensions only ([04](04-ingestion.md#whatsapp-message-yourself-export)).
- Files are never executed. PDFs are parsed with PyMuPDF only.
- **WhatsApp imports skip contact cards** (`.vcf`, someone else's details) **and never open nested archives** ([04](04-ingestion.md#storage-rules-approved-by-isreal-31-oct)).

## Rate limits

Per user, kept in Postgres with a fixed window:

| Action | Limit |
|---|---|
| `POST /saves`, `POST /saves/file` | 60 per hour |
| `POST /imports/whatsapp` | 3 per day |
| `POST /moments` | 30 per day |
| `POST /asks` | 60 per day |
| `POST /audits` | 5 per day |
| `GET /search` | 120 per minute |
| Model spend | `MODEL_USER_DAILY_BUDGET_USD` |
| Demo user | half of the above, and imports disabled (it already has the sample pile) |

## Supabase

- **The server is the only way in.** It connects to Postgres directly, as the table owner. Supabase's REST Data API isn't used: it's switched off, and every table has RLS with no policies, so the anon key reads nothing.
- **Keys stay server-side.** The service key and database password live only in server env vars. The web app never receives a Supabase key.

## Model data rules

- **Closed model (Muse Spark):** save content, minus private saves, with phone numbers masked.
- **Open model (Muse Spark Open, our host):** the profile plus the eligibility rule text. Nothing else.
- **Provider settings:** ask Meta's API whether it keeps inputs or trains on them, and turn that off if there's a setting **(confirm)**.

## Data retention and deletion

- `DELETE /saves/{id}`: deletes the save, its snapshots, its media object and its events.
- `DELETE /me`: deletes everything for the user, including storage objects, within the request (a job for large accounts).
- Demo user data is reset nightly.
- Model call `output`s cached in `model_calls` are deleted together with the user.

## Secrets management

- **Where secrets live:** only in the host's environment variables (Vercel, the server host, Supabase).
- **Checking:** `.env.example` files list the names and never hold values. Pre-commit runs `gitleaks` on staged files.
- **Rotation:** rotate `PROXY_SECRET` and the API keys if any of them is ever printed in logs or chat.

## Platform rules (disqualification risks)

The architecture treats these as constraints ([ADR 0008](adr/0008-platform-rules.md)):
- No YouTube downloading: no `yt-dlp`. Captions are read with `youtube-transcript-api` behind `FEATURE_YT_CAPTIONS` (Isreal's decision, 31 Oct, [ADR 0008](adr/0008-platform-rules.md)). CI fails if a downloader appears in the dependency lock.
- No Instagram or Facebook scraping. Only the official oEmbed, for embeds.
- No WhatsApp bot or WhatsApp Business API usage.
- X only through the official oEmbed, plus the user's own screenshots.

## Demo hygiene

- **Recording:** the demo is recorded on the **demo user**, seeded from Isreal's pile with private saves removed and phone numbers masked.
- **Before recording:** search the screen for digits longer than 7 characters, and for names of people other than Isreal.

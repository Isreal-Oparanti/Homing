# 08 · Frontend

`web/`: Next.js (App Router) + TypeScript.

## Stack

| Need | Choice | Why |
|---|---|---|
| Framework | Next.js App Router, React Server Components where they help | Isreal knows it, and it deploys on Vercel |
| Styling | Tailwind CSS + **shadcn/ui** (copied components, not a dependency) | Clean, consistent UI quickly |
| Icons | lucide-react | One icon per question (below) |
| Server state | TanStack Query | Caching, retries, optimistic card actions |
| Live updates | `EventSource` on `/api/stream` | SSE relay through Next.js |
| Auth | NextAuth (Google, plus a "Try the demo" credentials provider) | Same pattern as current Crowscap |
| Forms | react-hook-form + zod | The profile form |
| Dates | `date-fns` + `date-fns-tz` | Show times in the user's zone |
| Fonts | Inter (UI) + Source Serif 4 (quoted source text only), via `next/font` | See [13-brand.md](13-brand.md#type) |

**Pin exact versions at scaffold time.** No `"latest"` in `package.json`; the current Crowscap's `"latest"` pins are a lesson.

## Routes

| Route | Screen | Notes |
|---|---|---|
| `/` | Landing (signed out), otherwise redirect to `/today` | "Sign in with Google" · "Try the demo" |
| `/today` | **Today** | Home. Up to 3 cards, plus a "What's coming up?" input (moments) |
| `/threads` | **Threads** | List with counts and the next date |
| `/threads/[id]` | One thread | Saves in order, plus agent notes |
| `/saves/[id]` | **Save card** | Full page. Also opens as a sheet over other screens |
| `/team` | **The team** | Live feed, filterable by question |
| `/search` | **Search and ask** | One box. Typing shows matching saves instantly (words and meaning). **Ask** creates an answer page. |
| `/ask/[id]` | **Answer page** | One question's verified answer; "Ask a follow-up" creates a new page |
| `/audit/[id]` | **Audit report** | Started from a thread ("Audit this thread") or from Settings ("Audit everything") |
| `/import` | Import | WhatsApp export upload and progress |
| `/add` | Add | Paste, upload |
| `/settings` | Profile and settings | Eligibility profile, time zone, delete my data |
| `/share-target` | (handler) | Receives the Android share sheet |
| `/api/auth/[...nextauth]` | NextAuth | |
| `/api/backend/[...path]` | Proxy | Adds the secret and user headers ([ADR 0005](adr/0005-auth-proxy.md)) |
| `/api/stream` | SSE relay | Streams `/api/v1/events/stream`, forwards `Last-Event-ID` |

## Layout

- **Mobile first.** Most first users are on Android. Bottom tab bar: **Today · Threads · Ask · Team**, with a floating **+** (Add). The **Ask** tab is the search-and-ask box.
- **Desktop:** left sidebar with the same items. The save card opens as a right-hand sheet.
- Max content width is 720px for reading surfaces.

## The four questions, visually

| Question | Icon (lucide) |
|---|---|
| What is it? | `ScanText` |
| Is it true? | `ShieldCheck` |
| What's it for? | `Waypoints` |
| When will you need it? | `CalendarClock` |

Icons and labels are monochrome (`--ink-2`). Colour appears only on verdicts and verified quotes; see [13-brand.md](13-brand.md#colour). The same icons are the agents' avatars in **The team**.

## Key components (`web/components/`)

| Component | What it shows |
|---|---|
| `SaveCard` | Header (title, platform, saved date, original link or media), then four `AnswerRow`s. Each row shows a skeleton while its key is in `pending`. |
| `AnswerRow` | Question label + icon, the answer in one line, an expandable detail |
| `EvidenceQuote` | Source favicon + domain, the quoted line with the matched text highlighted, a "Verified on source" badge, a link to the source. **Only renders verified findings.** |
| `VerdictBadge` | `fits_you` · `closed` · `not_for_you` · `needs_your_answer` · `couldnt_confirm`, in plain words ("Fits you", "Closed", "Not for you", "Needs your answer", "Couldn't confirm") |
| `DeadlineText` | "Sun 2 Nov, 23:59 Lagos time", plus a muted "time zone not stated" when relevant, and an **Add to calendar** link (`/saves/{id}/calendar.ics`) |
| `TodayCard` | `why_now` (bold), title, `next_step`, proof chips, and the actions **Use it · Not for me · Later** |
| `PrepSheet` | 5 points, each with source chips (`Video title · 4:12`) that open the player at that second; then "They agree" / "They disagree" sections |
| `ReelPlayer` | YouTube IFrame API playing segments in order (`start`/`end`), or a `<video>` for files. Next/previous, with the segment source shown. |
| `TeamFeed` | Virtualised list of `AgentEvent`s: avatar, question name, summary, relative time, evidence chips. New events slide in live. |
| `ThreadList`, `ThreadView` | Titles, counts, next date; rename inline (sets `locked_by_user`) |
| `ImportPanel` | Drop zone → direct upload with progress → live counters from events (read, private, duplicates) → summary |
| `AnswerQuestion` | Inline answer for `needs_your_answer` (e.g. a French level select) |
| `MomentInput` | "What's coming up?" plus a date picker |
| `SearchAskBox` | One input. Instant results list below (each showing *matched by words* or *by meaning*). An **Ask** button, or Enter on a question, posts `/asks` and opens the answer page. |
| `AnswerPage` | The question; a summary; points, each with citation chips (save title, plus the timestamp for videos) that open the save card with the quote highlighted; "Where your saves disagree"; "Out of date"; "Coming up"; "Not in your saves" (said plainly); "Ask a follow-up" |
| `AuditReport` | Counts per kind, then items grouped by kind. Contradictions show two quotes side by side. Gaps and let-go items carry a "Suggestion" tag. Each item has one-tap actions (Merge · Archive · Re-check · Ignore). |

## Data flow

- **Reads:** TanStack Query → `fetch('/api/backend/…')` → proxy → API. Query keys are `['save', id]`, `['today']`, `['threads']`, `['thread', id]`, `['team']`.
- **Live:** `useEventStream()` opens `EventSource('/api/stream')`.
  - `agent_event` is prepended to `['team']`.
  - `save_updated` invalidates `['save', save_id]`.
  - `card_new` invalidates `['today']`.
  - `ask_progress` and `ask_ready` update `['ask', id]`; `audit_ready` invalidates `['audit', id]`.
  - It reconnects with backoff (1s → 30s) and resumes from the last event ID.
- **Writes:** mutations with optimistic updates for card actions. A failure rolls back and shows a toast with the API's plain `message`.
- **Uploads:** `POST /api/backend/uploads/sign` → `PUT` the file straight to `upload_url` with progress (XHR) → `POST /saves/file` or `/imports/whatsapp`. Files never pass through Vercel.

## Share target (Android installed web app)

`public/manifest.webmanifest`:
```json
"share_target": {
  "action": "/share-target",
  "method": "POST",
  "enctype": "multipart/form-data",
  "params": { "title": "title", "text": "text", "url": "url",
              "files": [{ "name": "files", "accept": ["image/*", "audio/*", "video/*", "application/pdf"] }] }
}
```

`app/share-target/route.ts`:
- **Text and URL:** `POST /saves`, then redirect to `/saves/{id}`.
- **Files ≤ 4 MB:** upload server-side to a signed URL, then `POST /saves/file`.
- **Larger files:** redirect to `/add?pending=share` with a message to pick the file again. (Vercel's body limit; see [01](01-architecture.md#why-this-shape).)

iPhone doesn't support web share targets, so the UI offers paste instead.

## States every screen must handle

Each one is designed and built:
- **Empty:** first run, with "Import your WhatsApp saves" or "Add your first save".
- **Loading:** skeletons, not spinners, per answer row.
- **Partial:** some answers are ready and some are pending.
- **Error:** a plain message and a retry. A failed answer row says what failed, using `saves.error`.
- **Private save:** the content is blurred, with "Kept private: looks like a code. We never send these to AI." and Reveal / Delete actions.

## Copy rules

- **Plain words**, written as short sentences ("Closes Sunday, 23:59 Lagos time").
- **Say what it does,** not what it doesn't do.
- **Never describe the user as a person.** Talk about goals and saves.
- **Numbers only when they're real** (counts from the database).
- **On answer pages, say plainly what isn't in the saves** ("Nothing you saved covers the application form"), and never fill the gap.
- **Ask is not a chat.** No assistant persona, no "As an AI…", no greeting. Just the answer page.
- **Verdict names are fixed:** Fits you · Closed · Not for you · Needs your answer · Couldn't confirm.

## Accessibility and performance

- **Accessibility:**
  - every interactive element is reachable by keyboard;
  - visible focus;
  - colour is never the only signal (verdicts have icon + text);
  - WCAG AA contrast.
- **Performance:**
  - the Today first-load JS budget is ≤ 170 kB gzipped;
  - images go through `next/image`;
  - the feed is virtualised past 100 items.

## Design tokens

The tokens, type and logo come from [13-brand.md](13-brand.md). Define them as CSS variables in `app/globals.css` and map them into the Tailwind theme, so components use `bg-surface`, `text-ink`, `text-teal` and so on, never raw hex values. Dark mode uses the same token names, switched on `prefers-color-scheme`, and is built only if time allows after Day 4.

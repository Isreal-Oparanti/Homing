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
| Fonts | Inter (UI) | Neutral and very readable |

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
| `/search` | Search | Full-text, no chat |
| `/import` | Import | WhatsApp export upload and progress |
| `/add` | Add | Paste, upload |
| `/settings` | Profile and settings | Eligibility profile, time zone, delete my data |
| `/share-target` | (handler) | Receives the Android share sheet |
| `/api/auth/[...nextauth]` | NextAuth | |
| `/api/backend/[...path]` | Proxy | Adds the secret and user headers ([ADR 0005](adr/0005-auth-proxy.md)) |
| `/api/stream` | SSE relay | Streams `/api/v1/events/stream`, forwards `Last-Event-ID` |

## Layout

- **Mobile first.** Most first users are on Android. Bottom tab bar: **Today · Threads · Team · Search**, with a floating **+** (Add).
- **Desktop:** left sidebar with the same items. The save card opens as a right-hand sheet.
- Max content width is 720px for reading surfaces.

## The four questions, visually

| Question | Icon (lucide) | Accent |
|---|---|---|
| What is it? | `ScanText` | slate |
| Is it true? | `ShieldCheck` | green (fits) · amber (needs your answer, couldn't confirm) · red (closed, not for you) |
| What's it for? | `Waypoints` | indigo |
| When will you need it? | `CalendarClock` | sky |

These icons are also the agents' avatars in **The team**.

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

## Data flow

- **Reads:** TanStack Query → `fetch('/api/backend/…')` → proxy → API. Query keys are `['save', id]`, `['today']`, `['threads']`, `['thread', id]`, `['team']`.
- **Live:** `useEventStream()` opens `EventSource('/api/stream')`.
  - `agent_event` is prepended to `['team']`.
  - `save_updated` invalidates `['save', save_id]`.
  - `card_new` invalidates `['today']`.
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

## Design tokens (Tailwind theme)

```
--bg: #FAFAF9   --surface: #FFFFFF   --text: #1C1917   --muted: #78716C
--border: #E7E5E4   --brand: #111111
--fits: #15803D   --attention: #B45309   --stop: #B91C1C   --info: #0369A1   --link: #4338CA
radius: 14px (cards), 10px (controls)   spacing scale: 4px
```

Dark mode: optional, only if time allows after Day 4.

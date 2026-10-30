# 13 · Brand

**Homing**, by Crowscap. *Save anything to use now or later.*

Visual reference: [brand/brand-sheet.html](brand/brand-sheet.html). Open it in a browser.

## Direction in one line

**Warm glass.** Frosted, translucent surfaces over a warm white background with soft red glows. Big, confident geometric headlines. Red is the brand; everything else stays quiet.

> Relic (relic-app.com) uses a similar glass look with a warm accent and is a direct competitor ("helps you remember"). We share the style family but not the details: our accent is red, not terracotta; our headline font is Plus Jakarta Sans, not Poppins; and our own pieces carry the identity (the four-question save card, verified quotes in serif).

## Logo

| File | Use |
|---|---|
| [brand/app-icon.svg](brand/app-icon.svg) | **The icon.** A white lowercase "h" on a red rounded square. The right leg stops short and lands on a dot: home. Installed-app icon, avatar, nav. |
| [brand/icon-dark.svg](brand/icon-dark.svg) | Icon on ink, with a coral dot, for dark contexts |
| [brand/favicon.svg](brand/favicon.svg) | Browser tab (same as the icon) |
| Wordmark | **homing** in Plus Jakarta Sans ExtraBold (800), lowercase, letter spacing −0.045em. The dot of the "i" is a red circle (`--red`). Built in HTML/CSS: a dotless `ı` plus a positioned dot. Export an outlined SVG before any print or social use. |

- **Lockup:** the icon, then the wordmark. The icon is as tall as the wordmark's x-height × 1.9, with a gap of 0.3× the icon's width.
- **Don'ts:**
  - don't recolour the icon tile;
  - don't put the icon on a busy photo;
  - don't add an outline;
  - don't use a capital "H".

## Colour

| Token | Value | Use |
|---|---|---|
| `--red` | `#D2402F` | **Brand and primary action** (main buttons, links, the "i" dot, key words in headlines) |
| `--red-600` | `#B8311F` | hover and pressed states |
| `--red-soft` | `#FCE9E5` | selected states, soft highlights |
| `--glow` | `#F2836F` | background glows only (radial gradients at low opacity) |
| `--bg` | `#FBF8F6` | page background (warm white) |
| `--ink` | `#16181B` | text, secondary dark buttons |
| `--ink-2` | `#4B4F55` | secondary text, question icons |
| `--muted` | `#868A90` | labels, meta |
| `--line` | `rgba(22,24,27,.08)` | dividers |
| `--glass` | `rgba(255,255,255,.62)` + `backdrop-filter: blur(18px) saturate(140%)` | cards, nav, sheets |
| `--glass-line` | `rgba(255,255,255,.7)` | glass borders, plus an inset top highlight |
| `--green` / `--green-soft` | `#1F7A4D` / `#E5F3EA` | **verified quotes, "Fits you"** |
| `--amber` / `--amber-soft` | `#B45309` / `#FCF1E4` | "Needs your answer", "Couldn't confirm" |
| grey (`--ink-2` on `#EFEEEC`) | | "Closed", "Not for you" |

**Rules:**
- **Red is the brand, not a warning.** Because the brand is red, "Closed" and "Not for you" are shown in calm **grey**. They're facts, not alarms. Never use red for errors in content.
- **Green means verified,** and only verified. Highlighted quote text and the "Fits you" badge use it.
- **One red action per screen.** Secondary actions are glass buttons.
- **Glass needs something behind it.** Always pair it with the warm background glows. Glass on a flat white page just looks grey.
- **Fallback:** where `backdrop-filter` isn't supported, use `rgba(255,255,255,.92)`.
- **Contrast:** white on `--red` passes AA for text 14px semibold and up (buttons). Body text is never red on white below 18px.

## Type

| Role | Font | Notes |
|---|---|---|
| Headlines, card titles, wordmark | **Plus Jakarta Sans** (600–800) | Letter spacing −0.02 to −0.045em |
| UI text, numbers | **Inter** (400–600) | `"tnum"` so dates and counts line up |
| Quoted source text | **Source Serif 4** | Only for text quoted from a source or a save, so a quote always looks like a quote |

**Scale (px):** 12 meta · 14 body · 15 answer · 19 card title · 28 section · 64 hero (40 on mobile).

## Shape and depth

- **Radius:** 22px for cards, 999px for buttons, nav and badges.
- **Shadow:** `0 8px 30px rgba(22,24,27,.06)`, plus an inset top highlight `inset 0 1px 0 rgba(255,255,255,.8)`. The primary button gets a soft red shadow: `0 6px 20px rgba(210,64,47,.35)`.
- **Nav:** a floating glass pill, centred, at most 760px wide.
- **Icons:** lucide, 1.8px stroke, 18px, in `--ink-2`.

## Voice

- **Plain, short and specific.** "Closes Sun 2 Nov, 23:59 Lagos time." Not "Don't miss out!"
- **Say what it does.** No hype words: no "supercharge", "magic" or "AI-powered" in the UI.
- **Calm about uncertainty.** "Couldn't confirm" and "Not in your saves" are stated plainly, never apologised for.

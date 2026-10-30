# 13 · Brand

**Homing**, by Crowscap. *Save anything to use now or later.*

Visual reference: [brand/brand-sheet.html](brand/brand-sheet.html). Open it in a browser.

## Direction in one line

Calm, paper-like, precise. **Colour is only used where it carries meaning.** It should feel like a well-made notebook that tells the truth, not a flashy AI app.

## Logo

| File | Use |
|---|---|
| [brand/mark.svg](brand/mark.svg) | The mark on light backgrounds |
| [brand/mark-dark.svg](brand/mark-dark.svg) | The mark on dark backgrounds |
| [brand/app-icon.svg](brand/app-icon.svg) | Installed-app icon, social avatar (export 192, 512 and a maskable 512 PNG) |
| [brand/favicon.svg](brand/favicon.svg) | Browser tab. Heavier strokes so it holds at 16px. |

- **The idea:** a path goes out and comes back around to a dot. The dot is home: a save returning at the right moment.
- **Wordmark:** the mark, then **homing**, all lowercase. Inter Semibold, letter spacing −0.035em. The mark is as tall as the letters' cap height × 1.4, with a gap of 0.3× the mark's width.
- **Don'ts:**
  - don't rotate the mark;
  - don't add an arrowhead (it then reads as a "refresh" icon);
  - don't use any dot colour other than teal;
  - don't use gradients.

## Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | `#F6F5F1` | `#0F1113` | page background |
| `--surface` | `#FFFFFF` | `#171A1D` | cards, sheets |
| `--ink` | `#14171A` | `#ECEDEE` | text, primary buttons |
| `--ink-2` | `#4A4F55` | `#B4B8BD` | secondary text |
| `--muted` | `#80848A` | `#7E838A` | labels, meta |
| `--line` | `#E5E3DE` | `#2A2E33` | borders, dividers |
| `--teal` | `#0E6B63` | `#4FC1B2` | **brand, "verified", "Fits you"** |
| `--teal-soft` | `#E3F1EE` | `#12302C` | verified highlight, badge background |
| `--amber` | `#B45309` | `#F0A35E` | "Needs your answer", "Couldn't confirm" |
| `--amber-soft` | `#FCF1E4` | `#33230F` | |
| `--red` | `#B42318` | `#F07B70` | "Closed", "Not for you" |
| `--red-soft` | `#FBEAE8` | `#3A1714` | |

**Rules:**
- **Teal means "checked and good".** The brand colour and the proof colour are deliberately the same: when you see teal, something was verified. Never use teal decoratively.
- **The four questions are monochrome.** Their icons and labels are in `--ink-2`. Colour appears only on verdicts and verified quotes.
- **Primary buttons are ink, not teal.** That keeps teal meaning "verified".
- **Contrast:** every text/background pair meets WCAG AA. Teal on `--teal-soft` is for badges at 12px semibold or larger.

## Type

| Role | Font | Notes |
|---|---|---|
| UI, headings, numbers | **Inter** (400, 500, 600, 650) | `font-feature-settings: "tnum"` so dates and counts line up |
| Quoted source text | **Source Serif 4** (400, italic) | **Only** for text quoted from a source or a save, so a quote always looks like a quote |

**Scale (px):** 12 meta · 14 body · 15 answer · 18 card title · 24 section · 34 page title. Line height 1.5 for body. Headings use letter spacing −0.01 to −0.03em.

## Shape and spacing

- **Radius:** 14px for cards, 10px for controls, 999px for badges.
- **Spacing:** a 4px scale, with 20px card padding.
- **Shadow:** at most `0 1px 2px rgba(20,23,26,.04)`. Depth comes from borders, not shadows.
- **Icons:** lucide, 1.8px stroke, 18px.

## Voice

- **Plain, short and specific.** "Closes Sun 2 Nov, 23:59 Lagos time." Not "Don't miss out!"
- **Say what it does.** No hype words: no "supercharge", "magic" or "AI-powered" in the UI.
- **Calm about uncertainty.** "Couldn't confirm" and "Not in your saves" are stated plainly, never apologised for.

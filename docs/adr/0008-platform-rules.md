# ADR 0008: Platform rules are architecture constraints

**Status:** accepted · 30 Oct 2026

## Context
The hackathon disqualifies projects that break platform policies. The current Crowscap used `yt-dlp` and `youtube-transcript-api`.

## Decision
- **YouTube:** oEmbed and the Data API only. No downloading, and no transcript scraping. Video understanding happens only through Meta's API if it accepts YouTube URLs, or on files the user supplies.
- **Instagram and Facebook:** official oEmbed for embeds only. No scraping. Users can add files they downloaded with the platform's own button.
- **WhatsApp:** the user's own chat export only. No bot, no Business API.
- **X:** official oEmbed (first post only), plus the user's screenshots.
- **Web pages:** respect robots.txt, one fetch per check, with an identified user agent.
- **Enforcement:** CI fails if `yt-dlp`, `youtube-transcript-api`, `instaloader` or similar packages appear in `uv.lock`.

## Consequences
Some saves can't be read inside, and the product says so plainly. That's a limit we state, not a rule we bend.

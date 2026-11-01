# ADR 0008: Platform rules are architecture constraints

**Status:** accepted · 30 Oct 2026

## Context
The hackathon disqualifies projects that break platform policies. The current Crowscap used `yt-dlp` and `youtube-transcript-api`.

## Decision
- **YouTube:** oEmbed and the Data API for metadata. **Captions** through `youtube-transcript-api`, behind `FEATURE_YT_CAPTIONS` (Isreal's decision, 31 Oct). **No downloading** of video or audio (no `yt-dlp`).
- **Instagram and Facebook:** official oEmbed for embeds only. No scraping. Users can add files they downloaded with the platform's own button.
- **WhatsApp:** the user's own chat export only. No bot, no Business API.
- **X:** official oEmbed (first post only), plus the user's screenshots.
- **Web pages:** respect robots.txt, one fetch per check, with an identified user agent.
- **Enforcement:** CI fails if `yt-dlp`, `instaloader` or similar downloaders appear in `uv.lock`. Built 1 Nov: `.github/workflows/platform-rules.yml` checks `server/uv.lock` and `web/package-lock.json` on every push to `main` and every pull request.

## Update · 31 Oct: YouTube captions

- **What the rules actually say:** the hackathon guide disqualifies projects that "violate legal, ethical, or platform policies" without naming YouTube. YouTube's Terms of Service forbid automated access ("robots, botnets or scrapers"), except as YouTube permits or applicable law allows.
- **The decision:** reading captions is a judgement call. Isreal chose it (option 2) for its value: timestamped words for the prep sheet. It's behind a flag, and we'll say so in the README.
- **Revisit:** ask at office hours. If the organisers say no, set `FEATURE_YT_CAPTIONS=false` and YouTube falls back to chapters.

## Update · 1 Nov: captions from the server
- **YouTube blocks cloud servers.** From the Paris EC2 server, both the caption library and yt-dlp were refused ("Sign in to confirm you're not a bot"). From Crowscap's AWS server yt-dlp got past that but YouTube returned no captions at all. From a home connection captions work.
- **Decision:** caption requests may go through a proxy (`CAPTIONS_PROXY_URL`), used by the caption library only. yt-dlp stays out.

## Consequences
Some saves can't be read inside, and the product says so plainly. That's a limit we state, not a rule we bend.

# Homing

**Save anything to use now or later.**

Homing answers four questions about every save: *What is it? Is it true? What's it for? When will you need it?* Then it brings the save back when it's needed.

Built for the Meta Global AI Developer Hackathon (Indie track) on Meta's Muse Spark and Muse Voice Transcribe.

> The judges' version of this README (what it does, how well it works, limits) is written on Wed 4 Nov.

## How Homing uses Meta's models

Models read, compare and organise; code checks every claim before you see it. The app names the model behind every step (Your agents, and each save card), and says "Code" when no model was used.

| Model | What it does in Homing | Measured on real use |
|---|---|---|
| **Muse Spark** | Reads every save: notes, links, X posts | 178 reads, about 2,600 tokens each |
| | Reads 20 small imported saves in one call | 77% fewer tokens than one call each |
| | Reads screenshots, flyers and PDFs from the image itself | 24 files |
| | Watches uploaded videos that say little, from a short-lived private link | 14 videos |
| | Compares a post with its official page and lists what the post left out, each point with a quote | 92 checks |
| | Organises a whole pile into goals in one long-context pass | 340 of 405 saves placed into 24 goals for 42,560 tokens, against about 900,000 placing them one at a time |
| | Pulls the useful points from each saved video, at the second they're said, and writes a prep sheet | 44 of 45 points confirmed in the captions at that second |
| | Answers questions from your saves only (Ask) | 49 of 49 quotes found word for word in the cited save |
| **Muse Voice Transcribe** | Turns voice notes and the sound of videos into words, so they can be read and checked | 31 recordings |

Code, not a model, decides dates and time zones, eligibility verdicts, whether a quote really appears in its source, whether a video point is said at that second, and when a save comes back. Numbers: [server/evals/REPORT.md](server/evals/REPORT.md).

## Run it locally

```bash
# server (needs Postgres with pgvector: docker compose up -d db, or a Supabase dev database)
cd server
python -m pip install uv
cp .env.example .env
python -m uv sync
python -m uv run alembic upgrade head
python -m uv run uvicorn app.main:app --reload --timeout-graceful-shutdown 3

# web
cd web
npm install
cp .env.example .env.local
npm run dev
```

## For developers

- What we're building and why: [docs/PLAN.md](docs/PLAN.md)
- How it's built: [docs/README.md](docs/README.md)

## Origin

Homing is built by Crowscap. The idea comes from Crowscap, Isreal Oparanti's personal memory product. This repository is new code written during the hackathon. No code was copied from the original Crowscap.

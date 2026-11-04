# Homing

[![CI](https://github.com/Isreal-Oparanti/Homing/actions/workflows/ci.yml/badge.svg)](https://github.com/Isreal-Oparanti/Homing/actions/workflows/ci.yml)

**You saved it because it mattered. Homing makes sure it comes back.**

- **Live app:** https://homing-rho.vercel.app (press **Try the demo**: a full pile, shared with other visitors; or sign in with Google for your own, empty and private)
- **3-minute video:** _link added at submission_
- Built for the Meta Global AI Developer Hackathon (Indie track) on **Muse Spark**, **Muse Wonder** and **Muse Voice Transcribe**.

## The problem

Everyone saves things "for later": a video that could change how you speak, a scholarship, a book someone swore by, a trick to try tomorrow. Then later never comes. The day you need it (the interview, the pitch, the deadline), it's buried somewhere you'll never scroll back to.

Isreal, who built this, has 624 of them in a WhatsApp chat to himself.

Saving is easy. Getting the right thing back, at the right moment, and knowing it's true: that's the hard part. Homing does that part.

## What it does

Homing answers four questions about every save, each answered by its own agent:

| Agent | Answers | How |
|---|---|---|
| **What is it?** | What the save is | Muse Spark reads links, posts, screenshots, flyers, PDFs and videos; Muse Voice Transcribe hears voice notes and video sound |
| **Is it true?** | What the official source says | Muse Wonder finds the organisation's own page (following a blog or post to it), Muse Spark compares, and code keeps only quotes found word for word; who can apply is judged by code against what you've told Homing |
| **What's it for?** | Which of your goals it serves | Muse Spark places it in a goal; Muse Wonder then **looks on the web for more** for that goal |
| **When will you need it?** | When it comes back | Code reads the deadline in your time zone; a moment you type ("recording my demo video tomorrow evening") brings back a **prep sheet** made from your saved videos, each tip playing from the second it's said |

And it keeps working without being asked: **Keep watching** runs at 5 am and 5 pm (Lagos time), re-reading official pages that can still change and saying exactly what changed ("the deadline moved from 12 Nov to 15 Nov", "it's now closed").

**Ask** answers questions from your own saves only, with every quote checked word for word.

## Try it in two minutes

1. Open https://homing-rho.vercel.app and press **Try the demo**.
2. Go to **Agents**. Press **Add** and paste a blog post about an opportunity, e.g. `https://www.opportunitiesforafricans.com/the-undp-africa-young-innovates-programme-2026-2027-for-young-nigerian-innovators/`. Stay on Agents and watch: Muse Wonder opens the blog, follows it to `youngafricainnovates.ng`, and Homing refuses any source it can't prove.
3. Open the save (about 2 minutes later): what the post left out, each point quoted from the official page; the one thing it needs to ask you ("resident in one of seven states?"); the deadline, read from "open 1 September – 18 November 2026".
4. On **Today**, type *recording my demo video tomorrow evening* and add it. Open the **Get ready** card: a prep sheet from the saved speaking videos. Tap a tip's chip: the video plays from that second.
5. Open a goal in **Threads** and press **Find more**. On Agents, watch the plan, the searches, the pages opened, and what code throws out (closed, last year's, not for you). Run it again later: the new plan rules out what the last run learned.
6. **Ask**: *How do I get better at speaking on camera?* Watch Muse Wonder search, open saves, and answer.

## How the agents work: the model proposes, code disposes

Three jobs give **Muse Wonder** tools and let it choose its own steps, each with code as the gate:

| Agent | Wonder's tools | Code refuses, and says why |
|---|---|---|
| **Ask** | search your saves, open a save, submit an answer | a quote that isn't word for word in the save it cites; a number its quote doesn't state |
| **Is it true? (finding the source)** | open the save's links, search the web, follow links, choose a source | a blog, list or social page; a page that doesn't name the thing |
| **What's it for? (finds more)** | plan, search the web, open pages, follow links, propose, finish with a lesson | not the organisation's own site; a list of many calls; closed; no closing date ahead and no sign it's open this year; who can apply rules the person out (judged by code: the profile never reaches the model) |

What makes it an agent rather than a script:
- **It plans.** Finds more always starts with a plan the person can read ("Plan: looking for equity-free grants… Ruling out: …"), with more thinking time for that turn.
- **It corrects itself.** A refusal goes back to Wonder with the problem named; it fixes it or moves on.
- **It remembers.** Each goal keeps the searches it ran and what they gave, the sites refused and why, what the person kept or dismissed (with a one-tap reason), and the lesson Wonder wrote at the end of each run. The next run starts from that memory: in a real run, the plan ruled out three programmes the previous run had been refused on.
- **It acts on its own schedule** (Keep watching), and its findings come back to the person.

Context engineering keeps it sharp and cheap: Wonder only ever names refs (W1, L12), so words on a page can't send it anywhere; a page's links are ranked by code before Wonder sees them (links to other sites and about applying first; menus, footers and social links dropped); older pages shrink in its context once read, while code always checks against the full page.

Details: [docs/03-agents.md](docs/03-agents.md).

## How Homing uses Meta's models

The app names the model behind every step (on Your agents and on each save card), and says "Code" when no model was used.

| Model | What it does in Homing |
|---|---|
| **Muse Spark** | Reads every save (notes, links, X posts, screenshots, flyers, PDFs, videos from a short-lived private link); compares a post with its official page; organises a whole pile into goals in one long-context pass (340 of 405 saves into 24 goals for 42,560 tokens); pulls points from saved videos at the second they're said and writes prep sheets |
| **Muse Wonder** | Runs three agents with tools: Ask, finding a save's official source, and finding more for a goal (plan, search, open, propose, learn) |
| **Muse Voice Transcribe** | Turns voice notes and the sound of videos into words, so they can be read and checked (31 recordings) |

Code, not a model, decides dates and time zones, eligibility, whether a quote really appears in its source, whether a video point is said at that second, whether a call is open, and when a save comes back.

## Proof

Every number is computed by [`server/evals/run.py`](server/evals/run.py); full report: [server/evals/REPORT.md](server/evals/REPORT.md).

| Check | Result |
|---|---|
| Dates read by code (real and post-style phrases, answers worked out by hand) | **30 of 30** |
| The finds gate on 12 real pages, labelled by hand (open calls; a blog; a call that says it's closed; last year's programme; a list of 14 calls; pages with no sign a call is open) | **12 of 12** |
| Ask on real runs: quotes found word for word in the cited save | **68 of 68** (0 dropped) |
| Prep sheets: video points found in the captions at the stated second | **44 of 45** (1 dropped by code) |
| Search by meaning on the real pile (labels are drafts) | 12 of 15 questions with a right save in the top 5 |

Building the eval found real bugs before judges could: a page saying "Our 2026 submissions are now closed!" would have passed; so would last year's programme and a list of 14 calls. All are now refused, with tests. The live demo found two more: a deadline window ("open 1 September – 18 November 2026") read as its start, and a rule about states judged as met from the country. Both fixed, with tests.

CI runs 250+ server tests, lint and the web build on every push.

## Guardrails

- **Prompt injection:** every prompt treats saved and web content as data, not instructions; agents can only name refs, never type URLs; nothing a model writes is run; code checks every quote, number and date. Tested with a page that tells the agent to open another site.
- **Privacy:** what Homing knows about you (country, age, study, company) is used only by code and never sent to a model. Saves that look private (passwords, codes, account numbers) are never sent to AI, pasted text included.
- **Fetching:** one guarded fetcher for every URL: public addresses only (re-checked on redirects), robots.txt respected, size-capped.
- **Cost:** daily token budgets per person and in total, a separate smaller share for the web agents (so finding more can never pause reading or Ask), one long web job at a time, time limits on every agent run, and a cap on Find more taps.

## Limits, said plainly

- YouTube shares captions only with a video's owner: a video without captions shows its description and offers **Paste its transcript**.
- Pages that only render in a browser (some application forms) can't be read; Homing says so and offers **Paste what it says**.
- The finds gate is strict on purpose: a run can come back with nothing kept rather than show a call it couldn't prove open.
- The demo account is shared by every visitor and is reset between judging days.
- Search eval labels are drafts until the owner confirms them.

## Run it locally

```bash
# server (needs Postgres with pgvector: docker compose up -d db, or a Supabase dev database)
cd server
python -m pip install uv
cp .env.example .env
python -m uv sync
python -m uv run alembic upgrade head
python -m uv run uvicorn app.main:app --reload --timeout-graceful-shutdown 3
python -m uv run python -m app.worker   # the agents

# web
cd web
npm install
cp .env.example .env.local
npm run dev
```

## For developers

- What we're building and why: [docs/PLAN.md](docs/PLAN.md)
- How it's built: [docs/README.md](docs/README.md)
- The agents: [docs/03-agents.md](docs/03-agents.md)

## Origin

Homing is built by Crowscap. The idea comes from Crowscap, Isreal Oparanti's personal memory product. This repository is new code written during the hackathon. No code was copied from the original Crowscap.

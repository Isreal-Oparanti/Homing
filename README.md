# Homing

[![CI](https://github.com/Isreal-Oparanti/Homing/actions/workflows/ci.yml/badge.svg)](https://github.com/Isreal-Oparanti/Homing/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Homing** (like a homing pigeon): wherever you let it go, it finds its way back. Your saves should too.

**A memory for everything you save: it reads it, proves it against the source, and brings it back the moment it matters.**

Built for the **Meta Global AI Developer Hackathon · Indie track**. Every model call runs on Meta's models (**Muse Spark**, **Muse Wonder**, **Muse Voice Transcribe**) through one gateway, `server/app/llm/gateway.py`.

**Live:** https://homing-rho.vercel.app (press **Try the demo**) · **Video:** https://youtu.be/n3XILic3pms

## Why

Everyone saves things "for later". A Y Combinator application. A conference's call for speakers. A job post. A video on how to speak on camera. Then later never comes.

- **People save out of fear of losing things, and the pile becomes stress.** Tab and link hoarders keep items "just in case", and the build-up weighs on them (Chang et al., CHI 2021 [1]).
- **Organising doesn't bring things back.** People who carefully file into folders find things no faster than people who don't (Whittaker et al., CHI 2011 [2]).
- **A save only frees your mind if you trust it will be there.** When people believe what they saved is safe, they remember new things better; when they don't, they can't let go (Storm & Stone, Psychological Science 2015 [3]).
- **An unfinished goal keeps nagging until it has a plan.** Making a specific plan for it is what quiets it (Masicampo & Baumeister, JPSP 2011 [4]).
- **Read-later apps die when "later" never comes.** Pocket, the best known, shut down on 8 July 2025 [5].
- **People want AI to do the legwork, but stay in charge.** Workers want agents to take over about 46% of their tasks, and most prefer a partnership to full automation (Shao et al., Stanford 2025 [6]).

And when a save does come back, it's often wrong. The post you saved is someone's retelling, not the source. A real one: a blog post said a UN innovation programme was *"for young innovators"*. The official page says applicants *"must be resident in one of the seven Cohort 2 states"*. The post left out the one rule that decides if you can apply.

Homing started from a real pile: **624 saves** in one "note to self" WhatsApp chat.

Homing's answer, in one line:

> **A save should come back on its own, at the moment it matters, saying only what its source can prove.**

In full: every save gets four answers, each from its own agent (*What is it? Is it true? What's it for? When will you need it?*). Models read, search and reason; code checks every quote, number, date and rule before you see it. Then the agents keep working without being asked: they check the source, find more for your goals, watch for changes, and prepare you for what's coming. Every run remembers what the last one learned.

Reading links with a model exists. Reminders exist. Web search exists. **We don't claim the parts. We claim the loop:** agents that act on your saves on their own, with code as the gate on every word, and memory that makes each run smarter than the last.

## From research to design

Each finding above became a design choice.

| What the research says | What Homing does |
|---|---|
| People save out of fear of losing things [1] | Homing keeps its own copy of what a page says the moment you save it. If the link dies, your save doesn't. |
| Folders don't help people find things again [2] | No folders. Homing sorts saves into your goals for you, and you find anything by asking in plain words. |
| Saving frees the mind only when you trust it [3] | Every answer shows the exact line it came from, checked word for word against the source. |
| An unfinished goal nags until it has a plan [4] | Every save gets a "when" and a next step. Tell Homing what's coming up and it writes you a prep sheet. |
| "Later" never comes [5] | Your home screen is **Today**: saves come to you on the right day. You don't have to go looking. |
| People want AI as a partner, not a replacement [6] | Agents do the searching and checking. You decide: keep it, say "not for me" and why, or answer the one question they can't. |

## How it works

```mermaid
flowchart LR
  S[You save a link, post, flyer, PDF, voice note, video] --> W[What is it?<br/>Muse Spark reads it<br/>Voice Transcribe hears it]
  W --> T[Is it true?<br/>Muse Wonder finds the official page<br/>Muse Spark compares]
  W --> F[What's it for?<br/>Muse Spark places it in a goal<br/>Muse Wonder finds more]
  T --> N[When will you need it?<br/>code reads the deadline<br/>in your time zone]
  T & F & N --> G{{Code is the gate<br/>quotes word for word<br/>numbers, dates, rules}}
  G --> Y[Today: it comes back<br/>with the next step]
  K[Keep watching<br/>5 am and 5 pm] --> T
  K --> F
```

The load-bearing mechanisms:

- **Code is the gate.** A quote is kept only if code finds it word for word in the source. A number, only if its quote states it. Dates are read by code, never by a model, in your time zone ("open 1 September to 18 November 2026" closes on 18 November). Who can apply is judged by code against what you told Homing; your profile is never sent to a model.
- **Muse Wonder works as an agent, three times.** In **Ask** it searches your saves and answers. In **Is it true?** it follows a blog or a post to the organisation's own page. In **What's it for?** it searches the web for more for your goals. Each time it chooses its own steps, and each time code refuses what it can't prove, says why, and sends it back.
- **It plans, and it learns.** Finding more starts with a plan you can read. Each goal keeps a memory: the searches it ran and what they found, the sites refused and why, what you kept, what you said wasn't for you, and the lesson Wonder wrote at the end of the run. The next run starts from it.
- **The context stays sharp.** Wonder can only name refs (W1, L12, P2), never type a URL, so words on a page can't send it anywhere. Code ranks a page's links before Wonder sees them, and pages it read a while ago shrink in its context; code always checks against the full page.
- **It acts on its own.** Keep watching runs at 5 am and 5 pm. It re-reads official pages that can still change. An unchanged page costs no model call. A changed one is checked again, and you're told exactly what changed: "the deadline moved from 12 Nov to 15 Nov".
- **It prepares you.** Type what's coming up ("recording my demo video tomorrow evening"). Homing goes through the videos you saved for that goal and writes a prep sheet; every tip plays its video from the second it's said, checked against the captions.

## Inside one agent run

This is **Find more**, step by step. Muse Wonder decides what to do; code decides what's true.

```mermaid
sequenceDiagram
  participant M as Goal memory
  participant C as Code
  participant W as Muse Wonder
  participant S as Muse Spark
  M->>C: past searches, refused sites, what you kept or turned down, last lesson
  C->>W: your goal, its saves, that memory, five tools
  W->>C: plan (what to look for, what to rule out)
  Note over C: code holds every other tool until there is a plan
  W->>C: web_search "startup accelerator applications open"
  C->>W: leads W1 to W8 (titles and snippets, no URLs)
  W->>C: open_page W3
  C->>W: page P1, plus its 20 best links L1 to L20, ranked by code
  W->>C: propose_find from P1, with quotes
  C->>S: is P1 the page for this one opportunity? who can apply?
  S->>C: yes, and the rules, each with its quote
  Note over C: official site? already saved? named word for word?<br/>summary quoted word for word? numbers backed?<br/>a list of many? says closed? deadline passed?<br/>open this year? fits what you told Homing?
  C->>W: refused, and why ("The page says it's closed")
  W->>C: open_page L4, propose_find again
  C->>W: accepted
  W->>C: finish, with a lesson for next time
  C->>M: what each search found, what was refused and why, the lesson
```

**Is it true?** runs the same way with its own tools: follow the post's links or search, open pages, then `choose_source` or `give_up`. If Wonder chooses a page the post's words aren't really on, code refuses it and Wonder keeps looking. If it runs out of turns, a fixed path takes over, so every save still gets checked.

**Ask** gives Wonder your saves as its tools (`search_saves`, `open_save`, `submit_answer`): it searches, reads, then answers. Code shows a point only when its quote is found word for word in the save it cites.

## Results (live, Meta's models, 4 Nov 2026)

Every number comes from the committed scripts ([`server/evals/run.py`](server/evals/run.py)) or the stored record of real runs. Full report: [`server/evals/REPORT.md`](server/evals/REPORT.md).

**With and without the gate**

What you would have seen if the model's output went straight to you, against what code let through.

| Where | Without the gate | With the gate |
|---|---|---|
| 12 real opportunity pages, labelled by hand | all 12 shown, **9 of them wrong** (closed, last year's, a list, a blog, no open call) | **3 shown, all 3 right** |
| Find more, live runs | 17 shown, **15 that failed a check** (closed, last year's, a list, not the official site, not for you) | **2 shown** |
| Prep sheets, tips from saved videos | 80 tips, **2 pointing at a second where they aren't said** | **78 tips**, each at the right second |
| Ask, quotes in answers | 65 quotes | **65 of 65** found word for word in the save |

The gate is strict on purpose: a run that keeps nothing beats one that shows you a call that already closed.

**The finds gate on 12 real pages: 12 of 12 right**

Twelve real pages, recorded on 4 Nov ([`evals/finds_pages.jsonl`](server/evals/finds_pages.jsonl)), each labelled by hand: would a careful person show this as open now? Code only, no model.

| Trap | Example | Code |
|---|---|---|
| A blog retelling the call, not the organisation | an opportunity blog | refused |
| "Our 2026 submissions are now closed!" | socialshifters.co | refused |
| Last year's programme ("April to June 2026") | startup.google.com | refused |
| One page listing 14 different calls | an opportunities roundup | refused |
| An organisation's page with no sign a call is open now | 6 foundation and programme sites | refused |
| Really open | ycombinator.com and 2 others | **kept** |

**A real run, step by step** (saving a blog post about a UN innovation programme, on the live demo):

| Time | Agent | Step |
|---|---|---|
| 17:14 | Is it true? · Muse Wonder | Opened the blog, then the programme's official site |
| 17:14 | Is it true? · Muse Wonder | Searched undp.org for the programme |
| 17:14 | Is it true? · **Code** | **Refused that source: those words aren't on the page word for word** |
| 17:14 | Is it true? · Muse Wonder | Chose the programme's official site as the source |
| 17:16 | Is it true? · Muse Wonder + Spark | 3 things the post left out. 1 question for you: "Do you live in one of the seven states it covers?" |
| 17:16 | When will you need it? · **Code** | Brings it back on Wed 11 Nov, from "open 1 September to 18 November 2026" |

**It learns** (two runs of Find more on the same goal, three minutes apart):
- **Run 1 ends with a lesson:** "Next time: Avoid 500 Sustainable Innovation (closed Sep 2025) …"
- **Run 2 starts from it:** "Plan: … Ruling out: … 500 Sustainable Innovation (closed Sep 2025) …"

**More checks**

| Check | Result |
|---|---|
| Dates read by code (real and post-style phrases, worked out by hand) | **30 of 30** |
| Search by meaning on a real pile | 12 of 15 questions with a right save in the top 5 |
| A page telling the agent to open another site | can't happen: there's no ref to it (test) |

## What it costs (tokens, from the gateway's counters)

| Job | Per run, about |
|---|---|
| Read a save (Muse Spark) | 2,600 |
| Ask, as an agent (Muse Wonder) | 30,000 |
| Find the official source (Muse Wonder) | 13,000 |
| Find more for a goal (Muse Wonder, plus Spark to read who can apply) | 190,000 |
| Keep watching an unchanged page | **0** (code only) |
| Sort a whole pile into goals (one long-context pass) | 42,560 for 340 saves, against about 900,000 one at a time |

## Status and test results (4 Nov 2026)

- **251 tests pass** (`pytest`), plus lint, types and the web production build, on every push in CI.
- Live at https://homing-rho.vercel.app, agents running around the clock.
- Every screen in the video is the live product.

## Quickstart

```bash
# server (Postgres with pgvector: docker compose up -d db)
cd server
python -m pip install uv
cp .env.example .env            # set META_API_KEY
python -m uv sync
python -m uv run alembic upgrade head
python -m uv run uvicorn app.main:app --reload
python -m uv run python -m app.worker      # the agents
python -m uv run pytest                    # the tests
python -m uv run python -m evals.run       # the eval report

# web
cd web
npm install
cp .env.example .env.local
npm run dev
```

More: [server/README.md](server/README.md) · [docs/](docs/README.md)

## Try the demo (two minutes)

1. Open https://homing-rho.vercel.app and press **Try the demo**.
2. Go to **Agents**, press **Add**, and paste the blog post we tested with: `https://www.opportunitiesforafricans.com/the-undp-africa-young-innovates-programme-2026-2027-for-young-nigerian-innovators/`. Watch the steps arrive.
3. About two minutes later, open the save: what the post left out, quoted from the official page; the one question; the deadline.
4. On **Today**, type *recording my demo video tomorrow evening*. Open the **Get ready** card and tap a chip: the video plays from that second.
5. In **Threads**, open a goal and press **Find more**. Watch the plan, the pages, and what code throws out.
6. In **Ask**, try *How do I get better at speaking on camera?*

## References

1. Chang, J. C., Hahn, N., Kim, Y., Coupland, J., Breneisen, B., Kim, H. S., Hwong, J., & Kittur, A. (2021). *When the Tab Comes Due: Challenges in the Cost Structure of Browser Tab Usage.* CHI 2021.
2. Whittaker, S., Matthews, T., Cerruti, J., Badenes, H., & Tang, J. (2011). *Am I wasting my time organizing email? A study of email refinding.* CHI 2011.
3. Storm, B. C., & Stone, S. M. (2015). *Saving-enhanced memory: The benefits of saving on the learning and remembering of new information.* Psychological Science, 26(2).
4. Masicampo, E. J., & Baumeister, R. F. (2011). *Consider it done! Plan making can eliminate the cognitive effects of unfulfilled goals.* Journal of Personality and Social Psychology, 101(4).
5. Mozilla (2025). *Pocket is shutting down* (announcement; service ended 8 July 2025).
6. Shao, Y., et al. (2025). *Future of Work with AI Agents: Auditing Automation and Augmentation Potential across the U.S. Workforce* (WORKBank). Stanford University.

MIT licensed. See [LICENSE](LICENSE).

# Homing: what we're building

_Homing is built by Crowscap. The idea comes from Crowscap's own memory product._

_Meta Global AI Developer Hackathon · Indie track_
_Due **Wed 4 Nov, 9 PM ET**, which is **Thu 5 Nov, 03:00 Lagos**_

This is the one document that says what we're building and why. When we're stuck, tired or drifting, we come back here before changing anything. Changes are made on purpose and recorded in the log at the bottom.

This file is for us. The pitch (video, README, X post) is written separately and comes from this file, not the other way round.

---

## 1. What we're building

**Homing: save anything to use now or later.**

Every time you save something, Homing answers four questions about it.

| Question | What the answer looks like |
|---|---|
| **What is it?** | "A 12-minute talk on speaking techniques." "An internship call from Afreximbank." |
| **Is it true?** | For saves with facts that can be wrong: what the official source says, and what the post left out. Every point quotes the exact line from the source. |
| **What's it for?** | Which of your goals it serves (for example "Getting into YC" or "Speaking better"), and what else you've saved for that goal. |
| **When will you need it?** | A date or a moment, such as "before the deadline on 15 Nov, Lagos time" or "the next time you record a video". |

- **Now:** you see the four answers right after you save. You can act on it straight away, or let it go knowing it's handled.
- **Later:** Homing brings the save back at that date or moment, together with the next step.
- **Anytime:**
  - **search** by meaning, so "YC" also finds "Y Combinator";
  - **ask** a question ("What do I know about getting into YC?") and get one answer page, built only from your saves, with every point linked to the save it came from;
  - **audit** a thread or everything: repeats, things that went bad, contradictions, gaps, and what to let go.

Behind each question is an agent. The agents work on their own schedules, every action they take is shown with its evidence, and every decision stays with you.

## 2. The problem

People save things because they mean to use them. Three things go wrong.

1. **The pile grows and weighs on you.** People save partly out of fear of losing things, and the pile itself becomes a source of stress (see section 3).
2. **The right save doesn't come back when it matters.** You start from scratch or miss the moment, even though you'd already saved what you needed.
3. **The save isn't the whole truth.** Posts leave things out, go out of date, or don't apply to you, and you find out only after acting on them.

The cost is highest for people outside the default user that big products are built around. For them, the deadline is in another time zone, the rules may exclude their country, and nobody nearby has done it before.

**Evidence from Isreal's WhatsApp "message yourself" chat** (624 text messages, plus photos, videos and files, 28 Jun 2025 – 28 Oct 2026):

| Finding | Detail |
|---|---|
| Most saves don't say why they were saved | About 6 in 10 messages are video links (YouTube, Instagram, Facebook). Few links say why: only 11 of 486 links have a label in the same message (counted 31 Oct). An earlier count gave 13%, which likely included labels sent as a separate message; settle the method before quoting it. |
| Goals show up even though they were never written down | Getting into YC: 7 saves, from the YC account page (11 Sep 2025) to a funding digest (12 Oct 2026). Funding and opportunities: about 25. Speaking better: 10. Making a product demo video: 7. AI and agent engineering: about 15. |
| What was needed had already been saved | The 12 Oct digest gives the YC Winter 2027 deadline as 2 Nov. Before this hackathon's demo video, 16 videos on speaking and demo-making were already saved. |
| Things get saved twice | 4 items were saved again on a later day, one of them 11 weeks after the first time. |
| Posts aren't the whole truth | The Afreximbank internship post left out several things the official posting says. The internship is on-site in Cairo. You need fluency in English or French *and* a working knowledge of the other. Full-time study is "preferred", not required. The $500 housing allowance is only for interns who relocate. The post says it closes 31 Oct, but the official posting shows no closing date. |
| The gap in today's Crowscap | Crowscap's 12 Aug pitch promised to bring saves back "exactly when needed". Today's Crowscap saves and organises, but it doesn't bring things back on its own. |

## 3. What research says about saving, and what we build because of it

| What's known | Source | What Homing does about it |
|---|---|---|
| People keep things (open tabs, saved links) partly out of fear of losing them, and the build-up causes stress. | Chang et al., *When the Tab Comes Due*, Carnegie Mellon, CHI 2021 | Saving is one action from anywhere, with nothing to fill in. At save time we keep a copy of the content (the page text, the post text, the transcript), so a dead link or deleted post doesn't lose it. |
| Filing things into folders doesn't help people find them later. | Whittaker et al., *Am I wasting my time organizing email?*, CHI 2011 | No folders and no tags. Agents connect saves to goals, and search finds anything. |
| Saving frees your memory for new things only when you trust the save will be there. | Storm & Stone, *Saving-enhanced memory*, Psychological Science, 2015 | Every save gets its four answers right away. Facts come with the source line, and you can see what each agent did. |
| An unfinished goal keeps nagging at you until you make a specific plan for it. | Masicampo & Baumeister, *Consider it done!*, Journal of Personality and Social Psychology, 2011 | Every save gets a "when". A save that comes back brings its next step with it. |
| Read-later apps fail when "later" never comes. Pocket, the best-known one, shut down on 8 July 2025. | Mozilla announcement, 2025 (the conclusion is our reading of it) | Bringing saves back is the core of the product, not a side feature. **Today** is the home screen. |
| Workers want AI to take over repetitive work, about 46% of tasks, but most prefer an equal partnership to full automation. | Shao et al., *Future of Work with AI Agents* (WORKBank), Stanford, 2025 | Agents do the reading, checking, connecting and timing. You make every decision: *Use it · Not for me · Later*. Homing doesn't act outside your library. |

Together, these give the theme fit. A save you trust, with a "when", stops taking up space in your head.

## 4. Who it's for

- **First users:** early-stage founders and young professionals in Nigeria, and in markets like it. They:
  - save a lot;
  - chase funding, programmes and skills;
  - keep their notes in WhatsApp.

  A missed deadline or a rule that excludes them costs them the most. *Assumption to test: they already spend money to get ahead, so they'll pay for this.*
- **Also welcome:** students and anyone else who saves a lot and uses little. They're not who we build the business around.
- **Who pays (untested):** people already pay for second brains (Readwise, Recall, mymind). Our paid part would be the agents' work.

## 5. How it works

### 5.1 Now: the save card

Saving something (paste, upload, share, or importing the WhatsApp export) creates a **save card** with the four answers. Two examples from the real pile:

> **Afreximbank internship call**, saved from a WhatsApp community post
> - **What is it?** An internship call from Afreximbank, read from the post.
> - **Is it true?** The official posting adds what the post left out: it's on-site in Cairo, you need the second language too, full-time study is only preferred, and the $500 housing is only for interns who relocate. The post says it closes 31 Oct; the official posting shows no closing date. _(Each point links to the official line.)_
> - **What's it for?** Funding and opportunities: your 26th save on this.
> - **When will you need it?** Now. If it's real, it closes tomorrow. Needs your answer: do you have a working knowledge of French?

> **"10 Speaking Techniques That Made Me A Top 1% Speaker" (YouTube)**
> - **What is it?** A talk on speaking techniques.
> - **Is it true?** Nothing to check.
> - **What's it for?** Speaking better: your 10th save on this since April.
> - **When will you need it?** Before your next talk or recording. Your hackathon demo video is due 4 Nov.

### 5.2 The agents (one per question)

Each agent keeps its own memory, runs on its own schedule, and logs every action, with a link to the evidence, in **The team** feed.

**What is it?**
- **Runs:** on every new save.
- **Does:** reads the save and writes down what it is and its key facts (dates, amounts, requirements, links). Keeps a copy of the content.
- **How each kind of save is read:**
  - Text notes: directly.
  - YouTube: title from oEmbed, plus the captions (`youtube-transcript-api`, behind a flag; Isreal's decision, 31 Oct). Description and chapters from the YouTube Data API when a key is set.
  - X posts: text from the official oEmbed.
  - Web pages: one fetch.
  - Images, flyers and PDFs: Muse Spark.
  - Voice notes: Muse Voice Transcribe.
  - Video files: Muse Spark, only for files we have legitimately.
  - Instagram and Facebook links: kept as links. We can't read inside them unless the user supplies the file.
- **Never:**
  - changes the original;
  - downloads YouTube videos;
  - scrapes Instagram or Facebook;
  - sends secret-looking items (codes, account numbers) to any model. Those are screened out by code first.

**Is it true?**
- **Runs:** on saves with checkable facts (opportunities, deadlines, prices, requirements). It re-checks open items once a day.
- **Does:**
  1. Finds the official source: links inside the post first, then a search.
  2. Fetches the source.
  3. Compares it with the post.
  4. Converts the deadline to your time zone.
  5. Checks your eligibility against your profile.
- **Labels each opportunity:** **fits you / closed / not for you / needs your answer**.
- **Proof rule:** every point must quote a line from the source. Code confirms the quote is on the page, and any point that fails is dropped.
- **Never guesses.** If the page won't open, it says "couldn't open the official page". If there's no date, it says "no date on the official page".

**What's it for?**
- **Runs:** after every save, plus once a day over the whole library, using Spark's long context.
- **Does:**
  - groups saves into **threads**, which are the goals they serve;
  - merges repeats ("you saved this on 8 Jul");
  - links related saves.
- **You stay in control:** you can rename, merge or split threads.
- **Never:** describes you as a person. Threads are about goals, not personality.

**When will you need it?**
- **Runs:** at save time, to set the "when", and then continuously, watching for that moment.
- **Where the "when" comes from:**
  1. a date inside the save;
  2. a date in a related save (for example, a deadline in the same thread);
  3. a moment you name ("recording Tuesday");
  4. otherwise, "no date". It comes back when you save something related or search for it.
- **Brings a save back when:**
  - its date is close;
  - a related save arrives;
  - your named moment arrives;
  - the save goes bad (closed, moved, dead link).
- **What comes back:** something you can use, with the next step. For example: a checklist; a **prep sheet** (what your saved videos agree and disagree on, each point linked to the exact second); or a short reel of those moments.
- **Limits:** at most 3 cards a day. Anything you dismiss doesn't come back.

**Why four agents and not one script:**
- They work at different times: on each save, daily, and at dates.
- You can see who did what.
- If one fails, the others keep working.

### 5.3 Ways in and out

- **In:**
  - Import the WhatsApp "message yourself" export, with media.
  - Paste or upload.
  - Share into the web app. Android "share to" works through the installed web app; iPhone users paste.
- **Out:**
  - The **Today** screen.
  - Calendar entries for dates.
  - Search by meaning and by words, Ask (answer pages) and Audit (reports).

## 6. Screens and words

| Word | Meaning |
|---|---|
| **Save** | Anything you add: a link, note, flyer, PDF, voice note or video |
| **Save card** | The four answers for one save |
| **Thread** | A goal your saves serve, with everything you saved for it |
| **Today** | The home screen: at most 3 things that need you now, each with its next step and proof |
| **The team** | A live feed of what each agent did, each entry linked to its evidence |
| **Answer page** | The result of asking a question: points built only from your saves, each linked to its save |
| **Audit** | A report on a thread or on everything: repeats, things that went bad, contradictions, gaps, what to let go |

Screens:
- **Today**
- **Threads**
- **Search and ask**: one box. Typing shows matching saves instantly; pressing *Ask* builds an answer page.
- **The team**
- the **save card**, which opens when you save or tap a save
- the **answer page** and the **audit report**

There's no chat thread. You search, ask one question at a time, or run an audit, and saves also come back on their own.

## 7. How it fits the hackathon

**Theme:**
- **"Build for Your World":** the notes app in our world is WhatsApp. Deadlines are shown in Lagos time, and eligibility is checked from Nigeria.
- **"Free up time and mental space":** agents do the reading and checking. A trusted save with a "when" stops nagging you (section 3).
- **"Possible now that wasn't before":** models that read every format and hold a whole library at once can understand saves that never had a label, and check them against their sources.

**Judging:**

| Criterion | Weight | Our case |
|---|---|---|
| Impact | 30% | A problem almost everyone has, hurting most for people outside the default. Shown on a real pile and real posts. Design grounded in research (section 3). |
| Use of Meta's models | 25% | Muse Spark reads flyers, PDFs and video, and reads the whole 16-month library in one pass. Voice Transcribe handles voice notes. Muse Spark Open matches personal details. The candidate for "surprised even us" is 16 saved videos turned into the points they agree on, each with its exact second. |
| Technical depth | 20% | Four agents with their own memory, schedules and triggers. Quotes checked by code. Dates and time zones worked out by code. Accuracy numbers measured on the real pile. |
| Demo | 25% | Agents visibly working on real saves, a real "what the post left out" moment, and a payoff that happens inside the video itself. |

**Bonus prizes:**
- **Best Agentic Use-Case ($5k):** a visible team on schedules, with the user deciding.
- **Most Viral on X ($20k, engagement counts until 8 Nov):** a relatable pile, plus a real opportunity-thread check.
- **Open weights ($10k):** Muse Spark Open, running on our own or partner inference.
- **Community Vote ($10k):** Nigerian founder and builder networks.

## 8. The 3-minute demo: past, now, later

| Time | Scene | What must be on screen |
|---|---|---|
| 0:00–0:15 | **Hook:** scrolling the real "message yourself" chat, 624 messages in 16 months | The real pile |
| 0:15–0:55 | **Past:** import the pile. The team feed fills up as agents read. Threads appear, such as "Getting into YC" and "Speaking better". | Agents working on real saves |
| 0:55–1:45 | **Now:** save a live opportunity post. The save card shows what it is, what the post left out (quoted), whether it fits you, and when you'll need it. | Proof from the official source |
| 1:45–2:40 | **Later:** the hackathon deadline comes up on **Today**: "You saved 16 videos for this." A prep sheet appears (and a reel, if video works). Then: "I recorded this video with it." | The payoff, inside the video |
| 2:40–3:00 | **Close:** written in the pitch phase. | — |

**Rules:**
- Show only what was built during the event.
- No numbers we didn't measure.
- Use opportunity posts that are still open on recording day.
- Hide phone numbers, account numbers and codes.

## 9. How we're different (prep for questions)

| Product | What it does | Where Homing differs |
|---|---|---|
| **Meta Muse** | A personal agent: works on goals you give it, acts for you with approval, sends proactive check-ins, and can search your Instagram saved posts. US/Canada and Japan; not Nigeria. | Works on your saves from any app, including WhatsApp and YouTube, which Muse doesn't read. Checks claims against official sources, and stays inside your library. |
| **Grok Bot + Obsidian** | A do-it-yourself setup where bots maintain a notes vault, for power users. | Nothing to set up. It starts from WhatsApp and checks claims against official sources. |
| **Relic** (relic-app.com, beta) | "Most tools help you save. Relic helps you remember." It gathers links, PDFs, notes, YouTube, Instagram and LinkedIn posts, organises them automatically, and helps you find and use what you've learned. | Closest in spirit. Homing checks saves against their official source, and brings each save back at a date or moment with the next step. Check Relic's features properly before the pitch **(confirm)**. |
| **Readwise / Recall / mymind** | Libraries. Readwise resurfaces highlights on a schedule; Recall and mymind wait for you to look. | Brings a save back when it's needed (dates, goals, moments) and checks it. |
| **ChatGPT / Perplexity / Pulse** | Answer what you ask; Pulse sends daily research cards. | Work from what you chose to save, not the open web, with a date or moment for each save. |
| "Isn't this just RAG?" | — | The main product is proactive: agents read, check and bring saves back on schedules and triggers. When you do ask, every save has already been understood (images, voice notes and videos included), the model picks the relevant ones by meaning, and code checks every quoted point against your saves. There's no chat thread. |

## 10. Rules we must not break

**Hackathon:**
- A new public repo with new code written during the event. No Crowscap code gets copied in, and the README says the idea comes from Crowscap.
- A live product and a 3-minute video.

**Banned project types:**
- medical advice
- basic RAG
- simple image analysers
- simple education chatbots
- job application screeners
- nutrition coaches
- personality analysers
- sports coaches
- political or war content

**Platforms (breaking these means disqualification):**
- No scraping Instagram or Facebook.
- No downloading YouTube.
- No WhatsApp bot. AI assistants have been banned on the WhatsApp Business API since 15 Jan 2026.
- X only through its official embed, or the user's own screenshots.

**Privacy:**
- Secret-looking items are screened out by code and never sent to a model.
- The demo hides personal numbers and codes.

**Git:** commit locally, and push only when Isreal says so.

## 11. Models and tools

| Job | Model or tool | Status |
|---|---|---|
| Reading images, PDFs and video; one long pass over the library; comparing a post with its source | Muse Spark (OpenAI-compatible API at `api.meta.ai/v1`) | Confirm the exact model ID in the Meta dashboard. Third-party docs list `muse-spark-1.1` (text, image, video, PDF). |
| Voice notes | Muse Voice Transcribe (`muse-voice-transcribe-1.0`) | Works (S0, 31 Oct): `/v1/asr/transcribe`, WAV only, so Opus is converted first. Accurate on a Nigerian-English note; a short Pidgin note worked too. |
| Matching your profile against eligibility rules | Muse Spark Open on Baseten or Modal (`meta-models/muse-spark-open-1026`) | Needs partner credits |
| YouTube details | YouTube oEmbed for the title; captions with `youtube-transcript-api` (behind `FEATURE_YT_CAPTIONS`); YouTube Data API for description and chapters | Captions decided 31 Oct (option 2). The Data API needs a Google key (optional) |
| X posts | X oEmbed (publish.twitter.com) | Free, first post only |
| Finding official sources | Links in the post first, then a search API | Check whether Meta's API includes web search |
| Reel of moments | YouTube embed with start and end times | No downloading |
| Stack | Next.js (web) + FastAPI and a Python worker (server) + Postgres and storage (Supabase). See [ADR 0001](adr/0001-stack.md) and the developer docs in [docs/README.md](README.md). | Decided |

## 12. Build plan

Build the whole demo path roughly first, then make each part deep. The slice-by-slice breakdown, with checks, tests and checkpoints, is in [14-build-slices.md](14-build-slices.md).

| Day | Goal | Done when |
|---|---|---|
| **Fri 30 Oct, evening** | Tests: can Muse Spark read a YouTube link? Does Voice Transcribe handle 5 real voice notes? Confirm model IDs. Scaffold the repo ([12-dev-workflow.md](12-dev-workflow.md)). | We know which video plan we're on |
| **Sat 31 Oct** | Rough path end to end on real saves pasted in: save card with four rough answers → Today and The team, with sign-in. **First deploy.** (S1–S5) | One save goes all the way through on a live URL |
| **Sun 1 Nov** | **Is it true?** in depth: official sources, quote checks, Lagos time, eligibility. Images, flyers and PDFs. Run it on real opportunity posts, including the 18-opportunity thread. (S6–S7) | The "Now" scene works on real posts |
| **Mon 2 Nov** | **WhatsApp import** of the full pile with media; **What's it for?** over the full pile; hybrid search (words + meaning) and **Ask**. Isreal grades 40 save cards (about 1 hour) for the accuracy numbers. | The "Past" scene works on all 624 saves; "How do I prepare for YC?" gives a verified answer page |
| **Tue 3 Nov** | **When will you need it?**: triggers, next steps, prep sheet, reel. **Audit** (repeats, went bad, contradictions). A sample pile judges can use without their own export. README. **Record in the evening.** | The "Later" scene works; video recorded |
| **Wed 4 Nov** | Polish, final deploy, X post, submit **before 03:00 Thu, Lagos time** | Submitted |

**Must work at submission:**
- [ ] Import a WhatsApp export with media, and see the saves read.
- [ ] A new save gets its save card with all four answers.
- [ ] **Is it true?** works on at least 5 real opportunity posts, with quoted proof.
- [ ] Threads are built over the full pile.
- [ ] Search finds saves by meaning ("YC" finds "Y Combinator"). **Ask** gives an answer page where every point is verified against a save.
- [ ] **Today** shows at most 3 brought-back saves, each with a next step.
- [ ] **The team** feed links every action to its evidence.
- [ ] A live URL with a sample pile.
- [ ] README: what it is, how to run it, which Meta models it uses, what came from Crowscap (the idea only), and honest limits.
- [ ] The 3-minute video.

**If we fall behind, cut in this order:**
1. the reel
2. Audit gaps and let-go suggestions (keep repeats and things that went bad)
3. polish on the threads view
4. voice notes
5. the daily re-check

**Never cut:** the proof on every claim, or the save card.

## 13. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Muse Spark can't read YouTube links (confirmed in S0) | **Decided (Isreal, 31 Oct):** read YouTube captions instead (option 2), behind a flag. Revisit after office hours. If captions are blocked from the server or ruled out, fall back to chapters. |
| YouTube blocks caption requests from cloud servers | Test from the deployed worker in S5. If blocked, captions are fetched on import from a non-cloud network, or we fall back to chapters. Decide then. |
| An official page blocks us | Say "couldn't open the official page". Never fill the gap. |
| No web search in Meta's API | Links in the post, plus one search API key |
| Voice Transcribe struggles with Nigerian voice notes | Show only what it gets right, and say it's English-first |
| The agents look like theatre | Every feed entry links to real evidence. Each agent has real memory and a real schedule. |
| API cost or rate limits on 624 saves | Read each save once, cache the results, and batch the long-context pass |
| Too much scope | Follow the cut order. The rough path through all three scenes comes first. |
| Demo posts close before recording | Re-pick posts on Tuesday. Afreximbank stays as the "what the post left out" example. |
| Judges don't have a WhatsApp export | The sample pile on the live URL |

## 14. Already rejected (don't go back)

| Idea | Why it's out |
|---|---|
| A general personal agent, "does the later", goals and reminders | That's what Muse, Dots, Duet and Grok Bot do |
| "Every save is a question you never asked" (researching what you didn't ask) | It mostly produces answers, which is chat-app territory |
| A standalone opportunity checker | Muse could do a version if asked. Now it's the **Is it true?** question inside Homing. |
| An agent that finds free servers for startups | The agent itself is the product, and that's Muse/Dots |
| Tracking class WhatsApp groups | No market: students won't pay |
| Live sermon verse projection | Crowded (Pewbeam, AnchorCast, SmartVerses) |
| Bookkeeping for traders from WhatsApp | Meta's own Business Agent is moving there |
| "WhatsApp Wrapped" | Close to the personality-analyser ban, and uses other people's data |
| Glasses, the "Receipts" fact-checker, exam prep | Rejected earlier |
| A WhatsApp bot | Banned on the Business API |
| A chat thread for asking questions | Looks like basic RAG and like every assistant, and invites made-up answers. We use one-question answer pages (Ask) instead. |
| Keyword-only search, or the model reading the whole library on every question | Keywords miss "YC" vs "Y Combinator". Whole-library reads get slower and pricier with every save. We use hybrid search plus the model picking from the top results. |
| Naming the agents "Reader" and "Librarian" | Too close to the viral Grok Bot + Obsidian post. We use the four questions instead. |

## 15. Rules to come back to

1. **Your saves are the source.** Homing works on what you saved, and you make the decisions.
2. **Proof or silence.** Every claim quotes its source and is checked by code. If we can't confirm something, we say so.
3. **Answer now, bring back later.** Every save gets its card straight away, plus a "when".
4. **Calm by default.** At most 3 cards a day, and anything dismissed stays dismissed.
5. **Rough path first.** All three demo scenes work roughly before anything gets polished.
6. **Real data only.** The real pile and real posts, and no numbers we didn't measure.

When stuck, re-read section 1, then section 8, then the cut order in section 12.

## 16. Open questions

- ~~Can Muse Spark take a YouTube link?~~ No (S0, 30 Oct). We read YouTube's captions instead (Isreal's decision, 31 Oct), and MP4 files we hold go to Muse Spark. Still open: can Muse Spark Open read video?
- Does Meta's API include web search? If not, which search API do we use?
- ~~What are the exact model IDs?~~ Answered 30 Oct: `muse-spark-1.3` and `muse-voice-transcribe-1.0`, among others (see [06](06-models.md#models-on-our-key)). Also answered in S0: transcription is `POST /v1/asr/transcribe` (WAV); Spark takes images and PDFs inline as base64, and video as an MP4 URL ([06](06-models.md#what-the-s0-check-found-30-oct)).
- ~~Hosting: is Railway OK, or is the old Crowscap server still available?~~ Answered 1 Nov: the API goes on AWS (Paris), the web app on Vercel. See [ADR 0007](adr/0007-hosting.md).
- Does Meta offer an embedding model? We found none, so we run a small open model ourselves. See [ADR 0003](adr/0003-search-ask-audit.md).
- How does the Community Vote work, and when does voting open?
- What's the YouTube Data API key setup?

## Change log

- **30 Oct, v1:** first plan.
- **30 Oct, v2:** rechecked.
  - The one-liner is now "save anything to use now or later", and the product gives value at save time (the save card), not only later.
  - "Is it time?" became "When will you need it?", because a concrete "when" is what lets the mind let go.
  - Added the research section, and each finding now maps to a design choice.
  - Moved defensive lines out of this file and into the pitch.
  - First users changed from students to founders and young professionals.
  - Fixed wrong claims about Muse (it does send proactive check-ins) and Readwise (it does resurface highlights).
  - Secret screening is done by code, not by a model.
  - Removed overclaims: "from every app", "you own it", "private" open model, and model IDs stated as facts.
  - Stated the Afreximbank requirements exactly.
  - Added search, a sample pile for judges, an early deploy, a grading session, a must-work checklist and a glossary.
  - The demo now runs past, now, later.
- **30 Oct, v3:** architecture decided and written up in the developer docs (`docs/01`–`12`, `docs/adr/`). Stack: Next.js, FastAPI with a worker, Postgres job queue, Supabase, and one model gateway.
- **30 Oct, v4:**
  - **Asking is back,** without a chat thread: **Ask** gives one verified answer page per question, and **Audit** gives a report on a thread or everything.
  - **Search is hybrid,** by words and by meaning, using a small open embedding model we run ourselves plus pgvector, because keyword-only search misses "YC" vs "Y Combinator".
  - Long context is kept for the thread rebuild and audits.
  - See [ADR 0003](adr/0003-search-ask-audit.md).
- **30 Oct, v5:** named **Homing** (Crowscap stays as the company and origin). Brand, logo and colours added in [13-brand.md](13-brand.md).
- **30 Oct, v6:** brand changed to warm glass with a red primary, a new "h" icon and a wordmark. Relic added as a close competitor.
- **30 Oct, v7:** build slices with checkpoints added ([14-build-slices.md](14-build-slices.md)). Saturday's rough path uses pasted saves; the WhatsApp import moves to Monday.
- **31 Oct, v8:** YouTube read through captions behind a flag (Isreal's decision, option 2; revisit after office hours). Voice Transcribe confirmed on real voice notes. Storage rules approved: text-only database; videos kept as 480p copies plus thumbnails; stickers, contact cards and nested zips skipped ([04](04-ingestion.md#storage-rules-approved-by-isreal-31-oct)).
- **31 Oct, v9:** after the S3 audit (Isreal's yes to all):
  - The sample Afreximbank card now shows "What is it?" from the post, and the facts only the official page has under "Is it true?".
  - The YouTube lines in 5.2, 11 and 16 now match the captions decision.
  - The label figure is stated with its method.
  - Spending is capped in tokens per day (everyone, per user, half for the demo user) until Meta publishes prices.
  - Rate limits are added to S5, before the public deploy.
  - A Workable reader is added to S4's "Is it true?", because the official Afreximbank page only shows its description to a plain fetch.
- **1 Nov, v10, live:**
  - **Hosting (Isreal: AWS for speed, no Docker):** the API runs on one EC2 instance in Paris, next to the database: two systemd services (`homing-api`, `homing-worker`) behind Caddy at `https://homing-api.crowscap.xyz` ([ADR 0007](adr/0007-hosting.md), `deploy/ec2/`). The web app is on Vercel at `homing-rho.vercel.app`, its functions in Paris. Database queries take about 9 ms from the server, against about 200 ms from Lagos.
  - **Files skip Vercel:** the browser sends them straight to the API with a 5-minute upload ticket, because Vercel caps requests at about 4.5 MB ([07](07-api.md#conventions)). Files live in a private Supabase bucket.
  - **One database for development and production,** so the demo pile is shared, with **job lanes** so neither machine takes the other's work ([03](03-agents.md)).
- **1 Nov, v11, YouTube from servers:** YouTube refuses caption requests from cloud servers. Tested from our Paris server and from Crowscap's AWS server in Virginia: the caption library is blocked, and yt-dlp is either asked to sign in or gets no captions. yt-dlp stays out ([ADR 0008](adr/0008-platform-rules.md)), and CI now fails if any downloader enters a lock file. An optional proxy for caption requests only is built; Webshare's free data-center proxies were blocked too (0 of 12 tries). A residential proxy is the remaining fix, Isreal's call on cost; videos saved from a home connection keep their captions.
- **1 Nov, v12, WhatsApp import, light on tokens (Isreal: "optimize for token management" but stay visibly agentic):**
  - The import reads Android and iOS exports, keeps each message's time, screens secrets, skips stickers, contact cards and nested zips, and adds nothing on a second run ([04](04-ingestion.md)).
  - Nothing to read, no model; imported saves send at most 8,000 characters; small saves are read 20 per call (77% fewer tokens, measured); only opportunities still open are checked, and The team says why the others weren't ("Check it now" on the card).
  - **Isreal's pile goes into his own account** (Google sign-in, allowed for his email only), not the demo account: it's personal.
- **1 Nov, v13, What's it for? over the whole pile (S9):** one long-context call proposes goals for every save, then a second look places what it left out; code checks every title and keeps the person's own names. On Isreal's pile: 340 of 405 saves into 24 goals ("Starting and scaling startups", "Learning Agentic AI", "Finding funding and grants", "Getting into YC" …) for 42,560 tokens, against about 900,000 placing them one by one ([03](03-agents.md#whats-it-for)). Also fixed: a deadline in a sentence with a hyphenated word ("apply on-time is November 2 at 8pm PT") was confirmed but not saved as the closing date.
- **2 Nov, v14, videos, voice notes and documents (S8 step 2):** Muse Voice Transcribe turns speech into words, and the reader reads them, so facts can be checked; a video that says little is watched by Spark from a short-lived private link; Word, PowerPoint and Excel text is read. A talking clip cost 1,911 tokens read from its words, against 15,530 for Spark watching it ([04](04-ingestion.md)).
- **2 Nov, v15, search and Ask (S10):** search by words and meaning at once, as you type, with a small open model we run ourselves (Meta has no embedding model; Isreal asked about Qwen's: see [ADR 0003](adr/0003-search-ask-audit.md#as-built-s10-2-nov-2026)). Ask gives one answer page per question: Spark picks the saves that answer it and writes points, and code shows a point only when its quote is found in the save. "Where can I find funding as an African founder?" got 12 verified points from Isreal's saves.
- **2 Nov, v16, Today (S11):** Today is composed by code when it's opened: at most 3 new cards a day, scored by urgency + importance − fatigue; a dismissed card never comes back; Later brings it back at 09:00 the next morning. The person types what's coming up ("recording my demo on Tuesday evening"): code reads the day and time, Spark picks the goals whose saves would help, and code keeps only real goals. With 3 or more saves behind it, a prep card appears 36 hours before. No timer: there's no push, so a tick would add nothing the person sees ([03](03-agents.md#when-will-you-need-it)).
- **2 Nov, v17, the Meta hackathon page (S11 done-when):** saving it showed "Mon 26 Oct" and "Couldn't confirm". Three fixes: pages built in the browser (Cerebral Valley, many startup sites) are read from their script data, 75 characters became 28,062; a time a few words after the date is taken ("Nov 4: Project submissions due by 9:00 PM ET"), only when the text gives one time; a date with no year that passed less than two months ago means this year, not next ("Oct 25" had become October 2027). When the official closing date has passed but the page has a date ahead, the "when" is that date, and Today keeps a closed save only while it has one (Isreal: people who got in still need it; the card says applications are closed).
- **2 Nov, v18, prep sheet and reel (S12):** a prep card opens a sheet made from the person's own videos: Spark pulls points from each video's captions, code keeps a point only if its quote is in the captions at that second, then Spark writes steps, agreements and disagreements, and code keeps a line only if every citation is one of those points. Each chip plays the video from that second; the reel plays the best moments, at most 3 minutes. Videos come from every goal the moment needs, in turns. Isreal's pile had titles only for its YouTube videos (imported on the server, which YouTube refuses), so captions were fetched once from his laptop with no model; reels from Instagram and the like can't be read from a link and the sheet says so.
- **3 Nov, v19, Your agents (from the workshops and a first-principles pass):** "The team" became **Your agents**: a live map of the four agents, each with its own character, sending each real step to the goal it touched or to you when it needs a decision; today's clock, hour by hour; and every step with its proof. Nothing on the map moves without a real event. "Team" read like a sharing feature; "Agents" is the word the hackathon, the workshops and the agentic prize use.
- **3 Nov, v20, delivery without opening the app (F2) and a sharper prep sheet (U5):** Homing has no push, so Today offers a private calendar feed: add it once to Google or Apple Calendar and every date and moment arrives with the phone's own reminder, linking back to the card. The prep sheet no longer passes on length or platform advice the moment doesn't ask for ("keep it to 30 seconds" came from Shorts videos; prompt v3). Also: passed dates read in the past tense; Today's "Coming back"; the save card made scannable; Your agents shows who's working and what needs you.
- **3 Nov, v21, Meta's models made visible (rubric: Use of Meta AI tooling, 25%):** every step and every answer names the Meta model that did it (Muse Spark, Muse Voice Transcribe), or says "Code"; Your agents shows each model's real calls and tokens; the README's "How Homing uses Meta's models" table gives only measured numbers. Fixed a false claim: the README said we used Muse Spark Open, which isn't on our key (it's on Fireworks). Next: Muse Wonder runs Ask as a real agent with tools, our verification as its gate.

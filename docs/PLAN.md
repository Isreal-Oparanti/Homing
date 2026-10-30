# Crowscap — hackathon plan

_Meta Global AI Developer Hackathon · Indie track · locked 30 Oct 2026_
_Due **Wed 4 Nov, 9 PM ET = Thu 5 Nov, 03:00 Lagos**_

This is the single source of truth for what we're building. When something goes wrong, or we start drifting, come back here first. Change this file only on purpose, and note the change in the log at the bottom.

---

## 1. The idea in one breath

**Save anything. Crowscap's agents answer four questions about every save: What is it? What's it for? Is it true? Is it time? Then they bring it back exactly when you need it.**

> It doesn't do your tasks. It makes sure you never start from zero.

## 2. The problem, with our own evidence

People save things because they mean to act on them, then never see them again. ("Later" never came for Pocket either. It shut down in July 2025.) Two things hurt most:

1. **You already had it, but it didn't come back when it mattered.**
2. **What you saved wasn't the whole truth.** Posts leave things out, go stale, or don't apply to you.

Evidence from Isreal's real WhatsApp "message yourself" chat (624 saves, Jun 2025 – Oct 2026):

| What we found | Detail |
|---|---|
| Most saves are unreadable as-is | About 6 in 10 are videos. Only 13% of links have a label typed next to them. |
| Goals that were never written down | Getting into YC: 7 saves (YC account page Sep 2025 → funding digest 12 Oct). Funding and opportunities: ~25. Speaking better: 10. Making a demo video: 7. AI and agent engineering: ~15. |
| The answer was already saved | The 12 Oct digest says YC W27 closes 2 Nov. Before the hackathon demo, there were 16 saved videos on speaking and demo-making, plus a "SaaS Launch Platforms" list saved 20 Aug. |
| Forgetting | 4 items were saved again on a later day. One Elon video was saved twice, 11 weeks apart. |
| Posts aren't the truth | The Afreximbank internship post left out that it's in **Cairo, on-site**, that it needs **English *and* a working knowledge of French**, that full-time study is only "preferred", and that the official page shows **no closing date**. |
| Crowscap's own promise | 12 Aug 2026: Crowscap "saves links, PDFs, lessons, random thoughts and bring them **exactly when needed**." The saving was built. The bringing back never was. |

## 3. Who it's for

**First users:** ambitious young people outside the default, starting with Nigerian students and early founders. They save in WhatsApp, their saves are full of opportunities, learning and ideas, and missing a deadline or a rule costs them real money and chances.

**Later:** anyone who saves a lot and uses little.

**Who pays:** people already pay for second brains like Readwise, Recall and mymind. The agents are the paid part. For someone hunting opportunities, one caught deadline is worth a year of subscription.

## 4. What it is and isn't

| It is | It isn't |
|---|---|
| A library of everything you save, from every app, that you own | A personal assistant (that's Muse, Dots, Duet) |
| Agents that read, connect, check and bring back | An agent that acts for you: no applying, emailing or buying |
| Proactive: it brings things back without you asking | A chat box. **There is no chat box. You don't ask; it brings.** |
| Every claim backed by the exact source line | A model's opinion |

## 5. The four questions (the agents)

Each agent owns one question, keeps its own memory, runs on its own schedule, and writes every action to **The team** feed with a link to the evidence.

### What is it? — reads every save
- **When it runs:** on every new save.
- **What it takes in:** text notes, links (YouTube, X, web pages), flyers and screenshots, PDFs, voice notes, video files.
- **What it produces:** a card with what the save is, what's in it, and its key facts (dates, amounts, requirements, links).
- **How each format is read:**
  - YouTube: oEmbed title, plus description and chapters from the official Data API.
  - X: oEmbed text.
  - Web pages: a single fetch.
  - Images and PDFs: Muse Spark.
  - Voice notes: Muse Voice Transcribe.
  - Video: Muse Spark, only where we have the file legitimately.
- **Never:** changes the source; downloads YouTube; scrapes Instagram or Facebook; sends secret-looking items to any model.

### What's it for? — connects saves
- **When it runs:** after reading, plus a daily pass over the whole library (Spark long context).
- **What it produces:**
  - **threads**: the goals your saves serve, each with its saves in order;
  - merged repeats ("you saved this on 8 Jul");
  - links between related saves.
- **Never:** labels you as a person (no personality talk). Threads are about goals, not who you are. You can rename, merge or split threads with one tap.

### Is it true? — checks anything that can be wrong
- **When it runs:** on saves that contain checkable facts (opportunities, deadlines, prices, requirements), plus a daily re-check of anything still open.
- **How it works:**
  1. Find the official source: links inside the post first, then search.
  2. Fetch it.
  3. Compare it with the post.
  4. Work out the deadline in your time zone.
  5. Check eligibility against your profile.
- **What it produces:** "What the post didn't tell you", with each point quoting the official line. **Code confirms the quote is really on the page**, and any point that fails is dropped. Each opportunity is labelled **fits you / closed / not for you / needs your answer**.
- **Never:** guesses. If the page can't be opened, it says "couldn't open the official page". If there's no date, it says "no date on the official page".

### Is it time? — brings things back
- **Triggers** (all fixed rules, none of them model guesses):
  1. A date inside a save is getting close.
  2. A new save lands in a thread you've been building.
  3. A moment you flag ("recording my demo Tuesday").
  4. A save goes bad: closed, moved, dead link.
- **What it produces:** something you can use now, such as a checklist, a **prep sheet** (points your saved videos agree on and disagree on, each linked to the exact second), or a short reel of those moments.
- **Never:** nags about things you dismissed. At most 3 cards a day.

**Why four agents and not one script:** they have separate jobs and separate schedules (every save, daily, on dates). You can see who did what. If one fails, the rest keep working.

## 6. What the user sees

1. **Today:** at most 3 cards that need you. Each card shows what it is, why now, and the proof, with three buttons: *Use it · Not for me · Later*.
2. **Threads:** your goals, each with its saves, the agents' notes, and checked facts.
3. **The team:** a live feed of what each agent did, linking to the evidence. You check in once a day.

**Adding things:** import your WhatsApp "message yourself" export (with media), paste, upload, or share to the web app.

## 7. The 3-minute demo (three scenes, no more)

| Time | Scene | Must show |
|---|---|---|
| 0:00–0:15 | Hook: scroll through the real "message yourself" chat. "624 messages to myself in 16 months." | The real pile |
| 0:15–0:55 | **Scene 1, the pile becomes goals.** Import. The team feed comes alive. Threads appear: "You've been working toward 6 things." | Agents visibly working on real saves |
| 0:55–1:45 | **Scene 2, Is it true?** A batch of opportunity posts gets sorted into fits you / closed / not for you. Zoom into one: "What the post didn't tell you", with highlighted official lines. | Proof on screen |
| 1:45–2:40 | **Scene 3, Is it time?** The hackathon deadline you saved leads to "You saved 16 videos for this" and a prep sheet (plus the reel if video works). "I recorded this video with it." | The payoff, inside the video itself |
| 2:40–3:00 | Close: "It doesn't do your tasks. It makes sure you never start from zero." Built on Muse Spark, Voice Transcribe and Muse Spark Open. | — |

Rules for the video:
- Only show what was built during the event.
- No numbers we didn't measure.
- Pick opportunity posts that are still open on recording day.

## 8. How we score

| Criterion | Weight | Our case |
|---|---|---|
| Impact | 30% | A pain everyone has, with the highest stakes for people outside the default (deadlines, eligibility, Lagos time). Shown on a real pile. "Build for Your World": in our world, the notes app is WhatsApp. |
| Use of Meta's models | 25% | Spark reads flyers, PDFs and video, and reads the whole 16-month library in one pass. Voice Transcribe handles voice notes. Spark Open does the private first pass. Candidate for "surprised even us": 16 videos turned into the points they agree on, each with its exact second. |
| Technical depth | 20% | Four agents with their own memory, schedules and triggers. Quotes are checked by code, and dates and time zones are worked out by code. Accuracy numbers from the real pile. |
| Demo | 25% | Agents visibly working, a real reveal, and a payoff inside the video. |

**Bonus prizes:**
- **Best Agentic Use-Case ($5k):** a visible team, on a schedule, with your approval.
- **Most Viral on X ($20k, engagement counts until 8 Nov):** "I gave my saves a team of agents", plus the opportunity-thread check.
- **Open weights ($10k):** Muse Spark Open.
- **Community Vote ($10k):** Nigerian student and founder networks.

## 9. Answers to "why not…"

| They say | We say |
|---|---|
| Muse already does this | Muse does tasks in your life, mostly when asked, inside Meta's apps. Crowscap works on your library from every app, brings things back unasked, and shows proof. Muse also isn't available in Nigeria. |
| Grok Bot + Obsidian | That's for power users who build vaults and write prompts. Crowscap is for everyone, starts from WhatsApp, and checks claims against official sources. |
| Recall / mymind / Readwise | Libraries that wait for you to come back. |
| Perplexity / ChatGPT | They answer what you ask, when you ask. You'd have to remember you saved it, and remember to ask. |
| "Isn't this just RAG?" | There's no chat box. Agents work on their own schedule and on triggers, and every claim is checked against the source by code. |

## 10. Rules we must not break

- **Hackathon:**
  - New public repo with new code written during the event. No Crowscap code gets copied in, and the README says the idea came from Crowscap.
  - Live product and a 3-minute video.
- **Banned project types:**
  - medical advice
  - basic RAG
  - simple image analysers
  - simple education chatbots
  - job application screeners
  - nutrition coaches
  - personality analysers
  - sports coaches
  - political or war content
- **Platforms (breaking these means disqualification):**
  - No scraping Instagram or Facebook.
  - No downloading YouTube.
  - No WhatsApp bot (AI assistants banned on the Business API since 15 Jan 2026).
  - X only through its official embed or the user's own screenshots.
- **Privacy:**
  - Secret-looking items never go to a model.
  - The demo hides phone numbers, account numbers and codes.
  - Personal profile details are matched on Spark Open.
- **Git:** commit locally and push only when Isreal says so.

## 11. Meta models and stack

| Job | Model / tool |
|---|---|
| Reading images, PDFs, video; long-context library pass; comparing post vs official page | Muse Spark (`muse-spark-1.1`: text, image, video, PDF), OpenAI-compatible at `api.meta.ai/v1` |
| Voice notes | Muse Voice Transcribe (`muse-voice-transcribe-1.0`). Validated on 25 languages including English; Pidgin and Yoruba are untested. |
| Private first pass (secret screen, profile matching) | Muse Spark Open on Baseten or Modal (`meta-models/muse-spark-open-1026`) |
| YouTube metadata | YouTube oEmbed plus the YouTube Data API (description, chapters) |
| X posts | publish.twitter.com oEmbed |
| Reel of moments | YouTube embed with start/end times. No downloading. |

Stack: _decide on Day 1 (keep it boring and fast)._

## 12. Build plan

Build the **whole demo path, thin, first**. Then deepen it.

| Day | Goal | Done when |
|---|---|---|
| Fri 30 Oct (eve) | The video test: can Spark read a YouTube link? Also: does Voice Transcribe handle 5 real voice notes? | We know which reel plan we're on |
| Sat 31 Oct | Thin slice: import, then all four questions on 30 real saves, then the three screens (rough) | One save goes end-to-end on screen |
| Sun 1 Nov | **Is it true?** deep: official source, quote check, deadlines in Lagos time, eligibility. Run it on the 18-opportunity thread. | The scene 2 reveal works on real posts |
| Mon 2 Nov | **What is it?** handles all formats (flyers, PDFs, voice notes). **What's it for?** builds threads over the full pile. | Scene 1 works on all 624 saves |
| Tue 3 Nov | **Is it time?**: triggers, prep sheet, reel. Accuracy numbers. README. **Record in the evening.** | Scene 3 works, and the video is recorded |
| Wed 4 Nov | Polish, deploy, post on X, submit **before 03:00 Thu Lagos** | Submitted |

**If we're behind, cut in this order:**
1. the reel
2. polish on the threads view
3. voice notes
4. the daily re-check

**Never cut:** the proof on every claim.

## 13. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Spark can't read YouTube links (14 of 16 demo videos are YouTube) | **Plan B:** screen-record the videos playing; Spark watches the recording. **Plan C:** the flyer-vs-official-page check becomes the main Meta-model moment, plus Voice Transcribe. Decide by noon Sat. |
| An official page blocks us | Say "couldn't open the official page". Never fill the gap. |
| No web search in Meta's API | Use links in the post, plus one search API key |
| Voice Transcribe struggles with Nigerian voice notes | Show only voice notes it gets right, and say it's English-first |
| The agents look like theatre | Every feed message links to real evidence, and each agent has real memory and a real schedule |
| Too much scope | Follow the cut order. The thin path through all three scenes comes first. |
| The demo posts close before recording | Re-pick posts on Tue. Afreximbank stays as the "what the post didn't tell you" example. |

## 14. Already rejected (don't loop back)

| Idea | Why it's out |
|---|---|
| General personal agent / "does the later" / goals and reminders | That's Muse, Dots, Duet and Grok Bot |
| "Every save is a question you never asked" (research what you didn't ask) | Mostly produces answers, which is chat territory |
| Opportunity checker as a standalone assistant | Muse can do a version if asked. Now it's one question inside Crowscap. |
| Free-server agent for startups | Agent shell = Muse/Dots |
| Class WhatsApp group tracker | No market; students won't pay |
| Live sermon verse projection | Crowded (Pewbeam, AnchorCast, SmartVerses…) |
| Trader bookkeeping from WhatsApp | Meta's own Business Agent is moving there |
| WhatsApp Wrapped | Close to the personality-analyser ban; uses other people's data |
| Glasses, Receipts fact-checker, exam prep | Rejected earlier |
| A Crowscap WhatsApp bot | Banned on the Business API |

## 15. When things go wrong — come back to these

1. **Library, not life.** We work on what you saved. We never do tasks for you.
2. **Proof or silence.** Every claim quotes its source and is checked by code. If we can't confirm it, we say so.
3. **You don't ask; it brings.** There's no chat box, and at most 3 cards a day.
4. **Thin path first.** All three demo scenes work roughly before anything gets polished.
5. **Real data only.** The real pile and real posts. No made-up numbers.

When stuck: re-read section 1, then section 7, then the cut order in section 12.

## 16. Open questions

- Can Muse Spark take a YouTube link directly? (Ask at office hours, 3–4 PM Lagos, and test.)
- Can Muse Spark Open read video?
- Does Meta's API include web search?
- The stack (Day 1).

## Change log

- 30 Oct 2026: plan locked after the recheck. Packaging changed from "Reader/Librarian" roles (too close to the viral Grok Bot + Obsidian post) to the four questions. The demo was cut to three scenes.

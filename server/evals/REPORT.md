# Homing evaluation

_Run 04 Nov 2026, 14:28. Every number below is computed by `evals/run.py` from fixed test sets or the stored record of real runs._

## 1. Reading dates

**30 of 30 right** (100%). Each phrase was read as of when it was written, in Lagos time; the right answer was worked out by hand. No model: dates are read by code.

## 2. Search by meaning

**12 of 15 questions** had a right save in the top 5; on average **78%** of the right saves were in the top 10. Run on Isreal's real pile. The right saves for each question are in `evals/search.jsonl`; Isreal checks them (draft until then).

| Question | Right save in top 5 | Right saves in top 10 |
|---|---|---|
| how do I get into Y Combinator | yes | 4 of 5 |
| YC interview | yes | 2 of 2 |
| grants for Nigerian startups | yes | 2 of 3 |
| startup accelerator in Africa | yes | 3 of 3 |
| pitching to investors | yes | 2 of 2 |
| speak with confidence | yes | 4 of 5 |
| web scraping tool for AI agents | yes | 2 of 2 |
| free API keys for AI models | yes | 2 of 2 |
| how to find a startup idea | yes | 2 of 2 |
| equity and ownership between cofounders | no | 0 of 1 |
| learn to build AI agents | yes | 2 of 2 |
| Paul Graham | yes | 2 of 2 |
| coding with AI without writing code yourself | no | 1 of 2 |
| Meta hackathon | yes | 1 of 1 |
| money for my startup that I don't pay back | no | 0 of 3 |

## 3. What the checks did on real runs

- **Ask:** 11 answers. The model proposed 68 points from 313 candidate saves; code found 68 quotes word for word in the cited save and dropped 0.
- **Prep sheets:** 1 sheet. Of 45 points taken from videos, 44 were found in the captions at the stated second and 1 was dropped.

**Model use so far:** 654 calls, 2,708,278 tokens in all.

| Purpose | Calls | Tokens per call |
|---|---|---|
| read.text | 183 | 2,618 |
| place.assign | 174 | 1,809 |
| check.compare | 94 | 6,477 |
| read.batch | 37 | 6,094 |
| transcribe.voice | 31 | not reported |
| video.points | 30 | 8,258 |
| read.file | 24 | 3,302 |
| find.agent | 18 | 9,191 |
| ask.agent | 17 | 6,485 |
| read.video | 14 | 9,022 |
| place.rebuild | 9 | 21,339 |
| prep.sheet | 7 | 10,310 |
| ask.answer | 5 | 8,005 |
| ask.select | 5 | 2,494 |
| find.compare | 3 | 9,928 |
| when.match_moment | 3 | 1,388 |

## 4. The finds gate on real pages

**12 of 12 right.** Real pages recorded on 2026-11-04 (`evals/finds_pages.jsonl`, by `evals/record_pages.py`), each labelled by hand from reading it: would a careful person show it as open? Code's checks only (official site, named on the page, not a list, not closed, open now), no model. 3 should be kept; the rest are the traps the live runs met: an opportunity blog, a call that says it's closed, last year's programme, a list of 14 calls, and pages with no sign a call is open.

| Page | Right answer | Code | Right? |
|---|---|---|---|
| ycombinator.com | keep: still accepting applications for the Winter 2027 batch | keep | yes |
| onevectasummit.com | keep: a 2026 challenge asking teams to apply, with no closing date given | keep | yes |
| anzisha.org | keep: applications for the 2027 intake opened on 29 September 2026 | keep | yes |
| opportunitiesforafricans.com | refuse: an opportunity blog, not the organisation's own site | refuse (not the organisation's own site) | yes |
| socialshifters.co | refuse: says its 2026 submissions are now closed | refuse (says it's closed) | yes |
| startup.google.com | refuse: the 2026 programme already ran (April to June 2026) | refuse (no sign it's open now) | yes |
| menterprise.africa | refuse: a list of 14 opportunities, not one of them | refuse (lists many opportunities) | yes |
| africabusinessheroes.org | refuse: a home page with no date or sign that a call is open now | refuse (no sign it's open now) | yes |
| tonyelumelufoundation.org | refuse: describes the programme but gives no date or sign it's open now | refuse (no sign it's open now) | yes |
| acceler8.africa | refuse: describes the programme but gives no date or sign it's open now | refuse (no sign it's open now) | yes |
| fatefoundation.org | refuse: an organisation's home page: news from April 2026, no open call | refuse (no sign it's open now) | yes |
| aueuyouth.com | refuse: a newsletter sign-up page with no call on it | refuse (doesn't name it) | yes |

## 5. Finding more on real runs

2 runs of What's it for? on the web so far: **1 finds kept**, 5 proposals refused by code, 0 left out as not for the person. Every refusal is a proposal the person never saw.

| Why code refused | Times |
|---|---|
| The page gives no sign it's open this year | 2 |
| That one is already in their saves | 1 |
| The name quote isn't on P2 word for word | 1 |
| The name quote isn't on the careers.twosigma.com page word for word | 1 |

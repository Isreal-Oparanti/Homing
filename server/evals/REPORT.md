# Homing evaluation

_Run 03 Nov 2026, 14:39. Every number below is computed by `evals/run.py` from fixed test sets or the stored record of real runs._

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

- **Ask:** 8 answers. The model proposed 53 points from 264 candidate saves; code found 53 quotes word for word in the cited save and dropped 0.
- **Prep sheets:** 1 sheet. Of 45 points taken from videos, 44 were found in the captions at the stated second and 1 was dropped.

**Model use so far:** 600 calls, 2,264,367 tokens in all.

| Purpose | Calls | Tokens per call |
|---|---|---|
| read.text | 179 | 2,609 |
| place.assign | 170 | 1,825 |
| check.compare | 92 | 6,425 |
| read.batch | 37 | 6,094 |
| transcribe.voice | 31 | not reported |
| video.points | 24 | 7,579 |
| read.file | 24 | 3,302 |
| read.video | 14 | 9,022 |
| place.rebuild | 7 | 20,002 |
| prep.sheet | 6 | 9,996 |
| ask.answer | 5 | 8,005 |
| ask.select | 5 | 2,494 |
| ask.agent | 4 | 6,900 |
| when.match_moment | 2 | 1,339 |

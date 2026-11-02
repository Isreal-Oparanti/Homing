# ADR 0003: Search by meaning, Ask and Audit, without a chat thread

**Status:** accepted · 30 Oct 2026. This replaces the earlier "search without embeddings" decision.

## Context
- **Users need three things:**
  - finding saves by meaning: "YC" should find "Y Combinator" and "accelerator interview tips";
  - asking questions: "What do I know about getting into YC?";
  - auditing their saves.
- **Keyword search alone** fails when the words differ.
- **Sending the whole library to the model on every question** (long context only) gets more expensive and slower with every save. It can't power search as you type, and models sometimes overlook items in long lists.
- **Meta's Model API has no embeddings endpoint,** as far as we can find **(confirm)**.
- **"Basic RAG" is banned.** A chat thread also invites made-up answers and makes us look like every assistant.

## Decision
1. **Search (instant, no model call):** hybrid.
   - Postgres full-text plus `pg_trgm` for typos.
   - **pgvector** cosine similarity over an embedding of each save's reading.
   - The two lists are merged with reciprocal rank fusion (RRF, k = 60).
2. **Embeddings:** a small open multilingual model running **locally in the worker**, e.g. `intfloat/multilingual-e5-small` through ONNX (384 dimensions) **(confirm availability at scaffold)**.
   - We embed the reading (title, what, key facts, label, the start of the snapshot), not raw pixels or audio. So images, voice notes and videos are found through what **What is it?** wrote about them.
   - Private saves are never indexed.
3. **Ask:** one question gives one **answer page**. It's not a conversation.
   1. Hybrid search, top 40, plus the saves in matching threads.
   2. Muse Spark picks the saves that actually answer the question.
   3. Load their snapshots.
   4. Spark writes points, each quoting a save.
   5. Code verifies every quote.
   6. Render the page.

   A follow-up is a new question that carries the previous one as context.
4. **Audit:** runs on a thread or the whole library, as a job. It produces a report:
   - repeats;
   - saves that went bad;
   - contradictions, with two verified quotes;
   - gaps, marked as suggestions;
   - what to let go.

   Each item has a one-tap action.
5. **Long context is used only where a whole view is the point:** the daily thread rebuild and Audit.

## Consequences
- **Gains:**
  - search by meaning, with a fixed cost per question as the library grows;
  - nothing leaves our servers for indexing, and there's no extra vendor;
  - answers are checked against the user's own saves, and the product still leads with saves coming back without being asked.
- **Costs:**
  - about half a day of work;
  - about +200 MB on the worker image (ONNX runtime and model);
  - embedding quality on Pidgin and Yoruba is unknown, so measure it in evals.

## Rejected
- **Keyword-only search:** misses synonyms and other ways of saying the same thing.
- **Long context only:** cost and wait time grow with the library; no search as you type.
- **An outside embeddings vendor:** another account, plus sending saves to another company.
- **A chat thread interface:** looks like basic RAG and like every assistant, and invites made-up answers.

## As built (S10, 2 Nov 2026)
- **Meta has no embedding model** (checked 2 Nov: `muse-spark-*`, `muse-wonder-1.0`, `muse-voice-transcribe-1.0`, `muse-image-1.0`, `sam-3.1`), so the plan holds: `multilingual-e5-small`, quantized ONNX (Xenova build, about 120 MB), run in our own API and worker (`app/search/embed.py`).
- **Measured on Isreal's laptop:** loads in about 1 s; one question in 4 ms; 32 saves in 0.10 s. 621 saves embedded.
- **Why not Qwen's `text-embedding-v4`** (which Crowscap uses through Alibaba Cloud), asked by Isreal: it is likely the stronger model, but it's a remote API, so every keystroke of search-as-you-type and every save would go to Alibaba Cloud, with a network round trip each time, another account and per-token cost, in a hackathon judged partly on Meta tooling. The open `Qwen3-Embedding-0.6B` could run locally but is about five times the size, too heavy for a 2 GB server running two processes. The small local model is good enough because search only has to bring the right saves into the top 40; Spark then picks what actually answers (Ask). Revisit if evals show misses, Pidgin and Yoruba first.
- **Search** (`app/search/hybrid.py`, `GET /search`): words (Postgres full-text over title and what, any meaningful word, word starts; trigram similarity on titles; the person's label) and meaning (pgvector HNSW, cosine) merged by RRF (k = 60). On Isreal's pile: "YC" → "3 actionable tips to get into YC", "Tips for becoming a YC founder", "3 common YC interview mistakes"; "Y Combinatr" → "Tips on getting into Y Combinator". In the top 40, meaning finds 11 of 25 funding saves for "how to raise money for my startup", 5 of 6 "Getting into YC" and 9 of 12 communication saves.
- **Ask** (`app/search/ask.py`, `POST /asks`, `GET /asks/{id}`): search top 40 plus the other saves in the top hits' goals (60 at most) → `ask.select` (Spark, low effort) picks up to 12 → `ask.answer` (Spark) writes points from their content, each quoting one save, plus what isn't covered → code keeps a point only if its quote is found in that save and its numbers are in the quote. A save Homing only knows the title of (under 300 characters) is listed under "Also in your saves" to open, never dressed up as a point.
  - "Where can I find funding as an African founder?": 12 verified points, none dropped, about 19,000 tokens, 42 s.
  - "How do I prepare for YC?": Isreal's YC saves are YouTube videos known by title only (captions blocked from servers), so the page lists the 5 to open and says the tips themselves aren't in his saves. A YouTube Data API key (descriptions) or captions would make it rich.

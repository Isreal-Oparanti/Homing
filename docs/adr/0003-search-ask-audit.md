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

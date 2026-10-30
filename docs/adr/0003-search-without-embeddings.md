# ADR 0003: No chat box, and search without embeddings (for now)

**Status:** accepted · 30 Oct 2026

## Context
The product brings things back on its own; users don't ask a chat box. The hackathon bans "basic RAG". Meta's API may not offer an embedding model **(confirm)**, and adding another vendor costs time and adds a privacy question.

## Decision
- No chat interface.
- Search uses Postgres full-text (`simple` config, weighted title > what > key facts) plus `pg_trgm` for typos.
- Grouping saves into threads uses Muse Spark's long context, not vector clustering.

## Consequences
- **Gains:** fewer parts, no vector store, and nothing that looks like basic RAG.
- **Costs:** search matches words, not meaning. That's acceptable for finding your own saves by title or topic.

## Revisit when
Meta offers embeddings, or users fail to find things in testing.

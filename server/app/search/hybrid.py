"""Search by words and by meaning, merged (ADR 0003). No model call: it's instant.

- **Words:** Postgres full-text over each reading's title and what, plus trigram similarity on
  titles for typos, plus the person's own label.
- **Meaning:** the nearest save vectors (multilingual-e5-small), so "YC" finds "Y Combinator".
- **Merged** with reciprocal rank fusion: a save both lists rank well comes first.
Private saves are never searched.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Reading, Save, SaveEmbedding, Snapshot
from app.jobs.errors import PermanentError
from app.jobs.runner import JobContext
from app.search.embed import get_embedder

MODEL = "multilingual-e5-small"
RRF_K = 60
CANDIDATES = 40  # from each list
SNAPSHOT_START = 600  # characters of the copy that go into a save's vector

# Tests swap this for a fake; nothing builds the model itself.
embedder_factory: Any = get_embedder


@dataclass(frozen=True)
class Hit:
    save_id: str
    score: float


def rrf(*ranked: list[str], k: int = RRF_K) -> list[Hit]:
    """Reciprocal rank fusion: each list adds 1 / (k + rank) for every id it holds."""
    scores: dict[str, float] = {}
    for ids in ranked:
        for rank, save_id in enumerate(ids, 1):
            scores[save_id] = scores.get(save_id, 0.0) + 1.0 / (k + rank)
    return [Hit(i, s) for i, s in sorted(scores.items(), key=lambda x: -x[1])]


def save_text(save: Save, reading: Reading, snapshot: Snapshot | None) -> str:
    """What a save's vector is made of: what What is it? wrote, the person's own words, the
    facts, and the start of our copy. Images, voice and video are found through these words."""
    facts = reading.key_facts or {}
    parts = [
        reading.title,
        reading.what or "",
        save.label or "",
        " ".join(
            f.get("text", "")
            for k in ("dates", "amounts", "requirements")
            for f in facts.get(k, [])
        ),
        " ".join(facts.get("organisations", [])),
        (snapshot.text[:SNAPSHOT_START] if snapshot is not None else ""),
    ]
    return " ".join(" ".join(p.split()) for p in parts if p)


def embed_saves(db: Session, saves: list[tuple[Save, Reading]]) -> int:
    """Embed saves whose text changed since their last vector. Returns how many were embedded.
    Everything is fetched and written in bulk: a database far away costs a round trip a query."""
    saves = [(s, r) for s, r in saves if s.visibility == "normal"]
    ids = [s.id for s, _ in saves]
    if not ids:
        return 0
    first: dict[str, Snapshot] = {}
    for snap in db.scalars(
        select(Snapshot).where(Snapshot.save_id.in_(ids)).order_by(Snapshot.save_id, Snapshot.id)
    ):
        first.setdefault(snap.save_id, snap)
    known = dict(
        db.execute(
            select(SaveEmbedding.save_id, SaveEmbedding.text_hash).where(
                SaveEmbedding.save_id.in_(ids)
            )
        ).all()
    )
    todo = []
    for save, reading in saves:
        text = save_text(save, reading, first.get(save.id))
        digest = hashlib.sha256(f"{MODEL}\n{text}".encode()).hexdigest()
        if known.get(save.id) != digest:
            todo.append((save, text, digest))
    for start in range(0, len(todo), 32):
        chunk = todo[start : start + 32]
        vectors = embedder_factory().embed([text for _, text, _ in chunk], "passage")
        rows = [
            {
                "save_id": save.id,
                "user_id": save.user_id,
                "model": MODEL,
                "text_hash": digest,
                "embedding": vector,
            }
            for (save, _, digest), vector in zip(chunk, vectors, strict=True)
        ]
        stmt = insert(SaveEmbedding).values(rows)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[SaveEmbedding.save_id],
                set_={
                    "model": stmt.excluded.model,
                    "text_hash": stmt.excluded.text_hash,
                    "embedding": stmt.excluded.embedding,
                },
            )
        )
    return len(todo)


def embed_one(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Job save.embed, after a save is read."""
    if ctx.user_id is None:
        raise PermanentError("save.embed needs a user.")
    row = ctx.db.execute(
        select(Save, Reading)
        .join(Reading, Reading.save_id == Save.id)
        .where(Save.id == str(payload.get("save_id")), Save.user_id == ctx.user_id)
    ).first()
    if row is not None:
        embed_saves(ctx.db, [(row[0], row[1])])


# Words that say nothing about what's wanted: a question shouldn't need them to match.
FILLER = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "about",
        "any",
        "can",
        "do",
        "does",
        "for",
        "from",
        "get",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    ]
)


def any_word(q: str) -> str:
    """A query matching any meaningful word, or its start ("fund" finds "funding")."""
    words = [w for w in re.findall(r"\w+", q.lower()) if w not in FILLER and len(w) > 1]
    return " | ".join(f"{w}:*" for w in dict.fromkeys(words or re.findall(r"\w+", q.lower())))


def _by_words(db: Session, user_id: str, q: str) -> list[str]:
    words = func.to_tsvector(
        "simple", func.coalesce(Reading.title, "") + " " + func.coalesce(Reading.what, "")
    )
    query = func.to_tsquery("simple", any_word(q))
    score = func.ts_rank(words, query) + func.similarity(Reading.title, q)
    rows = db.execute(
        select(Save.id)
        .join(Reading, Reading.save_id == Save.id)
        .where(
            Save.user_id == user_id,
            Save.visibility == "normal",
            or_(
                words.op("@@")(query),
                func.similarity(Reading.title, q) > 0.25,
                Save.label.ilike(f"%{q}%"),
            ),
        )
        .order_by(score.desc(), Save.saved_at.desc())
        .limit(CANDIDATES)
    ).all()
    return [r[0] for r in rows]


def _by_meaning(db: Session, user_id: str, q: str) -> list[str]:
    vector = embedder_factory().embed([q], "query")[0]
    rows = db.execute(
        select(SaveEmbedding.save_id)
        .join(Save, Save.id == SaveEmbedding.save_id)
        .where(SaveEmbedding.user_id == user_id, Save.visibility == "normal")
        .order_by(SaveEmbedding.embedding.cosine_distance(vector))
        .limit(CANDIDATES)
    ).all()
    return [r[0] for r in rows]


@dataclass(frozen=True)
class Found:
    save: Save
    reading: Reading
    score: float


def search(db: Session, user_id: str, q: str, limit: int = 20) -> list[Found]:
    q = " ".join(q.split())[:200]
    if not q:
        return []
    hits = rrf(_by_words(db, user_id, q), _by_meaning(db, user_id, q))[:limit]
    rows = {
        save.id: (save, reading)
        for save, reading in db.execute(
            select(Save, Reading)
            .join(Reading, Reading.save_id == Save.id)
            .where(Save.id.in_([h.save_id for h in hits]))
        ).all()
    }
    return [Found(*rows[h.save_id], h.score) for h in hits if h.save_id in rows]

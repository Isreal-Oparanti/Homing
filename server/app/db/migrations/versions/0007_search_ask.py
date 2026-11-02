"""Search by meaning and Ask (S10, ADR 0003).

- save_embeddings: one vector per save's reading (multilingual-e5-small, 384 numbers), with an
  HNSW index for cosine distance. Private saves are never embedded.
- A word index over readings for the keyword half of search, and a trigram index on titles
  for typos.
- asks: one question, one answer page.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "save_embeddings",
        sa.Column(
            "save_id", sa.Text(), sa.ForeignKey("saves.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_save_embeddings_user", "save_embeddings", ["user_id"])
    op.execute(
        "CREATE INDEX ix_save_embeddings_hnsw ON save_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_readings_words ON readings USING gin "
        "(to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(what, '')))"
    )
    op.execute("CREATE INDEX ix_readings_title_trgm ON readings USING gin (title gin_trgm_ops)")
    op.create_table(
        "asks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="working"),
        sa.Column("answer", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_asks_user", "asks", ["user_id", "created_at"])
    for table in ("save_embeddings", "asks"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("asks")
    op.execute("DROP INDEX IF EXISTS ix_readings_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_readings_words")
    op.drop_table("save_embeddings")

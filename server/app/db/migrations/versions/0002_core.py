"""Core tables: saves and their content, the job queue, the team feed, agent memory, model calls.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = [
    "media",
    "imports",
    "saves",
    "snapshots",
    "readings",
    "jobs",
    "agent_events",
    "agent_memory",
    "model_calls",
]


def _now() -> sa.TextClause:
    return sa.text("now()")


def _user_fk(nullable: bool = False) -> sa.Column:
    return sa.Column(
        "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=nullable
    )


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.Text(), primary_key=True),
        _user_fk(),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("duration_s", sa.Numeric()),
        sa.Column("original_bytes", sa.BigInteger()),
        sa.Column("thumb_key", sa.Text()),
        sa.Column("compressed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("original_filename", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index("ix_media_user_sha256", "media", ["user_id", "sha256"])

    op.create_table(
        "imports",
        sa.Column("id", sa.Text(), primary_key=True),
        _user_fk(),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("format", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="received"),
        sa.Column("counts", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "saves",
        sa.Column("id", sa.Text(), primary_key=True),
        _user_fk(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text()),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("import_id", sa.Text(), sa.ForeignKey("imports.id", ondelete="SET NULL")),
        sa.Column("url", sa.Text()),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("text", sa.Text()),
        sa.Column("label", sa.Text()),
        sa.Column("media_id", sa.Text(), sa.ForeignKey("media.id", ondelete="SET NULL")),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("status", sa.Text(), nullable=False, server_default="received"),
        sa.Column("visibility", sa.Text(), nullable=False, server_default="normal"),
        sa.Column("private_reason", sa.Text()),
        sa.Column("duplicate_of", sa.Text(), sa.ForeignKey("saves.id", ondelete="SET NULL")),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index("ix_saves_user_saved_at", "saves", ["user_id", sa.text("saved_at DESC")])
    op.create_index("ix_saves_user_content_hash", "saves", ["user_id", "content_hash"])
    op.create_index(
        "ix_saves_in_progress",
        "saves",
        ["status"],
        postgresql_where=sa.text("status IN ('received', 'reading')"),
    )

    op.create_table(
        "snapshots",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "save_id", sa.Text(), sa.ForeignKey("saves.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index("ix_snapshots_save_id", "snapshots", ["save_id"])

    op.create_table(
        "readings",
        sa.Column(
            "save_id",
            sa.Text(),
            sa.ForeignKey("saves.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("what", sa.Text(), nullable=False),
        sa.Column("key_facts", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_checkable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_opportunity", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("items", JSONB()),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        _user_fk(nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("dedupe_key", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index(
        "ux_jobs_dedupe_active",
        "jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_jobs_ready",
        "jobs",
        ["priority", "run_after", "id"],
        postgresql_where=sa.text("status = 'queued'"),
    )

    op.create_table(
        "agent_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        _user_fk(),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("save_id", sa.Text(), sa.ForeignKey("saves.id", ondelete="CASCADE")),
        sa.Column("thread_id", sa.Text()),
        sa.Column("card_id", sa.Text()),
        sa.Column("evidence", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index("ix_agent_events_user_id_id", "agent_events", ["user_id", "id"])

    op.create_table(
        "agent_memory",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("agent", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )

    op.create_table(
        "model_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        _user_fk(nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("tokens_in", sa.Integer()),
        sa.Column("tokens_out", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric()),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output", JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index(
        "ix_model_calls_cache",
        "model_calls",
        ["input_hash"],
        postgresql_where=sa.text("status = 'ok'"),
    )

    # Same rule as users: block Supabase's public Data API; the server is the table owner.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)

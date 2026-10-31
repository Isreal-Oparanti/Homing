"""The other three answers: checks (Is it true?), threads (What's it for?), whens (When?).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = ["checks", "threads", "thread_saves", "whens"]


def _now() -> sa.TextClause:
    return sa.text("now()")


def _save_pk() -> sa.Column:
    return sa.Column(
        "save_id", sa.Text(), sa.ForeignKey("saves.id", ondelete="CASCADE"), primary_key=True
    )


def upgrade() -> None:
    op.create_table(
        "checks",
        _save_pk(),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("official_url", sa.Text()),
        sa.Column("official_found_by", sa.Text()),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_source_text", sa.Text()),
        sa.Column("deadline_tz_stated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("findings", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("eligibility", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("question_for_user", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("next_check_at", sa.DateTime(timezone=True)),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
    )

    op.create_table(
        "threads",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("created_by", sa.Text(), nullable=False, server_default="agent"),
        sa.Column("locked_by_user", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index("ix_threads_user", "threads", ["user_id"])

    op.create_table(
        "thread_saves",
        sa.Column(
            "thread_id",
            sa.Text(),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "save_id", sa.Text(), sa.ForeignKey("saves.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("added_by", sa.Text(), nullable=False, server_default="agent"),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index("ix_thread_saves_save", "thread_saves", ["save_id"])

    op.create_table(
        "whens",
        _save_pk(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("bring_back_at", sa.DateTime(timezone=True)),
        sa.Column("moment_id", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text()),
        sa.Column("tz_stated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("time_stated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
    )
    op.create_index(
        "ix_whens_bring_back",
        "whens",
        ["bring_back_at"],
        postgresql_where=sa.text("kind = 'date'"),
    )

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)

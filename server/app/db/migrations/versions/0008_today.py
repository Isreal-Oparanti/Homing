"""Today (S11): moments the person types, and the cards Today shows.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moments",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("thread_ids", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_moments_user_at", "moments", ["user_id", "at"])
    op.create_table(
        "cards",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("save_id", sa.Text(), sa.ForeignKey("saves.id", ondelete="CASCADE")),
        sa.Column("moment_id", sa.Text(), sa.ForeignKey("moments.id", ondelete="CASCADE")),
        sa.Column("thread_ids", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("why_now", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.Text(), nullable=False, server_default="new"),
        sa.Column("surfaced_on", sa.Date(), nullable=True),
        sa.Column("later_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cards_user_state", "cards", ["user_id", "state", "surfaced_on"])
    for table in ("moments", "cards"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("cards")
    op.drop_table("moments")

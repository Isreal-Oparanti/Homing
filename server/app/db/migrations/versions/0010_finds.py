"""What's it for? finds on the web for a goal: only what passed code's checks (finds_more).

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finds",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("thread_id", sa.Text(), sa.ForeignKey("threads.id", ondelete="CASCADE")),
        sa.Column("from_save_ids", ARRAY(sa.Text()), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("what", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_text", sa.Text()),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("rules", JSONB(), nullable=False),
        sa.Column("quotes", JSONB(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("save_id", sa.Text(), sa.ForeignKey("saves.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "url", name="uq_finds_user_url"),
    )
    op.create_index("ix_finds_user_state", "finds", ["user_id", "state"])


def downgrade() -> None:
    op.drop_index("ix_finds_user_state", table_name="finds")
    op.drop_table("finds")

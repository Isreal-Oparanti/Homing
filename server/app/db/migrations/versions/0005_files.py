"""Files: a save can hold several files (screenshots of one thread); lists get per-item checks.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "saves", sa.Column("media_ids", ARRAY(sa.Text()), nullable=False, server_default="{}")
    )
    op.add_column(
        "checks",
        sa.Column("items", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("checks", "items")
    op.drop_column("saves", "media_ids")

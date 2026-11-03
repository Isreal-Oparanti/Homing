"""The Meta models behind each agent step, so the app can say which model did what.

Nullable on purpose: steps from before this column can't be credited, and NULL keeps them
"unknown" instead of looking like code did them. Apply with the code that fills it (deploy).

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_events",
        sa.Column("models", ARRAY(sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_events", "models")

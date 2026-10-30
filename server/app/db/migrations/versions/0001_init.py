"""Extensions and users.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("tz", sa.String(64), nullable=False, server_default="Africa/Lagos"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    # Supabase exposes the public schema through its Data API. RLS with no policies blocks
    # that route; the server connects as the table owner, which RLS doesn't apply to.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("users")

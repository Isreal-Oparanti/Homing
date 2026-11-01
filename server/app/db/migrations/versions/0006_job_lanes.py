"""Job lanes: development and production share the database, not each other's work.

A WhatsApp export waits on the disk of the machine that received it, so only that machine's
worker can import it. Each worker takes jobs from its own lane (JOB_LANE).

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("lane", sa.Text(), nullable=False, server_default="main"))


def downgrade() -> None:
    op.drop_column("jobs", "lane")

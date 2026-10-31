"""Eligibility: what the person has told Homing (profiles), and answers for one opportunity.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("birth_year", sa.Integer()),
        sa.Column("nationality", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("residence_country", sa.Text()),
        sa.Column("student_status", sa.Text()),
        sa.Column("education_level", sa.Text()),
        sa.Column("languages", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("company_stage", sa.Text()),
        sa.Column("company_registered", sa.Boolean()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY")
    # Answers that only make sense for one opportunity ("Are you a child of staff?").
    op.add_column(
        "checks",
        sa.Column("answers", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("checks", "answers")
    op.drop_table("profiles")

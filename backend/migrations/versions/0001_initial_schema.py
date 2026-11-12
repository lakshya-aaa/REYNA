"""Initial REYNA schema: users and activities tables.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_activities_confidence_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activities_category"), "activities", ["category"], unique=False)
    op.create_index(op.f("ix_activities_occurred_at"), "activities", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_activities_source"), "activities", ["source"], unique=False)
    op.create_index(op.f("ix_activities_status"), "activities", ["status"], unique=False)
    op.create_index(op.f("ix_activities_user_id"), "activities", ["user_id"], unique=False)
    op.create_index(
        "ix_activities_user_category", "activities", ["user_id", "category"], unique=False
    )
    op.create_index(
        "ix_activities_user_occurred_at", "activities", ["user_id", "occurred_at"], unique=False
    )
    op.create_index("ix_activities_user_source", "activities", ["user_id", "source"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_activities_user_source", table_name="activities")
    op.drop_index("ix_activities_user_occurred_at", table_name="activities")
    op.drop_index("ix_activities_user_category", table_name="activities")
    op.drop_index(op.f("ix_activities_user_id"), table_name="activities")
    op.drop_index(op.f("ix_activities_status"), table_name="activities")
    op.drop_index(op.f("ix_activities_source"), table_name="activities")
    op.drop_index(op.f("ix_activities_occurred_at"), table_name="activities")
    op.drop_index(op.f("ix_activities_category"), table_name="activities")
    op.drop_table("activities")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

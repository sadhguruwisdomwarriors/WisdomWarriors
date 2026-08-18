"""add profile_handle_history table

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_handle_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("handle", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("profile_id", "handle", name="uq_profile_handle_history_profile_id_handle"),
    )
    op.create_index("ix_profile_handle_history_profile_id", "profile_handle_history", ["profile_id"])
    op.create_index("ix_profile_handle_history_handle", "profile_handle_history", ["handle"])

    # Seed profile_handle_history from existing profiles
    op.execute(
        """
        INSERT INTO profile_handle_history (profile_id, handle)
        SELECT id, LOWER(username)
        FROM profiles
        WHERE id IS NOT NULL AND username IS NOT NULL
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_profile_handle_history_handle", table_name="profile_handle_history")
    op.drop_index("ix_profile_handle_history_profile_id", table_name="profile_handle_history")
    op.drop_table("profile_handle_history")

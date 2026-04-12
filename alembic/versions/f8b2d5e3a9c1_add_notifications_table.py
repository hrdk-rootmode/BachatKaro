"""Add notifications table for watchlist alerts and events

Revision ID: f8b2d5e3a9c1
Revises: e7a1d2c3f4b5
Create Date: 2026-04-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f8b2d5e3a9c1"
down_revision: Union[str, None] = "e7a1d2c3f4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_notifications_user", "notifications", ["user_id"], unique=False)
    op.create_index(
        "idx_notifications_user_unread",
        "notifications",
        ["user_id", "is_read"],
        unique=False,
        postgresql_where=sa.text("is_read = false"),
    )
    op.create_index("idx_notifications_created", "notifications", ["created_at"], unique=False)
    op.create_index("idx_notifications_type", "notifications", ["type"], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_notifications_type", table_name="notifications")
    op.drop_index("idx_notifications_created", table_name="notifications")
    op.drop_index("idx_notifications_user_unread", table_name="notifications")
    op.drop_index("idx_notifications_user", table_name="notifications")

    # Drop table
    op.drop_table("notifications")

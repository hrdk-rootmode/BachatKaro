"""Add missing price_history column to product_listings

Revision ID: b1e8c3f4d9a2
Revises: 9d2f5a7c1b4e
Create Date: 2026-03-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b1e8c3f4d9a2"
down_revision: Union[str, None] = "9d2f5a7c1b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_listings",
        sa.Column("price_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_listings", "price_history")

"""Add smart scrape schedule fields to product_listings

Revision ID: e7a1d2c3f4b5
Revises: c5f9a8b2e1d3
Create Date: 2026-03-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7a1d2c3f4b5"
down_revision: Union[str, None] = "c5f9a8b2e1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_listings", sa.Column("next_scrape_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("product_listings", sa.Column("last_price_change_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "product_listings",
        sa.Column("scrape_priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
    )

    op.create_index("idx_listings_next_scrape", "product_listings", ["next_scrape_at"], unique=False)
    op.create_index("idx_listings_last_price_change", "product_listings", ["last_price_change_at"], unique=False)
    op.create_index("idx_listings_scrape_priority", "product_listings", ["scrape_priority"], unique=False)
    op.create_index(
        "idx_listings_platform_due",
        "product_listings",
        ["platform_id", "next_scrape_at", "scrape_priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_listings_platform_due", table_name="product_listings")
    op.drop_index("idx_listings_scrape_priority", table_name="product_listings")
    op.drop_index("idx_listings_last_price_change", table_name="product_listings")
    op.drop_index("idx_listings_next_scrape", table_name="product_listings")

    op.drop_column("product_listings", "scrape_priority")
    op.drop_column("product_listings", "last_price_change_at")
    op.drop_column("product_listings", "next_scrape_at")

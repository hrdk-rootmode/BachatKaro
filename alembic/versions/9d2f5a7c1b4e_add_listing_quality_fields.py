"""Add listing quality and provenance fields

Revision ID: 9d2f5a7c1b4e
Revises: 005
Create Date: 2026-03-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d2f5a7c1b4e"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_listings", sa.Column("extraction_confidence", sa.Float(), nullable=True))
    op.add_column("product_listings", sa.Column("extraction_method", sa.String(length=32), nullable=True))
    op.add_column("product_listings", sa.Column("data_source", sa.String(length=32), nullable=True))
    op.add_column("product_listings", sa.Column("seller_name", sa.String(length=255), nullable=True))
    op.add_column("product_listings", sa.Column("seller_rating", sa.Float(), nullable=True))

    op.create_index("ix_product_listings_extraction_confidence", "product_listings", ["extraction_confidence"], unique=False)
    op.create_index("idx_listings_platform_confidence", "product_listings", ["platform_id", "extraction_confidence"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_listings_platform_confidence", table_name="product_listings")
    op.drop_index("ix_product_listings_extraction_confidence", table_name="product_listings")

    op.drop_column("product_listings", "seller_rating")
    op.drop_column("product_listings", "seller_name")
    op.drop_column("product_listings", "data_source")
    op.drop_column("product_listings", "extraction_method")
    op.drop_column("product_listings", "extraction_confidence")

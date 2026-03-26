"""Add confidence and provenance tracking

Revision ID: c5f9a8b2e1d3
Revises: b1e8c3f4d9a2
Create Date: 2026-03-22 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c5f9a8b2e1d3"
down_revision: Union[str, None] = "b1e8c3f4d9a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Products table - Add confidence and source tracking
    op.add_column('products', sa.Column('brand_confidence', sa.Float(), nullable=True))
    op.add_column('products', sa.Column('brand_source', sa.String(50), nullable=True))
    op.add_column('products', sa.Column('color_confidence', sa.Float(), nullable=True))
    op.add_column('products', sa.Column('color_source', sa.String(50), nullable=True))
    op.add_column('products', sa.Column('specs_confidence', sa.Float(), nullable=True))
    op.add_column('products', sa.Column('specs_source', sa.String(50), nullable=True))
    op.add_column('products', sa.Column('last_enriched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('products', sa.Column('enrichment_version', sa.Integer(), nullable=True, server_default='1'))
    
    # Platforms table - Add healing history and stats
    op.add_column('platforms', sa.Column('selector_history', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('platforms', sa.Column('last_healed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('platforms', sa.Column('healing_stats', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Create indexes for performance
    op.create_index('idx_products_brand_confidence', 'products', ['brand_confidence'])
    op.create_index('idx_products_color_confidence', 'products', ['color_confidence'])
    op.create_index('idx_products_last_enriched', 'products', ['last_enriched_at'])
    op.create_index('idx_platforms_last_healed', 'platforms', ['last_healed_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_platforms_last_healed', table_name='platforms')
    op.drop_index('idx_products_last_enriched', table_name='products')
    op.drop_index('idx_products_color_confidence', table_name='products')
    op.drop_index('idx_products_brand_confidence', table_name='products')
    
    # Drop platform columns
    op.drop_column('platforms', 'healing_stats')
    op.drop_column('platforms', 'last_healed_at')
    op.drop_column('platforms', 'selector_history')
    
    # Drop product columns
    op.drop_column('products', 'enrichment_version')
    op.drop_column('products', 'last_enriched_at')
    op.drop_column('products', 'specs_source')
    op.drop_column('products', 'specs_confidence')
    op.drop_column('products', 'color_source')
    op.drop_column('products', 'color_confidence')
    op.drop_column('products', 'brand_source')
    op.drop_column('products', 'brand_confidence')
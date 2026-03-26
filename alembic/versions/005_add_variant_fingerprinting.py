"""Add variant fingerprinting columns to products table

Revision ID: 005
Revises: 4fb89c14d13c
Create Date: 2026-03-18 10:00:00.000000

Enhanced product fingerprinting with variant detection:
- variant_fingerprint: Exact variant matching (iPhone 15 Pro 256GB Blue)
- base_fingerprint: Series matching (iPhone 15)
- variant_type: Pro/Plus/Max/Ultra detection
- storage_gb: Storage capacity in GB
- color: Product color
- condition: New/Refurbished detection

NO DATA LOSS - All changes are additive (ALTER TABLE)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '4fb89c14d13c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add variant fingerprinting columns to products table"""
    
    # Add variant detection columns
    op.add_column('products', sa.Column(
        'variant_fingerprint',
        sa.String(64),
        nullable=True,
        index=True,
        comment='Variant-specific fingerprint (iPhone 15 Pro 256GB)'
    ))
    
    op.add_column('products', sa.Column(
        'base_fingerprint',
        sa.String(64),
        nullable=True,
        index=True,
        comment='Base product fingerprint (iPhone 15 series)'
    ))
    
    op.add_column('products', sa.Column(
        'variant_type',
        sa.String(100),
        nullable=True,
        comment='Variant type (pro, plus, max, ultra, standard)'
    ))
    
    op.add_column('products', sa.Column(
        'storage_gb',
        sa.Integer,
        nullable=True,
        comment='Storage capacity in GB (256, 512, etc)'
    ))
    
    op.add_column('products', sa.Column(
        'color',
        sa.String(50),
        nullable=True,
        comment='Product color (blue, black, pink, etc)'
    ))
    
    op.add_column('products', sa.Column(
        'condition',
        sa.String(50),
        nullable=True,
        default='new',
        comment='Product condition (new, refurbished, used)'
    ))
    
    # Create indexes for cross-platform matching
    op.create_index(
        'idx_products_variant_fingerprint',
        'products',
        ['variant_fingerprint'],
        unique=False
    )
    
    op.create_index(
        'idx_products_base_fingerprint',
        'products',
        ['base_fingerprint'],
        unique=False
    )
    
    op.create_index(
        'idx_products_storage_color',
        'products',
        ['storage_gb', 'color'],
        unique=False
    )
    
    # Add variant_fingerprint column to product_listings table
    op.add_column('product_listings', sa.Column(
        'variant_fingerprint',
        sa.String(64),
        nullable=True,
        index=True,
        comment='Variant-specific fingerprint for cross-platform matching'
    ))
    
    # Create index on product_listings variant_fingerprint
    op.create_index(
        'idx_listings_variant_fp',
        'product_listings',
        ['variant_fingerprint'],
        unique=False
    )
    
    # Create a unique constraint for variant-platform-external_id
    op.create_unique_constraint(
        'uq_variant_per_platform',
        'product_listings',
        ['variant_fingerprint', 'platform_id', 'external_id']
    )


def downgrade() -> None:
    """Revert variant fingerprinting columns (CAUTION: Data from these columns will be lost)"""
    
    # Drop constraints
    try:
        op.drop_constraint('uq_variant_per_platform', 'product_listings')
    except Exception:
        pass  # Constraint might not exist
    
    # Drop indexes
    op.drop_index('idx_listings_variant_fp', 'product_listings')
    op.drop_index('idx_products_variant_fingerprint', 'products')
    op.drop_index('idx_products_base_fingerprint', 'products')
    op.drop_index('idx_products_storage_color', 'products')
    
    # Drop columns from product_listings
    op.drop_column('product_listings', 'variant_fingerprint')
    
    # Drop columns from products
    op.drop_column('products', 'variant_fingerprint')
    op.drop_column('products', 'base_fingerprint')
    op.drop_column('products', 'variant_type')
    op.drop_column('products', 'storage_gb')
    op.drop_column('products', 'color')
    op.drop_column('products', 'condition')

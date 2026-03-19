#!/usr/bin/env python3
"""
Backfill Variant Fingerprints - Phase 1 Implementation
========================================================

Updates all existing products with:
- variant_fingerprint: Exact product variant matching
- base_fingerprint: Product series matching  
- variant_type: Pro/Plus/Max detection
- storage_gb: Storage capacity
- color: Product color
- condition: New/Refurbished

This script safely updates existing data without loss.
All products retain their IDs and relationships.

Usage:
    python scripts/backfill_variant_fingerprints.py
    python scripts/backfill_variant_fingerprints.py --limit 100  # First 100 products
    python scripts/backfill_variant_fingerprints.py --batch-size 50  # 50 at a time

Author: DealHunt
Date: 2026-03-18
"""

import asyncio
import argparse
import sys
import os
import logging
from datetime import datetime

# Windows async fix
if sys.platform == 'win32':
    from asyncio.proactor_events import _ProactorBasePipeTransport
    def silence_proactor_del(self): pass
    _ProactorBasePipeTransport.__del__ = silence_proactor_del

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models import Product, ProductListing
from app.services.scraper.base import ProductData

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VariantFingerprintBackfiller:
    """Backfill variant fingerprints for existing products"""
    
    def __init__(self, batch_size: int = 50, limit: int = None):
        self.batch_size = batch_size
        self.limit = limit
        self.processed = 0
        self.updated = 0
        self.errors = 0
        self.start_time = None
    
    async def backfill_all(self):
        """Process all products in batches"""
        self.start_time = datetime.utcnow()
        
        async with async_session_maker() as db:
            logger.info(f"🔄 Starting backfill with batch_size={self.batch_size}, limit={self.limit}")
            
            # Get total count
            result = await db.execute(select(func.count(Product.id)))
            total = result.scalar()
            logger.info(f"📊 Total products to process: {total}")
            
            offset = 0
            while True:
                # Fetch batch
                result = await db.execute(
                    select(Product)
                    .offset(offset)
                    .limit(self.batch_size)
                )
                products = result.scalars().all()
                
                if not products:
                    break
                
                logger.info(f"⏳ Processing batch {offset // self.batch_size + 1} ({len(products)} products)...")
                
                # Process each product in batch
                for product in products:
                    try:
                        await self._update_product(product, db)
                        self.updated += 1
                    except Exception as e:
                        logger.error(f"❌ Error processing {product.id}: {e}")
                        self.errors += 1
                    
                    self.processed += 1
                    
                    # Check limit
                    if self.limit and self.processed >= self.limit:
                        logger.info(f"✋ Reached limit of {self.limit} products")
                        break
                
                # Commit batch
                await db.commit()
                logger.info(f"✅ Batch committed ({self.processed}/{total if not self.limit else self.limit})")
                
                offset += self.batch_size
                
                if self.limit and self.processed >= self.limit:
                    break
            
            self._print_summary()
    
    async def _update_product(self, product: Product, db: AsyncSession):
        """Update single product with variant fingerprints"""
        
        if not product.title or not product.brand:
            logger.warning(f"⏭️  Skipping {product.id}: Missing title or brand")
            return
        
        # Skip if already has variant_fingerprint set
        if product.variant_fingerprint:
            logger.debug(f"⏭️  Already has variant_fingerprint: {product.id}")
            return
        
        # Create temporary ProductData to leverage variant detection
        product_data = ProductData(
            external_id="backfill",
            title=product.title,
            current_price=1.0,  # Placeholder
            product_url="",
            platform_name="temp",
            brand=product.brand,
            category=product.category,
            subcategory=product.subcategory,
            specifications=product.specifications or {}
        )
        
        # Auto-detect variants
        product_data.detect_all_variants()
        
        # Update product with new fingerprints
        new_variant_fp = product_data.get_variant_fingerprint()
        new_base_fp = product_data.get_base_fingerprint()
        
        # IMPORTANT: Don't update the primary fingerprint if it causes duplicates
        # Instead, keep it as-is and just set the variant fingerprints
        product.variant_fingerprint = new_variant_fp
        product.base_fingerprint = new_base_fp
        product.variant_type = product_data.variant_type
        product.storage_gb = product_data.storage_gb
        product.color = product_data.color
        product.condition = product_data.condition.value if product_data.condition else "new"
        
        # Keep the old fingerprint as-is (don't overwrite with variant_fingerprint)
        # The old fingerprint is just a legacy field now
        
        logger.debug(
            f"📝 Updated {product.id}: "
            f"variant_type={product_data.variant_type}, "
            f"storage={product_data.storage_gb}, "
            f"color={product_data.color}"
        )
    
    def _print_summary(self):
        """Print execution summary"""
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        
        logger.info("="*60)
        logger.info("BACKFILL SUMMARY")
        logger.info("="*60)
        logger.info(f"⏱️  Total time: {elapsed:.1f}s")
        logger.info(f"📦 Processed: {self.processed} products")
        logger.info(f"✅ Updated: {self.updated} products")
        logger.info(f"❌ Errors: {self.errors} products")
        logger.info(f"⚡ Speed: {self.processed / elapsed:.1f} products/sec")
        logger.info("="*60)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Backfill variant fingerprints for existing products")
    parser.add_argument('--limit', type=int, help='Limit number of products to process')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size for processing')
    
    args = parser.parse_args()
    
    backfiller = VariantFingerprintBackfiller(
        batch_size=args.batch_size,
        limit=args.limit
    )
    
    await backfiller.backfill_all()


if __name__ == '__main__':
    asyncio.run(main())

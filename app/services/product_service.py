"""
Product Service
===============

Centralized database operations for Products and ProductListings.
Single source of truth - eliminates DRY violations between API and Jobs.

Features:
- Fingerprint-based deduplication
- Smart stats tracking (user searches vs job seeding)
- Platform auto-creation
- Listing create/update with external_id dedup
- Seed score calculation for job-created products

Author: DealHunt
Version: 1.0 (Centralized)
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Product, ProductListing, Platform
from app.services.scraper.base import ProductData

logger = logging.getLogger(__name__)


class ProductService:
    """
    Centralized database operations for Products and Listings.
    
    Used by:
    - app/api/v1/search.py (user URL searches)
    - app/jobs/daily_scrape_trending.py (trending job)
    - app/jobs/seed_products.py (seeding job)
    - app/jobs/daily_scrape.py (price update job)
    - scripts/*.py (CLI tools)
    """
    
    async def save_product(
        self,
        product_data: ProductData,
        db: AsyncSession,
        is_user_search: bool = False
    ) -> Product:
        """
        Save scraped AND enriched product to database.
        
        Handles:
        - Fingerprint-based deduplication
        - AI metadata storage
        - Stats incrementing (searches vs seed_score)
        - Platform auto-creation
        - Listing create/update with external_id dedup check
        
        Args:
            product_data: Enriched ProductData object
            db: AsyncSession
            is_user_search: If True, increments 'searches' stat.
                           If False, calculates 'seed_score' for trending.
        
        Returns:
            Product: The saved or updated Product model
        """
        fingerprint = product_data.fingerprint
        
        # =====================================================================
        # STEP 1: Check if product exists (Deduplication)
        # =====================================================================
        result = await db.execute(
            select(Product).where(Product.fingerprint == fingerprint)
        )
        existing_product = result.scalar_one_or_none()
        
        # =====================================================================
        # STEP 2: Build AI metadata
        # =====================================================================
        ai_metadata = self._build_ai_metadata(product_data, is_user_search)
        
        # =====================================================================
        # STEP 3: Create or Update Product
        # =====================================================================
        if existing_product:
            product = existing_product
            
            # Update AI metadata if new processing is better
            old_score = (product.ai_metadata or {}).get("quality_score", 0)
            new_score = product_data.ai_quality_score or 0
            
            if new_score > old_score:
                product.ai_metadata = ai_metadata
                product.specifications = product_data.specifications or product.specifications
                product.subcategory = product_data.subcategory or product.subcategory
                logger.debug(f"Updated AI metadata (score {old_score} → {new_score})")
            
            # Update image if missing
            if not product.image_url and product_data.image_url:
                product.image_url = product_data.image_url
            
            # Update brand if missing
            if (not product.brand or product.brand == "Unknown") and product_data.brand:
                product.brand = product_data.brand
            
            # Smart Stats Update
            product.stats = self._update_stats(
                current_stats=product.stats or {},
                is_user_search=is_user_search
            )
            
            logger.debug(f"Updated existing product: {fingerprint[:16]}...")
            
        else:
            # Create completely new product
            initial_stats = self._build_initial_stats(product_data, is_user_search)
            
            product = Product(
                fingerprint=fingerprint,
                title=getattr(product_data, 'title', 'Unknown'),
                brand=getattr(product_data, 'brand', None) or "Unknown",
                category=getattr(product_data, 'category', None) or "General",
                subcategory=getattr(product_data, 'subcategory', None),
                image_url=getattr(product_data, 'image_url', None),
                specifications=getattr(product_data, 'specifications', {}) or {},
                ai_metadata=ai_metadata,
                stats=initial_stats
            )
            db.add(product)
            await db.flush()  # Flush to get product.id
            
            logger.info(f"✅ Created new product: {product.title[:50]}...")
        
        # =====================================================================
        # STEP 4: Handle Platform & Listing
        # =====================================================================
        platform_name = getattr(product_data, 'platform_name', 'unknown').lower()
        platform = await self._get_or_create_platform(platform_name, db)
        
        await self._create_or_update_listing(
            product_id=product.id,
            platform_id=platform.id,
            product_data=product_data,
            db=db
        )
        
        # =====================================================================
        # STEP 5: Commit and Return
        # =====================================================================
        await db.commit()
        await db.refresh(product)
        
        return product
    
    def _build_ai_metadata(
        self, 
        product_data: ProductData, 
        is_user_search: bool
    ) -> Dict[str, Any]:
        """Build AI metadata dictionary for storage"""
        metadata = {
            "essence": getattr(product_data, 'ai_essence', None) or getattr(product_data, 'title', '')[:100].lower(),
            "tags": getattr(product_data, 'ai_tags', []) or [],
            "quality_score": getattr(product_data, 'ai_quality_score', 50) or 50,
            "processed_at": datetime.utcnow().isoformat(),
        }
        
        # Mark seeded products
        if not is_user_search:
            metadata["seeded"] = True
            metadata["seeded_at"] = datetime.utcnow().isoformat()
        
        return metadata
    
    def _build_initial_stats(
        self, 
        product_data: ProductData, 
        is_user_search: bool
    ) -> Dict[str, Any]:
        """Build initial stats for new products"""
        stats = {
            "views": 0,
            "clicks": 0,
            "watches": 0,
            "conversions": 0,
            "searches": 1 if is_user_search else 0,
        }
        
        # Add seed score for job-created products
        if not is_user_search:
            stats["seed_score"] = self._calculate_seed_score(product_data)
            stats["seeded"] = True
            stats["seeded_at"] = datetime.utcnow().isoformat()
        
        return stats
    
    def _update_stats(
        self, 
        current_stats: Dict[str, Any], 
        is_user_search: bool
    ) -> Dict[str, Any]:
        """Update stats for existing products"""
        new_stats = {**current_stats}
        
        if is_user_search:
            new_stats["searches"] = current_stats.get("searches", 0) + 1
            new_stats["last_searched"] = datetime.utcnow().isoformat()
        
        return new_stats
    
    def _calculate_seed_score(self, product_data: ProductData) -> int:
        """
        Calculate initial visibility score for seeded products.
        Based on real signals: rating, reviews, discount.
        """
        score = 0
        
        # Rating contribution (0-25 points)
        rating = getattr(product_data, 'rating', None)
        if rating and isinstance(rating, (int, float)) and rating > 0:
            score += int(float(rating) * 5)  # 5.0 rating = 25 points
        
        # Review count contribution (0-30 points)
        reviews = getattr(product_data, 'review_count', None)
        if reviews and isinstance(reviews, (int, float)):
            if reviews > 1000:
                score += 30
            elif reviews > 100:
                score += 20
            elif reviews > 10:
                score += 10
        
        # Discount contribution (0-20 points)
        discount = getattr(product_data, 'discount_percent', None)
        if discount and isinstance(discount, (int, float)) and discount > 20:
            score += min(20, int(float(discount) / 5))
        
        # AI quality contribution (0-10 points)
        ai_score = getattr(product_data, 'ai_quality_score', None)
        if ai_score and isinstance(ai_score, (int, float)) and ai_score > 50:
            score += int(float(ai_score) / 10)
        
        # Brand presence (5 points)
        brand = getattr(product_data, 'brand', None)
        if brand and str(brand).strip() and brand.lower() != "unknown":
            score += 5
        
        # Image presence (3 points)
        image_url = getattr(product_data, 'image_url', None)
        if image_url and str(image_url).strip():
            score += 3
        
        return score
    
    async def _get_or_create_platform(
        self, 
        platform_name: str, 
        db: AsyncSession
    ) -> Platform:
        """Get existing platform or create new one"""
        result = await db.execute(
            select(Platform).where(Platform.name == platform_name)
        )
        platform = result.scalar_one_or_none()
        
        if not platform:
            platform = Platform(
                name=platform_name,
                base_url=f"https://www.{platform_name}.com",
                is_active=True,
                selectors={}
            )
            db.add(platform)
            await db.flush()
            logger.info(f"Created new platform: {platform_name}")
        
        return platform
    
    async def _create_or_update_listing(
        self,
        product_id,
        platform_id: int,
        product_data: ProductData,
        db: AsyncSession
    ) -> ProductListing:
        """
        Create or update product listing with proper deduplication.
        
        Checks:
        1. Existing listing by product_id + platform_id
        2. Existing listing by external_id (catches cross-linked duplicates)
        """
        external_id = getattr(product_data, 'external_id', None)
        
        # =====================================================================
        # CHECK 1: By product_id + platform_id
        # =====================================================================
        result = await db.execute(
            select(ProductListing).where(
                ProductListing.product_id == product_id,
                ProductListing.platform_id == platform_id
            )
        )
        existing_listing = result.scalar_one_or_none()
        
        # =====================================================================
        # CHECK 2: By external_id (catches duplicates from different fingerprints)
        # =====================================================================
        if not existing_listing and external_id:
            external_check = await db.execute(
                select(ProductListing).where(
                    ProductListing.platform_id == platform_id,
                    ProductListing.external_id == external_id
                )
            )
            existing_listing = external_check.scalar_one_or_none()
            
            # Fix broken link if found
            if existing_listing and existing_listing.product_id != product_id:
                logger.warning(
                    f"Listing {external_id} exists with different product_id, "
                    f"updating link: {existing_listing.product_id} → {product_id}"
                )
                existing_listing.product_id = product_id
        
        # =====================================================================
        # PREPARE LISTING DATA
        # =====================================================================
        current_price = getattr(product_data, 'current_price', None)
        original_price = getattr(product_data, 'original_price', None)
        product_url = getattr(product_data, 'product_url', '') or ''
        
        # Generate affiliate URL
        affiliate_url = self._get_affiliate_url(product_url)
        
        # Safely extract discount percent
        discount = None
        raw_discount = getattr(product_data, 'discount_percent', None)
        if isinstance(raw_discount, (int, float)):
            discount = float(raw_discount)
            
        listing_data = {
            "current_price": float(current_price) if current_price else 0.0,
            "original_price": float(original_price) if original_price else None,
            "discount_percent": discount,
            "rating": getattr(product_data, 'rating', None),
            "review_count": getattr(product_data, 'review_count', None),
            "in_stock": getattr(product_data, 'in_stock', True),
            "last_scraped": datetime.utcnow(),
            "scrape_error_count": 0,
            "last_error": None,
        }
        
        # =====================================================================
        # CREATE OR UPDATE
        # =====================================================================
        if existing_listing:
            # UPDATE existing listing
            for key, value in listing_data.items():
                setattr(existing_listing, key, value)
            
            # Update URL if changed
            if product_url and existing_listing.product_url != product_url:
                existing_listing.product_url = product_url
                existing_listing.affiliate_url = affiliate_url
            
            logger.debug(f"Updated listing: {external_id or 'unknown'}")
            return existing_listing
        else:
            # CREATE new listing
            listing = ProductListing(
                product_id=product_id,
                platform_id=platform_id,
                external_id=external_id,
                product_url=product_url,
                affiliate_url=affiliate_url,
                **listing_data
            )
            db.add(listing)
            
            logger.debug(f"Created listing: {external_id or 'unknown'}")
            return listing
    
    def _get_affiliate_url(self, product_url: str) -> str:
        """Generate affiliate URL using url_detector"""
        if not product_url:
            return ""
        
        try:
            from app.services.scraper.url_detector import url_detector
            return url_detector.get_affiliate_url(product_url)
        except Exception as e:
            logger.debug(f"Affiliate URL generation failed: {e}")
            return product_url
    
    async def get_product_by_fingerprint(
        self, 
        fingerprint: str, 
        db: AsyncSession
    ) -> Optional[Product]:
        """Get product by fingerprint"""
        result = await db.execute(
            select(Product).where(Product.fingerprint == fingerprint)
        )
        return result.scalar_one_or_none()
    
    async def get_product_listings(
        self,
        product_id,
        db: AsyncSession,
        in_stock_only: bool = True
    ) -> list[ProductListing]:
        """Get all listings for a product"""
        query = select(ProductListing).where(
            ProductListing.product_id == product_id
        )
        
        if in_stock_only:
            query = query.where(ProductListing.in_stock == True)
        
        query = query.order_by(ProductListing.current_price.asc())
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def increment_product_stat(
        self,
        product_id,
        stat_name: str,
        db: AsyncSession,
        increment: int = 1
    ) -> None:
        """Increment a specific stat for a product"""
        product = await db.get(Product, product_id)
        if product:
            stats = product.stats or {}
            stats[stat_name] = stats.get(stat_name, 0) + increment
            stats[f"last_{stat_name}"] = datetime.utcnow().isoformat()
            product.stats = stats
            await db.commit()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
product_service = ProductService()
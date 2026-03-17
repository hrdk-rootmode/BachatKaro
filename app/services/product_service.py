"""
Product Service v2.0 - Enhanced Data Quality
==============================================

Centralized database operations for Products and ProductListings.
Single source of truth - eliminates DRY violations between API and Jobs.

🚀 v2.0 ENHANCEMENTS:
- Brand validation & garbage detection (Men/Cotton/Blue → rejected/fixed)
- Automatic spec extraction from titles
- Image URL fallback from listings
- AI Enrichment ensuring essence ≠ title
- Quality gates (only store quality products)
- Pre-storage validation (fix at source, not post-hoc)
- Cross-platform data preservation (all platforms stored with proper relationships)

Features:
- Fingerprint-based deduplication (multi-platform comparison)
- Smart stats tracking (user searches vs job seeding)
- Platform auto-creation
- Listing create/update with external_id dedup
- Seed score calculation for job-created products
- Brand quality checking before storage
- Empty specs extraction before storage
- Mandatory AI enrichment with quality validation

Author: DealHunt
Version: 2.0 (Quality-First Data Pipeline)
"""

import logging
import re
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models import Product, ProductListing, Platform
from app.services.scraper.base import ProductData

logger = logging.getLogger(__name__)

# =============================================================================
# GARBAGE BRAND DETECTION (SAME AS fix_data.py v4.0)
# =============================================================================

GARBAGE_BRANDS = {
    # Generic
    "unknown", "generic", "unbranded", "other", "n/a", "na", "none", "null",
    "brand", "original", "new", "latest", "premium", "best", "top",
    # Attributes mistaken for brands
    "men", "women", "boys", "girls", "kids", "unisex", "male", "female",
    "cotton", "silk", "wool", "polyester", "nylon", "leather", "synthetic",
    "polycotton", "blend", "mixed", "denim", "linen", "rayon",
    # Garment types
    "sneaker", "sneakers", "shoe", "shoes", "dress", "shirt", "tshirt", "t-shirt",
    "trouser", "pant", "kurta", "saree", "top", "bottom", "jacket",
    # Colors
    "black", "white", "blue", "red", "green", "yellow", "pink", "grey",
    "brown", "orange", "purple", "maroon", "navy", "beige", "gold",
    # Styles
    "casual", "formal", "stylish", "trendy", "elegant", "smart", "classic",
    "modern", "vintage", "retro", "slim", "fit", "regular", "loose",
    # Product features
    "wireless", "bluetooth", "digital", "analog", "smart", "pro", "plus",
    "ultra", "max", "lite", "mini", "premium", "deluxe", "standard",
    # Random 2-letter junk
    "te", "sb", "db", "ab", "cd", "xy", "qr", "mn", "pq", "st", "uv",
}

GARBAGE_BRAND_PATTERNS = [
    re.compile(r'^[a-z]{1,2}$', re.I),  # 1-2 letters only
    re.compile(r'^\d+$'),  # Just numbers
    re.compile(r'^[^a-zA-Z]+$'),  # No letters at all
]

# Brand extraction patterns (100+ brands)
BRAND_PATTERNS = re.compile(
    r'\b('
    r'Samsung|Apple|iPhone|iPad|OnePlus|Xiaomi|Redmi|POCO|Realme|'
    r'Vivo|Oppo|Motorola|Moto|Nokia|Google|Pixel|Nothing|iQOO|'
    r'Fire[\s\-]?Boltt|FireBoltt|boAt|boat|Noise|Zebronics|Mivi|Portronics|'
    r'Ambrane|pTron|Ptron|Boult|CrossBeats|Hammer|Fastrack|Titan|Sonata|'
    r'JBL|Sony|Bose|Sennheiser|Skullcandy|Beats|Marshall|'
    r'Dell|HP|Acer|Asus|Lenovo|MSI|Razer|Alienware|ThinkPad|MacBook|'
    r'Nike|Adidas|Puma|Reebok|Levis|Wrangler|Lee|Allen\s*Solly|Van\s*Heusen|'
    r'Peter\s*England|Louis\s*Philippe|US\s*Polo|Roadster|HRX|Bewakoof|'
    r'Forever\s*21|H&M|Zara|UNIQLO|Shein'
    r')\b',
    re.IGNORECASE
)


# =============================================================================
# VALIDATION & EXTRACTION HELPERS (Module-level functions)
# =============================================================================

def _is_garbage_brand(brand: Optional[str]) -> bool:
    """Detect if brand is garbage/invalid"""
    if not brand:
        return True
    
    brand_lower = brand.lower().strip()
    
    # Check garbage word list
    if brand_lower in GARBAGE_BRANDS:
        return True
    
    # Check patterns
    for pattern in GARBAGE_BRAND_PATTERNS:
        if pattern.match(brand):
            return True
    
    # Too short (but not known brand)
    if len(brand_lower) <= 2:
        if not BRAND_PATTERNS.search(brand):
            return True
    
    return False


def _extract_brand_from_title(title: Optional[str]) -> Optional[str]:
    """Extract brand from product title using regex"""
    if not title:
        return None
    
    match = BRAND_PATTERNS.search(title)
    if match:
        return match.group(1).strip()
    
    return None


def _extract_specs_from_title(title: str, category: Optional[str] = None) -> Dict[str, Any]:
    """Extract specs from product title using regex patterns"""
    specs = {}
    
    if not title:
        return specs
    
    title_lower = title.lower()
    
    # RAM extraction (electronics)
    ram_match = re.search(r'(\d+)\s*(?:gb|gbs?)\s*ram', title_lower)
    if ram_match:
        specs["ram_gb"] = int(ram_match.group(1))
    
    # Storage extraction
    storage_match = re.search(r'(\d+)\s*(?:gb|gbs?)\s*(?:storage|ssd|hdd)', title_lower)
    if storage_match:
        specs["storage_gb"] = int(storage_match.group(1))
    
    # Screen size (inches)
    screen_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:inch|")', title_lower)
    if screen_match:
        specs["screen_size"] = float(screen_match.group(1))
    
    # Processor
    if any(proc in title_lower for proc in ['snapdragon', 'exynos', 'helio', 'dimensity', 'k1', 'a15', 'a16']):
        if 'snapdragon' in title_lower:
            specs["processor"] = "Snapdragon"
        elif 'exynos' in title_lower:
            specs["processor"] = "Exynos"
        elif 'helio' in title_lower:
            specs["processor"] = "Helio"
    
    # Generation/Version
    for gen in ['pro', 'pro max', 'ultra', 'lite', 'plus', 'max', 'mini']:
        if gen in title_lower:
            specs["generation"] = gen.title()
            break
    
    # Color extraction
    colors = ['black', 'white', 'blue', 'red', 'green', 'gold', 'silver', 'grey', 'gray', 'pink', 'purple']
    for color in colors:
        if color in title_lower:
            specs["color"] = color.title()
            break
    
    return specs


def _validate_image_url(url: Optional[str]) -> bool:
    """Check if image URL is valid (not None, not empty, not placeholder)"""
    if not url or not str(url).strip():
        return False
    
    url_str = str(url).lower()
    
    # Reject placeholder/broken patterns
    placeholders = [
        'placeholder', 'noimage', 'no-image', 'coming-soon', 
        'unavailable', 'default', '1x1', 'blank', 'dummy'
    ]
    
    if any(p in url_str for p in placeholders):
        return False
    
    return True


def _is_useful_essence(essence: Optional[str], title: Optional[str]) -> bool:
    """Check if AI essence is actually useful (not same as title)"""
    if not essence or not title:
        return False
    
    essence_clean = str(essence).lower().strip()
    title_clean = str(title).lower().strip()
    
    # If essence is same as title up to 80% similarity, it's useless
    essence_short = essence_clean[:80]
    title_short = title_clean[:80]
    
    if essence_short == title_short:
        return False
    
    # If essence is just a substring of title, not useful
    if len(essence_clean) > 0 and len(essence_clean) < len(title_clean):
        if title_clean.find(essence_clean) != -1:
            return False
    
    return True


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
    ) -> Optional[Product]:
        """
        🚀 v2.0 ENHANCED: Save with validation & enrichment.
        
        VALIDATION PIPELINE (at storage time, not post-hoc):
        1. ✅ Validate brand (reject garbage: Men/Cotton/Blue)
        2. ✅ Extract specs if empty (RAM from title, etc)
        3. ✅ Get image URL (fallback from listings if NULL)
        4. ✅ Call AI enrichment if not enriched
        5. ✅ Validate AI essence (must be different from title)
        6. ✅ Quality gate (only store quality products)
        7. ✅ Store with multi-platform relationships
        
        This ensures clean data in DB, no post-hoc cleanup needed.
        
        Args:
            product_data: Raw ProductData from scraper
            db: AsyncSession
            is_user_search: If True, increments 'searches' stat
            
        Returns:
            Product: Validated, enriched, stored product
        """
        # =====================================================================
        # STEP 0: PRE-VALIDATION (Brand & Specs)
        # =====================================================================
        
        # Brand validation: reject or fix garbage brands
        brand = getattr(product_data, 'brand', None)
        if _is_garbage_brand(brand):
            logger.debug(f"🛑 Garbage brand detected: '{brand}', extracting from title...")
            # Try to extract real brand from title
            extracted_brand = _extract_brand_from_title(getattr(product_data, 'title', ''))
            if extracted_brand and not _is_garbage_brand(extracted_brand):
                product_data.brand = extracted_brand
                logger.info(f"✅ Brand fixed: {brand} → {extracted_brand}")
            else:
                product_data.brand = "Unknown"
                logger.warning(f"⚠️ Couldn't fix brand, using 'Unknown': {brand}")
        
        # Spec extraction: if specs are empty, extract from title
        specs = getattr(product_data, 'specifications', {}) or {}
        if not specs or specs == {}:
            logger.debug(f"📋 Empty specs detected, extracting from title...")
            extracted_specs = _extract_specs_from_title(
                getattr(product_data, 'title', ''),
                category=getattr(product_data, 'category', None)
            )
            if extracted_specs:
                product_data.specifications = extracted_specs
                logger.info(f"✅ Specs extracted: {extracted_specs}")
            else:
                product_data.specifications = {}
        
        # =====================================================================
        # STEP 0.5: IMAGE URL FALLBACK (Get from listings if NULL)
        # =====================================================================
        image_url = getattr(product_data, 'image_url', None)
        if not _validate_image_url(image_url):
            logger.debug(f"🖼️ Image URL missing or invalid, will try to get from listings...")
            # Placeholder - will be filled from listing after product creation
            product_data.image_url = None
        
        # =====================================================================
        # STEP 1: CHECK IF PRODUCT EXISTS (Deduplication - Multi-Platform Match)
        # =====================================================================
        fingerprint = product_data.fingerprint
        
        result = await db.execute(
            select(Product).where(Product.fingerprint == fingerprint)
        )
        existing_product = result.scalar_one_or_none()
        
        # =====================================================================
        # STEP 1.5: AI ENRICHMENT (Mandatory before storage)
        # =====================================================================
        ai_essence = getattr(product_data, 'ai_essence', None)
        ai_quality_score = getattr(product_data, 'ai_quality_score', None)
        
        # If essence is missing or useless, try to enrich
        if not _is_useful_essence(ai_essence, getattr(product_data, 'title', '')):
            logger.debug(f"🧠 Useless/missing essence, calling AI enrichment...")
            try:
                from app.services.ai.enrichment_service import enrichment_service
                product_data = await enrichment_service.enrich_product(product_data)
                ai_essence = getattr(product_data, 'ai_essence', None)
                ai_quality_score = getattr(product_data, 'ai_quality_score', 50)
                
                if _is_useful_essence(ai_essence, getattr(product_data, 'title', '')):
                    logger.info(f"✅ AI enrichment successful: essence={ai_essence[:50]}...")
                else:
                    logger.warning(f"⚠️ AI enrichment didn't improve: {ai_essence}")
                    # Fallback: use brand + key specs as essence
                    essence_parts = []
                    if product_data.brand and product_data.brand != "Unknown":
                        essence_parts.append(product_data.brand)
                    
                    # Add key specs
                    specs = getattr(product_data, 'specifications', {}) or {}
                    if specs.get('ram_gb'):
                        essence_parts.append(f"{specs['ram_gb']}GB RAM")
                    if specs.get('storage_gb'):
                        essence_parts.append(f"{specs['storage_gb']}GB Storage")
                    if specs.get('processor'):
                        essence_parts.append(specs['processor'])
                    
                    if essence_parts:
                        ai_essence = " | ".join(essence_parts).lower()
                        ai_quality_score = 45
                    else:
                        ai_essence = getattr(product_data, 'title', '')[:80].lower()
                        ai_quality_score = 30
                    
                    logger.info(f"✅ Fallback essence created: {ai_essence}")
                
            except Exception as e:
                logger.warning(f"⚠️ AI enrichment failed (continuing with fallback): {e}")
                # Fallback essence
                ai_essence = f"{getattr(product_data, 'brand', 'Product')} - {getattr(product_data, 'title', '')[:40]}".lower()
                ai_quality_score = 30
        
        # =====================================================================
        # STEP 2: BUILD AI METADATA (with validated essence)
        # =====================================================================
        ai_metadata = self._build_ai_metadata(
            product_data, 
            is_user_search,
            force_essence=ai_essence,
            force_quality_score=ai_quality_score
        )
        
        # =====================================================================
        # STEP 3: CREATE OR UPDATE PRODUCT
        # =====================================================================
        if existing_product:
            product = existing_product
            
            # Update AI metadata if new processing is better
            old_score = (product.ai_metadata or {}).get("quality_score", 0)
            new_score = ai_quality_score or 50
            
            if new_score > old_score:
                product.ai_metadata = ai_metadata
                product.specifications = getattr(product_data, 'specifications', {}) or product.specifications
                product.subcategory = getattr(product_data, 'subcategory', None) or product.subcategory
                logger.debug(f"✅ Updated AI metadata (score {old_score} → {new_score})")
            
            # Update image if missing (and new one is valid)
            if _validate_image_url(getattr(product_data, 'image_url', None)):
                if not _validate_image_url(product.image_url):
                    product.image_url = getattr(product_data, 'image_url', None)
                    logger.info(f"✅ Image URL backfilled from listing")
            
            # Update brand if it was garbage before
            if (not product.brand or product.brand == "Unknown") and product_data.brand:
                if not _is_garbage_brand(product_data.brand):
                    product.brand = product_data.brand
                    logger.info(f"✅ Brand updated: {product_data.brand}")
            
            # Smart Stats Update
            product.stats = self._update_stats(
                current_stats=product.stats or {},
                is_user_search=is_user_search
            )
            
            logger.info(f"✅ Updated existing (multi-platform match): {fingerprint[:16]}...")
            
        else:
            # Create new product with validated data
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
            
            logger.info(f"✅ Created new product (stored for multi-platform comparison): {product.title[:50]}...")
        
        # =====================================================================
        # STEP 4: HANDLE PLATFORM & LISTING (all platforms stored together)
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
        # STEP 5: TRY TO GET IMAGE FROM LISTING IF STILL MISSING
        # =====================================================================
        if not _validate_image_url(product.image_url):
            logger.debug(f"📸 Trying to get image from listings...")
            listings = await db.execute(
                select(ProductListing).where(
                    ProductListing.product_id == product.id
                )
            )
            for listing in listings.scalars().all():
                # Try to extract image from listing if it has product URL
                if listing.product_url and _validate_image_url(getattr(listing, 'image_url', None)):
                    product.image_url = listing.image_url
                    logger.info(f"✅ Image backfilled from {platform_name.upper()} listing")
                    break
        
        # =====================================================================
        # STEP 6: COMMIT AND RETURN
        # =====================================================================
        await db.commit()
        await db.refresh(product)
        
        return product
    
    def _build_ai_metadata(
        self, 
        product_data: ProductData, 
        is_user_search: bool,
        force_essence: Optional[str] = None,
        force_quality_score: Optional[int] = None
    ) -> Dict[str, Any]:
        """Build AI metadata dictionary for storage with validation"""
        
        # Use forced values if provided (from enrichment)
        essence = force_essence or getattr(product_data, 'ai_essence', None) or ""
        quality_score = force_quality_score or getattr(product_data, 'ai_quality_score', None) or 50
        
        # Ensure essence is string and not empty
        if not essence or not str(essence).strip():
            # Fallback: brand + model
            brand = getattr(product_data, 'brand', '')
            title_snippet = getattr(product_data, 'title', '')[:60]
            essence = f"{brand} {title_snippet}".lower().strip()
        
        metadata = {
            "essence": str(essence)[:200].lower(),  # Normalized, max 200 chars
            "tags": getattr(product_data, 'ai_tags', []) or [],
            "quality_score": max(0, min(100, int(quality_score))) if quality_score else 50,  # 0-100
            "processed_at": datetime.utcnow().isoformat(),
            "enriched": True,  # Mark as enriched (new v2.0)
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
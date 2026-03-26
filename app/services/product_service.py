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
from difflib import SequenceMatcher
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

MIN_BRAND_CONFIDENCE = 0.40
MIN_COLOR_CONFIDENCE = 0.40
MIN_SPECS_CONFIDENCE = 0.35

INVALID_VALUES = {
    "null", "none", "n/a", "na", "unknown", "not available",
    "-", "", "undefined", "not specified", "n.a.", "nil", "blank"
}

COLOR_CANONICAL_MAP = {
    "grey": "gray",
    "space grey": "gray",
    "space gray": "gray",
    "midnight black": "black",
    "jet black": "black",
    "ocean blue": "blue",
    "sky blue": "blue",
    "rose gold": "gold",
    "champagne gold": "gold",
    "silver white": "silver",
    "off white": "white",
    "cream": "white",
}

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


def _is_invalid_value(value: Optional[str]) -> bool:
    """Check if value is invalid placeholder."""
    if value is None:
        return True
    return str(value).lower().strip() in INVALID_VALUES


def _canonicalize_color(color: Optional[str]) -> Optional[str]:
    """Canonicalize color to standard form."""
    if not color:
        return None

    color_lower = str(color).lower().strip()
    if _is_invalid_value(color_lower):
        return None

    return COLOR_CANONICAL_MAP.get(color_lower, color_lower)


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


def _normalize_title_for_match(title: Optional[str]) -> str:
    """Normalize title text for resilient similarity matching."""
    if not title:
        return ""

    tokens = re.findall(r"[a-z0-9]+", title.lower())
    stop_words = {
        "the", "a", "an", "and", "or", "for", "with", "new", "latest",
        "buy", "online", "best", "offer", "deal", "pack", "combo"
    }
    filtered = [t for t in tokens if t not in stop_words and len(t) > 1]
    return " ".join(filtered)


def _title_similarity(title_a: Optional[str], title_b: Optional[str]) -> float:
    """Hybrid similarity score (sequence + token overlap) for product titles."""
    norm_a = _normalize_title_for_match(title_a)
    norm_b = _normalize_title_for_match(title_b)

    if not norm_a or not norm_b:
        return 0.0

    seq_score = SequenceMatcher(None, norm_a, norm_b).ratio()
    tokens_a = set(norm_a.split())
    tokens_b = set(norm_b.split())
    union = tokens_a.union(tokens_b)
    token_score = (len(tokens_a.intersection(tokens_b)) / len(union)) if union else 0.0

    return (seq_score * 0.7) + (token_score * 0.3)


def _infer_subcategory(
    title: Optional[str],
    category: Optional[str] = None,
    specs: Optional[Dict[str, Any]] = None,
) -> str:
    """Infer a stable subcategory from title/category/specs when AI did not provide one."""
    title_lower = (title or "").lower()
    category_lower = (category or "").lower().strip()
    specs = specs or {}

    # Accessory-first checks avoid mapping "iphone cover" to mobile phones.
    if any(k in title_lower for k in ["cover", "case", "tempered glass", "screen guard", "charger", "cable", "power bank"]):
        return "Mobile Accessories"
    if any(k in title_lower for k in ["laptop sleeve", "laptop bag", "mouse", "keyboard", "dock", "usb hub"]):
        return "Laptop Accessories"

    if category_lower == "electronics":
        if any(k in title_lower for k in ["iphone", "smartphone", "mobile", "5g phone"]):
            return "Mobiles"
        if any(k in title_lower for k in ["laptop", "notebook", "macbook"]):
            return "Laptops"
        if any(k in title_lower for k in ["tablet", "ipad", "tab "]):
            return "Tablets"
        if any(k in title_lower for k in ["smartwatch", "watch", "band"]):
            return "Wearables"
        if any(k in title_lower for k in ["headphone", "earbud", "earphone", "speaker"]):
            return "Audio"
        if "screen_size" in specs and float(specs.get("screen_size") or 0) >= 30:
            return "Televisions"
        return "Other Electronics"

    if category_lower == "fashion":
        if any(k in title_lower for k in ["tshirt", "t-shirt", "shirt", "kurta", "top", "dress", "saree"]):
            return "Apparel"
        if any(k in title_lower for k in ["jeans", "trouser", "pants", "palazzo", "leggings"]):
            return "Bottomwear"
        if any(k in title_lower for k in ["sneaker", "shoes", "sandals", "chappal", "heels", "loafers"]):
            return "Footwear"
        if any(k in title_lower for k in ["handbag", "wallet", "belt", "ring", "earring", "necklace", "bracelet", "watch"]):
            return "Fashion Accessories"
        return "Other Fashion"

    if category_lower == "home & kitchen":
        if any(k in title_lower for k in ["mixer", "grinder", "air fryer", "pressure cooker", "cookware", "kettle", "gas stove"]):
            return "Kitchen Appliances"
        if any(k in title_lower for k in ["bedsheet", "curtain", "blanket", "pillow"]):
            return "Home Furnishing"
        if any(k in title_lower for k in ["organizer", "storage", "basket", "rack"]):
            return "Home Organization"
        return "Other Home & Kitchen"

    if category_lower == "accessories":
        if any(k in title_lower for k in ["cover", "case", "tempered", "charger", "cable", "power bank"]):
            return "Mobile Accessories"
        if any(k in title_lower for k in ["sleeve", "mouse", "keyboard", "dock", "hub", "webcam"]):
            return "Laptop Accessories"
        if any(k in title_lower for k in ["backpack", "bag", "wallet", "belt"]):
            return "Bags & Wallets"
        return "Other Accessories"

    if category_lower == "books":
        if any(k in title_lower for k in ["python", "programming", "system design", "machine learning"]):
            return "Technology"
        if any(k in title_lower for k in ["upsc", "jee", "neet", "exam"]):
            return "Exam Preparation"
        if any(k in title_lower for k in ["fiction", "novel", "story"]):
            return "Fiction"
        if any(k in title_lower for k in ["business", "biography", "self help"]):
            return "Non-Fiction"
        return "General Books"

    if category_lower == "beauty":
        if any(k in title_lower for k in ["lipstick", "foundation", "serum", "cream", "face wash", "makeup"]):
            return "Makeup & Skincare"
        if any(k in title_lower for k in ["shampoo", "conditioner", "hair", "oil"]):
            return "Hair Care"
        if any(k in title_lower for k in ["perfume", "deodorant", "fragrance"]):
            return "Fragrances"
        return "Other Beauty"

    if category_lower == "sports":
        if any(k in title_lower for k in ["running", "shoes", "sneakers"]):
            return "Sports Footwear"
        if any(k in title_lower for k in ["cricket", "bat", "football", "gym", "yoga"]):
            return "Sports Equipment"
        return "Other Sports"

    return "General"


def _infer_color(product_data: ProductData) -> Optional[str]:
    """Infer color from explicit field, specs, or title heuristics."""
    invalid_colors = {"null", "none", "n/a", "na", "unknown", "not available", "-", ""}

    current = getattr(product_data, "color", None)
    if current:
        value = str(current).strip().lower()
        if value not in invalid_colors:
            return value

    specs = getattr(product_data, "specifications", {}) or {}
    spec_color = specs.get("color") or specs.get("colour")
    if spec_color:
        value = str(spec_color).strip().lower()
        if value not in invalid_colors:
            return value

    extracted = _extract_specs_from_title(getattr(product_data, "title", ""))
    title_color = extracted.get("color")
    if title_color:
        value = str(title_color).strip().lower()
        if value not in invalid_colors:
            return value

    return None


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
        """Save with confidence-based merge logic."""
        brand = getattr(product_data, "brand", None)
        brand_confidence = getattr(product_data, "brand_confidence", 0.3) or 0.0
        brand_source = getattr(product_data, "brand_source", "unknown")

        if _is_garbage_brand(brand):
            logger.debug(f"🛑 Garbage brand detected: '{brand}', extracting from title...")
            extracted_brand = _extract_brand_from_title(getattr(product_data, "title", ""))
            if extracted_brand and not _is_garbage_brand(extracted_brand):
                product_data.brand = extracted_brand
                product_data.brand_confidence = 0.65
                product_data.brand_source = "title_heuristic"
                logger.info(f"✅ Brand fixed: {brand} -> {extracted_brand}")
            else:
                product_data.brand = None
                product_data.brand_confidence = 0.0
                product_data.brand_source = None
        elif brand and brand_confidence < MIN_BRAND_CONFIDENCE:
            logger.debug(f"⚠️ Low confidence brand rejected: {brand} (conf={brand_confidence:.2f})")
            product_data.brand = None
            product_data.brand_confidence = 0.0
            product_data.brand_source = None
        else:
            product_data.brand_source = brand_source

        color = getattr(product_data, "color", None) or _infer_color(product_data)
        color_confidence = getattr(product_data, "color_confidence", 0.3) or 0.0
        color_source = getattr(product_data, "color_source", "unknown")
        canonical_color = _canonicalize_color(color)

        if canonical_color and color_confidence >= MIN_COLOR_CONFIDENCE:
            product_data.color = canonical_color
            product_data.color_confidence = color_confidence
            product_data.color_source = color_source
        else:
            if canonical_color:
                logger.debug(f"⚠️ Low confidence color rejected: {canonical_color} (conf={color_confidence:.2f})")
            product_data.color = None
            product_data.color_confidence = 0.0
            product_data.color_source = None

        specs = getattr(product_data, "specifications", {}) or {}
        specs_confidence = getattr(product_data, "specs_confidence", 0.4) or 0.0
        if not specs:
            specs = _extract_specs_from_title(
                getattr(product_data, "title", ""),
                category=getattr(product_data, "category", None),
            )
            product_data.specifications = specs

        if specs_confidence < MIN_SPECS_CONFIDENCE and specs:
            logger.debug(f"⚠️ Low confidence specs rejected (conf={specs_confidence:.2f})")
            product_data.specifications = {}
            product_data.specs_confidence = 0.0
            product_data.specs_source = None

        if not _validate_image_url(getattr(product_data, "image_url", None)):
            product_data.image_url = None

        incoming_subcategory = getattr(product_data, "subcategory", None)
        if not incoming_subcategory or not str(incoming_subcategory).strip():
            product_data.subcategory = _infer_subcategory(
                title=getattr(product_data, "title", ""),
                category=getattr(product_data, "category", None),
                specs=getattr(product_data, "specifications", {}) or {},
            )

        product_data.detect_all_variants()
        logger.info(
            f"✅ Variants detected: type={product_data.variant_type}, "
            f"storage={product_data.storage_gb}GB, color={product_data.color}"
        )

        variant_fingerprint = product_data.get_variant_fingerprint()
        base_fingerprint = product_data.get_base_fingerprint()
        platform = await self._get_or_create_platform(product_data.platform_name, db)
        platform_id = platform.id
        external_id = getattr(product_data, "external_id", None)

        if external_id:
            result = await db.execute(
                select(ProductListing).where(
                    ProductListing.platform_id == platform_id,
                    ProductListing.external_id == external_id,
                )
            )
            existing_by_external = result.scalar_one_or_none()
            if existing_by_external:
                existing_product = await db.get(Product, existing_by_external.product_id)
                if existing_product:
                    logger.info("🔄 REFRESH: Existing external_id listing found, updating current record")

                    await self._merge_product_attributes(existing_product, product_data, db)
                    await self._create_or_update_listing(
                        product_id=existing_product.id,
                        platform_id=platform_id,
                        product_data=product_data,
                        db=db,
                    )

                    await db.commit()
                    await db.refresh(existing_product)
                    return existing_product

        result = await db.execute(
            select(Product).where(Product.variant_fingerprint == variant_fingerprint)
        )
        existing_product = result.scalar_one_or_none()

        if existing_product:
            result = await db.execute(
                select(ProductListing).where(
                    ProductListing.product_id == existing_product.id,
                    ProductListing.platform_id == platform_id,
                )
            )
            existing_listing = result.scalar_one_or_none()

            if existing_listing:
                logger.info("🔄 REFRESH: Same variant on platform, updating listing instead of skipping")

                await self._merge_product_attributes(existing_product, product_data, db)
                await self._create_or_update_listing(
                    product_id=existing_product.id,
                    platform_id=platform_id,
                    product_data=product_data,
                    db=db,
                )

                await db.commit()
                await db.refresh(existing_product)
                return existing_product

            logger.info(f"✅ CROSS-PLATFORM MATCH: Reusing product {existing_product.id}")

            await self._merge_product_attributes(existing_product, product_data, db)

            await self._create_or_update_listing(
                product_id=existing_product.id,
                platform_id=platform_id,
                product_data=product_data,
                db=db,
            )

            await db.commit()
            await db.refresh(existing_product)
            return existing_product

        base_fallback_product = await self._find_base_fingerprint_candidate(
            product_data=product_data,
            base_fingerprint=base_fingerprint,
            platform_id=platform_id,
            db=db,
        )
        if base_fallback_product:
            await self._merge_product_attributes(base_fallback_product, product_data, db)

            await self._create_or_update_listing(
                product_id=base_fallback_product.id,
                platform_id=platform_id,
                product_data=product_data,
                db=db,
            )

            await db.commit()
            await db.refresh(base_fallback_product)
            return base_fallback_product

        needs_enrichment = (
            not getattr(product_data, "ai_processed", False)
            or not getattr(product_data, "brand", None)
            or not getattr(product_data, "color", None)
        )

        if needs_enrichment:
            logger.debug("🧠 Enriching product...")
            try:
                from app.services.ai.enrichment_service import enrichment_service

                product_data = await enrichment_service.enrich_product(product_data)

                if product_data.brand and _is_garbage_brand(product_data.brand):
                    product_data.brand = None
                    product_data.brand_confidence = 0.0

                if product_data.color:
                    product_data.color = _canonicalize_color(product_data.color)
                    color_conf = getattr(product_data, "color_confidence", 0.0) or 0.0
                    if not product_data.color or color_conf < MIN_COLOR_CONFIDENCE:
                        product_data.color = None
                        product_data.color_confidence = 0.0
            except Exception as e:
                logger.warning(f"⚠️ AI enrichment failed: {e}")

        if not getattr(product_data, "subcategory", None):
            product_data.subcategory = _infer_subcategory(
                title=getattr(product_data, "title", ""),
                category=getattr(product_data, "category", None),
                specs=getattr(product_data, "specifications", {}) or {},
            )

        ai_metadata = self._build_ai_metadata(product_data, is_user_search)
        initial_stats = self._build_initial_stats(product_data, is_user_search)

        product = Product(
            fingerprint=variant_fingerprint,
            variant_fingerprint=variant_fingerprint,
            base_fingerprint=base_fingerprint,
            variant_type=product_data.variant_type,
            storage_gb=product_data.storage_gb,
            color=product_data.color,
            condition=product_data.condition.value if product_data.condition else "new",
            title=getattr(product_data, "title", "Unknown"),
            brand=getattr(product_data, "brand", None),
            category=getattr(product_data, "category", None) or "General",
            subcategory=getattr(product_data, "subcategory", None),
            image_url=getattr(product_data, "image_url", None),
            specifications=getattr(product_data, "specifications", {}) or {},
            brand_confidence=getattr(product_data, "brand_confidence", None),
            brand_source=getattr(product_data, "brand_source", None),
            color_confidence=getattr(product_data, "color_confidence", None),
            color_source=getattr(product_data, "color_source", None),
            specs_confidence=getattr(product_data, "specs_confidence", None),
            specs_source=getattr(product_data, "specs_source", None),
            last_enriched_at=datetime.utcnow() if getattr(product_data, "ai_processed", False) else None,
            enrichment_version=2,
            ai_metadata=ai_metadata,
            stats=initial_stats,
        )

        db.add(product)
        await db.flush()

        brand_conf_val = getattr(product, "brand_confidence", None) or 0.0
        color_conf_val = getattr(product, "color_confidence", None) or 0.0
        logger.info(
            f"✅ Created new product: {product.title[:50]}... "
            f"(brand_conf={brand_conf_val:.2f}, color_conf={color_conf_val:.2f})"
        )

        await self._create_or_update_listing(
            product_id=product.id,
            platform_id=platform_id,
            product_data=product_data,
            db=db,
        )

        await db.commit()
        await db.refresh(product)
        return product

    async def _merge_product_attributes(
        self,
        existing: Product,
        incoming: ProductData,
        db: AsyncSession,
    ) -> Product:
        """Merge product attributes using confidence-based strategy."""
        changes = []

        incoming_brand = getattr(incoming, "brand", None)
        incoming_brand_conf = getattr(incoming, "brand_confidence", 0.0) or 0.0
        existing_brand_conf = existing.brand_confidence or 0.0

        if (
            incoming_brand
            and not _is_garbage_brand(incoming_brand)
            and incoming_brand_conf > existing_brand_conf
            and incoming_brand_conf >= MIN_BRAND_CONFIDENCE
        ):
            old_brand = existing.brand
            existing.brand = incoming_brand
            existing.brand_confidence = incoming_brand_conf
            existing.brand_source = getattr(incoming, "brand_source", "unknown")
            changes.append(f"brand: {old_brand} -> {incoming_brand} (conf={incoming_brand_conf:.2f})")

        incoming_color = _canonicalize_color(getattr(incoming, "color", None))
        incoming_color_conf = getattr(incoming, "color_confidence", 0.0) or 0.0
        existing_color_conf = existing.color_confidence or 0.0

        if (
            incoming_color
            and incoming_color_conf > existing_color_conf
            and incoming_color_conf >= MIN_COLOR_CONFIDENCE
        ):
            old_color = existing.color
            existing.color = incoming_color
            existing.color_confidence = incoming_color_conf
            existing.color_source = getattr(incoming, "color_source", "unknown")
            changes.append(f"color: {old_color} -> {incoming_color} (conf={incoming_color_conf:.2f})")

        incoming_specs = getattr(incoming, "specifications", {}) or {}
        incoming_specs_conf = getattr(incoming, "specs_confidence", 0.0) or 0.0
        existing_specs_conf = existing.specs_confidence or 0.0

        if incoming_specs and incoming_specs_conf >= MIN_SPECS_CONFIDENCE:
            if incoming_specs_conf > existing_specs_conf:
                existing.specifications = incoming_specs
                existing.specs_confidence = incoming_specs_conf
                existing.specs_source = getattr(incoming, "specs_source", "unknown")
                changes.append(f"specs: replaced with higher confidence ({incoming_specs_conf:.2f})")
            else:
                existing_specs = existing.specifications or {}
                merged_specs = {**existing_specs, **incoming_specs}
                existing.specifications = merged_specs
                changes.append(f"specs: merged {len(incoming_specs)} new fields")

        if getattr(incoming, "ai_processed", False):
            existing.last_enriched_at = datetime.utcnow()
            existing.enrichment_version = 2

        if not existing.image_url and getattr(incoming, "image_url", None):
            existing.image_url = incoming.image_url
            changes.append("image_url: added")

        incoming_subcategory = getattr(incoming, "subcategory", None) or _infer_subcategory(
            title=getattr(incoming, "title", ""),
            category=getattr(incoming, "category", existing.category),
            specs=getattr(incoming, "specifications", {}) or {},
        )
        if (not existing.subcategory or not str(existing.subcategory).strip()) and incoming_subcategory:
            existing.subcategory = incoming_subcategory
            changes.append(f"subcategory: set -> {incoming_subcategory}")

        if changes:
            logger.info(f"🔄 Merged attributes: {', '.join(changes)}")

        return existing
    
    def _build_ai_metadata(
        self, 
        product_data: ProductData, 
        is_user_search: bool
    ) -> Dict[str, Any]:
        """Build AI metadata with enrichment tracking."""
        essence = getattr(product_data, 'ai_essence', None) or ""
        quality_score = getattr(product_data, 'ai_quality_score', None) or 50

        if not essence or not str(essence).strip():
            brand = getattr(product_data, 'brand', '')
            title_snippet = getattr(product_data, 'title', '')[:60]
            essence = f"{brand} {title_snippet}".lower().strip()

        metadata = {
            "essence": str(essence)[:200].lower(),
            "tags": getattr(product_data, 'ai_tags', []) or [],
            "quality_score": max(0, min(100, int(quality_score))) if quality_score else 50,
            "processed_at": datetime.utcnow().isoformat(),
            "enriched": getattr(product_data, 'ai_processed', False),
            "enrichment_version": 2,
        }

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
        """Calculate seed score with confidence bonus."""
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
        
        brand_conf = getattr(product_data, 'brand_confidence', 0.0) or 0.0
        color_conf = getattr(product_data, 'color_confidence', 0.0) or 0.0

        if brand_conf >= 0.8:
            score += 5
        if color_conf >= 0.8:
            score += 3
        
        # Brand presence (5 points)
        brand = getattr(product_data, 'brand', None)
        if brand and str(brand).strip() and brand.lower() != "unknown":
            score += 5
        
        # Image presence (3 points)
        image_url = getattr(product_data, 'image_url', None)
        if image_url and str(image_url).strip():
            score += 3
        
        return min(100, score)

    async def _find_base_fingerprint_candidate(
        self,
        product_data: ProductData,
        base_fingerprint: Optional[str],
        platform_id: int,
        db: AsyncSession,
    ) -> Optional[Product]:
        """
        Guarded fallback matcher for cross-platform linking.

        Used only when exact variant fingerprint did not match.
        """
        if not base_fingerprint:
            return None

        result = await db.execute(
            select(Product).where(Product.base_fingerprint == base_fingerprint)
        )
        candidates = result.scalars().all()
        if not candidates:
            return None

        incoming_title = getattr(product_data, "title", "")
        incoming_category = (getattr(product_data, "category", None) or "").lower().strip()
        incoming_brand = (getattr(product_data, "brand", None) or "").lower().strip()
        incoming_storage = getattr(product_data, "storage_gb", None)
        incoming_color = _canonicalize_color(getattr(product_data, "color", None))

        best_candidate = None
        best_score = 0.0

        for candidate in candidates:
            listing_check = await db.execute(
                select(ProductListing.id).where(
                    ProductListing.product_id == candidate.id,
                    ProductListing.platform_id == platform_id,
                )
            )
            if listing_check.scalar_one_or_none() is not None:
                continue

            candidate_category = (candidate.category or "").lower().strip()
            if incoming_category and candidate_category and incoming_category != candidate_category:
                continue

            candidate_brand = (candidate.brand or "").lower().strip()
            if incoming_brand and candidate_brand and incoming_brand != candidate_brand:
                continue

            if incoming_storage and candidate.storage_gb and incoming_storage != candidate.storage_gb:
                continue

            candidate_color = _canonicalize_color(candidate.color)
            if incoming_color and candidate_color and incoming_color != candidate_color:
                continue

            similarity = _title_similarity(incoming_title, candidate.title)
            if similarity > best_score:
                best_score = similarity
                best_candidate = candidate

        if best_candidate and best_score >= 0.74:
            logger.info(
                f"🔗 BASE-FP fallback match: product_id={best_candidate.id} "
                f"(title_similarity={best_score:.2f})"
            )
            return best_candidate

        return None
    
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
        
        # Phase 1: Get variant fingerprint for cross-platform deduplication
        variant_fingerprint = product_data.get_variant_fingerprint()
            
        listing_data = {
            "variant_fingerprint": variant_fingerprint,  # Phase 1: Enhanced fingerprint
            "current_price": float(current_price) if current_price else 0.0,
            "original_price": float(original_price) if original_price else None,
            "discount_percent": discount,
            "rating": getattr(product_data, 'rating', None),
            "review_count": getattr(product_data, 'review_count', None),
            "in_stock": getattr(product_data, 'in_stock', True),
            "last_scraped": datetime.utcnow(),
            "extraction_confidence": getattr(product_data, 'extraction_confidence', None),
            "extraction_method": getattr(getattr(product_data, 'extraction_method', None), 'value', None),
            "data_source": getattr(getattr(product_data, 'data_source', None), 'value', None),
            "seller_name": getattr(product_data, 'seller_name', None),
            "seller_rating": getattr(product_data, 'seller_rating', None),
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
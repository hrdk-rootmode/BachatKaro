"""
Search API Routes - AI Enhanced Edition
Multi-platform product search with intelligent enrichment and cross-platform matching

FLOW:
1. User Search/URL → 2. Cache Check → 3. Scrape/API → 4. AI Enrich → 5. Save DB → 6. Response

Author: DealHunt
Updated: Refactored to use centralized services (DRY)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc, Integer, cast
from sqlalchemy.orm import selectinload
from typing import Dict, List, Optional, Set, Tuple
import hashlib
import time
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.database import get_db
from app.core.redis_client import RedisClient, get_redis
from app.core.config import settings
from app.models import Product, ProductListing, User, Transaction
from app.models import Platform as PlatformModel
from app.schemas import (
    SearchRequest,
    SearchByURLRequest,
    SearchResponse,
    ProductResponse,
    ProductListingResponse,
    TrendingProductResponse,
    Platform
)
from app.api.deps import get_current_user, check_rate_limit

# Services
from app.services.scraper.url_detector import url_detector, URLAnalysis, PlatformSupport
from app.services.scraper.generic_scraper import GenericAIScraper
from app.services.scraper.cross_platform_matcher import cross_platform_matcher
from app.services.scraper.search_queue import get_search_queue
from app.services.scraper.factory import get_platform_handler
from app.services.scraper.base import ProductData

# ✅ NEW: Centralized Services (Replaces duplicate code)
from app.services.ai.enrichment_service import enrichment_service
from app.services.product_service import product_service

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_search_cache_key(
    query: str,
    filters: dict,
    page: int = 1,
    sort_by: str = "relevance"
) -> str:
    """Generate cache key for search query"""
    platforms = filters.get('platforms', 'all')
    if isinstance(platforms, (list, tuple, set)):
        normalized_platforms = [
            getattr(platform, "value", str(platform)).lower()
            for platform in platforms
        ]
        platforms = ",".join(sorted(normalized_platforms)) if normalized_platforms else "all"

    filter_str = (
        f"{platforms}_{filters.get('min_price', 0)}_{filters.get('max_price', 999999)}"
        f"_{sort_by}_{page}_{getattr(settings, 'MIN_LISTING_CONFIDENCE', 0.6)}"
        f"_{getattr(settings, 'CROMA_ENABLED', False)}"
    )
    combined = f"{query.lower().strip()}_{filter_str}"
    return f"search:{hashlib.md5(combined.encode()).hexdigest()}"


def _get_enabled_platforms() -> set[str]:
    enabled = {"amazon", "flipkart", "meesho", "myntra", "nykaa", "croma"}
    if not getattr(settings, "CROMA_ENABLED", False):
        enabled.discard("croma")
    return enabled


def _listing_meets_quality(listing: ProductListing) -> bool:
    min_confidence = float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))
    confidence = listing.extraction_confidence
    if confidence is None:
        return True
    return confidence >= min_confidence


SEARCH_STOP_WORDS: Set[str] = {
    "a", "an", "and", "are", "at", "best", "buy", "for", "from", "in",
    "is", "it", "latest", "new", "of", "on", "or", "price", "the", "to", "with",
}


SEARCH_SYNONYMS: Dict[str, Set[str]] = {
    "cover": {"case", "backcover", "back", "protector"},
    "case": {"cover", "backcover"},
    "phone": {"mobile", "smartphone"},
    "mobile": {"phone", "smartphone"},
    "earbuds": {"earphones", "buds"},
    "charger": {"adapter", "charging"},
}


SEARCH_INTENT_RULES: Dict[str, Dict[str, object]] = {
    "mobile_accessories": {
        "query_terms": {
            "cover", "case", "tempered", "protector", "charger", "cable", "earbuds",
            "earphones", "airpods", "powerbank", "magsafe", "backcover", "mobile stand",
        },
        "product_terms": {
            "cover", "case", "tempered", "protector", "charger", "cable", "earbuds",
            "earphones", "airpods", "powerbank", "magsafe", "mobile stand", "holder", "strap",
        },
        "category_terms": {"accessories", "mobile accessories", "phone accessories"},
        "strict": True,
    },
    "laptop_accessories": {
        "query_terms": {
            "laptop bag", "sleeve", "mouse", "keyboard", "cooling", "dock", "docking",
            "usb hub", "webcam", "external ssd", "external hard disk", "laptop charger",
        },
        "product_terms": {
            "laptop bag", "sleeve", "mouse", "keyboard", "cooling", "dock", "docking",
            "usb hub", "webcam", "external ssd", "external hard disk", "laptop charger",
        },
        "category_terms": {"accessories", "laptop accessories", "computer accessories"},
        "strict": True,
    },
    "mobiles": {
        "query_terms": {
            "iphone", "samsung", "oneplus", "realme", "vivo", "oppo", "xiaomi",
            "redmi", "pixel", "mobile", "phone", "smartphone",
        },
        "product_terms": {
            "iphone", "samsung", "oneplus", "realme", "vivo", "oppo", "xiaomi",
            "redmi", "pixel", "mobile", "phone", "smartphone",
        },
        "category_terms": {"electronics", "mobiles", "smartphones", "phones"},
        "strict": False,
    },
    "tablets": {
        "query_terms": {"tablet", "ipad", "tab"},
        "product_terms": {"tablet", "ipad", "tab"},
        "category_terms": {"electronics", "tablets"},
        "strict": False,
    },
    "laptops": {
        "query_terms": {"laptop", "notebook", "macbook", "chromebook", "ultrabook"},
        "product_terms": {"laptop", "notebook", "macbook", "chromebook", "ultrabook"},
        "category_terms": {"electronics", "laptops", "computers"},
        "strict": False,
    },
    "fashion": {
        "query_terms": {"fashion", "shirt", "tshirt", "jeans", "dress", "saree", "kurta", "shoes"},
        "product_terms": {"fashion", "shirt", "tshirt", "jeans", "dress", "saree", "kurta", "shoes"},
        "category_terms": {"fashion", "clothing", "apparel"},
        "strict": False,
    },
    "beauty": {
        "query_terms": {"beauty", "skincare", "makeup", "lipstick", "cleanser", "serum", "sunscreen"},
        "product_terms": {"beauty", "skincare", "makeup", "lipstick", "cleanser", "serum", "sunscreen"},
        "category_terms": {"beauty", "cosmetics", "personal care"},
        "strict": False,
    },
    "home_kitchen": {
        "query_terms": {"home", "kitchen", "cookware", "mixer", "furniture", "vacuum"},
        "product_terms": {"home", "kitchen", "cookware", "mixer", "furniture", "vacuum"},
        "category_terms": {"home", "kitchen", "home & kitchen"},
        "strict": False,
    },
    "books": {
        "query_terms": {"book", "novel", "author", "paperback", "hardcover"},
        "product_terms": {"book", "novel", "author", "paperback", "hardcover"},
        "category_terms": {"books"},
        "strict": False,
    },
}


def _safe_usage_stats(user: User) -> dict:
    """Return a mutable usage stats dict that will be reassigned to trigger JSONB update."""
    return dict(user.usage_stats or {})


def _build_search_transaction(user_id, search_type: str, meta: dict | None = None) -> Transaction:
    """Create a lightweight transaction row for search analytics."""
    return Transaction(
        user_id=user_id,
        type=search_type,
        status="success",
        amount=0,
        currency="INR",
        meta_data=meta or {},
    )


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def _tokenize_query(query: str) -> List[str]:
    tokens = [token for token in _normalize_text(query).split(" ") if token]
    unique_tokens: List[str] = []
    seen: Set[str] = set()

    for token in tokens:
        if token in SEARCH_STOP_WORDS:
            continue
        if len(token) < 2:
            continue
        if token in seen:
            continue
        unique_tokens.append(token)
        seen.add(token)

    return unique_tokens


def _term_present(term: str, normalized_text: str) -> bool:
    term_text = _normalize_text(term)
    if not term_text:
        return False
    return term_text in normalized_text


def _expand_query_tokens(tokens: List[str]) -> List[str]:
    expanded: List[str] = []
    seen: Set[str] = set()

    for token in tokens:
        if token not in seen:
            expanded.append(token)
            seen.add(token)

        for synonym in SEARCH_SYNONYMS.get(token, set()):
            synonym_norm = _normalize_text(synonym)
            if not synonym_norm or synonym_norm in seen:
                continue
            expanded.append(synonym_norm)
            seen.add(synonym_norm)

    return expanded


def _build_product_blob(product: Product) -> Dict[str, str]:
    ai_metadata = product.ai_metadata or {}
    tags = ai_metadata.get("tags", []) if isinstance(ai_metadata, dict) else []

    title = _normalize_text(product.title)
    category = _normalize_text(f"{product.category or ''} {product.subcategory or ''}")
    brand = _normalize_text(product.brand)
    tags_text = _normalize_text(" ".join(tags) if isinstance(tags, list) else "")
    essence = _normalize_text(ai_metadata.get("essence") if isinstance(ai_metadata, dict) else "")
    all_text = _normalize_text(" ".join([title, category, brand, tags_text, essence]))

    return {
        "title": title,
        "category": category,
        "brand": brand,
        "tags": tags_text,
        "essence": essence,
        "all": all_text,
    }


def _detect_intent(tokens: List[str], expanded_tokens: List[str]) -> Optional[str]:
    query_blob = _normalize_text(" ".join(tokens or expanded_tokens))
    if not query_blob:
        return None

    best_intent: Optional[str] = None
    best_score = 0

    for intent, rule in SEARCH_INTENT_RULES.items():
        query_terms = rule.get("query_terms", set())
        score = 0

        for term in query_terms:
            if _term_present(str(term), query_blob):
                score += 3

        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent if best_score >= 3 else None


def _product_matches_intent(blob: Dict[str, str], intent: Optional[str]) -> bool:
    if not intent:
        return True

    rule = SEARCH_INTENT_RULES.get(intent)
    if not rule:
        return True

    category_terms = rule.get("category_terms", set())
    product_terms = rule.get("product_terms", set())

    category_match = any(_term_present(str(term), blob["category"]) for term in category_terms)
    term_match = any(_term_present(str(term), blob["all"]) for term in product_terms)

    return category_match or term_match


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _calculate_relevance_score(
    product: Product,
    query_tokens: List[str],
    expanded_tokens: List[str],
    intent: Optional[str]
) -> Tuple[float, int, bool]:
    blob = _build_product_blob(product)
    query_phrase = _normalize_text(" ".join(query_tokens))

    score = 0.0
    matched_primary_tokens = 0
    matched_expanded_tokens = 0

    if query_phrase and _term_present(query_phrase, blob["title"]):
        score += 45

    for token in query_tokens:
        if _term_present(token, blob["title"]):
            score += 20
            matched_primary_tokens += 1
            continue
        if _term_present(token, blob["category"]):
            score += 12
            matched_primary_tokens += 1
            continue
        if _term_present(token, blob["tags"]) or _term_present(token, blob["essence"]):
            score += 10
            matched_primary_tokens += 1
            continue
        if _term_present(token, blob["brand"]):
            score += 8
            matched_primary_tokens += 1

    for token in expanded_tokens:
        if token in query_tokens:
            continue
        if _term_present(token, blob["title"]):
            score += 8
            matched_expanded_tokens += 1
        elif _term_present(token, blob["category"]):
            score += 5
            matched_expanded_tokens += 1

    if matched_primary_tokens == 0 and matched_expanded_tokens > 0:
        matched_primary_tokens = 1

    intent_match = _product_matches_intent(blob, intent)
    if intent:
        score += 35 if intent_match else -40

    stats = product.stats or {}
    score += min(12, (_safe_int(stats.get("searches")) // 15) + (_safe_int(stats.get("views")) // 50))

    return score, matched_primary_tokens, intent_match


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

async def search_database(
    query: str,
    db: AsyncSession,
    platforms: Optional[List[Platform]] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: str = "relevance",
    page: int = 1,
    limit: int = 20
) -> Tuple[List[Product], int]:
    """Search products with intent-aware relevance scoring."""
    query_tokens = _tokenize_query(query)
    if not query_tokens:
        fallback = _normalize_text(query)
        query_tokens = [fallback] if fallback else []

    expanded_tokens = _expand_query_tokens(query_tokens)
    detected_intent = _detect_intent(query_tokens, expanded_tokens)

    search_terms = expanded_tokens[:12] or query_tokens[:8]
    search_conditions = []
    for term in search_terms:
        like = f"%{term}%"
        search_conditions.extend([
            Product.title.ilike(like),
            Product.brand.ilike(like),
            Product.category.ilike(like),
            Product.subcategory.ilike(like),
        ])

    if not search_conditions:
        raw_like = f"%{_normalize_text(query)}%"
        search_conditions = [Product.title.ilike(raw_like)]

    # Fetch a broader candidate set, then rank in memory.
    candidate_limit = max(limit * max(page, 1) * 6, 120)
    query_stmt = (
        select(Product)
        .where(or_(*search_conditions))
        .order_by(Product.created_at.desc())
        .limit(candidate_limit)
    )

    result = await db.execute(query_stmt)
    candidates = list(result.scalars().all())

    scored_candidates: List[Tuple[Product, float]] = []
    for product in candidates:
        score, matched_token_count, intent_match = _calculate_relevance_score(
            product=product,
            query_tokens=query_tokens,
            expanded_tokens=expanded_tokens,
            intent=detected_intent,
        )

        if matched_token_count == 0:
            continue

        intent_rule = SEARCH_INTENT_RULES.get(detected_intent or "") if detected_intent else None
        strict_intent = bool(intent_rule and intent_rule.get("strict", False))
        if strict_intent and not intent_match:
            continue

        scored_candidates.append((product, score))

    # Graceful fallback for strict intents if nothing matched.
    if not scored_candidates and detected_intent:
        for product in candidates:
            score, matched_token_count, _ = _calculate_relevance_score(
                product=product,
                query_tokens=query_tokens,
                expanded_tokens=expanded_tokens,
                intent=None,
            )
            if matched_token_count > 0:
                scored_candidates.append((product, score))

    scored_candidates.sort(key=lambda item: item[1], reverse=True)
    ranked_products = [product for product, _ in scored_candidates]

    total_candidates = len(ranked_products)
    offset = (page - 1) * limit
    paged_products = ranked_products[offset:offset + limit]

    logger.info(
        f"Search intent resolved | Query: {query} | Intent: {detected_intent or 'none'} | "
        f"Sort: {sort_by} | Candidates: {len(candidates)} | Ranked: {total_candidates} | Page: {page}"
    )

    return paged_products, total_candidates


async def get_product_listings(
    product_id,
    db: AsyncSession,
    platforms: Optional[List[Platform]] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> List[ProductListing]:
    """Get all listings for a product (✅ FIXED: Eager load platform relationship)"""
    query = select(ProductListing).where(
        ProductListing.product_id == product_id,
        ProductListing.in_stock == True
    ).options(selectinload(ProductListing.platform))  # ✅ Eager load platform

    if min_price is not None:
        query = query.where(ProductListing.current_price >= float(min_price))
    if max_price is not None:
        query = query.where(ProductListing.current_price <= float(max_price))
    
    query = query.order_by(ProductListing.current_price.asc())
    
    result = await db.execute(query)
    listings = list(result.scalars().all())

    requested_platforms = {p.value for p in platforms} if platforms else None
    enabled_platforms = _get_enabled_platforms()

    filtered_listings = []
    for listing in listings:
        platform_name = (
            listing.platform.name.lower()
            if hasattr(listing, "platform") and listing.platform
            else None
        )
        if platform_name and platform_name not in enabled_platforms:
            continue
        if requested_platforms and platform_name and platform_name not in requested_platforms:
            continue
        if not _listing_meets_quality(listing):
            continue
        filtered_listings.append(listing)

    return filtered_listings


def format_listing_response(listing: ProductListing, product: Product) -> ProductListingResponse:
    """Format ProductListing for API response (✅ FIXED: Proper field mapping)"""
    # Get platform name from relationship if loaded
    platform_name = "amazon"  # Default fallback
    if hasattr(listing, 'platform') and listing.platform:
        platform_name = listing.platform.name.lower()
    
    # Calculate discount percentage
    discount_percentage = None
    if listing.original_price and listing.current_price:
        discount_percentage = int(
            ((listing.original_price - listing.current_price) / listing.original_price) * 100
        )
    
    return ProductListingResponse(
        id=str(listing.id),
        platform=Platform[platform_name.upper()] if platform_name else Platform.AMAZON,
        platform_product_id=listing.external_id or str(listing.id),
        url=listing.affiliate_url or listing.product_url,
        title=product.title,  # ✅ Title comes from Product, not Listing
        current_price=Decimal(str(listing.current_price)),
        original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
        discount_percentage=discount_percentage,
        rating=Decimal(str(listing.rating)) if listing.rating else None,
        review_count=listing.review_count,
        image_url=product.image_url,  # ✅ Image comes from Product, not Listing
        in_stock=listing.in_stock,
        last_scraped_at=listing.last_scraped or datetime.utcnow(),
        extraction_confidence=listing.extraction_confidence,
        extraction_method=listing.extraction_method,
        data_source=listing.data_source,
        seller_name=listing.seller_name,
        seller_rating=Decimal(str(listing.seller_rating)) if listing.seller_rating is not None else None,
    )


def format_product_response(
    product: Product,
    listings: List[ProductListing]
) -> ProductResponse:
    """Format product with listings for API response"""
    ai_metadata = product.ai_metadata or {}
    
    # Calculate best price from listings
    best_price = Decimal('0')
    best_platform = Platform.AMAZON
    if listings:
        best_listing = min(listings, key=lambda x: x.current_price)
        best_price = Decimal(str(best_listing.current_price))
        if hasattr(best_listing, 'platform') and best_listing.platform:
            best_platform = Platform[best_listing.platform.name.upper()]
    
    # Calculate avg price
    avg_price = None
    if listings:
        avg_price = Decimal(str(sum(l.current_price for l in listings) / len(listings)))
    
    # Calculate price trend
    price_trend = "stable"
    if avg_price and best_price:
        if best_price < avg_price * Decimal('0.9'):
            price_trend = "down"
        elif best_price > avg_price * Decimal('1.1'):
            price_trend = "up"
    
    return ProductResponse(
        id=str(product.id),
        fingerprint=product.fingerprint,
        # ✅ NEW: Variant fingerprinting fields
        variant_fingerprint=product.variant_fingerprint,
        base_fingerprint=product.base_fingerprint,
        variant_type=product.variant_type,
        storage_gb=product.storage_gb,
        color=product.color,
        condition=product.condition,
        # Product base info
        title=product.title,
        brand=product.brand,
        category=product.category,
        subcategory=product.subcategory,
        image_url=product.image_url,
        specifications=product.specifications or {},
        # Confidence and provenance
        brand_confidence=product.brand_confidence,
        brand_source=product.brand_source,
        color_confidence=product.color_confidence,
        color_source=product.color_source,
        specs_confidence=product.specs_confidence,
        specs_source=product.specs_source,
        last_enriched_at=product.last_enriched_at,
        enrichment_version=product.enrichment_version,
        # Pricing
        best_price=best_price,
        best_platform=best_platform,
        avg_price=avg_price,
        price_trend=price_trend,
        # AI metadata
        ai_generated_essence=ai_metadata.get("essence", product.title),
        ai_extracted_specs=product.specifications or {},
        ai_tags=ai_metadata.get("tags", []),
        ai_metadata=ai_metadata,
        stats=product.stats or {},
        created_at=product.created_at,
        updated_at=product.updated_at,
        listings=[
            format_listing_response(listing, product)
            for listing in listings
        ]
    )


# =============================================================================
# URL SEARCH HELPER FUNCTIONS (USES CENTRALIZED SERVICES)
# =============================================================================

async def scrape_and_match(
    url: str,
    url_analysis: URLAnalysis,
    db: AsyncSession
) -> List[ProductData]:
    """
    Core function: Scrape → AI Enrich → Save → Find Alternatives
    
    ✅ REFACTORED: Uses centralized enrichment_service and product_service
    """
    source_product = None
    
    # =========================================================================
    # STEP 1: Scrape source product
    # =========================================================================
    if url_analysis.support_level == PlatformSupport.FULL:
        try:
            handler = await get_platform_handler(url_analysis.platform_name, db)
            source_product = await handler.get_product(url)
            
            if source_product:
                logger.info(
                    f"Scraped from {url_analysis.platform_name} "
                    f"(source: {source_product.data_source.value})"
                )
        except Exception as e:
            logger.error(f"Platform scraper failed: {e}")
    
    if not source_product and url_analysis.support_level in [PlatformSupport.FULL, PlatformSupport.PARTIAL]:
        try:
            logger.info(f"Using generic AI scraper for {url_analysis.platform_name}")
            generic_scraper = GenericAIScraper(url_analysis.platform_name)
            source_product = await generic_scraper.get_product(url)
        except Exception as e:
            logger.error(f"Generic scraper failed: {e}")
    
    if not source_product:
        logger.error(f"Failed to scrape product from {url}")
        return []
    
    # Add affiliate URL
    source_product.product_url = url_detector.get_affiliate_url(source_product.product_url)
    
    # =========================================================================
    # STEP 2: AI ENRICHMENT (✅ USING CENTRALIZED SERVICE)
    # =========================================================================
    source_product = await enrichment_service.enrich_product(source_product)
    
    # =========================================================================
    # STEP 3: SAVE TO DATABASE (✅ USING CENTRALIZED SERVICE)
    # =========================================================================
    try:
        saved_source_product = await product_service.save_product(
            product_data=source_product,
            db=db,
            is_user_search=True  # User-initiated search
        )
        if saved_source_product:
            source_product.raw_data = source_product.raw_data or {}
            source_product.raw_data["db_product_id"] = str(saved_source_product.id)
    except Exception as e:
        logger.error(f"Database save failed (continuing): {e}")
    
    # =========================================================================
    # STEP 4: FIND ALTERNATIVES
    # =========================================================================
    try:
        alternatives = await cross_platform_matcher.find_alternatives(
            source_product,
            db,
            search_if_not_found=True,
            skip_platforms=[url_analysis.platform_name]
        )
    except Exception as e:
        logger.error(f"Cross-platform matching failed: {e}")
        alternatives = [source_product]
    
    # =========================================================================
    # STEP 5: SAVE ALTERNATIVES (✅ USING CENTRALIZED SERVICES)
    # =========================================================================
    for alt in alternatives:
        if alt.platform_name.lower() != source_product.platform_name.lower():
            try:
                # Enrich alternatives too
                if not alt.ai_processed:
                    alt = await enrichment_service.enrich_product(alt)
                
                await product_service.save_product(
                    product_data=alt,
                    db=db,
                    is_user_search=True
                )
            except Exception as e:
                logger.debug(f"Failed to save alternative: {e}")
    
    return alternatives


async def format_url_search_response(
    source_url: str,
    source_platform: str,
    product: Product,
    listings: List[ProductListing],
    db: AsyncSession
) -> dict:
    """Format database product for URL search response"""
    # Find source listing
    source_listing = None
    other_listings = []
    
    for listing in listings:
        # Get platform name
        platform_result = await db.execute(
            select(PlatformModel).where(PlatformModel.id == listing.platform_id)
        )
        platform = platform_result.scalar_one_or_none()
        listing._platform_name = platform.name if platform else "unknown"
        
        if source_platform.lower() in listing._platform_name.lower():
            source_listing = listing
        else:
            other_listings.append(listing)
    
    if not source_listing and listings:
        source_listing = listings[0]
        other_listings = listings[1:]
    
    # Calculate best price
    all_listings = [source_listing] + other_listings if source_listing else other_listings
    best_listing = min(all_listings, key=lambda x: x.current_price) if all_listings else None
    
    return {
        "success": True,
        "product_id": str(product.id),
        "source": {
            "product_id": str(product.id),
            "platform": source_platform,
            "title": product.title,
            "price": float(source_listing.current_price) if source_listing else 0,
            "original_price": float(source_listing.original_price) if source_listing and source_listing.original_price else None,
            "rating": source_listing.rating if source_listing else None,
            "review_count": source_listing.review_count if source_listing else None,
            "image_url": product.image_url,
            "url": url_detector.get_affiliate_url(source_listing.product_url) if source_listing else source_url,
            "in_stock": source_listing.in_stock if source_listing else True,
            "brand": product.brand,
            "category": product.category,
            "subcategory": product.subcategory,
        },
        "alternatives": [
            {
                "platform": getattr(listing, '_platform_name', 'unknown'),
                "title": product.title,
                "price": float(listing.current_price),
                "original_price": float(listing.original_price) if listing.original_price else None,
                "rating": listing.rating,
                "review_count": listing.review_count,
                "image_url": product.image_url,
                "url": url_detector.get_affiliate_url(listing.product_url),
                "in_stock": listing.in_stock,
                "savings": float(source_listing.current_price - listing.current_price) if source_listing else 0,
                "savings_percent": round(
                    (float(source_listing.current_price - listing.current_price) /
                     float(source_listing.current_price)) * 100, 1
                ) if source_listing and listing.current_price < source_listing.current_price else 0
            }
            for listing in sorted(other_listings, key=lambda x: x.current_price)
        ],
        "best_deal": {
            "platform": getattr(best_listing, '_platform_name', source_platform) if best_listing else source_platform,
            "price": float(best_listing.current_price) if best_listing else 0,
            "savings": float(source_listing.current_price - best_listing.current_price) if source_listing and best_listing else 0,
            "is_source": getattr(best_listing, '_platform_name', '') == source_platform if best_listing else True
        },
        "total_options": len(all_listings),
        "fingerprint": product.fingerprint
    }


async def resolve_product_id_from_source(
    source_product: ProductData,
    db: AsyncSession
) -> Optional[str]:
    """Resolve saved Product ID from scraped ProductData fingerprints."""
    variant_fingerprint = None
    try:
        variant_fingerprint = source_product.get_variant_fingerprint()
    except Exception:
        variant_fingerprint = None

    if variant_fingerprint:
        variant_result = await db.execute(
            select(Product.id)
            .where(Product.variant_fingerprint == variant_fingerprint)
            .order_by(Product.created_at.desc())
            .limit(1)
        )
        variant_match = variant_result.scalar_one_or_none()
        if variant_match:
            return str(variant_match)

    fingerprint = getattr(source_product, "fingerprint", None)
    if fingerprint:
        fingerprint_result = await db.execute(
            select(Product.id)
            .where(Product.fingerprint == fingerprint)
            .order_by(Product.created_at.desc())
            .limit(1)
        )
        fingerprint_match = fingerprint_result.scalar_one_or_none()
        if fingerprint_match:
            return str(fingerprint_match)

    return None


# =============================================================================
# API ROUTES
# =============================================================================

@router.post("/search", response_model=SearchResponse)
async def search_products(
    request: SearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(check_rate_limit)
):
    """
    Search products across platforms with 3-tier caching
    """
    start_time = time.time()
    
    filters = {
        'platforms': request.platforms,
        'min_price': request.min_price,
        'max_price': request.max_price,
    }
    cache_key = calculate_search_cache_key(
        query=request.query,
        filters=filters,
        page=request.page,
        sort_by=request.sort_by or "relevance",
    )
    
    # TIER 1: Check Redis cache
    cached_results = await redis.get_json(cache_key)
    
    if cached_results:
        if isinstance(cached_results, dict):
            cached_products = cached_results.get("products", [])
            cached_total = int(cached_results.get("total_results", len(cached_products)))
        elif isinstance(cached_results, list):
            cached_products = cached_results
            cached_total = len(cached_products)
        else:
            cached_products = []
            cached_total = 0

        search_time_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"Cache HIT: {request.query} | "
            f"User: {user.id} | "
            f"Time: {search_time_ms}ms"
        )
        
        return SearchResponse(
            query=request.query,
            total_results=cached_total,
            page=request.page,
            products=cached_products,
            cache_hit=True,
            search_time_ms=search_time_ms
        )
    
    # TIER 2: Search database
    products, total_candidates = await search_database(
        query=request.query,
        db=db,
        platforms=request.platforms,
        min_price=request.min_price,
        max_price=request.max_price,
        sort_by=request.sort_by or "relevance",
        page=request.page
    )
    
    results = []
    for product in products:
        listings = await get_product_listings(
            product.id,
            db,
            platforms=request.platforms,
            min_price=request.min_price,
            max_price=request.max_price,
        )
        
        if listings:
            results.append(format_product_response(product, listings))

    if request.sort_by == "price_low":
        results.sort(key=lambda p: float(p.best_price or 0))
    elif request.sort_by == "price_high":
        results.sort(key=lambda p: float(p.best_price or 0), reverse=True)
    elif request.sort_by == "rating":
        results.sort(
            key=lambda p: max((float(listing.rating or 0) for listing in p.listings), default=0.0),
            reverse=True,
        )

    total_results = max(total_candidates, len(results))
    
    if results:
        await redis.set_json(
            cache_key,
            {
                "products": [r.model_dump(mode='json') for r in results],
                "total_results": total_results,
                "page": request.page,
            },
            ttl=3600
        )
    
    search_time_ms = int((time.time() - start_time) * 1000)
    
    # Update user stats and persist searchable audit event.
    usage_stats = _safe_usage_stats(user)
    usage_stats['daily_searches'] = int(usage_stats.get('daily_searches', 0) or 0) + 1
    usage_stats['total_searches'] = int(usage_stats.get('total_searches', 0) or 0) + 1
    usage_stats['last_search_date'] = datetime.utcnow().isoformat()
    usage_stats['last_search_query'] = request.query
    user.usage_stats = usage_stats

    db.add(_build_search_transaction(
        user.id,
        search_type="search",
        meta={"query": request.query, "origin": "text_search"}
    ))
    await db.commit()
    
    logger.info(
        f"Database search: {request.query} | "
        f"User: {user.id} | "
        f"Results: {len(results)} | "
        f"Time: {search_time_ms}ms"
    )
    
    if not results:
        logger.warning(f"No results found for query: {request.query}")
    
    return SearchResponse(
        query=request.query,
        total_results=total_results,
        page=request.page,
        products=results,
        cache_hit=False,
        search_time_ms=search_time_ms
    )


@router.post("/by-url")
async def search_by_url(
    request: SearchByURLRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(check_rate_limit)
):
    """
    Search by product URL - Find same product across ALL platforms
    
    ✅ REFACTORED: Uses centralized services for AI enrichment and DB save
    """
    start_time = time.time()
    url = request.url.strip()
    
    # Step 1: Analyze URL
    url_analysis = url_detector.analyze(url)
    
    logger.info(
        f"URL Search: {url[:50]}... | "
        f"Platform: {url_analysis.platform_name} | "
        f"Support: {url_analysis.support_level.value} | "
        f"User: {user.id}"
    )
    
    # Step 2: Check if platform is supported
    if url_analysis.support_level == PlatformSupport.UNSUPPORTED:
        if not url_analysis.domain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid URL format"
            )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unsupported_platform",
                "message": f"Platform '{url_analysis.platform_name}' is not supported yet",
                "detected_domain": url_analysis.domain,
                "supported_platforms": url_detector.get_supported_platforms()
            }
        )

    if url_analysis.platform_name == "croma" and not getattr(settings, "CROMA_ENABLED", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "platform_paused",
                "message": "Croma is temporarily paused for quality rollout"
            }
        )
    
    # Step 3: Check database cache first
    cache_key = f"url_search:{hashlib.md5(url.encode()).hexdigest()}"
    cached_result = await redis.get_json(cache_key)

    if cached_result and isinstance(cached_result, dict) and isinstance(cached_result.get("source"), str):
        logger.warning(
            f"Ignoring legacy malformed URL cache payload for: {url[:50]}"
        )
        cached_result = None

    if cached_result:
        search_time_ms = int((time.time() - start_time) * 1000)
        logger.info(f"URL search cache HIT: {url[:50]} | Time: {search_time_ms}ms")
        cached_result["cache_hit"] = True
        cached_result["search_time_ms"] = search_time_ms
        return cached_result
    
    # Step 4: Check if product exists in database
    if url_analysis.product_id:
        platform_result = await db.execute(
            select(PlatformModel).where(PlatformModel.name == url_analysis.platform_name)
        )
        platform = platform_result.scalar_one_or_none()
        
        if platform:
            listing_result = await db.execute(
                select(ProductListing)
                .where(
                    ProductListing.external_id == url_analysis.product_id,
                    ProductListing.platform_id == platform.id
                )
                .options(selectinload(ProductListing.product))
            )
            existing_listing = listing_result.scalar_one_or_none()
            
            if existing_listing and existing_listing.product:
                # Product exists - get all listings
                product = existing_listing.product
                all_listings = await get_product_listings(product.id, db)
                
                # Format response
                response = await format_url_search_response(
                    source_url=url,
                    source_platform=url_analysis.platform_name,
                    product=product,
                    listings=all_listings,
                    db=db
                )
                
                # Cache result
                await redis.set_json(cache_key, response, ttl=1800)
                
                search_time_ms = int((time.time() - start_time) * 1000)
                response["cache_hit"] = False
                response["response_origin"] = "database"
                response["search_time_ms"] = search_time_ms
                
                logger.info(
                    f"URL search DB HIT: {url[:50]} | "
                    f"Time: {search_time_ms}ms"
                )
                
                return response
    
    # Step 5: Need to scrape
    search_queue = get_search_queue(redis)
    
    try:
        logger.info(f"Starting URL scrape for: {url[:60]}...")
        alternatives = await search_queue.search_url(
            url=url,
            user=user,
            scrape_func=lambda u: scrape_and_match(u, url_analysis, db)
        )
        logger.info(f"Scrape completed. Found {len(alternatives) if alternatives else 0} alternatives")
    except Exception as e:
        logger.error(f"URL search scraping failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "scraping_failed",
                "message": f"Failed to fetch product details: {str(e)}",
                "platform": url_analysis.platform_name,
                "suggestion": "URL might be invalid or product might not exist on this platform"
            }
        )
    
    if not alternatives:
        logger.warning(f"No alternatives found for URL: {url[:60]}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "product_not_found",
                "message": "Could not extract product information from URL. The product might not exist or the URL might be invalid.",
                "url": url,
                "platform": url_analysis.platform_name,
                "suggestion": "Try with a direct product URL (e.g., amazon.in/dp/B0XXXXXX)"
            }
        )
    
    # Step 6: Format response
    source_product = next(
        (p for p in alternatives if url_analysis.platform_name in p.platform_name.lower()),
        alternatives[0]
    )
    
    enabled_platforms = _get_enabled_platforms()
    min_confidence = float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))

    filtered_alternatives = [
        p for p in alternatives
        if p.platform_name.lower() in enabled_platforms
        and (p.extraction_confidence is None or p.extraction_confidence >= min_confidence)
    ]
    if filtered_alternatives:
        alternatives = filtered_alternatives
        source_product = next(
            (p for p in alternatives if url_analysis.platform_name in p.platform_name.lower()),
            alternatives[0]
        )

    other_alternatives = [
        p for p in alternatives
        if p.platform_name != source_product.platform_name
    ]

    source_product_id = None
    if isinstance(getattr(source_product, "raw_data", None), dict):
        source_product_id = source_product.raw_data.get("db_product_id")

    if not source_product_id:
        source_product_id = await resolve_product_id_from_source(source_product, db)
    
    # Calculate savings
    savings_info = cross_platform_matcher.calculate_savings(alternatives)
    
    response = {
        "success": True,
        "product_id": source_product_id,
        "source": {
            "product_id": source_product_id,
            "platform": source_product.platform_name,
            "title": source_product.title,
            "price": float(source_product.current_price),
            "original_price": float(source_product.original_price) if source_product.original_price else None,
            "discount_percent": source_product.discount_percent,
            "rating": source_product.rating,
            "review_count": source_product.review_count,
            "image_url": source_product.image_url,
            "url": url_detector.get_affiliate_url(source_product.product_url),
            "in_stock": source_product.in_stock,
            "brand": source_product.brand,
            "category": source_product.category,
            "subcategory": source_product.subcategory,
            "ai_essence": source_product.ai_essence,
            "ai_tags": source_product.ai_tags,
            "ai_quality_score": source_product.ai_quality_score
        },
        "alternatives": [
            {
                "platform": alt.platform_name,
                "title": alt.title,
                "price": float(alt.current_price),
                "original_price": float(alt.original_price) if alt.original_price else None,
                "discount_percent": alt.discount_percent,
                "rating": alt.rating,
                "review_count": alt.review_count,
                "image_url": alt.image_url,
                "url": url_detector.get_affiliate_url(alt.product_url),
                "in_stock": alt.in_stock,
                "savings": float(source_product.current_price - alt.current_price),
                "savings_percent": round(
                    (float(source_product.current_price - alt.current_price) / 
                     float(source_product.current_price)) * 100, 1
                ) if alt.current_price < source_product.current_price else 0
            }
            for alt in sorted(other_alternatives, key=lambda x: x.current_price)
        ],
        "best_deal": {
            "platform": savings_info["best_platform"],
            "price": savings_info["best_price"],
            "savings": savings_info["max_savings"],
            "savings_percent": savings_info.get("savings_percent", 0),
            "is_source": savings_info["best_platform"] == source_product.platform_name
        },
        "total_options": len(alternatives),
        "fingerprint": source_product.fingerprint,
        "cache_hit": False,
        "response_origin": "live_scrape"
    }
    
    # Update user stats and persist searchable audit event.
    usage_stats = _safe_usage_stats(user)
    usage_stats['daily_searches'] = int(usage_stats.get('daily_searches', 0) or 0) + 1
    usage_stats['total_searches'] = int(usage_stats.get('total_searches', 0) or 0) + 1
    usage_stats['last_search_date'] = datetime.utcnow().isoformat()
    usage_stats['last_url_search'] = url
    user.usage_stats = usage_stats

    db.add(_build_search_transaction(
        user.id,
        search_type="ai_search",
        meta={"url": url, "origin": "url_search"}
    ))
    await db.commit()
    
    # Cache result
    await redis.set_json(cache_key, response, ttl=1800)
    
    search_time_ms = int((time.time() - start_time) * 1000)
    response["search_time_ms"] = search_time_ms
    
    logger.info(
        f"URL search COMPLETED: {url[:50]} | "
        f"Alternatives: {len(other_alternatives)} | "
        f"Best price: {savings_info['best_platform']} @ ₹{savings_info['best_price']} | "
        f"Time: {search_time_ms}ms"
    )
    
    return response


# =============================================================================
# TRENDING ENDPOINT
# =============================================================================

@router.get("/trending", response_model=List[TrendingProductResponse])
async def get_trending_products(
    limit: int = 50,
    user: User = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    """
    Get trending products sorted by engagement (views + searches)
    
    Sorts by stats['views'] + stats['searches'] + stats['seed_score']
    
    ✅ FIXED: Simplified query to avoid SQLAlchemy aggregation hydration issues
    """
    cache_key = "trending:products:top50"
    
    # Check Redis cache first
    cached = await redis.get_json(cache_key)
    
    if cached:
        logger.info(f"Trending cache HIT | User: {user.id}")
        return cached
    
    try:
        # ✅ STEP 1: Get ALL products with at least one in-stock listing
        result = await db.execute(
            select(Product)
            .join(ProductListing, Product.id == ProductListing.product_id)
            .where(
                ProductListing.in_stock == True,
                (ProductListing.extraction_confidence.is_(None) |
                 (ProductListing.extraction_confidence >= float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))))
            )
            .distinct(Product.id)  # Avoid duplicates from multiple listings
            .order_by(Product.id)
        )
        
        products = result.scalars().all()
        logger.info(f"Fetched {len(products)} trending products from DB")
        
        # ✅ STEP 2: Sort by engagement score in memory
        def get_engagement_score(product):
            stats = product.stats or {}
            return (
                int(stats.get("views", 0)) +
                int(stats.get("searches", 0)) +
                int(stats.get("clicks", 0)) +
                int(stats.get("seed_score", 0))
            )
        
        # Sort by engagement (descending) and take top N
        sorted_products = sorted(
            products,
            key=get_engagement_score,
            reverse=True
        )[:limit]
        
    except Exception as e:
        logger.error(f"Error fetching trending products: {e}", exc_info=True)
        sorted_products = []
    
    # ✅ STEP 3: Build response
    trending = []
    rank = 1
    
    for product in sorted_products:
        try:
            # Get best price for this product
            listing_result = await db.execute(
                select(ProductListing)
                .options(selectinload(ProductListing.platform))
                .where(
                    ProductListing.product_id == product.id,
                    ProductListing.in_stock == True,
                    (ProductListing.extraction_confidence.is_(None) |
                     (ProductListing.extraction_confidence >= float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))))
                )
                .order_by(ProductListing.current_price.asc())
                .limit(1)
            )
            best_listing = listing_result.scalar_one_or_none()

            if best_listing and best_listing.platform and best_listing.platform.name.lower() == "croma" and not getattr(settings, "CROMA_ENABLED", False):
                continue
            
            best_price = float(best_listing.current_price) if best_listing else 0
            best_discount = int(best_listing.discount_percent or 0) if best_listing else None
            best_platform = best_listing.platform.name.lower() if best_listing and best_listing.platform else "amazon"
            
            # Get AI metadata
            ai_metadata = product.ai_metadata or {}
            stats = product.stats or {}
            
            # Calculate engagement score
            engagement_score = (
                int(stats.get("views", 0)) +
                int(stats.get("searches", 0)) +
                int(stats.get("clicks", 0))
            )
            
            # Build response object
            trending_item = TrendingProductResponse(
                product_id=str(product.id),  # ✅ FIX: Convert UUID to string
                title=ai_metadata.get("essence", product.title),
                # ✅ NEW: Variant fingerprinting fields
                variant_fingerprint=product.variant_fingerprint,
                base_fingerprint=product.base_fingerprint,
                variant_type=product.variant_type,
                # Pricing
                best_price=best_price,
                best_platform=best_platform,
                discount_percentage=best_discount,
                image_url=product.image_url,
                search_count=engagement_score,
                rank=rank
            )
            
            trending.append(trending_item)
            rank += 1
            
        except Exception as e:
            logger.error(f"Error processing product {product.id}: {e}", exc_info=True)
            continue
    
    # ✅ STEP 4: Cache results for 1 hour
    if trending:
        try:
            await redis.set_json(
                cache_key,
                [t.model_dump(mode='json') for t in trending],
                ttl=3600
            )
            logger.info(f"Cached {len(trending)} trending products")
        except Exception as e:
            logger.warning(f"Failed to cache trending products: {e}")
    
    logger.info(
        f"Trending products fetched | "
        f"Count: {len(trending)} | "
        f"User: {user.id}"
    )
    
    return trending


@router.get("/platforms/supported")
async def get_supported_platforms(
    user: User = Depends(get_current_user)
):
    """
    Get list of supported platforms for URL search
    """
    return {
        "platforms": url_detector.get_supported_platforms(),
        "notes": {
            "full": "Platform-specific scraper with high accuracy",
            "partial": "AI-powered scraping with moderate accuracy",
            "unsupported": "Cannot scrape - URL will be rejected"
        }
    }
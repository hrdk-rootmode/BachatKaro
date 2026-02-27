"""
Search API Routes - AI Enhanced Edition
Multi-platform product search with intelligent enrichment and cross-platform matching

FLOW:
1. User Search/URL → 2. Cache Check → 3. Scrape/API → 4. AI Enrich → 5. Save DB → 6. Response

Author: DealHunt
Updated: Full AI Integration + Duplicate Handling + FIXED TRENDING SORT
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc, Integer, cast
from sqlalchemy.orm import selectinload
from typing import List, Optional
import hashlib
import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.database import get_db
from app.core.redis_client import RedisClient, get_redis
from app.models import Product, ProductListing, User
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
from app.services.ai.groq_client import groq_client

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_search_cache_key(query: str, filters: dict) -> str:
    """Generate cache key for search query"""
    filter_str = f"{filters.get('platforms', 'all')}_{filters.get('min_price', 0)}_{filters.get('max_price', 999999)}"
    combined = f"{query.lower().strip()}_{filter_str}"
    return f"search:{hashlib.md5(combined.encode()).hexdigest()}"


# =============================================================================
# AI ENRICHMENT FUNCTIONS (THE KEY ADDITION)
# =============================================================================

async def _enrich_product_with_ai(product_data: ProductData) -> ProductData:
    """
    Enrich product data using AI
    
    This modifies product_data in-place, adding:
    - ai_essence (normalized fingerprint)
    - ai_tags (searchable keywords)
    - ai_quality_score (0-100)
    - category/subcategory
    - standardized specifications
    """
    if product_data.ai_processed:
        return product_data
    
    try:
        # Call AI for enrichment
        enriched = await groq_client.process_product(product_data)
        
        # Update product with AI data
        product_data.ai_essence = enriched.get("essence")
        product_data.ai_tags = enriched.get("tags", [])
        product_data.ai_quality_score = enriched.get("quality_score", 50)
        product_data.category = enriched.get("category") or product_data.category
        product_data.subcategory = enriched.get("subcategory")
        
        # Merge specifications
        if enriched.get("specifications"):
            product_data.specifications = {
                **(product_data.specifications or {}),
                **enriched["specifications"]
            }
        
        product_data.ai_processed = True
        
        logger.info(
            f"AI enriched: {product_data.title[:40]}... → "
            f"{product_data.ai_essence[:30] if product_data.ai_essence else 'N/A'}"
        )
        
    except Exception as e:
        logger.error(f"AI enrichment failed (continuing with raw data): {e}")
        product_data.ai_processed = False
    
    return product_data


async def save_product_to_database(
    product_data: ProductData,
    db: AsyncSession
) -> Product:
    """
    Save scraped AND enriched product to database
    
    FIXED: Properly handles duplicate listings
    """
    # Use AI fingerprint if available
    fingerprint = product_data.fingerprint
    
    # Check if product exists
    result = await db.execute(
        select(Product).where(Product.fingerprint == fingerprint)
    )
    existing_product = result.scalar_one_or_none()
    
    # Build AI metadata
    ai_metadata = {
        "essence": product_data.ai_essence or product_data.title[:100].lower(),
        "tags": product_data.ai_tags or [],
        "quality_score": product_data.ai_quality_score or 50,
        "processed_at": datetime.utcnow().isoformat()
    }
    
    if existing_product:
        product = existing_product
        
        # Update AI metadata if new processing is better
        old_score = (product.ai_metadata or {}).get("quality_score", 0)
        if product_data.ai_quality_score and product_data.ai_quality_score > old_score:
            product.ai_metadata = ai_metadata
            product.specifications = product_data.specifications or product.specifications
            product.subcategory = product_data.subcategory or product.subcategory
        
        # Increment search count in stats
        current_stats = product.stats or {}
        product.stats = {
            **current_stats,
            "searches": current_stats.get("searches", 0) + 1,
            "last_searched": datetime.utcnow().isoformat()
        }
    else:
        # Create new product
        product = Product(
            fingerprint=fingerprint,
            title=product_data.title,
            brand=product_data.brand,
            category=product_data.category or "General",
            subcategory=product_data.subcategory,
            image_url=product_data.image_url,
            specifications=product_data.specifications or {},
            ai_metadata=ai_metadata,
            stats={
                "views": 0,
                "clicks": 0,
                "watches": 0,
                "searches": 1,
                "conversions": 0
            }
        )
        db.add(product)
        await db.flush()
    
    # Get or create platform
    platform_result = await db.execute(
        select(PlatformModel).where(PlatformModel.name == product_data.platform_name.lower())
    )
    platform = platform_result.scalar_one_or_none()
    
    if not platform:
        platform = PlatformModel(
            name=product_data.platform_name.lower(),
            base_url=f"https://www.{product_data.platform_name.lower()}.com",
            is_active=True,
            selectors={}
        )
        db.add(platform)
        await db.flush()
    
    # =========================================================================
    # FIX: Check for existing listing BEFORE trying to create
    # =========================================================================
    
    listing_result = await db.execute(
        select(ProductListing).where(
            ProductListing.product_id == product.id,
            ProductListing.platform_id == platform.id
        )
    )
    existing_listing = listing_result.scalar_one_or_none()
    
    # ALSO check by external_id to catch duplicates
    if not existing_listing and product_data.external_id:
        external_check = await db.execute(
            select(ProductListing).where(
                ProductListing.platform_id == platform.id,
                ProductListing.external_id == product_data.external_id
            )
        )
        existing_listing = external_check.scalar_one_or_none()
        
        # If found by external_id but different product_id, update product_id
        if existing_listing and existing_listing.product_id != product.id:
            logger.warning(
                f"Listing {product_data.external_id} exists with different product_id, updating..."
            )
            existing_listing.product_id = product.id
    
    # Prepare listing data
    listing_data = {
        "current_price": float(product_data.current_price),
        "original_price": float(product_data.original_price) if product_data.original_price else None,
        "discount_percent": product_data.discount_percent,
        "rating": product_data.rating,
        "review_count": product_data.review_count,
        "in_stock": product_data.in_stock,
        "last_scraped": datetime.utcnow()
    }
    
    if existing_listing:
        # UPDATE existing listing
        for key, value in listing_data.items():
            setattr(existing_listing, key, value)
        
        logger.debug(f"Updated listing: {product_data.external_id}")
    else:
        # CREATE new listing
        listing = ProductListing(
            product_id=product.id,
            platform_id=platform.id,
            external_id=product_data.external_id,
            product_url=product_data.product_url,
            affiliate_url=url_detector.get_affiliate_url(product_data.product_url),
            **listing_data
        )
        db.add(listing)
        
        logger.debug(f"Created listing: {product_data.external_id}")
    
    await db.commit()
    await db.refresh(product)
    
    return product


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

async def search_database(
    query: str,
    db: AsyncSession,
    platforms: Optional[List[Platform]] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    page: int = 1,
    limit: int = 20
) -> List[Product]:
    """Search products in database using title field"""
    search_terms = query.lower().split()
    
    # Match against title
    title_conditions = [
        Product.title.ilike(f"%{term}%")
        for term in search_terms
    ]
    
    query_stmt = select(Product).where(or_(*title_conditions))
    
    # Pagination
    offset = (page - 1) * limit
    query_stmt = query_stmt.offset(offset).limit(limit)
    
    result = await db.execute(query_stmt)
    products = result.scalars().all()
    
    return list(products)


async def get_product_listings(
    product_id,
    db: AsyncSession,
    platforms: Optional[List[Platform]] = None
) -> List[ProductListing]:
    """Get all listings for a product"""
    query = select(ProductListing).where(
        ProductListing.product_id == product_id,
        ProductListing.in_stock == True
    )
    
    query = query.order_by(ProductListing.current_price.asc())
    
    result = await db.execute(query)
    return list(result.scalars().all())


def format_product_response(
    product: Product,
    listings: List[ProductListing]
) -> ProductResponse:
    """Format product with listings for API response"""
    ai_metadata = product.ai_metadata or {}
    
    # Calculate best price from listings
    best_price = 0
    best_platform = "amazon"
    if listings:
        best_listing = min(listings, key=lambda x: x.current_price)
        best_price = best_listing.current_price
        best_platform = "amazon"  # Default
    
    # Calculate avg price
    avg_price = None
    if listings:
        avg_price = sum(l.current_price for l in listings) / len(listings)
    
    # Calculate price trend
    price_trend = "stable"
    if avg_price and best_price:
        if best_price < avg_price * 0.9:
            price_trend = "down"
        elif best_price > avg_price * 1.1:
            price_trend = "up"
    
    return ProductResponse(
        id=product.id,
        fingerprint=product.fingerprint,
        best_price=best_price,
        best_platform=best_platform,
        avg_price=avg_price,
        price_trend=price_trend,
        ai_generated_essence=ai_metadata.get("essence", product.title),
        ai_extracted_specs=product.specifications or {},
        ai_tags=ai_metadata.get("tags", []),
        created_at=product.created_at,
        listings=[
            ProductListingResponse.model_validate(listing)
            for listing in listings
        ]
    )


# =============================================================================
# URL SEARCH HELPER FUNCTIONS (UPDATED WITH AI ENRICHMENT)
# =============================================================================

async def scrape_and_match(
    url: str,
    url_analysis: URLAnalysis,
    db: AsyncSession
) -> List[ProductData]:
    """
    Core function: Scrape → AI Enrich → Save → Find Alternatives
    
    UPDATED: Now includes AI enrichment step
    """
    source_product = None
    
    # Step 1: Scrape source product
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
    # STEP 2: AI ENRICHMENT (THE KEY STEP)
    # =========================================================================
    
    source_product = await _enrich_product_with_ai(source_product)
    
    # =========================================================================
    # STEP 3: SAVE TO DATABASE
    # =========================================================================
    
    try:
        await save_product_to_database(source_product, db)
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
    # STEP 5: SAVE ALTERNATIVES (with AI enrichment)
    # =========================================================================
    
    for alt in alternatives:
        if alt.platform_name.lower() != source_product.platform_name.lower():
            try:
                # Enrich alternatives too
                if not alt.ai_processed:
                    alt = await _enrich_product_with_ai(alt)
                await save_product_to_database(alt, db)
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
        "source": {
            "platform": source_platform,
            "title": product.title,
            "price": float(source_listing.current_price) if source_listing else 0,
            "original_price": float(source_listing.original_price) if source_listing and source_listing.original_price else None,
            "rating": source_listing.rating if source_listing else None,
            "review_count": source_listing.review_count if source_listing else None,
            "image_url": product.image_url,
            "url": url_detector.get_affiliate_url(source_listing.product_url) if source_listing else source_url,
            "in_stock": source_listing.in_stock if source_listing else True,
            "brand": product.brand
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
        'max_price': request.max_price
    }
    cache_key = calculate_search_cache_key(request.query, filters)
    
    # TIER 1: Check Redis cache
    cached_results = await redis.get_json(cache_key)
    
    if cached_results:
        search_time_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"Cache HIT: {request.query} | "
            f"User: {user.id} | "
            f"Time: {search_time_ms}ms"
        )
        
        return SearchResponse(
            query=request.query,
            total_results=len(cached_results),
            page=request.page,
            products=cached_results,
            cache_hit=True,
            search_time_ms=search_time_ms
        )
    
    # TIER 2: Search database
    products = await search_database(
        query=request.query,
        db=db,
        platforms=request.platforms,
        min_price=request.min_price,
        max_price=request.max_price,
        page=request.page
    )
    
    results = []
    for product in products:
        listings = await get_product_listings(
            product.id,
            db,
            platforms=request.platforms
        )
        
        if listings:
            results.append(format_product_response(product, listings))
    
    if results:
        await redis.set_json(
            cache_key,
            [r.model_dump(mode='json') for r in results],
            ttl=3600
        )
    
    search_time_ms = int((time.time() - start_time) * 1000)
    
    # Update user stats
    if user.usage_stats is None:
        user.usage_stats = {}
    user.usage_stats['daily_searches'] = user.usage_stats.get('daily_searches', 0) + 1
    user.usage_stats['last_search_date'] = datetime.utcnow().isoformat()
    user.usage_stats['last_search_query'] = request.query
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
        total_results=len(results),
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
    
    UPDATED: Now includes AI enrichment for better matching
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
    
    # Step 3: Check database cache first
    cache_key = f"url_search:{hashlib.md5(url.encode()).hexdigest()}"
    cached_result = await redis.get_json(cache_key)
    
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
                response["source"] = "database"
                response["search_time_ms"] = search_time_ms
                
                logger.info(
                    f"URL search DB HIT: {url[:50]} | "
                    f"Time: {search_time_ms}ms"
                )
                
                return response
    
    # Step 5: Need to scrape
    search_queue = get_search_queue(redis)
    
    try:
        alternatives = await search_queue.search_url(
            url=url,
            user=user,
            scrape_func=lambda u: scrape_and_match(u, url_analysis, db)
        )
    except Exception as e:
        logger.error(f"URL search scraping failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "scraping_failed",
                "message": f"Failed to fetch product details: {str(e)}",
                "platform": url_analysis.platform_name
            }
        )
    
    if not alternatives:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "product_not_found",
                "message": "Could not extract product information from URL",
                "url": url,
                "platform": url_analysis.platform_name
            }
        )
    
    # Step 6: Format response
    source_product = next(
        (p for p in alternatives if url_analysis.platform_name in p.platform_name.lower()),
        alternatives[0]
    )
    
    other_alternatives = [
        p for p in alternatives
        if p.platform_name != source_product.platform_name
    ]
    
    # Calculate savings
    savings_info = cross_platform_matcher.calculate_savings(alternatives)
    
    response = {
        "success": True,
        "source": {
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
        "source": "live_scrape"
    }
    
    # Update user stats
    if user.usage_stats is None:
        user.usage_stats = {}
    user.usage_stats['daily_searches'] = user.usage_stats.get('daily_searches', 0) + 1
    user.usage_stats['last_url_search'] = url
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
# TRENDING ENDPOINT - FIXED!
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
    
    FIXED: Now sorts by stats['views'] + stats['searches'] instead of listing_count
    This merges:
    - User searched items (high searches count)
    - Seeded trending items (high views count from boost)
    """
    cache_key = "trending:products:top50"
    
    # Check Redis cache first
    cached = await redis.get_json(cache_key)
    
    if cached:
        logger.info(f"Trending cache HIT | User: {user.id}")
        return cached
    
    # ==========================================================================
    # FIXED QUERY: Sort by (views + searches) instead of listing_count
    # Also fixes N+1 query issue by using a single JOIN with aggregation
    # ==========================================================================
    
    try:
        # Build optimized query with proper stats sorting
        # Using COALESCE to handle NULL stats
        result = await db.execute(
            select(
                Product,
                func.min(ProductListing.current_price).label('best_price'),
                func.max(ProductListing.discount_percent).label('best_discount'),
                func.count(ProductListing.id).label('listing_count')
            )
            .join(ProductListing, Product.id == ProductListing.product_id)
            .where(ProductListing.in_stock == True)
            .group_by(Product.id)
            .order_by(
                desc(
                    func.coalesce(
                        func.cast(Product.stats['views'].astext, Integer), 0
                    ) +
                    func.coalesce(
                        func.cast(Product.stats['searches'].astext, Integer), 0
                    ) +
                    func.coalesce(
                        func.cast(Product.stats['seed_score'].astext, Integer), 0
                    )
                )
            )
            .limit(limit)
        )
        
        rows = result.all()
        
    except Exception as e:
        # Fallback query if JSONB casting fails (older PostgreSQL)
        logger.warning(f"Optimized trending query failed, using fallback: {e}")
        
        result = await db.execute(
            select(Product)
            .join(ProductListing)
            .group_by(Product.id)
            .order_by(desc(func.count(ProductListing.id)))
            .limit(limit)
        )
        
        products = result.scalars().all()
        rows = [(p, None, None, 0) for p in products]
    
    # Build response
    trending = []
    rank = 1
    
    for row in rows:
        # Handle both tuple and single object results
        if isinstance(row, tuple):
            product = row[0]
            best_price = row[1] if len(row) > 1 else None
            best_discount = row[2] if len(row) > 2 else None
        else:
            product = row
            best_price = None
            best_discount = None
        
        # Get best price if not from aggregation
        if best_price is None:
            listing_result = await db.execute(
                select(ProductListing)
                .where(
                    ProductListing.product_id == product.id,
                    ProductListing.in_stock == True
                )
                .order_by(ProductListing.current_price.asc())
                .limit(1)
            )
            cheapest_listing = listing_result.scalar_one_or_none()
            best_price = cheapest_listing.current_price if cheapest_listing else 0
            best_discount = cheapest_listing.discount_percent if cheapest_listing else None
        
        # Get AI metadata
        ai_metadata = product.ai_metadata or {}
        stats = product.stats or {}
        
        # Calculate engagement score (for search_count field)
        engagement_score = (
            stats.get("views", 0) +
            stats.get("searches", 0) +
            stats.get("clicks", 0)
        )
        
        # Determine best platform (simplified - can enhance later)
        best_platform = "amazon"  # Default, could query for actual best
        
        trending.append(TrendingProductResponse(
            product_id=product.id,
            title=ai_metadata.get("essence", product.title),
            best_price=float(best_price) if best_price else 0,
            best_platform=best_platform,
            discount_percentage=float(best_discount) if best_discount else None,
            image_url=product.image_url,
            search_count=engagement_score,  # Now represents total engagement
            rank=rank
        ))
        rank += 1
    
    # Cache results for 1 hour
    if trending:
        await redis.set_json(
            cache_key,
            [t.model_dump(mode='json') for t in trending],
            ttl=3600
        )
    
    logger.info(
        f"Trending calculated from DB | "
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
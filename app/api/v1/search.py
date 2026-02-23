"""
Search API Routes - ENHANCED
Multi-platform product search with 3-tier caching + URL-based cross-platform search

New Features:
- Paste any product URL from supported/unsupported platforms
- Auto-detect platform from URL
- Find same product on other platforms
- Show best price comparison
- Queue management for concurrent searches
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc
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

# New imports for URL search
from app.services.scraper.url_detector import url_detector, URLAnalysis, PlatformSupport
from app.services.scraper.generic_scraper import GenericAIScraper
from app.services.scraper.cross_platform_matcher import cross_platform_matcher
from app.services.scraper.search_queue import get_search_queue
from app.services.scraper.factory import get_platform_handler
from app.services.scraper.base import ProductData

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
    # Get AI metadata
    ai_metadata = product.ai_metadata or {}
    
    # Calculate best price from listings
    best_price = 0
    best_platform = "amazon"
    if listings:
        best_listing = min(listings, key=lambda x: x.current_price)
        best_price = best_listing.current_price
        best_platform = "amazon"  # Default, could get from platform_id
    
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


async def save_product_to_database(
    product_data: ProductData,
    db: AsyncSession
) -> Product:
    """Save scraped product to database"""
    # Check if product exists (by fingerprint)
    result = await db.execute(
        select(Product).where(Product.fingerprint == product_data.fingerprint)
    )
    existing_product = result.scalar_one_or_none()
    
    if existing_product:
        # Update existing product
        product = existing_product
    else:
        # Create new product
        product = Product(
            fingerprint=product_data.fingerprint,
            title=product_data.title,
            brand=product_data.brand,
            category=product_data.category,
            image_url=product_data.image_url,
            specifications=product_data.specifications,
            ai_metadata={
                "tags": [],
                "quality_score": 0,
                "essence": product_data.title[:100]
            }
        )
        db.add(product)
        await db.flush()
    
    # Get or create platform
    platform_result = await db.execute(
        select(PlatformModel).where(PlatformModel.name == product_data.platform_name)
    )
    platform = platform_result.scalar_one_or_none()
    
    if not platform:
        # Create platform entry
        platform = PlatformModel(
            name=product_data.platform_name,
            base_url=f"https://{product_data.platform_name}.com",
            is_active=True,
            selectors={}
        )
        db.add(platform)
        await db.flush()
    
    # Create or update listing
    listing_result = await db.execute(
        select(ProductListing).where(
            ProductListing.product_id == product.id,
            ProductListing.platform_id == platform.id
        )
    )
    existing_listing = listing_result.scalar_one_or_none()
    
    if existing_listing:
        # Update existing listing
        existing_listing.current_price = float(product_data.current_price)
        existing_listing.original_price = float(product_data.original_price) if product_data.original_price else None
        existing_listing.discount_percent = product_data.discount_percent
        existing_listing.rating = product_data.rating
        existing_listing.review_count = product_data.review_count
        existing_listing.in_stock = product_data.in_stock
        existing_listing.last_scraped = datetime.utcnow()
    else:
        # Create new listing
        listing = ProductListing(
            product_id=product.id,
            platform_id=platform.id,
            external_id=product_data.external_id,
            product_url=product_data.product_url,
            affiliate_url=product_data.affiliate_url,
            current_price=float(product_data.current_price),
            original_price=float(product_data.original_price) if product_data.original_price else None,
            discount_percent=product_data.discount_percent,
            rating=product_data.rating,
            review_count=product_data.review_count,
            in_stock=product_data.in_stock,
            last_scraped=datetime.utcnow()
        )
        db.add(listing)
    
    await db.commit()
    await db.refresh(product)
    
    return product


# =============================================================================
# URL SEARCH HELPER FUNCTIONS
# =============================================================================

async def scrape_and_match(
    url: str,
    url_analysis: URLAnalysis,
    db: AsyncSession
) -> List[ProductData]:
    """
    Core function to scrape product and find cross-platform alternatives
    
    Flow:
    1. Scrape source product (platform-specific or generic)
    2. Find alternatives on other platforms
    3. Return all options sorted by price
    """
    source_product = None
    
    # Step 1: Scrape source product
    if url_analysis.support_level == PlatformSupport.FULL:
        # Use platform-specific scraper
        try:
            handler = await get_platform_handler(url_analysis.platform_name, db)
            source_product = await handler.get_product(url)
        except Exception as e:
            logger.error(f"Platform scraper failed: {e}")
            # Fall through to generic scraper
    
    if not source_product and url_analysis.support_level in [PlatformSupport.FULL, PlatformSupport.PARTIAL]:
        # Use generic AI scraper
        logger.info(f"Using generic AI scraper for {url_analysis.platform_name}")
        generic_scraper = GenericAIScraper(url_analysis.platform_name)
        source_product = await generic_scraper.get_product(url)
    
    if not source_product:
        logger.error(f"Failed to scrape product from {url}")
        return []
    
    # Add affiliate URL
    source_product.product_url = url_detector.get_affiliate_url(source_product.product_url)
    
    # Step 2: Save to database
    await save_product_to_database(source_product, db)
    
    # Step 3: Find alternatives on other platforms
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
    
    # Save alternatives to database
    for alt in alternatives:
        if alt.platform_name != source_product.platform_name:
            try:
                await save_product_to_database(alt, db)
            except Exception as e:
                logger.warning(f"Failed to save alternative: {e}")
    
    return alternatives


# =============================================================================
# ROUTES
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
    Search by product URL - Find same product across ALL platforms!
    
    Features:
    - Auto-detects platform from URL (Amazon, Flipkart, etc.)
    - Scrapes product details
    - Finds same product on other platforms
    - Returns best prices with savings comparison
    
    Supported Platforms (Full):
    - Amazon.in / Amazon.com
    - Flipkart.com
    - Meesho.com
    - Myntra.com
    
    Partial Support (AI Scraping):
    - Snapdeal, Croma, Reliance Digital, Tata Cliq, Ajio, Nykaa
    
    Example Request:
        POST /api/v1/search/by-url
        {
            "url": "https://www.amazon.in/iPhone-15-Pro-Max-256GB/dp/B0CHX3TW6X"
        }
    
    Example Response:
        {
            "success": true,
            "source": {
                "platform": "amazon",
                "title": "Apple iPhone 15 Pro Max 256GB",
                "price": 144900,
                "url": "https://amazon.in/dp/B0CHX3TW6X?tag=dealhunt-21"
            },
            "alternatives": [...],
            "best_deal": {
                "platform": "flipkart",
                "price": 139900,
                "savings": 5000,
                "savings_percent": 3.5
            },
            "total_options": 3
        }
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
        # Check if it's even a product URL
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
        # Try to find by external_id and platform
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
                await redis.set_json(cache_key, response, ttl=1800)  # 30 min cache
                
                search_time_ms = int((time.time() - start_time) * 1000)
                response["cache_hit"] = False
                response["source"] = "database"
                response["search_time_ms"] = search_time_ms
                
                logger.info(
                    f"URL search DB HIT: {url[:50]} | "
                    f"Time: {search_time_ms}ms"
                )
                
                return response
    
    # Step 5: Need to scrape - use queue manager
    search_queue = get_search_queue(redis)
    
    try:
        # This handles deduplication and concurrent requests
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
            "brand": source_product.brand
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


@router.get("/trending", response_model=List[TrendingProductResponse])
async def get_trending_products(
    limit: int = 50,
    user: User = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    """Get trending products (top searched)"""
    cache_key = "trending:products:top50"
    
    cached = await redis.get_json(cache_key)
    
    if cached:
        logger.info(f"Trending cache HIT | User: {user.id}")
        return cached
    
    result = await db.execute(
        select(Product, func.count(ProductListing.id).label('listing_count'))
        .join(ProductListing)
        .group_by(Product.id)
        .order_by(desc('listing_count'))
        .limit(limit)
    )
    
    trending = []
    for product, count in result:
        listing_result = await db.execute(
            select(ProductListing)
            .where(ProductListing.product_id == product.id)
            .order_by(ProductListing.current_price.asc())
            .limit(1)
        )
        cheapest_listing = listing_result.scalar_one_or_none()
        
        ai_metadata = product.ai_metadata or {}
        
        trending.append(TrendingProductResponse(
            product_id=product.id,
            title=ai_metadata.get("essence", product.title),
            best_price=cheapest_listing.current_price if cheapest_listing else 0,
            best_platform="amazon",
            discount_percentage=cheapest_listing.discount_percent if cheapest_listing else None,
            image_url=product.image_url,
            search_count=count,
            rank=len(trending) + 1
        ))
    
    if trending:
        await redis.set_json(
            cache_key,
            [t.model_dump(mode='json') for t in trending],
            ttl=3600
        )
    
    logger.info(f"Trending calculated from DB | Count: {len(trending)}")
    
    return trending


@router.get("/platforms/supported")
async def get_supported_platforms(
    user: User = Depends(get_current_user)
):
    """
    Get list of supported platforms for URL search
    
    Returns platforms with their support level:
    - full: Complete scraping with platform-specific selectors
    - partial: AI-powered generic scraping (lower accuracy)
    - unsupported: Cannot scrape
    """
    return {
        "platforms": url_detector.get_supported_platforms(),
        "notes": {
            "full": "Platform-specific scraper with high accuracy",
            "partial": "AI-powered scraping with moderate accuracy",
            "unsupported": "Cannot scrape - URL will be rejected"
        }
    }
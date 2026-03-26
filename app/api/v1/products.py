"""
Product Detail & Price History Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.core.database import get_db
from app.core.redis_client import RedisClient, get_redis
from app.core.config import settings
from app.models import Product, ProductListing, PriceHistory, User
from app.schemas import (
    ProductResponse,
    ProductListingResponse,
    PriceHistoryResponse,
    PriceHistoryPoint,
    Platform
)
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_listing_allowed(listing: ProductListing) -> bool:
    if hasattr(listing, "platform") and listing.platform:
        if listing.platform.name.lower() == "croma" and not getattr(settings, "CROMA_ENABLED", False):
            return False

    min_confidence = float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))
    if listing.extraction_confidence is not None and listing.extraction_confidence < min_confidence:
        return False

    return True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_listing_response(listing: ProductListing, product: Product) -> ProductListingResponse:
    """Format ProductListing ORM model to ProductListingResponse"""
    # Get platform name from relationship (should be eager-loaded)
    platform_name = "amazon"  # Default
    if hasattr(listing, 'platform') and listing.platform:
        platform_name = listing.platform.name.lower()
    
    try:
        platform_enum = Platform[platform_name.upper()]
    except (KeyError, AttributeError):
        platform_enum = Platform.AMAZON
    
    return ProductListingResponse(
        id=str(listing.id),  # ✅ Convert UUID to string
        platform=platform_enum,
        platform_product_id=listing.external_id or "",
        url=listing.product_url or "",
        title=product.title,  # ✅ Get from product parameter (already loaded)
        current_price=listing.current_price,
        original_price=listing.original_price,
        discount_percentage=int(listing.discount_percent) if listing.discount_percent else None,
        rating=listing.rating,
        review_count=listing.review_count,
        image_url=product.image_url,  # ✅ Get from product parameter (already loaded)
        in_stock=listing.in_stock,
        last_scraped_at=listing.last_scraped or datetime.now(),
        extraction_confidence=listing.extraction_confidence,
        extraction_method=listing.extraction_method,
        data_source=listing.data_source,
        seller_name=listing.seller_name,
        seller_rating=Decimal(str(listing.seller_rating)) if listing.seller_rating is not None else None,
        variant_fingerprint=listing.variant_fingerprint
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """Get complete product details with all platform listings"""
    cache_key = f"product:{product_id}"
    cached = await redis.get_json(cache_key)
    
    if cached:
        logger.info(f"Product cache HIT: {product_id} | User: {user.id}")
        return ProductResponse(**cached)
    
    product = await db.get(Product, product_id)
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    result = await db.execute(
        select(ProductListing)
        .where(ProductListing.product_id == product_id)
        .order_by(ProductListing.current_price.asc())
        .options(selectinload(ProductListing.platform))  # ✅ Eager-load platform relationship
    )
    all_listings = result.scalars().all()
    listings = [l for l in all_listings if l is not None and _is_listing_allowed(l)]

    if not listings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No high-confidence listings available for this product"
        )
    
    logger.debug(f"Product {product_id}: Fetched {len(listings)} listings (total: {len(all_listings)})")
    
    # Get AI metadata
    ai_metadata = product.ai_metadata or {}
    
    # Calculate best price from listings
    best_price = 0
    best_platform = "amazon"
    avg_price = None
    if listings:
        # Filter listings with valid prices
        listings_with_price = [l for l in listings if l.current_price is not None]
        if listings_with_price:
            best_listing = min(listings_with_price, key=lambda x: x.current_price or 0)
            best_price = float(best_listing.current_price or 0)
            if hasattr(best_listing, "platform") and best_listing.platform:
                best_platform = best_listing.platform.name.lower()
            prices = [float(l.current_price) for l in listings_with_price if l.current_price]
            if prices:
                avg_price = sum(prices) / len(prices)
    
    price_trend = "stable"
    if avg_price and best_price:
        if best_price < avg_price * 0.9:
            price_trend = "down"
        elif best_price > avg_price * 1.1:
            price_trend = "up"
    
    response = ProductResponse(
        id=str(product.id),  # ✅ FIX: Convert UUID to string
        fingerprint=product.fingerprint,
        # ✅ NEW: Variant fingerprinting fields
        variant_fingerprint=product.variant_fingerprint,
        base_fingerprint=product.base_fingerprint,
        variant_type=product.variant_type,
        storage_gb=product.storage_gb,
        color=product.color,
        condition=product.condition,
        # Pricing
        best_price=best_price,
        best_platform=best_platform,
        avg_price=avg_price,
        price_trend=price_trend,
        # AI metadata
        ai_generated_essence=ai_metadata.get("essence", product.title),
        ai_extracted_specs=product.specifications or {},
        ai_tags=ai_metadata.get("tags", []),
        created_at=product.created_at,
        listings=[
            format_listing_response(listing, product)  # ✅ Use helper function with product data
            for listing in listings
            if listing is not None  # ✅ CRITICAL: Filter None values
        ]
    )
    
    await redis.set_json(
        cache_key,
        response.model_dump(mode='json'),
        ttl=3600
    )
    
    logger.info(f"Product fetched: {product_id} | Listings: {len(listings)}")
    
    return response


@router.get("/{product_id}/price-history", response_model=PriceHistoryResponse)
async def get_price_history(
    product_id: str,
    platform: Platform,
    days: int = 120,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """Get price history for product on specific platform"""
    if days > 365:
        days = 365
    
    cache_key = f"price_history:{product_id}:{platform}:{days}"
    cached = await redis.get_json(cache_key)
    
    if cached:
        logger.info(f"Price history cache HIT: {product_id}/{platform}")
        return PriceHistoryResponse(**cached)
    
    # Get product listing - using JSONB price_history from ProductListing
    result = await db.execute(
        select(ProductListing)
        .where(
            ProductListing.product_id == product_id,
            ProductListing.in_stock == True
        )
        .options(selectinload(ProductListing.platform))
        .order_by(ProductListing.last_scraped.desc().nullslast())
    )
    all_listings = result.scalars().all()
    listing = next(
        (
            l for l in all_listings
            if l.platform and l.platform.name.lower() == platform.value and _is_listing_allowed(l)
        ),
        None,
    )
    
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product not available on {platform}"
        )
    
    # Get price history from JSONB column
    price_history_data = listing.price_history_json or []
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    history_points = []
    for entry in price_history_data:
        try:
            price = entry.get("p")
            date_str = entry.get("d")
            
            if price and date_str:
                entry_date = datetime.fromisoformat(date_str)
                if entry_date >= cutoff_date:
                    history_points.append(
                        PriceHistoryPoint(
                            date=entry_date,
                            price=Decimal(str(price)),
                            platform=platform
                        )
                    )
        except (ValueError, TypeError):
            continue
    
    history_points.sort(key=lambda x: x.date)
    
    # If no historical data exists, use fallback
    has_historical_data = len([p for p in price_history_data if len(price_history_data) > 1]) > 0
    
    if not history_points:
        history_points = [
            PriceHistoryPoint(
                date=datetime.utcnow(),
                price=Decimal(str(listing.current_price)),
                platform=platform
            )
        ]
    
    prices = [point.price for point in history_points]
    lowest_price = min(prices)
    highest_price = max(prices)
    average_price = sum(prices) / len(prices)
    
    # ✅ If only 1 data point, all three will be same - that's normal
    logger.debug(
        f"Price history for {product_id} on {platform}: "
        f"Points: {len(history_points)}, Low: ₹{lowest_price}, High: ₹{highest_price}, Avg: ₹{average_price}"
    )
    
    price_drop_percentage = None
    if highest_price > 0:
        current_price = Decimal(str(listing.current_price))
        price_drop_percentage = ((highest_price - current_price) / highest_price) * 100
    
    response = PriceHistoryResponse(
        product_id=product_id,
        platform=platform,
        history=history_points,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=Decimal(str(average_price)),
        price_drop_percentage=Decimal(str(price_drop_percentage)) if price_drop_percentage else None
    )
    
    await redis.set_json(
        cache_key,
        response.model_dump(mode='json'),
        ttl=21600
    )
    
    logger.info(f"Price history: Product {product_id} | Platform: {platform} | Records: {len(history_points)}")
    
    return response
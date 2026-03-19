"""
Product Detail & Price History Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.core.database import get_db
from app.core.redis_client import RedisClient, get_redis
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
    )
    listings = list(result.scalars().all())
    
    # Get AI metadata
    ai_metadata = product.ai_metadata or {}
    
    # Calculate best price from listings
    best_price = 0
    best_platform = "amazon"
    avg_price = None
    if listings:
        best_listing = min(listings, key=lambda x: x.current_price)
        best_price = best_listing.current_price
        avg_price = sum(l.current_price for l in listings) / len(listings)
    
    price_trend = "stable"
    if avg_price and best_price:
        if best_price < avg_price * 0.9:
            price_trend = "down"
        elif best_price > avg_price * 1.1:
            price_trend = "up"
    
    response = ProductResponse(
        id=product.id,
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
            ProductListingResponse.model_validate(listing)
            for listing in listings
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
        .where(ProductListing.product_id == product_id)
        .limit(1)
    )
    listing = result.scalar_one_or_none()
    
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
"""
Watchlist API Routes
Price tracking and alert management
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from typing import List
from datetime import datetime
from decimal import Decimal
import logging

from app.core.database import get_db
from app.core.redis_client import RedisClient, get_redis
from app.models import User, Product, ProductListing, UserWatchlist
from app.schemas import (
    WatchlistAddRequest,
    WatchlistUpdateRequest,
    WatchlistItemResponse,
    WatchlistResponse,
    UserPlan
)
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# CONSTANTS
# =============================================================================

WATCHLIST_LIMITS = {
    "free": 5,
    "pro": 20,
    "premium": 50
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_watchlist_limit(plan: str) -> int:
    """Get watchlist limit based on user plan"""
    return WATCHLIST_LIMITS.get(plan, 5)


async def get_product_with_best_listing(
    product_id: str,
    db: AsyncSession
) -> tuple:
    """Get product and its cheapest listing"""
    # Get product
    product = await db.get(Product, product_id)
    if not product:
        return None, None
    
    # Get cheapest listing
    result = await db.execute(
        select(ProductListing)
        .where(ProductListing.product_id == product_id)
        .order_by(ProductListing.current_price.asc())
        .limit(1)
    )
    listing = result.scalar_one_or_none()
    
    return product, listing


def format_watchlist_item(
    watchlist_item: UserWatchlist,
    product: Product,
    listing: ProductListing
) -> WatchlistItemResponse:
    """Format watchlist item for response"""
    # Calculate price change percentage
    price_change = None
    if listing and listing.original_price and listing.original_price > 0:
        price_change = ((listing.original_price - listing.current_price) / listing.original_price) * 100
    
    # Check if target price is reached
    is_target_reached = False
    if watchlist_item.target_price and listing:
        is_target_reached = listing.current_price <= watchlist_item.target_price
    
    return WatchlistItemResponse(
        id=str(watchlist_item.id),
        product_id=str(watchlist_item.product_id),
        target_price=Decimal(str(watchlist_item.target_price)) if watchlist_item.target_price else None,
        notify_any_drop=watchlist_item.notify,
        created_at=watchlist_item.created_at,
        product_title=product.title if product else "Unknown Product",
        current_price=Decimal(str(listing.current_price)) if listing else Decimal("0"),
        original_price=Decimal(str(listing.original_price)) if listing and listing.original_price else None,
        platform="amazon",  # Default, would come from platform relationship
        image_url=product.image_url if product else None,
        product_url=listing.product_url if listing else "",
        in_stock=listing.in_stock if listing else False,
        price_change_percentage=Decimal(str(round(price_change, 2))) if price_change else None,
        is_target_reached=is_target_reached
    )


# =============================================================================
# ROUTES
# =============================================================================

@router.get("", response_model=WatchlistResponse)
async def get_watchlist(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Get user's complete watchlist with current prices
    
    Returns:
        Watchlist items with product details and price alerts status
    """
    # Check cache first
    cache_key = f"watchlist:{user.id}"
    cached = await redis.get_json(cache_key)
    
    if cached:
        logger.info(f"Watchlist cache HIT | User: {user.id}")
        return WatchlistResponse(**cached)
    
    # Get watchlist items
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user.id)
        .order_by(UserWatchlist.created_at.desc())
    )
    watchlist_items = result.scalars().all()
    
    # Build response with product details
    items = []
    for item in watchlist_items:
        product, listing = await get_product_with_best_listing(str(item.product_id), db)
        if product:
            items.append(format_watchlist_item(item, product, listing))
    
    # Get limit based on plan
    limit = get_watchlist_limit(user.plan)
    
    response = WatchlistResponse(
        items=items,
        total_count=len(items),
        limit=limit,
        limit_reached=len(items) >= limit
    )
    
    # Cache for 5 minutes
    await redis.set_json(
        cache_key,
        response.model_dump(mode='json'),
        ttl=300
    )
    
    logger.info(f"Watchlist fetched | User: {user.id} | Items: {len(items)}")
    
    return response


@router.post("", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    request: WatchlistAddRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Add product to watchlist
    
    Features:
    - Set target price for alerts
    - Enable/disable notifications
    - Respects plan-based limits
    """
    # Check watchlist limit
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user.id)
    )
    current_count = len(result.scalars().all())
    limit = get_watchlist_limit(user.plan)
    
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Watchlist limit reached ({limit} items). Upgrade your plan for more slots."
        )
    
    # Check if product exists
    product = await db.get(Product, request.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check if already in watchlist
    existing = await db.execute(
        select(UserWatchlist)
        .where(
            and_(
                UserWatchlist.user_id == user.id,
                UserWatchlist.product_id == request.product_id
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product already in watchlist"
        )
    
    # Create watchlist entry
    watchlist_item = UserWatchlist(
        user_id=user.id,
        product_id=request.product_id,
        target_price=float(request.target_price) if request.target_price else None,
        notify=request.notify_any_drop
    )
    
    db.add(watchlist_item)
    await db.commit()
    await db.refresh(watchlist_item)
    
    # Invalidate cache
    await redis.delete(f"watchlist:{user.id}")
    
    # Get product details for response
    product, listing = await get_product_with_best_listing(request.product_id, db)
    
    # Update product stats
    if product.stats:
        product.stats['watches'] = product.stats.get('watches', 0) + 1
    else:
        product.stats = {'watches': 1}
    await db.commit()
    
    logger.info(
        f"Product added to watchlist | User: {user.id} | "
        f"Product: {request.product_id} | Target: {request.target_price}"
    )
    
    return format_watchlist_item(watchlist_item, product, listing)


@router.put("/{item_id}", response_model=WatchlistItemResponse)
async def update_watchlist_item(
    item_id: str,
    request: WatchlistUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Update watchlist item (target price, notifications)
    """
    # Get watchlist item
    result = await db.execute(
        select(UserWatchlist)
        .where(
            and_(
                UserWatchlist.id == item_id,
                UserWatchlist.user_id == user.id
            )
        )
    )
    watchlist_item = result.scalar_one_or_none()
    
    if not watchlist_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist item not found"
        )
    
    # Update fields
    if request.target_price is not None:
        watchlist_item.target_price = float(request.target_price)
    
    if request.notify_any_drop is not None:
        watchlist_item.notify = request.notify_any_drop
    
    await db.commit()
    await db.refresh(watchlist_item)
    
    # Invalidate cache
    await redis.delete(f"watchlist:{user.id}")
    
    # Get product details
    product, listing = await get_product_with_best_listing(str(watchlist_item.product_id), db)
    
    logger.info(f"Watchlist item updated | User: {user.id} | Item: {item_id}")
    
    return format_watchlist_item(watchlist_item, product, listing)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    item_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Remove product from watchlist
    """
    # Get watchlist item
    result = await db.execute(
        select(UserWatchlist)
        .where(
            and_(
                UserWatchlist.id == item_id,
                UserWatchlist.user_id == user.id
            )
        )
    )
    watchlist_item = result.scalar_one_or_none()
    
    if not watchlist_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist item not found"
        )
    
    # Delete
    await db.delete(watchlist_item)
    await db.commit()
    
    # Invalidate cache
    await redis.delete(f"watchlist:{user.id}")
    
    logger.info(f"Watchlist item removed | User: {user.id} | Item: {item_id}")
    
    return None


@router.get("/check/{product_id}")
async def check_watchlist_status(
    product_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Check if product is in user's watchlist
    
    Useful for showing "heart" icon status on product cards
    """
    result = await db.execute(
        select(UserWatchlist)
        .where(
            and_(
                UserWatchlist.user_id == user.id,
                UserWatchlist.product_id == product_id
            )
        )
    )
    item = result.scalar_one_or_none()
    
    if item:
        return {
            "in_watchlist": True,
            "watchlist_id": str(item.id),
            "target_price": item.target_price,
            "notify": item.notify
        }
    
    return {
        "in_watchlist": False
    }
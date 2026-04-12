"""
Watchlist API Routes
Price tracking and alert management
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from typing import List
from datetime import datetime, timedelta
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
from app.services.plan_catalog import get_plan_catalog, get_plan_limit

logger = logging.getLogger(__name__)
router = APIRouter()

WATCHLIST_GRACE_DAYS = 2


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


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


def _parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


async def _get_watchlist_state(user: User, db: AsyncSession) -> dict:
    plan_catalog = await get_plan_catalog(db)
    usage_stats = dict(user.usage_stats or {})
    current_plan = str(user.plan).lower()
    base_limit = get_plan_limit(plan_catalog, current_plan, "watchlist_limit", 5)
    watchlist_bonus = int(usage_stats.get("watchlist_bonus") or 0)
    limit = base_limit + watchlist_bonus
    grace_until = _parse_datetime(usage_stats.get("watchlist_grace_until"))
    now = datetime.utcnow()
    grace_active = bool(grace_until and grace_until > now)
    grace_days_remaining = int((grace_until - now).days) if grace_active else None

    return {
        "base_limit": base_limit,
        "limit": limit,
        "watchlist_bonus": watchlist_bonus,
        "grace_until": grace_until,
        "is_grace_period": grace_active,
        "grace_days_remaining": grace_days_remaining,
        "warning_message": usage_stats.get("watchlist_grace_reason"),
    }


async def _prune_excess_watchlist_items(user: User, db: AsyncSession, redis: RedisClient, limit: int) -> int:
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user.id)
        .order_by(UserWatchlist.created_at.asc(), UserWatchlist.id.asc())
    )
    watchlist_items = result.scalars().all()
    current_count = len(watchlist_items)

    if current_count <= limit:
        return 0

    prune_count = current_count - limit
    for item in watchlist_items[:prune_count]:
        await db.delete(item)

    await db.commit()
    await redis.delete(f"watchlist:{user.id}")

    logger.warning(
        f"Watchlist auto-pruned | User: {user.id} | Removed: {prune_count} | Limit: {limit}"
    )

    return prune_count


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
    
    watchlist_state = await _get_watchlist_state(user, db)

    # Auto-prune only after the grace window has expired
    pruned_count = 0
    if not watchlist_state["is_grace_period"]:
        pruned_count = await _prune_excess_watchlist_items(user, db, redis, watchlist_state["limit"])

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
    limit = watchlist_state["limit"]
    total_count = len(items)
    over_limit_count = max(0, total_count - limit)
    warning_message = None

    if over_limit_count > 0:
        if watchlist_state["is_grace_period"]:
            remaining = watchlist_state["grace_days_remaining"]
            warning_message = (
                f"Grace period active: remove {over_limit_count} item{'s' if over_limit_count != 1 else ''} within {remaining} day{'s' if remaining != 1 else ''}."
                if remaining is not None
                else f"Grace period active: remove {over_limit_count} excess item{'s' if over_limit_count != 1 else ''}."
            )
        else:
            warning_message = (
                f"Watchlist exceeds your limit by {over_limit_count} item{'s' if over_limit_count != 1 else ''}."
            )
    
    response = WatchlistResponse(
        items=items,
        total_count=total_count,
        limit=limit,
        limit_reached=total_count >= limit,
        is_grace_period=watchlist_state["is_grace_period"],
        grace_days_remaining=watchlist_state["grace_days_remaining"],
        over_limit_count=over_limit_count,
        warning_message=warning_message,
        pruned_count=pruned_count,
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
    watchlist_state = await _get_watchlist_state(user, db)
    limit = watchlist_state["limit"]

    # If grace has expired, auto-prune before allowing any more actions.
    if not watchlist_state["is_grace_period"]:
        await _prune_excess_watchlist_items(user, db, redis, limit)

    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user.id)
    )
    current_count = len(result.scalars().all())

    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Watchlist limit reached ({limit} items)."
                if not watchlist_state["is_grace_period"]
                else f"Watchlist grace period active. Remove {current_count - limit + 1} item{'s' if current_count - limit + 1 != 1 else ''} before adding more."
            )
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
    # Resolve the watchlist row by either watchlist item ID or product ID.
    # The frontend can send either form depending on where removal is triggered.
    result = await db.execute(
        select(UserWatchlist).where(
            and_(
                UserWatchlist.user_id == user.id,
                (UserWatchlist.id == item_id) | (UserWatchlist.product_id == item_id)
            )
        )
    )
    watchlist_item = result.scalar_one_or_none()

    if not watchlist_item:
        # Treat already-removed items as success so stale UI state does not surface
        # an unnecessary error after the list has refreshed.
        logger.info(f"Watchlist item already absent | User: {user.id} | Item: {item_id}")
        return None
    
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
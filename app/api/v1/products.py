"""
Product Detail & Price History Routes

CENTRALIZED DATA ACCESS:
- Uses QueryService for all database operations
- Uses BusinessLogic for all data formatting and calculations
- Direct database-to-frontend communication (no Redis caching)
- Real-time data always fresh

✅ FIXED: Refresh endpoint now gracefully handles scraper failures
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import inspect

from app.core.database import get_db
from app.core.config import settings
from app.core.redis_client import RedisClient
from app.models import Product, ProductListing, PriceHistory, User, Platform as PlatformModel
from app.schemas import (
    ProductResponse,
    PriceHistoryResponse,
    Platform,
    PlatformPriceSnapshot,
    LocationPriceRefreshRequest,
    LocationRefreshPriceResponse,
)
from app.api.deps import get_current_user
from app.services.queries import QueryService
from app.services.logic import BusinessLogic

logger = logging.getLogger(__name__)
router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _compute_freshness_status(last_updated_at: datetime) -> str:
    age_hours = max(0.0, (_utc_now() - _ensure_utc(last_updated_at)).total_seconds() / 3600)
    if age_hours < 2:
        return "fresh"
    if age_hours < 12:
        return "stale"
    return "very_stale"


def _build_location_cache_key(
    product_id: str,
    pincode: str,
    state: Optional[str],
    platform: Optional[Platform],
) -> str:
    scope = platform.value if platform else "all"
    state_key = (state or "").strip().lower().replace(" ", "_")
    return f"location_price:{product_id}:{pincode}:{state_key}:{scope}"


async def _maybe_apply_location_context(
    handler: Any,
    pincode: str,
    state: Optional[str],
    platform_name: str,
) -> bool:
    """
    Best-effort location injection hook.
    Handlers can optionally implement one of these methods:
    - set_location_context(pincode: str, state: Optional[str])
    - set_pincode(pincode: str)
    """
    try:
        if hasattr(handler, "set_location_context"):
            fn = getattr(handler, "set_location_context")
            result = fn(pincode=pincode, state=state)
            if inspect.isawaitable(result):
                await result
            return True

        if hasattr(handler, "set_pincode"):
            fn = getattr(handler, "set_pincode")
            result = fn(pincode)
            if inspect.isawaitable(result):
                await result
            return True
    except Exception as e:
        logger.warning(f"Location context hook failed on {platform_name}: {e}")

    return False


async def _append_price_history_if_changed(
    db: AsyncSession,
    listing: ProductListing,
    new_price: float,
    recorded_at: datetime,
) -> bool:
    """Insert a history row only when it differs from the latest stored snapshot."""
    latest_result = await db.execute(
        select(PriceHistory.price, PriceHistory.in_stock)
        .where(PriceHistory.product_listing_id == listing.id)
        .order_by(PriceHistory.recorded_at.desc(), PriceHistory.id.desc())
        .limit(1)
    )
    latest_row = latest_result.first()

    normalized_in_stock = listing.in_stock if listing.in_stock is not None else True
    if latest_row is not None:
        latest_price_raw, latest_in_stock_raw = latest_row
        latest_price = float(latest_price_raw) if latest_price_raw is not None else None
        latest_in_stock = latest_in_stock_raw if latest_in_stock_raw is not None else True

        if latest_price is not None and abs(float(new_price) - latest_price) <= 0.01 and bool(latest_in_stock) == bool(normalized_in_stock):
            return False

    db.add(
        PriceHistory(
            product_listing_id=listing.id,
            price=Decimal(str(new_price)),
            in_stock=normalized_in_stock,
            recorded_at=recorded_at,
        )
    )
    return True


def _to_positive_float(value: Any) -> Optional[float]:
    """Convert numeric-like input to positive float, else None."""
    if value is None:
        return None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _to_valid_discount(value: Any) -> Optional[float]:
    """Normalize discount to a practical percentage range."""
    if value is None:
        return None
    try:
        parsed = float(value)
        if 0 < parsed <= 95:
            return round(parsed, 1)
    except (TypeError, ValueError):
        return None
    return None


def _normalize_live_price_snapshot(
    current_price_raw: Any,
    original_price_raw: Any,
    discount_raw: Any,
    fallback_original_price: Any = None,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Enforce a stable pricing snapshot before DB writes.

    Guarantees:
    - current_price is payable/live price
    - original_price is kept only when it is strictly greater than current_price
    - discount is recomputed when original_price is valid
    """
    current_price = _to_positive_float(current_price_raw)
    if current_price is None:
        return None, None, None

    original_price = _to_positive_float(original_price_raw)
    if original_price is None:
        original_price = _to_positive_float(fallback_original_price)

    # Defensive reorder if source extraction returns swapped values.
    if original_price is not None and original_price <= current_price:
        low = min(current_price, original_price)
        high = max(current_price, original_price)
        current_price = low
        original_price = high if high > low else None

    # Guard against extraction outliers like 44 captured instead of 4499.
    if original_price is not None and current_price > 0:
        ratio = original_price / current_price
        if ratio >= 8.0 and current_price < 100.0 and original_price >= 1000.0:
            current_price = original_price
            original_price = None

    # Guard against decimal-strip inflation (e.g. 12900.00 -> 1290000).
    # If original is wildly high and dividing by 100 yields a sane strike price,
    # normalize it back instead of exposing noisy MRP to clients.
    if original_price is not None and current_price > 0:
        ratio = original_price / current_price
        if ratio >= 20.0 and original_price >= 100000.0:
            corrected_original = original_price / 100.0
            if corrected_original > current_price and corrected_original / current_price <= 5.0:
                original_price = corrected_original

    discount_percent: Optional[float] = None
    if original_price is not None and original_price > current_price:
        discount_percent = round(((original_price - current_price) / original_price) * 100, 1)
    else:
        original_price = None
        discount_percent = _to_valid_discount(discount_raw)

    return current_price, original_price, discount_percent


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get complete product details with all platform listings
    
    ✅ Direct DB access (no cache)
    ✅ Real-time prices
    ✅ All platforms in one response
    ✅ Cross-platform comparison data included
    """
    try:
        # Get product from DB
        query_service = QueryService(db)
        
        # ✅ FIX: Handle integer product IDs correctly (string conversion)
        product = await query_service.get_product_by_id(str(product_id))
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get all listings for this product
        listings = await query_service.get_product_listings(str(product_id), order_by="price_asc")
        
        # Filter to valid listings only
        valid_listings = BusinessLogic.filter_valid_listings(listings, product)
        
        if not valid_listings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No high-confidence listings available for this product"
            )
        
        logger.debug(
            f"Product {product_id}: "
            f"Fetched {len(valid_listings)} valid listings (total: {len(listings)})"
        )
        
        # Format and return response
        response = BusinessLogic.format_product_response(product, valid_listings)
        logger.info(f"Product fetched: {product_id} | User: {user.id} | Listings: {len(valid_listings)}")
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch product details: {str(e)[:100]}"
        )


@router.get("/{product_id}/price-history", response_model=PriceHistoryResponse)
async def get_price_history(
    product_id: str,
    platform: Platform,
    days: int = 120,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get price history for product on specific platform
    
    ✅ Direct DB access (no cache)
    ✅ Full history returned
    ✅ Real-time data
    """
    try:
        if days > 365:
            days = 365
        
        query_service = QueryService(db)
        
        # Verify product exists
        product = await query_service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get listing for this platform
        listing = await query_service.get_listing_by_platform(product_id, platform.value)
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not available on {platform.value}"
            )
        
        # Verify listing is valid
        if not BusinessLogic.is_listing_allowed(listing) or \
           not BusinessLogic.is_variant_consistent(listing, product):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product listing not available on {platform.value}"
            )
        
        # Get price history
        history = await query_service.get_price_history(
            product_id,
            platform.value,
            days=days
        )
        
        # Format and return response
        response = BusinessLogic.format_price_history_response(product, listing, history)
        logger.info(
            f"Price history: Product {product_id} | Platform: {platform.value} | "
            f"Records: {len(history)} | User: {user.id}"
        )
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching price history for {product_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch price history: {str(e)[:100]}"
        )


@router.post("/{product_id}/refresh-price", response_model=ProductResponse)
async def refresh_product_price(
    product_id: str,
    platform: Optional[Platform] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Force refresh prices for a specific product by scraping its listing URLs live
    
    ✅ FIXED: Graceful fallback to DB data when scraper fails
    ✅ No 503 errors - always returns latest DB snapshot
    ✅ Proper error handling with rollback
    """
    query_service = QueryService(db)
    
    # =========================================================================
    # STEP 1: Verify product exists and get current DB data
    # =========================================================================
    try:
        product = await query_service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get all listings for this product
        all_listings = await query_service.get_product_listings(product_id)
        
        # Filter to valid listings
        filtered_listings = BusinessLogic.filter_valid_listings(all_listings, product)
        
        # Further filter by platform if specified
        if platform:
            filtered_listings = [
                l for l in filtered_listings
                if hasattr(l, "platform") and l.platform and 
                l.platform.name.lower() == platform.value
            ]
        
        if not filtered_listings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No eligible listings found to refresh"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading product {product_id} for refresh: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load product: {str(e)[:100]}"
        )
    
    # =========================================================================
    # STEP 2: Attempt live scraping (with graceful failure handling)
    # =========================================================================
    refresh_started_at = _utc_now()
    now_utc = refresh_started_at
    refreshed_count = 0
    changed_count = 0
    failed_platforms = []
    refreshed_platforms: List[str] = []
    attempted_platforms: List[str] = []
    scraper_available = False
    
    # ✅ FIX 1: Wrap scraper import in try/except
    try:
        from app.services.scraper.factory import get_platform_handler
        scraper_available = True
    except ImportError as e:
        logger.error(f"❌ Scraper module not available: {e}")
        scraper_available = False
    except Exception as e:
        logger.error(f"❌ Unexpected error importing scraper: {e}")
        scraper_available = False
    
    # Only attempt scraping if module is available
    if scraper_available:
        for listing in filtered_listings:
            platform_name = (
                listing.platform.name.lower()
                if hasattr(listing, "platform") and listing.platform
                else None
            )
            if not platform_name or not listing.product_url:
                continue

            attempted_platforms.append(platform_name)
            
            try:
                # ✅ FIX 2: Pass db session to handler for healing persistence
                handler = await get_platform_handler(platform_name, db=db)
                if not handler:
                    failed_platforms.append(platform_name)
                    continue
                
                # Scrape live product data
                product_data = await handler.get_product(listing.product_url)
                live_price = getattr(product_data, "current_price", None) if product_data else None
                if not product_data or live_price is None:
                    listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                    listing.last_error = "No data from live refresh"
                    failed_platforms.append(platform_name)
                    continue
                
                refreshed_count += 1
                refreshed_platforms.append(platform_name)
                old_price = listing.current_price
                previous_in_stock = listing.in_stock

                normalized_price, normalized_original, normalized_discount = _normalize_live_price_snapshot(
                    current_price_raw=live_price,
                    original_price_raw=getattr(product_data, "original_price", None),
                    discount_raw=getattr(product_data, "discount_percent", None),
                    fallback_original_price=listing.original_price,
                )
                if normalized_price is None:
                    listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                    listing.last_error = "Invalid live price snapshot"
                    failed_platforms.append(platform_name)
                    continue
                
                # Update stock status
                if getattr(product_data, "in_stock", None) is not None:
                    listing.in_stock = bool(product_data.in_stock)

                # Keep listing snapshot aligned with latest live scrape fields.
                listing.current_price = normalized_price
                listing.original_price = normalized_original
                listing.discount_percent = normalized_discount

                if getattr(product_data, "rating", None) is not None:
                    listing.rating = float(product_data.rating)

                if getattr(product_data, "review_count", None) is not None:
                    listing.review_count = int(product_data.review_count)

                if getattr(product_data, "image_url", None):
                    listing.image_url = str(product_data.image_url)

                if getattr(product_data, "title", None):
                    listing.title = str(product_data.title)
                
                # Update scrape metadata
                listing.last_scraped = now_utc
                listing.scrape_error_count = 0
                listing.last_error = None
                
                # Update price if new value available
                if normalized_price is not None:
                    await _append_price_history_if_changed(
                        db=db,
                        listing=listing,
                        new_price=normalized_price,
                        recorded_at=now_utc,
                    )
                    
                    # Track price changes
                    if old_price is None or abs(float(normalized_price) - float(old_price)) > 0.01:
                        changed_count += 1
                        listing.last_price_change_at = now_utc
            
            except Exception as e:
                listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                listing.last_error = str(e)[:500]
                logger.error(f"Scrape error for listing {listing.id}: {e}")
                failed_platforms.append(platform_name)
    
    # =========================================================================
    # STEP 3: Commit changes (with proper error handling)
    # =========================================================================
    # ✅ FIX 3: Wrap commit in try/except with rollback
    commit_success = False
    try:
        await db.commit()
        commit_success = True
        logger.info(
            f"✅ Refresh commit successful: Product {product_id} | "
            f"Refreshed: {refreshed_count} | Changed: {changed_count}"
        )
    except Exception as e:
        logger.error(f"❌ Error committing refresh changes: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        # Continue to return DB data even if commit failed
    
    # =========================================================================
    # STEP 4: Return response with explicit live-refresh metadata
    # =========================================================================
    if refreshed_count == 0:
        unique_failed = sorted(set(failed_platforms))
        failed_text = ", ".join(unique_failed) if unique_failed else "all configured platforms"
        
        logger.warning(
            f"⚠️ Live refresh failed for {failed_text} on product {product_id}. "
            f"Returning current DB snapshot. Scraper available: {scraper_available}"
        )
        
        # Don't raise error - just return DB data
        # User will see current prices even if scrape failed
    else:
        logger.info(
            f"✅ Live refresh: Product {product_id} | "
            f"Refreshed: {refreshed_count} | Changed: {changed_count} | User: {user.id}"
        )

    response = await get_product(product_id=product_id, user=user, db=db)

    elapsed_ms = int((_utc_now() - refresh_started_at).total_seconds() * 1000)
    refresh_meta = {
        "requested_platform": platform.value if platform else "all",
        "scraper_available": scraper_available,
        "attempted_count": len(attempted_platforms),
        "attempted_platforms": sorted(set(attempted_platforms)),
        "refreshed_count": refreshed_count,
        "refreshed_platforms": sorted(set(refreshed_platforms)),
        "changed_count": changed_count,
        "failed_platforms": sorted(set(failed_platforms)),
        "commit_success": commit_success,
        "live_used": bool(refreshed_count > 0 and commit_success),
        "performed_at": now_utc.isoformat(),
        "duration_ms": elapsed_ms,
    }

    current_stats = dict(response.stats or {})
    current_stats["live_refresh"] = refresh_meta
    response.stats = current_stats
    return response


@router.post("/{product_id}/refresh-price/location", response_model=LocationRefreshPriceResponse)
async def refresh_product_price_by_location(
    product_id: str,
    payload: LocationPriceRefreshRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Location-aware live refresh.

    Hybrid mode behavior:
    - Uses global listing prices as baseline
    - Applies pincode/state context when platform handler supports it
    - Caches response in Redis for short TTL to reduce repeated scraping
    - Does not persist pincode/state into SQL tables
    """
    if not getattr(settings, "LOCATION_REFRESH_ENABLED", True):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location refresh is disabled"
        )

    cache_key = _build_location_cache_key(
        product_id=product_id,
        pincode=payload.pincode,
        state=payload.state,
        platform=payload.platform,
    )
    redis_client = RedisClient()

    if not payload.force_refresh:
        cached = await redis_client.get_json(cache_key)
        if isinstance(cached, dict):
            try:
                cached["cache_hit"] = True
                return LocationRefreshPriceResponse(**cached)
            except Exception:
                logger.warning("Invalid cached location payload, rebuilding")

    query_service = QueryService(db)
    product = await query_service.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    all_listings = await query_service.get_product_listings(product_id)
    valid_listings = BusinessLogic.filter_valid_listings(all_listings, product)

    if payload.platform:
        valid_listings = [
            listing for listing in valid_listings
            if hasattr(listing, "platform") and listing.platform and listing.platform.name.lower() == payload.platform.value
        ]

    if not valid_listings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No eligible listings found for location refresh"
        )

    max_listings = max(1, int(getattr(settings, "LOCATION_REFRESH_MAX_LISTINGS_PER_REQUEST", 8)))
    valid_listings = valid_listings[:max_listings]

    from app.services.scraper.factory import get_platform_handler

    now_utc = _utc_now()
    snapshots: List[PlatformPriceSnapshot] = []
    location_applied_platforms = 0
    changed_count = 0
    refreshed_count = 0
    refresh_errors: List[str] = []

    for listing in valid_listings:
        platform_name = (
            listing.platform.name.lower()
            if hasattr(listing, "platform") and listing.platform
            else "amazon"
        )
        platform_enum = BusinessLogic._get_platform_enum(platform_name)

        try:
            handler = await get_platform_handler(platform_name, db=db)
            if not handler:
                refresh_errors.append(f"{platform_name}: handler unavailable")
                snapshots.append(
                    PlatformPriceSnapshot(
                        platform=platform_enum,
                        current_price=Decimal(str(listing.current_price or 0)),
                        original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
                        discount_percentage=int(listing.discount_percent) if listing.discount_percent else None,
                        in_stock=listing.in_stock if listing.in_stock is not None else True,
                        last_updated_at=listing.last_scraped or now_utc,
                        location_applied=False,
                        location_scope="global",
                    )
                )
                continue

            location_applied = await _maybe_apply_location_context(
                handler=handler,
                pincode=payload.pincode,
                state=payload.state,
                platform_name=platform_name,
            )
            if location_applied:
                location_applied_platforms += 1

            product_data = await handler.get_product(listing.product_url)
            if not product_data or getattr(product_data, "current_price", None) is None:
                refresh_errors.append(f"{platform_name}: live price unavailable")
                snapshots.append(
                    PlatformPriceSnapshot(
                        platform=platform_enum,
                        current_price=Decimal(str(listing.current_price or 0)),
                        original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
                        discount_percentage=int(listing.discount_percent) if listing.discount_percent else None,
                        in_stock=listing.in_stock if listing.in_stock is not None else True,
                        last_updated_at=listing.last_scraped or now_utc,
                        location_applied=False,
                        location_scope="global",
                    )
                )
                continue

            refreshed_count += 1
            old_price = float(listing.current_price) if listing.current_price is not None else None
            previous_in_stock = listing.in_stock

            normalized_price, normalized_original, normalized_discount = _normalize_live_price_snapshot(
                current_price_raw=getattr(product_data, "current_price", None),
                original_price_raw=getattr(product_data, "original_price", None),
                discount_raw=getattr(product_data, "discount_percent", None),
                fallback_original_price=listing.original_price,
            )
            if normalized_price is None:
                refresh_errors.append(f"{platform_name}: invalid live price snapshot")
                snapshots.append(
                    PlatformPriceSnapshot(
                        platform=platform_enum,
                        current_price=Decimal(str(listing.current_price or 0)),
                        original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
                        discount_percentage=int(listing.discount_percent) if listing.discount_percent else None,
                        in_stock=listing.in_stock if listing.in_stock is not None else True,
                        last_updated_at=listing.last_scraped or now_utc,
                        location_applied=False,
                        location_scope="global",
                    )
                )
                continue

            listing.current_price = normalized_price
            listing.original_price = normalized_original
            listing.discount_percent = normalized_discount
            if getattr(product_data, "in_stock", None) is not None:
                listing.in_stock = bool(product_data.in_stock)

            listing.last_scraped = now_utc
            listing.scrape_error_count = 0
            listing.last_error = None

            await _append_price_history_if_changed(
                db=db,
                listing=listing,
                new_price=normalized_price,
                recorded_at=now_utc,
            )

            if old_price is None or abs(normalized_price - old_price) > 0.01:
                changed_count += 1
                listing.last_price_change_at = now_utc

            snapshots.append(
                PlatformPriceSnapshot(
                    platform=platform_enum,
                    current_price=Decimal(str(normalized_price)),
                    original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
                    discount_percentage=int(listing.discount_percent) if listing.discount_percent else None,
                    in_stock=listing.in_stock if listing.in_stock is not None else True,
                    last_updated_at=now_utc,
                    location_applied=location_applied,
                    location_scope="pincode" if location_applied else "global",
                    pincode=payload.pincode if location_applied else None,
                    state=payload.state if location_applied else None,
                )
            )

        except Exception as e:
            listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
            listing.last_error = str(e)[:500]
            refresh_errors.append(f"{platform_name}: {str(e)[:80]}")
            snapshots.append(
                PlatformPriceSnapshot(
                    platform=platform_enum,
                    current_price=Decimal(str(listing.current_price or 0)),
                    original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
                    discount_percentage=int(listing.discount_percent) if listing.discount_percent else None,
                    in_stock=listing.in_stock if listing.in_stock is not None else True,
                    last_updated_at=listing.last_scraped or now_utc,
                    location_applied=False,
                    location_scope="global",
                )
            )

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Location refresh commit failed for product {product_id}: {e}", exc_info=True)
        await db.rollback()

    in_stock_snapshots = [s for s in snapshots if s.current_price > 0 and s.in_stock]
    candidate_snapshots = in_stock_snapshots or [s for s in snapshots if s.current_price > 0]
    if not candidate_snapshots:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to build price response from refreshed data"
        )

    best_snapshot = min(candidate_snapshots, key=lambda s: s.current_price)
    message = None
    if refresh_errors:
        message = f"Partial refresh completed. {len(refresh_errors)} platform(s) used global fallback."

    response_obj = LocationRefreshPriceResponse(
        product_id=product_id,
        pincode=payload.pincode,
        state=payload.state,
        best_price=best_snapshot.current_price,
        best_platform=best_snapshot.platform,
        all_platforms=snapshots,
        last_updated_at=now_utc,
        freshness_status=_compute_freshness_status(now_utc),
        cache_hit=False,
        location_applied_platforms=location_applied_platforms,
        message=message,
    )

    cache_ttl = max(60, int(getattr(settings, "LOCATION_REFRESH_CACHE_TTL_SECONDS", 1200)))
    await redis_client.set_json(cache_key, response_obj.model_dump(mode="json"), ttl=cache_ttl)

    logger.info(
        f"Location refresh: product={product_id} pincode={payload.pincode} "
        f"refreshed={refreshed_count} changed={changed_count} "
        f"location_applied={location_applied_platforms} cache_ttl={cache_ttl}s user={user.id}"
    )

    return response_obj


@router.get("/{product_id}/cross-platform-variants")
async def get_cross_platform_variants(
    product_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all variants of the same product across different platforms
    
    Used for: "See this product on other platforms with different variants"
    
    Returns:
        {
            "base_product": { product info },
            "variants": [
                {
                    "variant_fingerprint": "iPhone 15 Pro 256GB Gold",
                    "platforms": [ { platform, price, url }, ... ]
                },
                ...
            ]
        }
    
    ✅ Groups by variant (e.g., color, storage)
    ✅ Shows all platform availability for each variant
    ✅ Used in cross-platform comparison UI
    """
    try:
        query_service = QueryService(db)
        
        # Get base product
        product = await query_service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Build product family by fingerprint to avoid missing cross-platform matches
        family_product_ids = {str(product.id)}
        if getattr(product, "base_fingerprint", None):
            family_result = await db.execute(
                select(Product.id).where(Product.base_fingerprint == product.base_fingerprint)
            )
            family_product_ids.update(str(pid) for pid in family_result.scalars().all())
        elif getattr(product, "variant_fingerprint", None):
            family_result = await db.execute(
                select(Product.id).where(Product.variant_fingerprint == product.variant_fingerprint)
            )
            family_product_ids.update(str(pid) for pid in family_result.scalars().all())

        family_products = await query_service.get_products_by_ids(list(family_product_ids))
        product_by_id = {str(p.id): p for p in family_products}

        all_listings: List[ProductListing] = []
        seen_listing_ids = set()
        for family_product_id in family_product_ids:
            listings_for_product = await query_service.get_product_listings(family_product_id, order_by="price_asc")
            for listing in listings_for_product:
                listing_id = str(getattr(listing, "id", ""))
                if listing_id and listing_id not in seen_listing_ids:
                    all_listings.append(listing)
                    seen_listing_ids.add(listing_id)

        # For family view, keep all listing-allowed records and validate variant consistency
        # against their own parent product (not only the currently opened product).
        valid_listings: List[ProductListing] = []
        for listing in all_listings:
            parent_product = product_by_id.get(str(getattr(listing, "product_id", "")))
            if not BusinessLogic.is_listing_allowed(listing):
                continue
            if parent_product and not BusinessLogic.is_variant_consistent(listing, parent_product):
                continue
            valid_listings.append(listing)
        
        if not valid_listings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No available listings for this product"
            )
        
        # Group by variant fingerprint
        variants_map = {}
        for listing in valid_listings:
            parent_product = product_by_id.get(str(getattr(listing, "product_id", "")))
            variant_fp = (
                getattr(listing, "variant_fingerprint", None)
                or getattr(parent_product, "variant_fingerprint", None)
                or "standard"
            )
            if variant_fp not in variants_map:
                variants_map[variant_fp] = []
            variants_map[variant_fp].append(listing)
        
        # Format response
        variants_data = []
        for variant_fp, listings_for_variant in variants_map.items():
            platform_data = []
            for listing in sorted(listings_for_variant, key=lambda x: x.current_price or 0):
                parent_product = product_by_id.get(str(getattr(listing, "product_id", ""))) or product
                platform_name = "amazon"
                if hasattr(listing, "platform") and listing.platform:
                    platform_name = listing.platform.name.lower()
                
                platform_data.append({
                    "product_id": str(getattr(listing, "product_id", "")),
                    "title": getattr(parent_product, "title", product.title),
                    "platform": platform_name,
                    "price": float(listing.current_price or 0),
                    "original_price": float(listing.original_price or 0) if listing.original_price else None,
                    "discount_percent": int(listing.discount_percent) if listing.discount_percent else None,
                    "url": listing.product_url or "",
                    "in_stock": listing.in_stock if listing.in_stock is not None else False,
                    "rating": listing.rating,
                    "review_count": listing.review_count,
                    "last_scraped": listing.last_scraped.isoformat() if listing.last_scraped else None
                })
            
            variants_data.append({
                "variant_fingerprint": variant_fp,
                "platform_count": len(platform_data),
                "platforms": platform_data,
                "cheapest_price": min(p["price"] for p in platform_data) if platform_data else 0
            })
        
        # Sort by cheapest price
        variants_data.sort(key=lambda x: x["cheapest_price"])
        
        response_data = {
            "product_id": str(product.id),
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "image_url": product.image_url,
            "family_product_count": len(family_product_ids),
            "total_platforms": len(set(l.platform_id for l in valid_listings)),
            "total_listings": len(valid_listings),
            "variants": variants_data
        }
        
        logger.info(
            f"Cross-platform variants: Product {product_id} | "
            f"Family products: {len(family_product_ids)} | "
            f"Variants: {len(variants_data)} | Platforms: {response_data['total_platforms']} | "
            f"User: {user.id}"
        )
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching cross-platform variants for {product_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch cross-platform comparison: {str(e)[:100]}"
        )
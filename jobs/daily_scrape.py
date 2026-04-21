"""
Daily Price Scraping Job
========================

Runs at 2:00 AM IST to update all product prices

Features:
- Scrapes products in active watchlists (prioritized)
- Updates recently searched products
- Rate limiting per platform
- Error recovery and retry logic
- Price history recording
- Detailed logging to system_logs table

Author: DealHunt
Version: 2.0 (Cleaned & Enhanced)
"""

import logging
import asyncio
import random
import re
import pytz
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from decimal import Decimal

# Add parent directory to Python path for imports
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 🔧 WINDOWS FIX: Silence Proactor Event Loop Warning
if sys.platform == 'win32':
    from asyncio.proactor_events import _ProactorBasePipeTransport
    def silence_proactor_del(self): pass
    _ProactorBasePipeTransport.__del__ = silence_proactor_del

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, case, func, literal

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import (
    Product, ProductListing, Platform, UserWatchlist,
    SystemLog, PriceHistory
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

MAX_PRODUCTS_PER_RUN = max(1, int(getattr(settings, "DAILY_SCRAPE_MAX_PRODUCTS_PER_RUN", 500)))
SCRAPE_INTERVAL_HOURS = 6  # Scrape products not updated in 24h
# Slightly slower default spacing helps continuous runs avoid burst warnings.
DELAY_BETWEEN_PRODUCTS = max(0, int(getattr(settings, "DAILY_SCRAPE_DELAY_SECONDS", 4)))
MAX_ERRORS_BEFORE_SKIP = max(3, int(getattr(settings, "DAILY_SCRAPE_MAX_ERRORS_BEFORE_SKIP", 8)))
BATCH_SIZE = 60  # Commit after each batch
RATE_LIMIT_COOLDOWN_SECONDS = max(30, int(getattr(settings, "DAILY_SCRAPE_RATE_LIMIT_COOLDOWN_SECONDS", 120)))

# Price spike guard: reject newly scraped price if it deviates by more than
# this factor from the previous known price.  Set to 0 to disable.
PRICE_SPIKE_MAX_RATIO = float(getattr(settings, "DAILY_SCRAPE_PRICE_SPIKE_MAX_RATIO", 5.0))

# Per-product scrape timeout so a single hung page cannot stall the loop.
PER_PRODUCT_SCRAPE_TIMEOUT_SECONDS = int(getattr(settings, "DAILY_SCRAPE_PER_PRODUCT_TIMEOUT", 60))

DEFAULT_INTERVAL_MINUTES = max(5, int(getattr(settings, "DAILY_SCRAPE_DEFAULT_INTERVAL_MINUTES", 720)))
WATCHLIST_INTERVAL_MINUTES = max(5, int(getattr(settings, "DAILY_SCRAPE_WATCHLIST_INTERVAL_MINUTES", 30)))
FAST_RECHECK_INTERVAL_MINUTES = max(5, int(getattr(settings, "DAILY_SCRAPE_FAST_RECHECK_INTERVAL_MINUTES", 20)))
PLATFORM_INTERVAL_MINUTES = {
    "amazon": max(5, int(getattr(settings, "DAILY_SCRAPE_AMAZON_INTERVAL_MINUTES", 120))),
    "flipkart": max(5, int(getattr(settings, "DAILY_SCRAPE_FLIPKART_INTERVAL_MINUTES", 360))),
    "myntra": max(5, int(getattr(settings, "DAILY_SCRAPE_MYNTRA_INTERVAL_MINUTES", 720))),
    "meesho": max(5, int(getattr(settings, "DAILY_SCRAPE_MEESHO_INTERVAL_MINUTES", 1440))),
    "nykaa": max(5, int(getattr(settings, "DAILY_SCRAPE_NYKAA_INTERVAL_MINUTES", 1440))),
    "croma": max(5, int(getattr(settings, "DAILY_SCRAPE_CROMA_INTERVAL_MINUTES", 1440))),
}

_RUN_LOCK = asyncio.Lock()


# =============================================================================
# MAIN JOB FUNCTION
# =============================================================================

def is_rate_limit_or_block(
    error: Exception = None,
    error_text: str = None,
    status_code: int = None,
    headers: Dict[str, str] = None
) -> bool:
    """
    ✅ NEW: Enhanced rate limit/block detection
    
    Checks multiple signals:
    - HTTP status codes (429, 503, 520, 522, 524)
    - Retry-After header
    - X-RateLimit headers
    - Error text patterns
    - Captcha/challenge HTML
    
    Args:
        error: Exception object
        error_text: Error message text
        status_code: HTTP status code
        headers: Response headers dict
    
    Returns:
        True if rate limited or blocked
    """
    # 1. Check HTTP status codes
    if status_code in [429, 503, 520, 522, 524]:
        return True
    
    # 2. Check Retry-After header (standard)
    if headers:
        if 'Retry-After' in headers or 'retry-after' in headers:
            return True
        
        # Check X-RateLimit-Remaining
        remaining = headers.get('X-RateLimit-Remaining') or headers.get('x-ratelimit-remaining')
        if remaining is not None:
            try:
                if int(remaining) == 0:
                    return True
            except (ValueError, TypeError):
                pass
    
    # 3. Check error text patterns
    if error_text:
        error_lower = error_text.lower()
        rate_limit_keywords = [
            "rate limit", "429", "burst limit", "too many requests",
            "cooling down", "please slow down", "too many login attempts",
            "captcha", "challenge", "verify you're human", "403 forbidden",
            "access denied", "blocked", "bot detection", "cloudflare",
            "akamai", "perimeter", "security check"
        ]
        if any(keyword in error_lower for keyword in rate_limit_keywords):
            return True
    
    # 4. Check exception type
    if error:
        error_str = str(error).lower()
        if any(keyword in error_str for keyword in ["rate limit", "too many", "captcha", "blocked"]):
            return True
        
        # Check exception class name
        error_class = error.__class__.__name__.lower()
        if "ratelimit" in error_class or "throttle" in error_class:
            return True
    
    return False


def _extract_retry_after_seconds(error: Exception = None, error_text: str = None) -> Optional[int]:
    """Extract retry-after seconds from exception metadata or message text."""
    if error is not None:
        retry_after = getattr(error, "retry_after", None)
        if retry_after is not None:
            try:
                return max(1, int(retry_after))
            except (TypeError, ValueError):
                pass

    text = error_text or (str(error) if error is not None else "")
    if not text:
        return None

    match = re.search(r"retry\s*after\s*(\d+)\s*s?", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"cool(?:ing)?\s*down\s*for\s*(\d+)\s*s?", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None

def _platform_interval_minutes(platform_name: str) -> int:
    """Get base interval in minutes for a platform."""
    return PLATFORM_INTERVAL_MINUTES.get(platform_name.lower(), DEFAULT_INTERVAL_MINUTES)


def _compute_next_scrape_at(
    platform_name: str,
    *,
    is_watchlisted: bool,
    price_changed: bool,
    scrape_failed: bool,
    error_streak: int,
) -> datetime:
    """Compute next scrape schedule using platform policy + adaptive backoff."""
    now_utc = datetime.now(pytz.UTC)

    if scrape_failed:
        backoff_minutes = min(_platform_interval_minutes(platform_name), max(5, 5 * (2 ** max(error_streak - 1, 0))))
        return now_utc + timedelta(minutes=backoff_minutes)

    if price_changed:
        return now_utc + timedelta(minutes=FAST_RECHECK_INTERVAL_MINUTES)

    if is_watchlisted:
        return now_utc + timedelta(minutes=WATCHLIST_INTERVAL_MINUTES)

    return now_utc + timedelta(minutes=_platform_interval_minutes(platform_name))


async def run_daily_scrape(force_all: bool = False, max_products: Optional[int] = None) -> Dict[str, Any]:
    """
    Main daily scrape job
    
    Process:
    1. Get products to scrape (watchlisted + stale)
    2. Group by platform for rate limiting
    3. Scrape each with delays
    4. Update prices in database
    5. Record price history
    6. Log results to system_logs
    
    Returns:
        Dictionary with scrape statistics
    """
    logger.info("🔄 Starting daily price scrape...")
    start_time = datetime.now(pytz.UTC)
    
    stats = {
        "products_found": 0,
        "products_scraped": 0,
        "products_updated": 0,
        "products_failed": 0,
        "price_changes": 0,
        "history_records": 0,
        "total_listings_considered": 0,
        "spike_rejections": 0,
        "rate_limit_incidents": 0,
        "platforms": {},
        "errors": [],
        "duration_seconds": 0
    }
    
    if _RUN_LOCK.locked():
        logger.warning("⚠️ Daily scrape skipped: previous run is still active")
        stats["message"] = "Skipped because previous run is still active"
        return stats

    try:
        async with _RUN_LOCK:
            async with async_session_maker() as db:
                # Import Redis client for cache invalidation
                from app.core.redis_client import get_redis
                redis = await get_redis()
                watchlisted_product_ids = await _get_watchlisted_product_ids(db)

                # Step 1: Get products to scrape
                listings = await _get_products_to_scrape(
                    db,
                    watchlisted_product_ids=watchlisted_product_ids,
                    force_all=force_all,
                    max_products=max_products,
                )
                stats["products_found"] = len(listings)
                
                total_query = select(func.count()).select_from(ProductListing).join(Platform, ProductListing.platform_id == Platform.id).where(Platform.is_active == True)
                stats["total_listings_considered"] = await db.scalar(total_query) or 0

                if not listings:
                    logger.info("✅ No products need scraping")
                    stats["message"] = "No products to scrape"
                    await _log_scrape_results(db, stats, start_time)
                    return stats

                logger.info(f"📦 Found {len(listings)} products to scrape")

                # Step 2: Get active platforms
                platforms = await _get_active_platforms(db)

                # Step 3: Group by platform
                products_by_platform = _group_by_platform(listings, platforms)

                # Step 4: Scrape each platform
                for platform_name, platform_listings in products_by_platform.items():
                    platform_stats = await _scrape_platform(
                        db=db,
                        platform_name=platform_name,
                        listings=platform_listings,
                        watchlisted_product_ids=watchlisted_product_ids,
                    )

                    stats["platforms"][platform_name] = platform_stats
                    stats["products_scraped"] += platform_stats["scraped"]
                    stats["products_updated"] += platform_stats["updated"]
                    stats["products_failed"] += platform_stats["failed"]
                    stats["price_changes"] += platform_stats["price_changes"]
                    stats["history_records"] += platform_stats.get("history_records", 0)
                    stats["spike_rejections"] += platform_stats.get("spike_rejections", 0)
                    stats["rate_limit_incidents"] += platform_stats.get("rate_limits", 0)

                    if platform_stats.get("errors"):
                        stats["errors"].extend(platform_stats["errors"][:5])

                # Step 5: Calculate duration
                stats["duration_seconds"] = round(
                    (datetime.now(pytz.UTC) - start_time).total_seconds(), 2
                )

                # Step 6: Log results
                await _log_scrape_results(db, stats, start_time)

                # Invalidate watchlist cache if prices changed
                if stats["price_changes"] > 0:
                    try:
                        # Get all users who have watchlisted products
                        result = await db.execute(select(UserWatchlist.user_id).distinct())
                        user_ids = result.scalars().all()
                        
                        # Invalidate cache for each user
                        for user_id in user_ids:
                            await redis.delete(f"watchlist:{user_id}")
                        
                        logger.info(f"Invalidated watchlist cache for {len(user_ids)} users after price changes")
                    except Exception as e:
                        logger.warning(f"Failed to invalidate watchlist cache: {e}")

                logger.info(
                    f"✅ Daily scrape completed | "
                    f"Scraped: {stats['products_scraped']} | "
                    f"Updated: {stats['products_updated']} | "
                    f"Failed: {stats['products_failed']} | "
                    f"Price Changes: {stats['price_changes']} | "
                    f"Duration: {stats['duration_seconds']}s"
                )

                return stats
            
    except Exception as e:
        logger.error(f"❌ Daily scrape failed: {e}")
        stats["error"] = str(e)
        stats["duration_seconds"] = round(
            (datetime.now(pytz.UTC) - start_time).total_seconds(), 2
        )
        return stats


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def _get_watchlisted_product_ids(db: AsyncSession) -> set:
    """Get watchlisted product IDs as a set."""
    watchlist_result = await db.execute(select(UserWatchlist.product_id).distinct())
    return {r[0] for r in watchlist_result.fetchall() if r[0] is not None}


async def _get_products_to_scrape(
    db: AsyncSession,
    watchlisted_product_ids: set,
    force_all: bool = False,
    max_products: Optional[int] = None,
) -> List[ProductListing]:
    """Get products that need scraping (prioritized)"""
    cutoff_time = datetime.now(pytz.UTC) - timedelta(hours=SCRAPE_INTERVAL_HOURS)
    now_utc = datetime.now(pytz.UTC)
    max_items = max(1, int(max_products or MAX_PRODUCTS_PER_RUN))
    
    try:
        watchlist_condition = ProductListing.product_id.in_(watchlisted_product_ids) if watchlisted_product_ids else False
        watchlist_sort = case((watchlist_condition, 0), else_=1) if watchlisted_product_ids else literal(1)

        if force_all:
            due_condition = or_(
                ProductListing.last_scraped < cutoff_time,
                ProductListing.last_scraped.is_(None),
                ProductListing.next_scrape_at <= now_utc,
                ProductListing.next_scrape_at.is_(None),
            )
        else:
            due_condition = or_(
                ProductListing.next_scrape_at <= now_utc,
                ProductListing.next_scrape_at.is_(None),
            )

        if watchlisted_product_ids:
            due_condition = or_(watchlist_condition, due_condition)

        query = (
            select(ProductListing)
            .join(Platform, ProductListing.platform_id == Platform.id)
            .where(
                and_(
                    Platform.is_active == True,
                    due_condition,
                )
            )
            .order_by(
                watchlist_sort,
                ProductListing.scrape_priority.asc(),
                func.coalesce(ProductListing.next_scrape_at, ProductListing.last_scraped).asc().nullsfirst(),
            )
            .limit(max_items)
        )
        
        result = await db.execute(query)
        return list(result.scalars().all())
        
    except Exception as e:
        logger.error(f"Error getting products to scrape: {e}")
        return []


async def _get_active_platforms(db: AsyncSession) -> Dict[int, Platform]:
    """Get all active platforms"""
    try:
        result = await db.execute(
            select(Platform).where(Platform.is_active == True)
        )
        platforms = result.scalars().all()
        return {p.id: p for p in platforms}
    except Exception as e:
        logger.error(f"Error getting platforms: {e}")
        return {}


def _group_by_platform(
    listings: List[ProductListing],
    platforms: Dict[int, Platform]
) -> Dict[str, List[ProductListing]]:
    """Group listings by platform name"""
    grouped = {}
    
    for listing in listings:
        platform = platforms.get(listing.platform_id)
        if platform:
            platform_name = platform.name
            if platform_name not in grouped:
                grouped[platform_name] = []
            grouped[platform_name].append(listing)
    
    return grouped


def _apply_platform_cooldown(
    listings: List[ProductListing],
    start_index: int,
    cooldown_until: datetime,
    reason: str,
) -> None:
    """Set next scrape time for current and remaining listings of a blocked platform."""
    for pending in listings[start_index:]:
        pending.next_scrape_at = cooldown_until
        if not pending.last_error:
            pending.last_error = reason[:500]


async def _scrape_platform(
    db: AsyncSession,
    platform_name: str,
    listings: List[ProductListing],
    watchlisted_product_ids: set,
) -> Dict[str, Any]:
    """
    ✅ FIXED: Better error tracking - separate product vs platform failures
    
    Scrapes all listings for a platform with smart error handling:
    - Tracks consecutive_general_errors and consecutive_rate_limits separately
    - Skips individual products on transient errors (not whole platform)
    - Only skips platform after 5 consecutive rate limits
    - Uses enhanced rate limit detection
    """
    logger.info(f"📱 Scraping {platform_name}: {len(listings)} products")
    
    stats = {
        "scraped": 0,
        "updated": 0,
        "failed": 0,
        "history_records": 0,
        "marked_out_of_stock": 0,
        "skipped_low_confidence": 0,
        "skipped_products": 0,
        "price_changes": 0,
        "spike_rejections": 0,  # Fix S1: count price-spike guard triggers
        "rate_limits": 0,
        "errors": []
    }
    
    # ✅ NEW: Separate error tracking
    consecutive_general_errors = 0
    consecutive_rate_limits = 0
    max_rate_limits_before_platform_skip = 5
    
    for i, listing in enumerate(listings, 1):
        now_utc = datetime.now(pytz.UTC)
        is_watchlisted = listing.product_id in watchlisted_product_ids
        
        # Skip low confidence products
        min_confidence = float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))
        if listing.extraction_confidence is not None and listing.extraction_confidence < min_confidence:
            stats["skipped_low_confidence"] += 1
            listing.next_scrape_at = _compute_next_scrape_at(
                platform_name,
                is_watchlisted=is_watchlisted,
                price_changed=False,
                scrape_failed=False,
                error_streak=0,
            )
            continue
        
        # ✅ NEW: Check if too many rate limits (platform-level skip)
        if consecutive_rate_limits >= max_rate_limits_before_platform_skip:
            logger.error(
                f"⚠️ Skipping {platform_name} after {consecutive_rate_limits} "
                f"consecutive rate limits (platform-level)"
            )
            stats["errors"].append(
                f"Platform skipped after {consecutive_rate_limits} rate limits"
            )
            break
        
        try:
            # Scrape product price
            previous_in_stock = listing.in_stock
            scrape_signal = {}
            new_price, scraped_in_stock = await _scrape_product_price(db, platform_name, listing, signal=scrape_signal)
            
            if scraped_in_stock is not None:
                listing.in_stock = scraped_in_stock
            
            # Handle explicit out-of-stock (valid result)
            if scraped_in_stock is False:
                listing.last_scraped = now_utc
                listing.scrape_error_count = 0
                listing.last_error = None
                stock_changed = previous_in_stock is not False
                if stock_changed:
                    listing.last_price_change_at = now_utc

                if listing.current_price is not None and await _record_price_history(
                    db,
                    listing,
                    float(listing.current_price),
                    recorded_at=now_utc,
                ):
                    stats["history_records"] += 1

                listing.next_scrape_at = _compute_next_scrape_at(
                    platform_name,
                    is_watchlisted=is_watchlisted,
                    price_changed=stock_changed,
                    scrape_failed=False,
                    error_streak=0,
                )
                stats["scraped"] += 1
                stats["updated"] += 1
                stats["marked_out_of_stock"] += 1
                
                # ✅ Reset error counters on success
                consecutive_general_errors = 0
                consecutive_rate_limits = 0
                continue
            
            # Handle successful price scrape
            if new_price is not None:
                old_price = listing.current_price
                price_changed = bool(old_price and abs(float(new_price) - float(old_price)) > 0.01)
                prev_stock = previous_in_stock if previous_in_stock is not None else True
                curr_stock = listing.in_stock if listing.in_stock is not None else True
                stock_changed = bool(prev_stock) != bool(curr_stock)
                
                listing.last_scraped = now_utc
                listing.scrape_error_count = 0
                listing.last_error = None
                
                if price_changed:
                    listing.current_price = new_price
                    stats["price_changes"] += 1
                    stats["updated"] += 1
                    listing.last_price_change_at = now_utc
                    logger.debug(f"💰 Price change: {listing.external_id} ₹{old_price} → ₹{new_price}")
                else:
                    listing.current_price = new_price
                    stats["updated"] += 1

                # Dedupe against last recorded row so baseline can be rebuilt safely.
                if await _record_price_history(db, listing, new_price, recorded_at=now_utc):
                    stats["history_records"] += 1
                
                stats["scraped"] += 1
                
                # ✅ Reset error counters on success
                consecutive_general_errors = 0
                consecutive_rate_limits = 0
                
                listing.next_scrape_at = _compute_next_scrape_at(
                    platform_name,
                    is_watchlisted=is_watchlisted,
                    price_changed=price_changed,
                    scrape_failed=False,
                    error_streak=0,
                )
            else:
                # No price extracted (soft failure)
                stats["failed"] += 1
                stats["skipped_products"] += 1
                # Fix S1: track spike guard triggers via local signal dict
                if scrape_signal.get("spike_rejected"):
                    stats["spike_rejections"] += 1
                    listing.last_error = "Price spike rejected"
                else:
                    listing.last_error = "No price extracted"
                listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                listing.next_scrape_at = _compute_next_scrape_at(
                    platform_name,
                    is_watchlisted=is_watchlisted,
                    price_changed=False,
                    scrape_failed=True,
                    error_streak=listing.scrape_error_count,
                )
                consecutive_general_errors += 1
        
        except Exception as e:
            stats["failed"] += 1
            stats["skipped_products"] += 1
            
            error_text = str(e).lower()
            
            # ✅ NEW: Enhanced rate limit detection
            is_rate_limited = is_rate_limit_or_block(
                error=e,
                error_text=error_text
            )
            
            listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
            listing.last_error = str(e)[:500]
            
            if is_rate_limited:
                stats["rate_limits"] += 1
                # ✅ NEW: Track rate limits separately
                consecutive_rate_limits += 1
                # Don't increment general errors for rate limits
                consecutive_general_errors = max(0, consecutive_general_errors - 1)

                retry_after_seconds = _extract_retry_after_seconds(error=e, error_text=error_text)
                cooldown_seconds = max(
                    RATE_LIMIT_COOLDOWN_SECONDS,
                    retry_after_seconds if retry_after_seconds is not None else RATE_LIMIT_COOLDOWN_SECONDS,
                )

                hard_blocked = any(token in error_text for token in [
                    "blocked", "access denied", "akamai", "captcha", "security check"
                ])

                jittered_cooldown = cooldown_seconds + random.uniform(5, 20)
                listing.next_scrape_at = now_utc + timedelta(seconds=jittered_cooldown)

                logger.warning(
                    f"⏳ {platform_name}: Rate limited on product {listing.external_id}, "
                    f"backing off {jittered_cooldown:.0f}s (streak: {consecutive_rate_limits})"
                )

                # Add to error list
                if len(stats["errors"]) < 10:
                    stats["errors"].append(f"Rate limit: {listing.external_id}")

                # Hard block or long retry-after: cool down whole platform for this cycle.
                should_cooldown_platform = (
                    hard_blocked or
                    cooldown_seconds >= 600 or
                    consecutive_rate_limits >= 2
                )

                if should_cooldown_platform:
                    platform_cooldown_until = now_utc + timedelta(seconds=jittered_cooldown)
                    _apply_platform_cooldown(
                        listings=listings,
                        start_index=max(0, i - 1),
                        cooldown_until=platform_cooldown_until,
                        reason=f"platform_rate_limited:{platform_name}",
                    )

                    logger.error(
                        f"🚫 {platform_name}: applying platform cooldown until "
                        f"{platform_cooldown_until.isoformat()} after rate limit/block"
                    )
                    if len(stats["errors"]) < 10:
                        stats["errors"].append(
                            f"Platform cooldown applied ({int(jittered_cooldown)}s)"
                        )
                    consecutive_rate_limits = max_rate_limits_before_platform_skip
                    break

                # Keep loop responsive in continuous mode; do not sleep for full retry window.
                await asyncio.sleep(min(8.0, jittered_cooldown))
            else:
                # ✅ NEW: Regular error - classify as transient or permanent
                consecutive_general_errors += 1
                error_type = type(e).__name__
                
                # Transient errors: retry sooner
                if error_type in ["Timeout", "ConnectionError", "TimeoutError"]:
                    listing.next_scrape_at = now_utc + timedelta(hours=2)
                    logger.debug(f"Transient error ({error_type}), retry in 2h")
                # Permanent errors: retry much later
                elif error_type in ["ProductNotFound", "InvalidPrice", "ValueError"]:
                    listing.next_scrape_at = now_utc + timedelta(days=7)
                    logger.debug(f"Permanent error ({error_type}), retry in 7 days")
                # Unknown: normal backoff
                else:
                    listing.next_scrape_at = _compute_next_scrape_at(
                        platform_name,
                        is_watchlisted=is_watchlisted,
                        price_changed=False,
                        scrape_failed=True,
                        error_streak=listing.scrape_error_count,
                    )
                
                if len(stats["errors"]) < 10:
                    stats["errors"].append(f"{listing.external_id}: {str(e)[:100]}")
        
        # Commit in batches
        if i % BATCH_SIZE == 0:
            try:
                await db.commit()
            except Exception as e:
                logger.error(f"Batch commit error: {e}")
                await db.rollback()
        
        # Rate limiting delay between products
        delay = DELAY_BETWEEN_PRODUCTS + random.uniform(0, 1)
        await asyncio.sleep(delay)
    
    # Final commit
    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Final commit error: {e}")
        await db.rollback()
    
    logger.info(
        f"   ✅ {platform_name}: Scraped={stats['scraped']}, "
        f"Updated={stats['updated']}, Failed={stats['failed']}, "
        f"History={stats['history_records']}, "
        f"Skipped={stats['skipped_products']}, RateLimits={consecutive_rate_limits}, "
        f"SpikeRejections={stats['spike_rejections']}"
    )
    
    return stats

async def _scrape_product_price(
    db: AsyncSession,
    platform_name: str,
    listing: ProductListing,
    signal: Optional[Dict] = None
) -> tuple[Optional[float], Optional[bool]]:
    """
    Scrape current price for a product
    
    In development mode: Returns simulated price
    In production: Uses actual scraper

    Returns:
        (price, in_stock)
        - price can be None when unavailable or scraping fails
        - in_stock is None when availability cannot be determined
    """
    # Optional mock mode (disabled by default)
    if bool(getattr(settings, "DAILY_SCRAPE_USE_MOCK_MODE", False)):
        if listing.current_price:
            # Simulate small price variations for testing
            variation = random.uniform(-0.05, 0.05)
            return round(float(listing.current_price) * (1 + variation), 2), True
        return None, listing.in_stock
    
    # Production: Use actual scraper
    try:
        from app.services.scraper.factory import get_platform_handler
        
        handler = await get_platform_handler(platform_name, db=db)
        if not handler:
            return None, None
        
        # Fix S3: wrap in timeout so a single hung page cannot stall the loop
        product_data = await asyncio.wait_for(
            handler.get_product(listing.product_url),
            timeout=PER_PRODUCT_SCRAPE_TIMEOUT_SECONDS,
        )

        if not product_data:
            state = {}
            rate_limiter = getattr(handler, "rate_limiter", None)
            if rate_limiter and hasattr(rate_limiter, "get_circuit_state"):
                try:
                    state = rate_limiter.get_circuit_state(platform_name) or {}
                except Exception:
                    state = {}

            state_name = str(state.get("state", "")).lower()
            state_reason = str(state.get("reason", "")).lower()
            if state_name == "open" or any(token in state_reason for token in ["retry after", "circuit open", "blocked"]):
                raise RuntimeError(
                    f"Platform blocked or rate-limited: {platform_name} circuit={state_name or 'unknown'} reason={state.get('reason', 'n/a')}"
                )
            return None, None

        if getattr(product_data, "in_stock", True) is False:
            return None, False
        
        if product_data and product_data.current_price:
            new_price = float(product_data.current_price)

            # Fix S1: price spike guard — reject if new price deviates wildly
            # from the previous known price.  First-ever scrape (None) is exempt.
            if PRICE_SPIKE_MAX_RATIO > 0 and listing.current_price is not None:
                old_price = float(listing.current_price)
                if old_price > 0:
                    ratio = new_price / old_price
                    effective_max_ratio = PRICE_SPIKE_MAX_RATIO
                    if platform_name.lower() == "flipkart":
                        effective_max_ratio = max(effective_max_ratio, 8.0)

                    # Allow recovery from previously corrupted tiny baselines
                    # (e.g., old ₹189 due to past parse issue, new ₹1299 is real).
                    if (
                        platform_name.lower() == "flipkart"
                        and ratio > effective_max_ratio
                        and old_price < 500
                        and new_price >= 1000
                    ):
                        logger.info(
                            f"✅ Spike guard bypassed for likely baseline-recovery "
                            f"{platform_name}/{listing.external_id}: "
                            f"₹{old_price:.0f} → ₹{new_price:.0f} (ratio={ratio:.2f})"
                        )
                        return new_price, getattr(product_data, "in_stock", True)

                    if ratio > effective_max_ratio or ratio < (1.0 / effective_max_ratio):
                        if signal is not None:
                            signal["spike_rejected"] = True
                        logger.warning(
                            f"🚫 Price spike rejected for {platform_name}/{listing.external_id}: "
                            f"₹{old_price:.0f} → ₹{new_price:.0f} (ratio={ratio:.2f})"
                        )
                        return None, None  # treat as extraction failure

            return new_price, getattr(product_data, "in_stock", True)
        
        return None, getattr(product_data, "in_stock", None)
        
    except Exception as e:
        logger.debug(f"Scraper error for {platform_name}: {e}")
        raise


async def _record_price_history(
    db: AsyncSession,
    listing: ProductListing,
    new_price: float,
    recorded_at: Optional[datetime] = None,
)-> bool:
    """Record history row only when price/stock differs from latest stored row."""
    try:
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

        history_entry = PriceHistory(
            product_listing_id=listing.id,
            price=Decimal(str(new_price)),
            in_stock=normalized_in_stock,
            recorded_at=recorded_at or datetime.now(pytz.UTC)
        )
        db.add(history_entry)
        return True
    except Exception as e:
        # Fix S5: upgraded from debug to warning so price-history gaps are visible
        logger.warning(f"Failed to record price history for listing {listing.id}: {e}")
        return False


async def _log_scrape_results(
    db: AsyncSession,
    stats: Dict[str, Any],
    start_time: datetime
):
    """Log scrape results to system_logs table"""
    try:
        today = date.today()
        
        # Get or create today's log
        result = await db.execute(
            select(SystemLog).where(SystemLog.log_date == today)
        )
        system_log = result.scalar_one_or_none()
        
        scraping_data = {
            "job": "daily_scrape",
            "timestamp": start_time.isoformat(),
            "products_found": stats.get("products_found", 0),
            "products_scraped": stats.get("products_scraped", 0),
            "products_updated": stats.get("products_updated", 0),
            "products_failed": stats.get("products_failed", 0),
            "price_changes": stats.get("price_changes", 0),
            "duration_seconds": stats.get("duration_seconds", 0),
            "platforms": stats.get("platforms", {}),
            "error_count": len(stats.get("errors", []))
        }
        
        if system_log:
            summary = system_log.scraping_summary or {}
            summary["daily_scrape"] = scraping_data
            summary["last_scrape"] = scraping_data
            system_log.scraping_summary = summary
        else:
            system_log = SystemLog(
                log_date=today,
                scraping_summary={
                    "daily_scrape": scraping_data,
                    "last_scrape": scraping_data
                },
                analytics={},
                ml_processing={}
            )
            db.add(system_log)
        
        await db.commit()
        
    except Exception as e:
        logger.warning(f"Failed to log scrape results: {e}")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Daily Price Scraping Job")
    parser.add_argument("--force-all", action="store_true", 
                       help="Force scrape all products regardless of timing")
    parser.add_argument("--continuous", action="store_true",
                       help="Run continuously with periodic refresh cycles")
    parser.add_argument("--interval-minutes", type=int,
                       default=int(getattr(settings, "DAILY_SCRAPE_LOOP_INTERVAL_MINUTES", 10)),
                       help="Minutes between continuous cycles (default from settings)")
    parser.add_argument("--max-cycles", type=int, default=0,
                       help="Stop after N cycles in continuous mode (0 = run forever)")
    parser.add_argument("--max-products", type=int, default=0,
                       help="Override max products per run (0 = use configured default)")
    args = parser.parse_args()
    
    print("🚀 Starting Daily Scrape Job...")
    print("=" * 60)
    
    async def main():
        try:
            max_products = args.max_products if args.max_products and args.max_products > 0 else None

            if args.continuous:
                cycle = 0
                print(f"🔁 Continuous mode enabled | Interval: {args.interval_minutes} minutes")
                while True:
                    cycle += 1
                    print(f"\n🕒 Cycle {cycle} started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    result = await run_daily_scrape(force_all=args.force_all, max_products=max_products)

                    print("\n📊 Cycle Results:")
                    print(f"   Total Considered: {result.get('total_listings_considered', 0)}")
                    print(f"   Due Listings: {result.get('products_found', 0)}")
                    print(f"   Products Scraped: {result.get('products_scraped', 0)}")
                    print(f"   Products Updated: {result.get('products_updated', 0)}")
                    print(f"   Price Changes: {result.get('price_changes', 0)}")
                    print(f"   Spike Rejections: {result.get('spike_rejections', 0)}")
                    print(f"   History Records: {result.get('history_records', 0)}")
                    print(f"   Rate Limit Incidents: {result.get('rate_limit_incidents', 0)}")
                    print(f"   Failed: {result.get('products_failed', 0)}")
                    print(f"   Duration: {result.get('duration_seconds', 0)}s")

                    if args.max_cycles > 0 and cycle >= args.max_cycles:
                        print(f"\n🛑 Reached max cycles: {args.max_cycles}")
                        break

                    print(f"⏳ Sleeping for {args.interval_minutes} minutes...")
                    await asyncio.sleep(max(1, args.interval_minutes) * 60)

                return

            if args.force_all:
                # Override the cutoff time to scrape everything for one run
                global SCRAPE_INTERVAL_HOURS
                SCRAPE_INTERVAL_HOURS = 0
                print("🔧 Force mode: Scrape all products")

            result = await run_daily_scrape(force_all=args.force_all, max_products=max_products)
            
            print("\n📊 Results:")
            print(f"   Total Considered: {result.get('total_listings_considered', 0)}")
            print(f"   Due Listings: {result.get('products_found', 0)}")
            print(f"   Products Scraped: {result.get('products_scraped', 0)}")
            print(f"   Products Updated: {result.get('products_updated', 0)}")
            print(f"   Price Changes: {result.get('price_changes', 0)}")
            print(f"   Spike Rejections: {result.get('spike_rejections', 0)}")
            print(f"   History Records: {result.get('history_records', 0)}")
            print(f"   Rate Limit Incidents: {result.get('rate_limit_incidents', 0)}")
            print(f"   Failed: {result.get('products_failed', 0)}")
            print(f"   Duration: {result.get('duration_seconds', 0)}s")
            
            if result.get("error"):
                print(f"\n❌ Error: {result['error']}")
            else:
                print("\n✅ Job completed successfully!")
                
        except Exception as e:
            print(f"\n💥 Critical error: {e}")
            import traceback
            traceback.print_exc()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Daily scrape interrupted by user.")
    finally:
        print("\n🏁 Daily scrape job finished.")
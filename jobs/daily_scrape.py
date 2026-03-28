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
DELAY_BETWEEN_PRODUCTS = max(0, int(getattr(settings, "DAILY_SCRAPE_DELAY_SECONDS", 2)))
MAX_ERRORS_BEFORE_SKIP = max(3, int(getattr(settings, "DAILY_SCRAPE_MAX_ERRORS_BEFORE_SKIP", 8)))
BATCH_SIZE = 60  # Commit after each batch
RATE_LIMIT_COOLDOWN_SECONDS = max(30, int(getattr(settings, "DAILY_SCRAPE_RATE_LIMIT_COOLDOWN_SECONDS", 120)))

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
                watchlisted_product_ids = await _get_watchlisted_product_ids(db)

                # Step 1: Get products to scrape
                listings = await _get_products_to_scrape(
                    db,
                    watchlisted_product_ids=watchlisted_product_ids,
                    force_all=force_all,
                    max_products=max_products,
                )
                stats["products_found"] = len(listings)

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

                    if platform_stats.get("errors"):
                        stats["errors"].extend(platform_stats["errors"][:5])

                # Step 5: Calculate duration
                stats["duration_seconds"] = round(
                    (datetime.now(pytz.UTC) - start_time).total_seconds(), 2
                )

                # Step 6: Log results
                await _log_scrape_results(db, stats, start_time)

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


async def _scrape_platform(
    db: AsyncSession,
    platform_name: str,
    listings: List[ProductListing],
    watchlisted_product_ids: set,
) -> Dict[str, Any]:
    """Scrape all listings for a single platform with rate limiting"""
    logger.info(f"📱 Scraping {platform_name}: {len(listings)} products")
    
    stats = {
        "scraped": 0,
        "updated": 0,
        "failed": 0,
        "marked_out_of_stock": 0,
        "skipped_low_confidence": 0,
        "price_changes": 0,
        "errors": []
    }
    
    consecutive_errors = 0
    
    for i, listing in enumerate(listings, 1):
        now_utc = datetime.now(pytz.UTC)
        is_watchlisted = listing.product_id in watchlisted_product_ids
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

        # Skip platform if too many errors
        if consecutive_errors >= MAX_ERRORS_BEFORE_SKIP:
            logger.warning(f"⚠️ Skipping {platform_name} after {consecutive_errors} errors")
            stats["errors"].append(f"Skipped after {consecutive_errors} consecutive errors")
            break
        
        try:
            # Scrape product price
            previous_in_stock = listing.in_stock
            new_price, scraped_in_stock = await _scrape_product_price(platform_name, listing)

            if scraped_in_stock is not None:
                listing.in_stock = scraped_in_stock

            # Explicit out-of-stock is a valid scrape result; keep it out of failed bucket.
            if scraped_in_stock is False:
                listing.last_scraped = now_utc
                listing.scrape_error_count = 0
                listing.last_error = None
                stock_changed = previous_in_stock is not False
                if stock_changed:
                    listing.last_price_change_at = now_utc
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
                consecutive_errors = 0
                continue
            
            if new_price is not None:
                old_price = listing.current_price
                price_changed = bool(old_price and abs(float(new_price) - float(old_price)) > 0.01)
                
                # Update listing
                listing.last_scraped = now_utc
                listing.scrape_error_count = 0
                listing.last_error = None
                
                # Check for price change
                if price_changed:
                    listing.current_price = new_price
                    stats["price_changes"] += 1
                    stats["updated"] += 1
                    listing.last_price_change_at = now_utc
                    
                    # Record price history
                    await _record_price_history(db, listing, new_price)
                    
                    logger.debug(
                        f"💰 Price change: {listing.external_id} "
                        f"₹{old_price} → ₹{new_price}"
                    )
                else:
                    listing.current_price = new_price
                    stats["updated"] += 1
                
                stats["scraped"] += 1
                consecutive_errors = 0
                listing.next_scrape_at = _compute_next_scrape_at(
                    platform_name,
                    is_watchlisted=is_watchlisted,
                    price_changed=price_changed,
                    scrape_failed=False,
                    error_streak=0,
                )
                
            else:
                stats["failed"] += 1
                consecutive_errors += 1
                listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                listing.last_error = "No price extracted"
                listing.next_scrape_at = _compute_next_scrape_at(
                    platform_name,
                    is_watchlisted=is_watchlisted,
                    price_changed=False,
                    scrape_failed=True,
                    error_streak=listing.scrape_error_count,
                )
                
        except Exception as e:
            stats["failed"] += 1
            error_text = str(e).lower()
            is_rate_limited = any(
                token in error_text
                for token in ["rate limit", "429", "burst limit", "too many requests", "cooling down"]
            )

            listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
            listing.last_error = str(e)[:500]
            listing.next_scrape_at = _compute_next_scrape_at(
                platform_name,
                is_watchlisted=is_watchlisted,
                price_changed=False,
                scrape_failed=True,
                error_streak=listing.scrape_error_count,
            )

            if is_rate_limited:
                # Avoid tripping platform skip too early on burst windows.
                consecutive_errors = max(0, consecutive_errors - 1)
                cooldown = RATE_LIMIT_COOLDOWN_SECONDS + random.uniform(10, 30)
                logger.warning(f"⏳ {platform_name}: rate-limited, backing off for {cooldown:.0f}s")
                await asyncio.sleep(cooldown)
            else:
                consecutive_errors += 1
            
            if len(stats["errors"]) < 10:
                stats["errors"].append(f"{listing.external_id}: {str(e)[:100]}")
            
            logger.debug(f"Failed to scrape {listing.external_id}: {e}")
        
        # Commit in batches
        if i % BATCH_SIZE == 0:
            try:
                await db.commit()
            except Exception as e:
                logger.error(f"Batch commit error: {e}")
                await db.rollback()
        
        # Rate limiting delay
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
        f"Updated={stats['updated']}, Failed={stats['failed']}"
    )
    
    return stats


async def _scrape_product_price(
    platform_name: str,
    listing: ProductListing
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
        
        handler = await get_platform_handler(platform_name)
        if not handler:
            return None, None
        
        product_data = await handler.get_product(listing.product_url)

        if not product_data:
            return None, None

        if getattr(product_data, "in_stock", True) is False:
            return None, False
        
        if product_data and product_data.current_price:
            return float(product_data.current_price), getattr(product_data, "in_stock", True)
        
        return None, getattr(product_data, "in_stock", None)
        
    except Exception as e:
        logger.debug(f"Scraper error for {platform_name}: {e}")
        raise


async def _record_price_history(
    db: AsyncSession,
    listing: ProductListing,
    new_price: float
):
    """Record price change in history"""
    try:
        history_entry = PriceHistory(
            product_listing_id=listing.id,
            price=Decimal(str(new_price)),
            in_stock=listing.in_stock if listing.in_stock is not None else True,
            recorded_at=datetime.now(pytz.UTC)
        )
        db.add(history_entry)
    except Exception as e:
        logger.debug(f"Failed to record price history: {e}")


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
                    print(f"   Products Found: {result.get('products_found', 0)}")
                    print(f"   Products Scraped: {result.get('products_scraped', 0)}")
                    print(f"   Products Updated: {result.get('products_updated', 0)}")
                    print(f"   Price Changes: {result.get('price_changes', 0)}")
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
            print(f"   Products Found: {result.get('products_found', 0)}")
            print(f"   Products Scraped: {result.get('products_scraped', 0)}")
            print(f"   Products Updated: {result.get('products_updated', 0)}")
            print(f"   Price Changes: {result.get('price_changes', 0)}")
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
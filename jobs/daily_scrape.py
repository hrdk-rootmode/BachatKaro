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
from sqlalchemy import select, text, and_, or_

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

MAX_PRODUCTS_PER_RUN = 500  # Limit to avoid overload
SCRAPE_INTERVAL_HOURS = 6  # Scrape products not updated in 24h
DELAY_BETWEEN_PRODUCTS = 2  # Seconds between scrapes (rate limiting)
MAX_ERRORS_BEFORE_SKIP = 3  # Skip platform after consecutive errors
BATCH_SIZE = 60  # Commit after each batch


# =============================================================================
# MAIN JOB FUNCTION
# =============================================================================

async def run_daily_scrape() -> Dict[str, Any]:
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
    
    try:
        async with async_session_maker() as db:
            # Step 1: Get products to scrape
            listings = await _get_products_to_scrape(db)
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
                    listings=platform_listings
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

async def _get_products_to_scrape(db: AsyncSession) -> List[ProductListing]:
    """Get products that need scraping (prioritized)"""
    cutoff_time = datetime.now(pytz.UTC) - timedelta(hours=SCRAPE_INTERVAL_HOURS)
    
    try:
        # Get watchlisted product IDs (highest priority)
        watchlist_result = await db.execute(
            select(UserWatchlist.product_id).distinct()
        )
        watchlisted_ids = [r[0] for r in watchlist_result.fetchall()]
        
        # Query for listings that need updating
        query = (
            select(ProductListing)
            .where(
                or_(
                    # Watchlisted products always get priority
                    ProductListing.product_id.in_(watchlisted_ids) if watchlisted_ids else False,
                    # Products not scraped recently
                    ProductListing.last_scraped < cutoff_time,
                    ProductListing.last_scraped.is_(None)
                )
            )
            .order_by(
                # Prioritize: watchlisted first, then oldest scraped
                ProductListing.last_scraped.asc().nullsfirst()
            )
            .limit(MAX_PRODUCTS_PER_RUN)
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
    listings: List[ProductListing]
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
        min_confidence = float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))
        if listing.extraction_confidence is not None and listing.extraction_confidence < min_confidence:
            stats["skipped_low_confidence"] += 1
            continue

        # Skip platform if too many errors
        if consecutive_errors >= MAX_ERRORS_BEFORE_SKIP:
            logger.warning(f"⚠️ Skipping {platform_name} after {consecutive_errors} errors")
            stats["errors"].append(f"Skipped after {consecutive_errors} consecutive errors")
            break
        
        try:
            # Scrape product price
            new_price, scraped_in_stock = await _scrape_product_price(platform_name, listing)

            if scraped_in_stock is not None:
                listing.in_stock = scraped_in_stock

            # Explicit out-of-stock is a valid scrape result; keep it out of failed bucket.
            if scraped_in_stock is False:
                listing.last_scraped = datetime.now(pytz.UTC)
                listing.scrape_error_count = 0
                listing.last_error = None
                stats["scraped"] += 1
                stats["updated"] += 1
                stats["marked_out_of_stock"] += 1
                consecutive_errors = 0
                continue
            
            if new_price is not None:
                old_price = listing.current_price
                
                # Update listing
                listing.last_scraped = datetime.now(pytz.UTC)
                listing.scrape_error_count = 0
                listing.last_error = None
                
                # Check for price change
                if old_price and abs(float(new_price) - float(old_price)) > 0.01:
                    listing.current_price = new_price
                    stats["price_changes"] += 1
                    stats["updated"] += 1
                    
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
                
            else:
                stats["failed"] += 1
                consecutive_errors += 1
                listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                
        except Exception as e:
            stats["failed"] += 1
            consecutive_errors += 1
            listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
            listing.last_error = str(e)[:500]
            
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
    # Development/Mock mode
    if settings.DEBUG or settings.ENVIRONMENT == "development":
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
    args = parser.parse_args()
    
    print("🚀 Starting Daily Scrape Job...")
    print("=" * 60)
    
    async def main():
        try:
            if args.force_all:
                # Override the cutoff time to scrape everything
                global SCRAPE_INTERVAL_HOURS
                SCRAPE_INTERVAL_HOURS = 0  # Scrape everything
                print("🔧 Force mode: Scrape all products")
            
            result = await run_daily_scrape()
            
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
    
    asyncio.run(main())
    print("\n🏁 Daily scrape job finished.")
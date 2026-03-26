"""
Diagnostic script to find where daily_scrape hangs
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app.core.config import settings
from app.core.database import async_session_maker
from sqlalchemy import select, text
from app.models import Platform, ProductListing, UserWatchlist
from datetime import datetime, timedelta
import pytz

async def diagnose():
    print("[1] Checking database connection...")
    try:
        async with async_session_maker() as db:
            print("    ✅ Database connection OK")
            
            print("\n[2] Checking Platform table...")
            result = await db.execute(select(Platform))
            platforms = result.scalars().all()
            print(f"    ✅ Found {len(platforms)} platforms")
            if len(platforms) == 0:
                print("    ⚠️  WARNING: No platforms in database!")
            for p in platforms[:3]:
                print(f"       - {p.name} (active: {p.is_active})")
            
            print("\n[3] Checking ProductListing table...")
            result = await db.execute(select(ProductListing).limit(1))
            count_result = await db.execute(text("SELECT COUNT(*) FROM product_listing"))
            count = count_result.scalar()
            print(f"    ✅ Found {count} total product listings")
            
            print("\n[4] Checking UserWatchlist table...")
            wl_result = await db.execute(text("SELECT COUNT(*) FROM user_watchlist"))
            wl_count = wl_result.scalar()
            print(f"    ✅ Found {wl_count} watchlist entries")
            
            print("\n[5] Running EXACT query from daily_scrape...")
            cutoff_time = datetime.now(pytz.UTC) - timedelta(hours=0)
            watchlist_result = await db.execute(
                select(UserWatchlist.product_id).distinct()
            )
            watchlisted_ids = [r[0] for r in watchlist_result.fetchall()]
            print(f"    ✅ Watchlist query OK ({len(watchlisted_ids)} products)")
            
            print("\n[6] Querying ProductListing (THIS IS WHERE IT HANGS)...")
            from sqlalchemy import or_
            try:
                query = (
                    select(ProductListing)
                    .where(
                        or_(
                            ProductListing.product_id.in_(watchlisted_ids) if watchlisted_ids else False,
                            ProductListing.last_scraped < cutoff_time,
                            ProductListing.last_scraped.is_(None)
                        )
                    )
                    .order_by(ProductListing.last_scraped.asc().nullsfirst())
                    .limit(500)
                )
                result = await db.execute(query)
                listings = list(result.scalars().all())
                print(f"    ✅ ProductListing query OK ({len(listings)} results)")
            except Exception as e:
                print(f"    ❌ ProductListing query FAILED: {e}")
                import traceback
                traceback.print_exc()
            
            print("\n✅ All diagnostics passed!")
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("DAILY SCRAPE DIAGNOSTIC")
    print("=" * 60)
    print(f"DEBUG: {settings.DEBUG}")
    print(f"DATABASE_URL: {settings.DATABASE_URL[:50]}...")
    print("=" * 60)
    asyncio.run(diagnose())

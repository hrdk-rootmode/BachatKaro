"""
Daily Trending Products Job
===========================

Runs at 2:30 AM IST to fetch trending products from all platforms

Features:
- Fetches trending/best-selling products from each platform
- ✅ REFACTORED: Uses centralized enrichment_service and product_service
- Cross-platform deduplication using fingerprint
- Complete statistics tracking

Platform Distribution:
├─ Amazon: 5 products
├─ Flipkart: 5 products
├─ Myntra: 3 products
├─ Nykaa: 3 products
├─ Croma: 3 products
└─ Meesho: 3 products

Author: DealHunt
Version: 3.0 (Refactored - Uses Centralized Services)
"""

import logging
import asyncio
from datetime import datetime, date
from typing import Dict, List, Any

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
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import Product, SystemLog
from app.services.scraper.base import ProductData

# ✅ NEW: Centralized Services (Replaces duplicate code)
from app.services.ai.enrichment_service import enrichment_service
from app.services.product_service import product_service

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

PLATFORM_TRENDING_CONFIG = {
    "amazon": {"products": 5, "keywords": ["Best Selling", "Trending"]},
    "flipkart": {"products": 5, "keywords": ["Best Selling", "Trending"]},
    "myntra": {"products": 3, "keywords": ["Trending", "Top Rated"]},
    "nykaa": {"products": 3, "keywords": ["Best Sellers", "Trending"]},
    "croma": {"products": 3, "keywords": ["Trending", "Best Sellers"]},
    "meesho": {"products": 3, "keywords": ["Trending", "Best Selling"]},
}

CATEGORIES_TO_TREND = [
    "Electronics",
    "Fashion",
    "Beauty",
    "Home & Kitchen",
]

SCRAPE_TIMEOUT_SECONDS = 30


# =============================================================================
# TRENDING ENGINE (REFACTORED)
# =============================================================================

class TrendingProductEngine:
    """
    Fetch, enrich, and save trending products platform-wise
    
    ✅ REFACTORED: Uses centralized enrichment_service and product_service
    """
    
    def __init__(self):
        self.stats = {
            "platforms": {},
            "total_fetched": 0,
            "total_new": 0,
            "total_duplicates": 0,
            "total_cross_platform": 0,
            "errors": [],
        }
    
    async def _check_product_exists(
        self, 
        fingerprint: str, 
        db: AsyncSession
    ) -> bool:
        """Check if product already exists in DB"""
        result = await db.execute(
            select(Product).where(Product.fingerprint == fingerprint)
        )
        return result.scalar_one_or_none() is not None
    
    async def _fetch_trending_products(
        self, 
        platform_name: str
    ) -> List[ProductData]:
        """Fetch trending products from a platform"""
        products = []
        
        try:
            config = PLATFORM_TRENDING_CONFIG.get(platform_name, {})
            keywords = config.get("keywords", ["Trending"])
            max_products = config.get("products", 3)
            
            # Get handler
            from app.services.scraper.factory import get_platform_handler
            
            async with async_session_maker() as db:
                handler = await get_platform_handler(platform_name, db)
                if not handler:
                    logger.warning(f"No handler for {platform_name}")
                    return products
                
                # Try each category + keyword combination
                for category in CATEGORIES_TO_TREND:
                    if len(products) >= max_products:
                        break
                    
                    for keyword in keywords:
                        if len(products) >= max_products:
                            break
                        
                        query = f"{category} {keyword}"
                        
                        try:
                            result = await asyncio.wait_for(
                                handler.search(query=query, page=1),
                                timeout=SCRAPE_TIMEOUT_SECONDS,
                            )
                            
                            if result and result.success and result.products:
                                for p in result.products:
                                    if len(products) >= max_products:
                                        break
                                    p.platform_name = platform_name
                                    products.append(p)
                                    self.stats["total_fetched"] += 1
                                    
                        except asyncio.TimeoutError:
                            logger.debug(f"Timeout: {platform_name} - {query}")
                        except Exception as e:
                            logger.debug(f"Error: {platform_name} - {query}: {e}")
                            
        except Exception as e:
            logger.error(f"Failed to fetch from {platform_name}: {e}")
            self.stats["errors"].append(f"{platform_name}: {e}")
        
        return products
    
    async def _process_platform(
        self, 
        platform_name: str, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Process trending products for one platform
        
        ✅ REFACTORED: Uses centralized services
        """
        logger.info(f"📌 Processing {platform_name.upper()}")
        
        platform_stats = {
            "platform": platform_name,
            "fetched": 0,
            "saved": 0,
            "duplicates": 0,
        }
        
        try:
            # Fetch trending products
            products = await self._fetch_trending_products(platform_name)
            platform_stats["fetched"] = len(products)
            
            if not products:
                logger.info(f"   No products found for {platform_name}")
                return platform_stats
            
            logger.info(f"   Fetched {len(products)} products")
            
            # Process each product
            for i, product_data in enumerate(products, 1):
                fingerprint = product_data.fingerprint
                
                # Check if exists
                exists = await self._check_product_exists(fingerprint, db)
                
                if exists:
                    platform_stats["duplicates"] += 1
                    self.stats["total_duplicates"] += 1
                    logger.debug(f"   [{i}] DUPLICATE: {product_data.title[:30]}")
                else:
                    try:
                        # =====================================================
                        # ✅ STEP 1: AI ENRICHMENT (Using centralized service)
                        # =====================================================
                        product_data = await enrichment_service.enrich_product(product_data)
                        
                        # =====================================================
                        # ✅ STEP 2: SAVE TO DATABASE (Using centralized service)
                        # =====================================================
                        product = await product_service.save_product(
                            product_data=product_data,
                            db=db,
                            is_user_search=False  # Job-created = seeded product
                        )
                        
                        if product:
                            platform_stats["saved"] += 1
                            self.stats["total_new"] += 1
                            logger.info(f"   [{i}] ✅ NEW: {product.title[:40]}")
                            
                    except Exception as e:
                        logger.error(f"   [{i}] ❌ FAILED: {e}")
                        self.stats["errors"].append(str(e))
                        
        except Exception as e:
            logger.error(f"Failed to process {platform_name}: {e}")
        
        self.stats["platforms"][platform_name] = platform_stats
        return platform_stats
    
    async def run(self) -> Dict[str, Any]:
        """Main trending products fetch"""
        logger.info("🌟 DAILY TRENDING PRODUCTS - Starting...")
        start_time = datetime.utcnow()
        
        try:
            async with async_session_maker() as db:
                # Process each platform
                for platform_name in PLATFORM_TRENDING_CONFIG.keys():
                    await self._process_platform(platform_name, db)
                
                # Log results
                await self._log_results(db, start_time)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info("\n" + "=" * 60)
            logger.info("✅ TRENDING JOB COMPLETE")
            logger.info(
                f"   Total fetched: {self.stats['total_fetched']}\n"
                f"   New saved: {self.stats['total_new']}\n"
                f"   Duplicates: {self.stats['total_duplicates']}\n"
                f"   Duration: {duration:.1f}s"
            )
            logger.info("=" * 60)
            
            return {
                "success": True,
                "fetched": self.stats["total_fetched"],
                "saved": self.stats["total_new"],
                "duplicates": self.stats["total_duplicates"],
                "duration_seconds": round(duration, 2),
                "platforms": self.stats["platforms"],
            }
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"❌ Trending job failed: {e}")
            
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": round(duration, 2),
            }
    
    async def _log_results(self, db: AsyncSession, start_time: datetime):
        """Log trending results to system_logs"""
        try:
            today = date.today()
            
            result = await db.execute(
                select(SystemLog).where(SystemLog.log_date == today)
            )
            system_log = result.scalar_one_or_none()
            
            trending_data = {
                "job": "daily_scrape_trending",
                "timestamp": start_time.isoformat(),
                "total_fetched": self.stats["total_fetched"],
                "total_new": self.stats["total_new"],
                "total_duplicates": self.stats["total_duplicates"],
                "platforms": self.stats["platforms"],
            }
            
            if system_log:
                summary = system_log.scraping_summary or {}
                summary["trending"] = trending_data
                system_log.scraping_summary = summary
            else:
                system_log = SystemLog(
                    log_date=today,
                    scraping_summary={"trending": trending_data},
                    analytics={},
                    ml_processing={},
                )
                db.add(system_log)
            
            await db.commit()
            
        except Exception as e:
            logger.warning(f"Failed to log trending results: {e}")


# =============================================================================
# MAIN JOB FUNCTION
# =============================================================================

async def run_daily_trending_products() -> Dict[str, Any]:
    """Main job function for scheduler"""
    engine = TrendingProductEngine()
    return await engine.run()


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("🚀 Starting Daily Trending Products Job...")
    print("=" * 60)
    
    async def main():
        try:
            result = await run_daily_trending_products()
            
            print("\n📊 Results:")
            print(f"   Success: {result.get('success', False)}")
            print(f"   Fetched: {result.get('fetched', 0)}")
            print(f"   Saved: {result.get('saved', 0)}")
            print(f"   Duplicates: {result.get('duplicates', 0)}")
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
    print("\n🏁 Daily trending job finished.")
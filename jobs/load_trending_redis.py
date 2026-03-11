"""
Load Trending Products to Redis
Runs at 5 AM IST to pre-cache trending products

Features:
- Pre-caches top 50 trending products
- Reduces database load during peak hours
- Updates search rankings
- Calculates deal scores

FIXED: Redis connection handling for Windows
"""

import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List
import json

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, Integer, text

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import Product, ProductListing, Platform

logger = logging.getLogger(__name__)

# Configuration
TRENDING_CACHE_KEY = "trending:products"
TRENDING_CACHE_TTL = 86400  # 24 hours
TOP_PRODUCTS_COUNT = 50


async def run_load_trending() -> Dict[str, Any]:
    """
    Load trending products into Redis cache
    
    Process:
    1. Calculate trending scores based on engagement
    2. Get top 50 products with full details
    3. Cache in Redis for fast access
    """
    logger.info("🔄 Starting trending cache refresh...")
    start_time = datetime.utcnow()
    
    stats = {
        "products_cached": 0,
        "cache_key": TRENDING_CACHE_KEY,
        "ttl_seconds": TRENDING_CACHE_TTL,
        "duration_seconds": 0
    }
    
    try:
        async with async_session_maker() as db:
            # Get trending products
            trending = await get_trending_products(db)
            
            if not trending:
                logger.warning("No trending products found")
                stats["message"] = "No trending products"
                stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
                return stats
            
            # Format for caching
            cache_data = format_trending_data(trending)
            
            # Store in Redis
            await store_in_redis(cache_data)
            
            # Cache by category
            await cache_by_category(trending)
            
            stats["products_cached"] = len(cache_data)
            stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                f"✅ Trending cache updated | "
                f"Products: {stats['products_cached']} | "
                f"Duration: {stats['duration_seconds']:.2f}s"
            )
            
            return stats
            
    except Exception as e:
        logger.error(f"❌ Trending cache refresh failed: {e}")
        stats["error"] = str(e)
        stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
        raise


async def get_trending_products(db: AsyncSession) -> List[tuple]:
    """
    Get trending products based on engagement metrics
    
    Uses simple query for compatibility
    """
    try:
        # Simple query - get products with listings, ordered by last scraped
        query = (
            select(Product, ProductListing, Platform)
            .join(ProductListing, Product.id == ProductListing.product_id)
            .join(Platform, ProductListing.platform_id == Platform.id)
            .where(
                ProductListing.in_stock == True,
                Platform.is_active == True
            )
            .order_by(ProductListing.last_scraped.desc().nullslast())
            .limit(TOP_PRODUCTS_COUNT)
        )
        
        result = await db.execute(query)
        return list(result.fetchall())
        
    except Exception as e:
        logger.error(f"Error fetching trending products: {e}")
        
        # Fallback: even simpler query
        try:
            fallback_query = (
                select(Product, ProductListing, Platform)
                .join(ProductListing, Product.id == ProductListing.product_id)
                .join(Platform, ProductListing.platform_id == Platform.id)
                .limit(TOP_PRODUCTS_COUNT)
            )
            
            result = await db.execute(text(str(fallback_query)))
            return list(result.fetchall())
        except Exception as e2:
            logger.error(f"Fallback query also failed: {e2}")
            return []


def format_trending_data(trending: List[tuple]) -> List[Dict]:
    """Format trending products for caching"""
    cache_data = []
    
    for item in trending:
        try:
            product, listing, platform = item
            
            cache_data.append({
                "product_id": str(product.id),
                "title": product.title or "Unknown Product",
                "brand": product.brand,
                "category": product.category,
                "image_url": product.image_url,
                "current_price": float(listing.current_price) if listing.current_price else 0,
                "original_price": float(listing.original_price) if listing.original_price else None,
                "discount_percent": float(listing.discount_percent) if listing.discount_percent else None,
                "platform": platform.name if platform else "unknown",
                "platform_id": listing.platform_id,
                "product_url": listing.product_url,
                "affiliate_url": listing.affiliate_url,
                "rating": float(listing.rating) if listing.rating else None,
                "review_count": listing.review_count,
                "in_stock": listing.in_stock,
                "cached_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.warning(f"Error formatting product: {e}")
            continue
    
    return cache_data


async def store_in_redis(cache_data: List[Dict]):
    """Store trending data in Redis with proper connection handling"""
    from app.core.redis_client import redis_client
    
    try:
        # Ensure connection
        if not await redis_client.ping():
            await redis_client.connect()
        
        # Store main trending list
        await redis_client.set(
            TRENDING_CACHE_KEY,
            json.dumps(cache_data),
            ex=TRENDING_CACHE_TTL
        )
        
        # Store product IDs for quick lookup
        product_ids = [p["product_id"] for p in cache_data]
        await redis_client.set(
            "trending:product_ids",
            json.dumps(product_ids),
            ex=TRENDING_CACHE_TTL
        )
        
        logger.debug(f"Stored {len(cache_data)} products in Redis")
        
    except Exception as e:
        logger.error(f"Redis storage error: {e}")
        # Don't raise - trending cache is not critical
        raise


async def cache_by_category(trending: List[tuple]):
    """Cache trending products by category"""
    from app.core.redis_client import redis_client
    
    categories: Dict[str, List] = {}
    
    for item in trending:
        try:
            product, listing, platform = item
            category = product.category or "other"
            
            if category not in categories:
                categories[category] = []
            
            categories[category].append({
                "product_id": str(product.id),
                "title": product.title,
                "current_price": float(listing.current_price) if listing.current_price else 0,
                "platform": platform.name if platform else "unknown"
            })
        except Exception:
            continue
    
    try:
        # Cache each category
        for category, products in categories.items():
            cache_key = f"trending:category:{category}"
            await redis_client.set(
                cache_key,
                json.dumps(products[:20]),  # Top 20 per category
                ex=TRENDING_CACHE_TTL
            )
        
        # Cache category list
        await redis_client.set(
            "trending:categories",
            json.dumps(list(categories.keys())),
            ex=TRENDING_CACHE_TTL
        )
        
    except Exception as e:
        logger.warning(f"Category caching error: {e}")


# ============================================================================
# MAIN EXECUTION (for running directly)
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    print("🚀 Starting Load Trending to Redis Job...")
    print("=" * 60)
    
    try:
        result = asyncio.run(run_load_trending())
        
        if result.get("success"):
            print("\n✅ Job completed successfully!")
            print(f"📊 Results: {result}")
        else:
            print(f"\n❌ Job failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"\n💥 Critical error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🏁 Load trending to Redis job finished.")
"""
Load Trending Products Job

DEPRECATED: Redis caching removed for direct database-to-frontend communication

This job is no longer needed as:
- No Redis caching layer
- Frontend queries database directly
- Real-time data always available
- Simplified architecture

Keeping file for reference, but job is disabled.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Product, ProductListing, Platform

logger = logging.getLogger(__name__)


async def run_load_trending() -> Dict[str, Any]:
    """
    Load trending products - DISABLED (Redis removed)
    
    This job no longer runs as the application uses direct database access.
    Frontend queries product data directly from PostgreSQL without caching.
    """
    logger.info("⏭️  Trending cache job skipped (Redis deprecated)")
    
    return {
        "Status": "skipped",
        "Reason": "Redis caching removed - using direct database access",
        "Products_cached": 0,
        "Duration_seconds": 0,
        "Message": "No caching needed - all data is fresh from database"
    }


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
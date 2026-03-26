"""
Home Page API Endpoints
Provides curated content for home page display
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, Integer
from sqlalchemy.orm import selectinload
from typing import List, Optional
import logging

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.api.deps import get_current_user
from app.models import Product, ProductListing, Platform
from app.schemas import TrendingProductResponse
from app.core.redis_client import RedisClient

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/featured", response_model=List[TrendingProductResponse])
async def get_featured_products(
    limit: int = 10,
    user = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    """
    Get featured products for home page banner
    Returns hand-picked products with high engagement
    """
    cache_key = "home:featured:products"
    
    # Check Redis cache
    cached = await redis.get_json(cache_key)
    if cached:
        logger.info(f"Featured products cache HIT | User: {user.id}")
        return cached
    
    try:
        # ✅ FIX: Get products from DIFFERENT platforms for variety, not just cheapest
        # This ensures banner shows Amazon, Flipkart, Meesho, etc.
        result = await db.execute(
            select(Product)
            .where(
                Product.image_url.isnot(None),
                Product.title.isnot(None)
            )
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        
        products = result.scalars().all()
        logger.info(f"Fetched {len(products)} featured products")
        
        # Build response - get ONE listing per product (try to vary platforms)
        featured = []
        platform_rotation = ['amazon', 'flipkart', 'meesho', 'nykaa', 'myntra']
        platform_index = 0
        
        for product in products:
            try:
                # ✅ Try to get a listing from different platforms in rotation
                preferred_platform = platform_rotation[platform_index % len(platform_rotation)]
                platform_index += 1
                
                # Get ALL listings for this product with platform eager-loaded
                result = await db.execute(
                    select(ProductListing)
                    .where(ProductListing.product_id == product.id)
                    .options(selectinload(ProductListing.platform))
                    .order_by(ProductListing.current_price.asc())
                )
                all_listings = list(result.scalars().all())
                
                if not all_listings:
                    continue
                
                # Find listing with preferred platform
                listing = None
                for l in all_listings:
                    if l.platform and l.platform.name.lower() == preferred_platform.lower():
                        listing = l
                        break
                
                # If preferred platform not available, use cheapest from any platform
                if not listing:
                    listing = all_listings[0]  # Already sorted by price asc
                
                if not listing or not listing.platform:
                    continue
                
                ai_metadata = product.ai_metadata or {}
                
                featured_item = TrendingProductResponse(
                    product_id=str(product.id),
                    title=ai_metadata.get("essence", product.title),
                    image_url=product.image_url,
                    platform=listing.platform.name,
                    current_price=float(listing.current_price),
                    original_price=float(listing.original_price) if listing.original_price else None,
                    discount_percent=listing.discount_percent or 0,
                    rank=len(featured) + 1,
                    category=product.category,
                    brand=product.brand
                )
                
                featured.append(featured_item)
                
            except Exception as e:
                logger.error(f"Error building featured product {product.id}: {e}", exc_info=True)
                continue
        
        # Cache for 30 minutes
        if featured:
            await redis.set_json(
                cache_key,
                [item.model_dump(mode='json') for item in featured],
                ttl=1800
            )
            logger.info(f"Cached {len(featured)} featured products with platform variety")
        
        logger.info(f"Featured products ready | Count: {len(featured)}")
        return featured
        
    except Exception as e:
        logger.error(f"Error fetching featured products: {e}", exc_info=True)
        return []


@router.get("/categories", response_model=dict)
async def get_home_categories(
    user = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    """
    Get categories with product counts for home page
    """
    cache_key = "home:categories:counts"
    
    # Check Redis cache
    cached = await redis.get_json(cache_key)
    if cached:
        return cached
    
    try:
        # Get product counts by category
        result = await db.execute(
            select(Product.category, func.count(Product.id))
            .where(Product.category.isnot(None))
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
        )
        
        categories = {}
        for category, count in result.all():
            categories[category] = count
        
        # Add trending categories
        trending_categories = {
            "Electronics": categories.get("Electronics", 0),
            "Fashion": categories.get("Fashion", 0),
            "Beauty": categories.get("Beauty", 0),
            "Home & Kitchen": categories.get("Home & Kitchen", 0),
            "Sports": categories.get("Sports", 0),
            "Books": categories.get("Books", 0)
        }
        
        # Cache for 1 hour
        await redis.set_json(cache_key, trending_categories, ttl=3600)
        
        return trending_categories
        
    except Exception as e:
        logger.error(f"Error fetching categories: {e}", exc_info=True)
        return {}


@router.get("/deals", response_model=List[TrendingProductResponse])
async def get_home_deals(
    limit: int = 20,
    user = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    """
    Get best deals for home page
    Products with highest discounts
    """
    cache_key = "home:deals:products"
    
    # Check Redis cache
    cached = await redis.get_json(cache_key)
    if cached:
        logger.info(f"Home deals cache HIT | User: {user.id}")
        return cached
    
    try:
        # Get products with highest discounts
        result = await db.execute(
            select(ProductListing, Product)
            .join(Product, ProductListing.product_id == Product.id)
            .where(
                ProductListing.discount_percent > 0,
                ProductListing.in_stock == True
            )
            .order_by(ProductListing.discount_percent.desc())
            .limit(limit)
        )
        
        deals = []
        for listing, product in result.all():
            try:
                ai_metadata = product.ai_metadata or {}
                
                deal_item = TrendingProductResponse(
                    product_id=str(product.id),
                    title=ai_metadata.get("essence", product.title),
                    image_url=product.image_url,
                    platform=listing.platform.name,
                    current_price=float(listing.current_price),
                    original_price=float(listing.original_price) if listing.original_price else None,
                    discount_percent=listing.discount_percent,
                    rank=len(deals) + 1,
                    category=product.category,
                    brand=product.brand
                )
                
                deals.append(deal_item)
                
            except Exception as e:
                logger.error(f"Error building deal {product.id}: {e}")
                continue
        
        # Cache for 15 minutes
        if deals:
            await redis.set_json(
                cache_key,
                [item.model_dump(mode='json') for item in deals],
                ttl=900
            )
            logger.info(f"Cached {len(deals)} home deals")
        
        logger.info(f"Home deals ready | Count: {len(deals)}")
        return deals
        
    except Exception as e:
        logger.error(f"Error fetching home deals: {e}", exc_info=True)
        return []

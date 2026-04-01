"""
Home Page API Endpoints

CENTRALIZED DATA ACCESS:
- Uses QueryService for all database operations
- Uses BusinessLogic for formatting and calculations
- Direct database-to-frontend communication (no Redis caching)
- Real-time product data
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.schemas import TrendingProductResponse
from app.services.queries import QueryService
from app.services.logic import BusinessLogic

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/featured", response_model=List[TrendingProductResponse])
async def get_featured_products(
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get featured products for home page banner
    
    ✅ Direct DB access (no cache)
    ✅ Platform diversity rotating
    ✅ Real-time featured products
    """
    try:
        query_service = QueryService(db)
        
        # Get featured products from DB
        products = await query_service.get_featured_products(limit=limit)
        
        if not products:
            logger.info(f"No featured products available | User: {user.id}")
            return []
        
        # Get listings for each product, with platform diversity
        all_listings_map = {}
        for product in products:
            listings = await query_service.get_product_listings(str(product.id))
            # Filter valid listings
            valid_listings = BusinessLogic.filter_valid_listings(listings, product)
            if valid_listings:
                all_listings_map[str(product.id)] = valid_listings
        
        # Select diverse listings
        product_listing_pairs = BusinessLogic.select_diverse_listings(products, all_listings_map)
        
        # Format responses
        featured = []
        for product, listing in product_listing_pairs:
            try:
                # Get platform count for this product
                product_id_str = str(product.id)
                listings_for_product = all_listings_map.get(product_id_str, [])
                platform_count = len(listings_for_product)
                response = BusinessLogic.format_trending_response(product, listing, platform_count=platform_count)
                response.rank = len(featured) + 1
                featured.append(response)
            except Exception as e:
                logger.error(f"Error formatting featured product {product.id}: {e}")
                continue
        
        logger.info(f"Featured products: {len(featured)} | User: {user.id}")
        return featured
        
    except Exception as e:
        logger.error(f"Error fetching featured products: {e}", exc_info=True)
        return []


@router.get("/categories", response_model=dict)
async def get_home_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get categories with product counts for home page
    
    ✅ Direct DB access (no cache)
    ✅ Real-time category data
    """
    try:
        query_service = QueryService(db)
        
        # Get category counts
        categories = await query_service.get_categories_with_counts()

        # Normalize to master-catalog section keys expected by the app.
        master_counts = {
            "mobiles": 0,
            "tablets": 0,
            "laptops": 0,
            "mobile_accessories": 0,
            "laptop_accessories": 0,
            "fashion": 0,
            "home_kitchen": 0,
            "books": 0,
        }

        for category, count in categories.items():
            category_text = str(category or "").lower()
            numeric_count = int(count or 0)

            if "book" in category_text:
                master_counts["books"] += numeric_count
            elif any(token in category_text for token in ["fashion", "clothing", "apparel"]):
                master_counts["fashion"] += numeric_count
            elif any(token in category_text for token in ["home", "kitchen", "furniture"]):
                master_counts["home_kitchen"] += numeric_count
            elif any(token in category_text for token in ["tablet", "ipad"]):
                master_counts["tablets"] += numeric_count
            elif any(token in category_text for token in ["laptop accessory", "computer accessory"]):
                master_counts["laptop_accessories"] += numeric_count
            elif any(token in category_text for token in ["mobile accessory", "phone accessory"]):
                master_counts["mobile_accessories"] += numeric_count
            elif any(token in category_text for token in ["laptop", "notebook", "computer"]):
                master_counts["laptops"] += numeric_count
            elif "accessor" in category_text:
                master_counts["mobile_accessories"] += numeric_count
            elif any(token in category_text for token in ["mobile", "phone", "smartphone", "electronics"]):
                master_counts["mobiles"] += numeric_count

        logger.info(f"Categories fetched: {len(master_counts)} | User: {user.id}")
        return master_counts
        
    except Exception as e:
        logger.error(f"Error fetching categories: {e}", exc_info=True)
        return {}


@router.get("/deals", response_model=List[TrendingProductResponse])
async def get_home_deals(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get best deals for home page
    
    ✅ Direct DB access (no cache)
    ✅ Highest discounts first
    ✅ Real-time deals
    """
    try:
        query_service = QueryService(db)
        
        # Get products with discounts
        products = await query_service.get_products_with_discount(
            min_discount=10,
            limit=limit
        )
        
        if not products:
            logger.info(f"No deals available | User: {user.id}")
            return []
        
        # Get and format listings
        deals = []
        for product in products:
            try:
                # Get listings for this product
                listings = await query_service.get_product_listings(str(product.id))
                valid_listings = BusinessLogic.filter_valid_listings(listings, product)
                
                if not valid_listings:
                    continue
                
                # Use listing with highest discount
                best_deal_listing = max(valid_listings, key=lambda l: l.discount_percent or 0)
                
                # Get platform count for this product
                platform_count = len(valid_listings)
                response = BusinessLogic.format_trending_response(product, best_deal_listing, platform_count=platform_count)
                response.rank = len(deals) + 1
                deals.append(response)
                
            except Exception as e:
                logger.error(f"Error formatting deal {product.id}: {e}")
                continue
        
        logger.info(f"Home deals: {len(deals)} | User: {user.id}")
        return deals
        
    except Exception as e:
        logger.error(f"Error fetching home deals: {e}", exc_info=True)
        return []


@router.get("/cross-platform", response_model=List[TrendingProductResponse])
async def get_home_cross_platform(
    limit: int = 24,
    min_platforms: int = 2,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get products that are available across multiple platforms.

    ✅ Direct DB access
    ✅ Cross-platform matched products only
    ✅ Intended for home page quick section
    """
    try:
        query_service = QueryService(db)
        safe_limit = max(1, min(int(limit or 24), 60))
        safe_min_platforms = max(2, min(int(min_platforms or 2), 6))

        candidates = await query_service.get_cross_platform_products(
            limit=max(safe_limit * 3, 30),
            min_platforms=safe_min_platforms,
        )

        if not candidates:
            logger.info(f"No cross-platform home products available | User: {user.id}")
            return []

        response_items: List[TrendingProductResponse] = []

        for product, raw_platform_count in candidates:
            listings = await query_service.get_product_listings(str(product.id), order_by="price_asc")
            valid_listings = BusinessLogic.filter_valid_listings(listings, product)
            if not valid_listings:
                continue

            distinct_platforms = {
                str(getattr(listing.platform, "name", "")).lower()
                for listing in valid_listings
                if getattr(listing, "platform", None) is not None
            }
            platform_count = len([p for p in distinct_platforms if p])
            platform_count = max(platform_count, int(raw_platform_count or 0))

            if platform_count < safe_min_platforms:
                continue

            best_listing = min(
                valid_listings,
                key=lambda listing: float(listing.current_price or float("inf")),
            )

            item = BusinessLogic.format_trending_response(
                product,
                best_listing,
                platform_count=platform_count,
            )
            item.rank = len(response_items) + 1
            response_items.append(item)

            if len(response_items) >= safe_limit:
                break

        logger.info(
            f"Home cross-platform products: {len(response_items)} | "
            f"min_platforms: {safe_min_platforms} | User: {user.id}"
        )
        return response_items

    except Exception as e:
        logger.error(f"Error fetching cross-platform home products: {e}", exc_info=True)
        return []

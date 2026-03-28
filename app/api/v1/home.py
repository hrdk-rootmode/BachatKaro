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
        
        # Format as dict
        trending_categories = {
            "Electronics": categories.get("Electronics", 0),
            "Fashion": categories.get("Fashion", 0),
            "Beauty": categories.get("Beauty", 0),
            "Home & Kitchen": categories.get("Home & Kitchen", 0),
            "Sports": categories.get("Sports", 0),
            "Books": categories.get("Books", 0)
        }
        
        logger.info(f"Categories fetched: {len(trending_categories)} | User: {user.id}")
        return trending_categories
        
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

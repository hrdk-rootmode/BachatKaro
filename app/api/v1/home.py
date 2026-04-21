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


@router.get("/category/{category_id}", response_model=List[TrendingProductResponse])
async def get_category_products(
    category_id: str,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all products for a specific category
    
    ✅ Direct DB access (no cache)
    ✅ Category-specific filtering
    ✅ Real-time category products
    """
    try:
        query_service = QueryService(db)
        
        # Map category IDs to search keywords and tighter include/exclude guards.
        category_keywords_map = {
            'mobiles': ['phone', 'smartphone', 'iphone', 'samsung', 'redmi', 'oneplus', 'realme', 'pixel', 'oppo', 'vivo', 'mobile'],
            'tablets': ['ipad', 'tablet', 'tab'],
            'laptops': ['laptop', 'notebook', 'macbook', 'chromebook', 'gaming laptop', 'ultrabook'],
            'mobile_accessories': ['cover', 'case', 'tempered', 'protector', 'charger', 'cable', 'earbuds', 'earphones', 'power bank', 'magsafe', 'airpods', 'mobile accessory'],
            'laptop_accessories': ['laptop bag', 'sleeve', 'mouse', 'keyboard', 'cooling pad', 'dock', 'usb hub', 'webcam', 'external ssd', 'hard disk', 'laptop accessory'],
            'fashion': ['shirt', 'tshirt', 't-shirt', 'jeans', 'dress', 'saree', 'kurta', 'shoes', 'fashion', 'watch', 'clothing'],
            'home_kitchen': ['mixer', 'kitchen', 'cookware', 'vacuum', 'chair', 'table', 'mattress', 'home', 'furniture'],
            'books': ['book', 'novel', 'author', 'paperback', 'hardcover', 'bestseller'],
        }

        category_rules = {
            'mobiles': {
                'include_any': ['mobile', 'smartphone', 'phone', 'iphone', 'samsung', 'redmi', 'oneplus', 'realme', 'vivo', 'oppo', 'pixel'],
                'exclude_any': ['women', 'men', 'kurta', 'saree', 'dress', 'shoe']
            },
            'tablets': {
                'include_any': ['tablet', 'ipad', 'tab'],
                'exclude_any': ['women', 'men', 'kurta', 'saree', 'dress', 'shoe']
            },
            'laptops': {
                'include_any': ['laptop', 'notebook', 'macbook', 'chromebook', 'ultrabook'],
                'exclude_any': ['women', 'men', 'kurta', 'saree', 'dress', 'shoe', 'lipstick', 'makeup']
            },
            'mobile_accessories': {
                'include_any': ['cover', 'case', 'tempered', 'charger', 'cable', 'earbud', 'earphone', 'power bank', 'magsafe'],
                'exclude_any': ['kurta', 'saree', 'dress', 'shoe']
            },
            'laptop_accessories': {
                'include_any': ['laptop bag', 'sleeve', 'mouse', 'keyboard', 'cooling pad', 'dock', 'usb hub', 'webcam', 'ssd', 'hard disk'],
                'exclude_any': ['kurta', 'saree', 'dress', 'shoe']
            },
            'fashion': {
                'include_any': ['fashion', 'shirt', 'tshirt', 'jeans', 'dress', 'saree', 'kurta', 'shoe', 'clothing'],
                'exclude_any': ['laptop', 'mobile', 'tablet', 'vacuum', 'cookware']
            },
            'home_kitchen': {
                'include_any': ['home', 'kitchen', 'cookware', 'vacuum', 'furniture', 'mixer', 'chair', 'table', 'mattress'],
                'exclude_any': ['kurta', 'saree', 'dress', 'shoe']
            },
            'books': {
                'include_any': ['book', 'novel', 'author', 'paperback', 'hardcover', 'bestseller'],
                'exclude_any': ['laptop', 'mobile', 'fashion', 'dress', 'saree']
            },
        }
        
        keywords = category_keywords_map.get(category_id, [])
        if not keywords:
            logger.warning(f"Unknown category: {category_id} | User: {user.id}")
            return []
        
        # Get products matching category keywords
        products = await query_service.search_products_by_keywords(
            keywords=keywords,
            limit=max(limit * 4, 160)
        )
        
        if not products:
            logger.info(f"No products found for category {category_id} | User: {user.id}")
            return []
        
        # Get and format listings
        category_products = []
        rules = category_rules.get(category_id, {"include_any": keywords, "exclude_any": []})
        include_any = [str(x).lower() for x in rules.get("include_any", [])]
        exclude_any = [str(x).lower() for x in rules.get("exclude_any", [])]

        for product in products:
            try:
                searchable = " ".join([
                    str(getattr(product, "title", "") or ""),
                    str(getattr(product, "brand", "") or ""),
                    str(getattr(product, "category", "") or ""),
                    str(getattr(product, "subcategory", "") or ""),
                ]).lower()

                if exclude_any and any(token in searchable for token in exclude_any):
                    continue
                if include_any and not any(token in searchable for token in include_any):
                    continue

                # Get listings for this product
                listings = await query_service.get_product_listings(str(product.id))
                valid_listings = BusinessLogic.filter_valid_listings(listings, product)
                
                if not valid_listings:
                    continue
                
                # Use listing with best price
                best_listing = min(valid_listings, key=lambda l: l.current_price or float('inf'))
                
                # Get platform count for this product
                platform_count = len(valid_listings)
                response = BusinessLogic.format_trending_response(product, best_listing, platform_count=platform_count)
                response.rank = len(category_products) + 1
                category_products.append(response)

                if len(category_products) >= limit:
                    break
                
            except Exception as e:
                logger.error(f"Error formatting product {product.id}: {e}")
                continue
        
        logger.info(f"Category {category_id} products: {len(category_products)} | User: {user.id}")
        return category_products
        
    except Exception as e:
        logger.error(f"Error fetching category products: {e}", exc_info=True)
        return []


@router.get("/recently-price-changed", response_model=List[TrendingProductResponse])
async def get_recently_price_changed(
    days: int = 7,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get products with recent price changes for home page
    
    ✅ Direct DB access (no cache)
    ✅ Sorted by most recent price change
    ✅ Real-time price change data
    """
    try:
        query_service = QueryService(db)
        
        # Get products with recent price changes
        product_listing_pairs = await query_service.get_recently_price_changed_products(
            days=days,
            limit=limit
        )
        
        if not product_listing_pairs:
            logger.info(f"No recently price-changed products available | User: {user.id}")
            return []
        
        # Format responses
        recently_changed = []
        for product, listing in product_listing_pairs:
            try:
                # Get all listings for this product to calculate platform count
                all_listings = await query_service.get_product_listings(str(product.id))
                valid_listings = BusinessLogic.filter_valid_listings(all_listings, product)
                platform_count = len(valid_listings)
                
                response = BusinessLogic.format_trending_response(product, listing, platform_count=platform_count)
                response.rank = len(recently_changed) + 1
                recently_changed.append(response)
            except Exception as e:
                logger.error(f"Error formatting recently changed product {product.id}: {e}")
                continue
        
        logger.info(f"Recently price-changed products: {len(recently_changed)} | User: {user.id}")
        return recently_changed
        
    except Exception as e:
        logger.error(f"Error fetching recently price-changed products: {e}", exc_info=True)
        return []

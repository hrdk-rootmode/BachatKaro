"""
Product Detail & Price History Routes

CENTRALIZED DATA ACCESS:
- Uses QueryService for all database operations
- Uses BusinessLogic for all data formatting and calculations
- Direct database-to-frontend communication (no Redis caching)
- Real-time data always fresh

✅ FIXED: Refresh endpoint now gracefully handles scraper failures
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.core.database import get_db
from app.models import Product, ProductListing, PriceHistory, User, Platform as PlatformModel
from app.schemas import (
    ProductResponse,
    PriceHistoryResponse,
    Platform
)
from app.api.deps import get_current_user
from app.services.queries import QueryService
from app.services.logic import BusinessLogic

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get complete product details with all platform listings
    
    ✅ Direct DB access (no cache)
    ✅ Real-time prices
    ✅ All platforms in one response
    ✅ Cross-platform comparison data included
    """
    try:
        # Get product from DB
        query_service = QueryService(db)
        product = await query_service.get_product_by_id(product_id)
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get all listings for this product
        listings = await query_service.get_product_listings(product_id, order_by="price_asc")
        
        # Filter to valid listings only
        valid_listings = BusinessLogic.filter_valid_listings(listings, product)
        
        if not valid_listings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No high-confidence listings available for this product"
            )
        
        logger.debug(
            f"Product {product_id}: "
            f"Fetched {len(valid_listings)} valid listings (total: {len(listings)})"
        )
        
        # Format and return response
        response = BusinessLogic.format_product_response(product, valid_listings)
        logger.info(f"Product fetched: {product_id} | User: {user.id} | Listings: {len(valid_listings)}")
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch product details: {str(e)[:100]}"
        )


@router.get("/{product_id}/price-history", response_model=PriceHistoryResponse)
async def get_price_history(
    product_id: str,
    platform: Platform,
    days: int = 120,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get price history for product on specific platform
    
    ✅ Direct DB access (no cache)
    ✅ Full history returned
    ✅ Real-time data
    """
    try:
        if days > 365:
            days = 365
        
        query_service = QueryService(db)
        
        # Verify product exists
        product = await query_service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get listing for this platform
        listing = await query_service.get_listing_by_platform(product_id, platform.value)
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not available on {platform.value}"
            )
        
        # Verify listing is valid
        if not BusinessLogic.is_listing_allowed(listing) or \
           not BusinessLogic.is_variant_consistent(listing, product):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product listing not available on {platform.value}"
            )
        
        # Get price history
        history = await query_service.get_price_history(
            product_id,
            platform.value,
            days=days
        )
        
        # Format and return response
        response = BusinessLogic.format_price_history_response(product, listing, history)
        logger.info(
            f"Price history: Product {product_id} | Platform: {platform.value} | "
            f"Records: {len(history)} | User: {user.id}"
        )
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching price history for {product_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch price history: {str(e)[:100]}"
        )


@router.post("/{product_id}/refresh-price", response_model=ProductResponse)
async def refresh_product_price(
    product_id: str,
    platform: Optional[Platform] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Force refresh prices for a specific product by scraping its listing URLs live
    
    ✅ FIXED: Graceful fallback to DB data when scraper fails
    ✅ No 503 errors - always returns latest DB snapshot
    ✅ Proper error handling with rollback
    """
    query_service = QueryService(db)
    
    # =========================================================================
    # STEP 1: Verify product exists and get current DB data
    # =========================================================================
    try:
        product = await query_service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get all listings for this product
        all_listings = await query_service.get_product_listings(product_id)
        
        # Filter to valid listings
        filtered_listings = BusinessLogic.filter_valid_listings(all_listings, product)
        
        # Further filter by platform if specified
        if platform:
            filtered_listings = [
                l for l in filtered_listings
                if hasattr(l, "platform") and l.platform and 
                l.platform.name.lower() == platform.value
            ]
        
        if not filtered_listings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No eligible listings found to refresh"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading product {product_id} for refresh: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load product: {str(e)[:100]}"
        )
    
    # =========================================================================
    # STEP 2: Attempt live scraping (with graceful failure handling)
    # =========================================================================
    now_utc = datetime.utcnow()
    refreshed_count = 0
    changed_count = 0
    failed_platforms = []
    scraper_available = False
    
    # ✅ FIX 1: Wrap scraper import in try/except
    try:
        from app.services.scraper.factory import get_platform_handler
        scraper_available = True
    except ImportError as e:
        logger.error(f"❌ Scraper module not available: {e}")
        scraper_available = False
    except Exception as e:
        logger.error(f"❌ Unexpected error importing scraper: {e}")
        scraper_available = False
    
    # Only attempt scraping if module is available
    if scraper_available:
        for listing in filtered_listings:
            platform_name = (
                listing.platform.name.lower()
                if hasattr(listing, "platform") and listing.platform
                else None
            )
            if not platform_name or not listing.product_url:
                continue
            
            try:
                # ✅ FIX 2: Pass db session to handler for healing persistence
                handler = await get_platform_handler(platform_name, db=db)
                if not handler:
                    failed_platforms.append(platform_name)
                    continue
                
                # Scrape live product data
                product_data = await handler.get_product(listing.product_url)
                if not product_data:
                    listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                    listing.last_error = "No data from live refresh"
                    failed_platforms.append(platform_name)
                    continue
                
                refreshed_count += 1
                old_price = listing.current_price
                new_price = float(product_data.current_price) \
                    if getattr(product_data, "current_price", None) else None
                
                # Update stock status
                if getattr(product_data, "in_stock", None) is not None:
                    listing.in_stock = bool(product_data.in_stock)
                
                # Update scrape metadata
                listing.last_scraped = now_utc
                listing.scrape_error_count = 0
                listing.last_error = None
                
                # Update price if new value available
                if new_price is not None:
                    listing.current_price = new_price
                    
                    # Record in price history
                    db.add(
                        PriceHistory(
                            product_listing_id=listing.id,
                            price=Decimal(str(new_price)),
                            in_stock=listing.in_stock if listing.in_stock is not None else True,
                            recorded_at=now_utc
                        )
                    )
                    
                    # Track price changes
                    if old_price is None or abs(float(new_price) - float(old_price)) > 0.01:
                        changed_count += 1
                        listing.last_price_change_at = now_utc
            
            except Exception as e:
                listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                listing.last_error = str(e)[:500]
                logger.error(f"Scrape error for listing {listing.id}: {e}")
                failed_platforms.append(platform_name)
    
    # =========================================================================
    # STEP 3: Commit changes (with proper error handling)
    # =========================================================================
    # ✅ FIX 3: Wrap commit in try/except with rollback
    try:
        await db.commit()
        logger.info(
            f"✅ Refresh commit successful: Product {product_id} | "
            f"Refreshed: {refreshed_count} | Changed: {changed_count}"
        )
    except Exception as e:
        logger.error(f"❌ Error committing refresh changes: {e}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        # Continue to return DB data even if commit failed
    
    # =========================================================================
    # STEP 4: Return response (ALWAYS return DB data, never 503)
    # =========================================================================
    # ✅ FIX 4: Don't raise 503, log warning and return current DB state
    if refreshed_count == 0:
        unique_failed = sorted(set(failed_platforms))
        failed_text = ", ".join(unique_failed) if unique_failed else "all configured platforms"
        
        logger.warning(
            f"⚠️ Live refresh failed for {failed_text} on product {product_id}. "
            f"Returning current DB snapshot. Scraper available: {scraper_available}"
        )
        
        # Don't raise error - just return DB data
        # User will see current prices even if scrape failed
    else:
        logger.info(
            f"✅ Live refresh: Product {product_id} | "
            f"Refreshed: {refreshed_count} | Changed: {changed_count} | User: {user.id}"
        )
    
    # Always return fresh data from DB (whether scrape succeeded or not)
    return await get_product(product_id=product_id, user=user, db=db)


@router.get("/{product_id}/cross-platform-variants")
async def get_cross_platform_variants(
    product_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all variants of the same product across different platforms
    
    Used for: "See this product on other platforms with different variants"
    
    Returns:
        {
            "base_product": { product info },
            "variants": [
                {
                    "variant_fingerprint": "iPhone 15 Pro 256GB Gold",
                    "platforms": [ { platform, price, url }, ... ]
                },
                ...
            ]
        }
    
    ✅ Groups by variant (e.g., color, storage)
    ✅ Shows all platform availability for each variant
    ✅ Used in cross-platform comparison UI
    """
    try:
        query_service = QueryService(db)
        
        # Get base product
        product = await query_service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get all listings for this product
        all_listings = await query_service.get_product_listings(product_id, order_by="price_asc")
        
        # Filter to valid listings
        valid_listings = BusinessLogic.filter_valid_listings(all_listings, product)
        
        if not valid_listings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No available listings for this product"
            )
        
        # Group by variant fingerprint
        variants_map = {}
        for listing in valid_listings:
            variant_fp = getattr(listing, "variant_fingerprint", None) or "standard"
            if variant_fp not in variants_map:
                variants_map[variant_fp] = []
            variants_map[variant_fp].append(listing)
        
        # Format response
        variants_data = []
        for variant_fp, listings_for_variant in variants_map.items():
            platform_data = []
            for listing in sorted(listings_for_variant, key=lambda x: x.current_price or 0):
                platform_name = "amazon"
                if hasattr(listing, "platform") and listing.platform:
                    platform_name = listing.platform.name.lower()
                
                platform_data.append({
                    "platform": platform_name,
                    "price": float(listing.current_price or 0),
                    "original_price": float(listing.original_price or 0) if listing.original_price else None,
                    "discount_percent": int(listing.discount_percent) if listing.discount_percent else None,
                    "url": listing.product_url or "",
                    "in_stock": listing.in_stock if listing.in_stock is not None else False,
                    "rating": listing.rating,
                    "review_count": listing.review_count,
                    "last_scraped": listing.last_scraped.isoformat() if listing.last_scraped else None
                })
            
            variants_data.append({
                "variant_fingerprint": variant_fp,
                "platform_count": len(platform_data),
                "platforms": platform_data,
                "cheapest_price": min(p["price"] for p in platform_data) if platform_data else 0
            })
        
        # Sort by cheapest price
        variants_data.sort(key=lambda x: x["cheapest_price"])
        
        response_data = {
            "product_id": str(product.id),
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "image_url": product.image_url,
            "total_platforms": len(set(l.platform_id for l in valid_listings)),
            "total_listings": len(valid_listings),
            "variants": variants_data
        }
        
        logger.info(
            f"Cross-platform variants: Product {product_id} | "
            f"Variants: {len(variants_data)} | Platforms: {response_data['total_platforms']} | "
            f"User: {user.id}"
        )
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching cross-platform variants for {product_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch cross-platform comparison: {str(e)[:100]}"
        )
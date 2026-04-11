"""
Centralized Database Queries Module

All database operations are centralized here for:
- Single point of data access
- Easy debugging and maintenance
- Direct database-to-frontend communication (no Redis caching)
- Consistent query patterns

Usage:
    from app.services.queries import QueryService
    
    service = QueryService(db)
    product = await service.get_product(product_id)
    listings = await service.get_product_listings(product_id)
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.models import Product, ProductListing, PriceHistory, Platform, User
from app.schemas import Platform as PlatformEnum

logger = logging.getLogger(__name__)


class QueryService:
    """
    Centralized query service - SINGLE SOURCE OF TRUTH for all database operations
    
    No caching, no Redis - Direct database access ensures:
    ✅ Real-time data
    ✅ Fresh prices always
    ✅ No stale cache issues
    ✅ Easy to debug
    ✅ Single file to modify
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logger
    
    # ========================================================================
    # PRODUCT QUERIES
    # ========================================================================
    
    async def get_product_by_id(self, product_id: str) -> Optional[Product]:
        """
        Get single product by ID
        
        Args:
            product_id: UUID of product
            
        Returns:
            Product ORM object or None if not found
        """
        self.logger.debug(f"Query: get_product_by_id({product_id})")
        product = await self.db.get(Product, product_id)
        return product
    
    async def get_products_by_ids(self, product_ids: List[str]) -> List[Product]:
        """
        Get multiple products by IDs (efficient batch query)
        
        Args:
            product_ids: List of product UUIDs
            
        Returns:
            List of Product ORM objects
        """
        if not product_ids:
            return []
        
        self.logger.debug(f"Query: get_products_by_ids(count={len(product_ids)})")
        result = await self.db.execute(
            select(Product).where(Product.id.in_(product_ids))
        )
        return result.scalars().all()
    
    async def search_products(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Product], int]:
        """
        Search products by title/description
        
        Args:
            query: Search term
            limit: Max results to return
            offset: Pagination offset
            
        Returns:
            Tuple of (products list, total count)
        """
        self.logger.debug(f"Query: search_products(query='{query}', limit={limit}, offset={offset})")
        
        search_token = f"%{query.lower()}%"
        
        # Get total count
        count_result = await self.db.execute(
            select(func.count(Product.id)).where(
                func.lower(Product.title).like(search_token)
            )
        )
        total = count_result.scalar() or 0
        
        # Get paginated results
        result = await self.db.execute(
            select(Product)
            .where(func.lower(Product.title).like(search_token))
            .order_by(Product.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        products = result.scalars().all()
        
        self.logger.debug(f"Search found {len(products)}/{total} products")
        return products, total
    
    async def search_products_by_keywords(
        self,
        keywords: List[str],
        limit: int = 100
    ) -> List[Product]:
        """
        Search products by multiple keywords (category filtering)
        
        Args:
            keywords: List of keywords to match against title, category, subcategory
            limit: Max results to return
            
        Returns:
            List of Product ORM objects matching any keyword
        """
        if not keywords:
            return []
        
        self.logger.debug(f"Query: search_products_by_keywords(keywords={keywords}, limit={limit})")
        
        normalized_keywords = [str(k or "").strip().lower() for k in keywords]
        normalized_keywords = [k for k in normalized_keywords if len(k) >= 2]
        if not normalized_keywords:
            return []

        # Build OR conditions for all keywords over stable Product fields.
        conditions = []
        for keyword in normalized_keywords:
            search_token = f"%{keyword}%"
            conditions.append(func.lower(Product.title).like(search_token))
            conditions.append(func.lower(Product.category).like(search_token))
            conditions.append(func.lower(func.coalesce(Product.subcategory, "")).like(search_token))
            conditions.append(func.lower(func.coalesce(Product.brand, "")).like(search_token))

        result = await self.db.execute(
            select(Product)
            .where(or_(*conditions))
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        products = result.scalars().all()

        self.logger.debug(f"Keyword search found {len(products)} products")
        return products

    
    # ========================================================================
    # LISTING QUERIES
    # ========================================================================
    
    async def get_product_listings(
        self,
        product_id: str,
        order_by: str = "price_asc"
    ) -> List[ProductListing]:
        """
        Get ALL listings for a product
        
        Args:
            product_id: UUID of product
            order_by: Sort method - 'price_asc', 'price_desc', 'date_desc'
            
        Returns:
            List of ProductListing ORM objects with platform eager-loaded
        """
        self.logger.debug(f"Query: get_product_listings({product_id}, order_by={order_by})")
        
        query = select(ProductListing).where(
            ProductListing.product_id == product_id
        ).options(selectinload(ProductListing.platform))
        
        # Apply ordering
        if order_by == "price_asc":
            query = query.order_by(ProductListing.current_price.asc())
        elif order_by == "price_desc":
            query = query.order_by(ProductListing.current_price.desc())
        else:  # date_desc
            query = query.order_by(ProductListing.last_scraped.desc().nullslast())
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_listing_by_platform(
        self,
        product_id: str,
        platform: str
    ) -> Optional[ProductListing]:
        """
        Get listing for specific platform
        
        Args:
            product_id: UUID of product
            platform: Platform name (e.g., 'amazon', 'flipkart')
            
        Returns:
            ProductListing ORM object or None
        """
        self.logger.debug(f"Query: get_listing_by_platform({product_id}, {platform})")
        
        result = await self.db.execute(
            select(ProductListing)
            .join(Platform, ProductListing.platform_id == Platform.id)
            .where(
                ProductListing.product_id == product_id,
                func.lower(Platform.name) == platform.lower()
            )
            .options(selectinload(ProductListing.platform))
            .order_by(ProductListing.last_scraped.desc().nullslast())
        )
        listings = result.scalars().all()
        return listings[0] if listings else None
    
    async def get_cheapest_listing(
        self,
        product_id: str
    ) -> Optional[ProductListing]:
        """
        Get cheapest listing for a product across all platforms
        
        Args:
            product_id: UUID of product
            
        Returns:
            ProductListing with lowest price or None
        """
        self.logger.debug(f"Query: get_cheapest_listing({product_id})")
        
        result = await self.db.execute(
            select(ProductListing)
            .where(
                ProductListing.product_id == product_id,
                ProductListing.current_price.isnot(None)
            )
            .options(selectinload(ProductListing.platform))
            .order_by(ProductListing.current_price.asc())
            .limit(1)
        )
        return result.scalars().first()
    
    # ========================================================================
    # PRICE HISTORY QUERIES
    # ========================================================================
    
    async def get_price_history(
        self,
        product_id: str,
        platform: str,
        days: int = 120
    ) -> List[PriceHistory]:
        """
        Get price history for product on specific platform
        
        Args:
            product_id: UUID of product
            platform: Platform name
            days: Number of days to look back (max 365)
            
        Returns:
            List of PriceHistory ORM objects, sorted by date ascending
        """
        if days > 365:
            days = 365
        
        self.logger.debug(f"Query: get_price_history({product_id}, {platform}, days={days})")
        
        from_date = datetime.utcnow() - timedelta(days=days)
        
        # First, get the listing to find listing_id
        listing = await self.get_listing_by_platform(product_id, platform)
        if not listing:
            self.logger.warning(f"No listing found for {product_id} on {platform}")
            return []
        
        # Get price history for this listing
        # ✅ FIXED: Use product_listing_id (not listing_id)
        result = await self.db.execute(
            select(PriceHistory)
            .where(
                PriceHistory.product_listing_id == listing.id,
                PriceHistory.recorded_at >= from_date
            )
            .order_by(PriceHistory.recorded_at.asc())
        )
        history = result.scalars().all()
        self.logger.debug(f"Found {len(history)} price history points")
        return history
    
    async def get_latest_price_for_listing(
        self,
        listing_id: str
    ) -> Optional[PriceHistory]:
        """
        Get most recent price record for a listing
        
        Args:
            listing_id: UUID of listing
            
        Returns:
            Most recent PriceHistory record or None
        """
        self.logger.debug(f"Query: get_latest_price_for_listing({listing_id})")
        
        # ✅ FIXED: Use product_listing_id (not listing_id)
        result = await self.db.execute(
            select(PriceHistory)
            .where(PriceHistory.product_listing_id == listing_id)
            .order_by(PriceHistory.recorded_at.desc())
            .limit(1)
        )
        return result.scalars().first()
    
    # ========================================================================
    # FEATURED/TRENDING QUERIES
    # ========================================================================
    
    async def get_featured_products(self, limit: int = 10) -> List[Product]:
        """
        Get featured products (newest with image)
        
        Args:
            limit: Number of products to return
            
        Returns:
            List of recent products with images
        """
        self.logger.debug(f"Query: get_featured_products(limit={limit})")
        
        result = await self.db.execute(
            select(Product)
            .where(
                Product.image_url.isnot(None),
                Product.title.isnot(None)
            )
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def get_trending_products(
        self,
        limit: int = 20,
        days: int = 7
    ) -> List[Product]:
        """
        Get trending products (most viewed/saved recently)
        
        Args:
            limit: Number of products to return
            days: Time window for trending
            
        Returns:
            List of trending products
        """
        self.logger.debug(f"Query: get_trending_products(limit={limit}, days={days})")
        
        from_date = datetime.utcnow() - timedelta(days=days)
        
        result = await self.db.execute(
            select(Product)
            .where(
                Product.image_url.isnot(None),
                Product.title.isnot(None),
                Product.created_at >= from_date
            )
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    # ========================================================================
    # CATEGORY QUERIES
    # ========================================================================
    
    async def get_categories_with_counts(self) -> dict:
        """
        Get all categories with product counts
        
        Returns:
            Dict of {category: count}
        """
        self.logger.debug("Query: get_categories_with_counts()")
        
        result = await self.db.execute(
            select(Product.category, func.count(Product.id))
            .where(Product.category.isnot(None))
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
        )
        
        categories = {}
        for category, count in result.all():
            if category:
                categories[category] = count
        
        self.logger.debug(f"Found {len(categories)} categories")
        return categories
    
    async def get_products_by_category(
        self,
        category: str,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Product], int]:
        """
        Get products filtered by category
        
        Args:
            category: Category name
            limit: Results per page
            offset: Pagination offset
            
        Returns:
            Tuple of (products list, total count)
        """
        self.logger.debug(f"Query: get_products_by_category({category}, limit={limit}, offset={offset})")
        
        # Get total count
        count_result = await self.db.execute(
            select(func.count(Product.id)).where(Product.category == category)
        )
        total = count_result.scalar() or 0
        
        # Get paginated results
        result = await self.db.execute(
            select(Product)
            .where(Product.category == category)
            .order_by(Product.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        products = result.scalars().all()
        
        return products, total
    
    # ========================================================================
    # PLATFORM QUERIES
    # ========================================================================
    
    async def get_all_platforms(self) -> List[Platform]:
        """
        Get all available platforms
        
        Returns:
            List of Platform ORM objects
        """
        self.logger.debug("Query: get_all_platforms()")
        
        result = await self.db.execute(select(Platform))
        return result.scalars().all()
    
    async def get_platform_by_name(self, name: str) -> Optional[Platform]:
        """
        Get platform by name
        
        Args:
            name: Platform name (e.g., 'amazon')
            
        Returns:
            Platform ORM object or None
        """
        self.logger.debug(f"Query: get_platform_by_name({name})")
        
        result = await self.db.execute(
            select(Platform).where(func.lower(Platform.name) == name.lower())
        )
        return result.scalars().first()
    
    # ========================================================================
    # DEALS/DISCOUNTS QUERIES
    # ========================================================================
    
    async def get_products_with_discount(
        self,
        min_discount: int = 10,
        limit: int = 20
    ) -> List[Product]:
        """
        Get products with discounts above threshold
        
        Args:
            min_discount: Minimum discount percentage
            limit: Number of products to return
            
        Returns:
            List of products with discounts
        """
        self.logger.debug(f"Query: get_products_with_discount(min_discount={min_discount}, limit={limit})")
        
        # ✅ FIXED: Removed problematic DISTINCT ON, using subquery approach
        # First get product IDs with discounts
        subquery = (
            select(ProductListing.product_id)
            .where(
                ProductListing.discount_percent >= min_discount
            )
            .distinct()
            .limit(limit)
        ).subquery()
        
        # Then get the products
        result = await self.db.execute(
            select(Product)
            .where(
                Product.id.in_(select(subquery.c.product_id)),
                Product.image_url.isnot(None)
            )
            .limit(limit)
        )
        return result.scalars().all()

    async def get_cross_platform_products(
        self,
        limit: int = 10,
        min_platforms: int = 2,
    ) -> List[Tuple[Product, int]]:
        """
        Get products present on multiple platforms.

        Args:
            limit: Max products to return
            min_platforms: Minimum distinct platform count

        Returns:
            List of tuples: (Product, distinct_platform_count)
        """
        min_platforms = max(2, int(min_platforms or 2))
        limit = max(1, int(limit or 10))

        self.logger.debug(
            f"Query: get_cross_platform_products(limit={limit}, min_platforms={min_platforms})"
        )

        platform_stats = (
            select(
                ProductListing.product_id.label("product_id"),
                func.count(func.distinct(ProductListing.platform_id)).label("platform_count"),
                func.max(
                    func.coalesce(
                        ProductListing.last_scraped,
                        ProductListing.last_price_change_at,
                        ProductListing.created_at,
                    )
                ).label("last_listing_activity"),
            )
            .where(
                ProductListing.in_stock == True,
                ProductListing.current_price.isnot(None),
            )
            .group_by(ProductListing.product_id)
            .having(func.count(func.distinct(ProductListing.platform_id)) >= min_platforms)
            .subquery()
        )

        result = await self.db.execute(
            select(Product, platform_stats.c.platform_count)
            .join(platform_stats, Product.id == platform_stats.c.product_id)
            .where(
                Product.image_url.isnot(None),
                Product.title.isnot(None),
            )
            .order_by(
                platform_stats.c.platform_count.desc(),
                platform_stats.c.last_listing_activity.desc(),
                func.coalesce(Product.updated_at, Product.created_at).desc(),
            )
            .limit(limit)
        )

        rows = result.all()
        return [(row[0], int(row[1] or 0)) for row in rows]
    
    # ========================================================================
    # USER QUERIES
    # ========================================================================
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get user by ID
        
        Args:
            user_id: User UUID
            
        Returns:
            User ORM object or None
        """
        self.logger.debug(f"Query: get_user_by_id({user_id})")
        user = await self.db.get(User, user_id)
        return user
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email
        
        Args:
            email: User email
            
        Returns:
            User ORM object or None
        """
        self.logger.debug(f"Query: get_user_by_email({email})")
        
        result = await self.db.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        return result.scalars().first()
    
    # ========================================================================
    # BULK/ADMIN QUERIES
    # ========================================================================
    
    async def get_all_products(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Product], int]:
        """
        Get all products (admin use)
        
        Args:
            limit: Results per page
            offset: Pagination offset
            
        Returns:
            Tuple of (products list, total count)
        """
        self.logger.debug(f"Query: get_all_products(limit={limit}, offset={offset})")
        
        # Get total count
        count_result = await self.db.execute(select(func.count(Product.id)))
        total = count_result.scalar() or 0
        
        # Get paginated results
        result = await self.db.execute(
            select(Product)
            .order_by(Product.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        products = result.scalars().all()
        
        return products, total
    
    async def get_stale_listings(self, hours: int = 24) -> List[ProductListing]:
        """
        Get listings that haven't been updated in N hours
        
        Args:
            hours: Hours since last scrape
            
        Returns:
            List of stale ProductListing objects
        """
        self.logger.debug(f"Query: get_stale_listings(hours={hours})")
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        result = await self.db.execute(
            select(ProductListing)
            .where(
                (ProductListing.last_scraped.is_(None)) |
                (ProductListing.last_scraped < cutoff_time)
            )
            .order_by(ProductListing.last_scraped.asc().nullsfirst())
        )
        return result.scalars().all()
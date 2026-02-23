"""
Cross-Platform Product Matcher
Finds same product across multiple e-commerce platforms

Features:
- Fingerprint-based matching
- Fuzzy title matching
- Price comparison
- Best deal detection
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal
from datetime import datetime
import re
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Product, ProductListing, Platform as PlatformModel
from app.services.scraper.base import ProductData, SearchResult
from app.services.scraper.factory import get_platform_handler, get_all_handlers
from app.core.config import settings

logger = logging.getLogger(__name__)


class CrossPlatformMatcher:
    """
    Find same product across different platforms
    
    Strategy:
    1. Check database for existing matches (fingerprint)
    2. Search on all platforms using product title
    3. Score matches by similarity
    4. Return all alternatives sorted by price
    
    Usage:
        matcher = CrossPlatformMatcher()
        alternatives = await matcher.find_alternatives(
            source_product,
            db,
            search_if_not_found=True
        )
    """
    
    # Minimum similarity score for match
    MIN_SIMILARITY_SCORE = 0.6
    
    # Maximum concurrent searches
    MAX_CONCURRENT_SEARCHES = 4
    
    # Common words to ignore in matching
    STOP_WORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'it', 'as', 'be', 'this', 'that',
        'are', 'was', 'were', 'been', 'being', 'have', 'has', 'had', 'do',
        'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
        'must', 'shall', 'can', 'need', 'dare', 'ought', 'used', 'new',
        'best', 'top', 'latest', 'pack', 'set', 'combo', 'offer', 'deal'
    }
    
    def __init__(self):
        self._search_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SEARCHES)
    
    async def find_alternatives(
        self,
        source_product: ProductData,
        db: AsyncSession,
        search_if_not_found: bool = True,
        skip_platforms: List[str] = None
    ) -> List[ProductData]:
        """
        Find same product on other platforms
        
        Args:
            source_product: Product to find alternatives for
            db: Database session
            search_if_not_found: Search on other platforms if not in DB
            skip_platforms: Platforms to skip (usually source platform)
        
        Returns:
            List of ProductData from all platforms (including source)
        """
        skip_platforms = skip_platforms or []
        skip_platforms.append(source_product.platform_name)
        
        alternatives = [source_product]
        
        # Step 1: Check database for existing matches
        db_matches = await self._find_in_database(
            source_product.fingerprint,
            db,
            skip_platforms
        )
        
        if db_matches:
            logger.info(
                f"Found {len(db_matches)} existing alternatives in database "
                f"for {source_product.title[:50]}"
            )
            alternatives.extend(db_matches)
        
        # Step 2: Search on other platforms if enabled
        if search_if_not_found:
            # Get search query from product title
            search_query = self._extract_search_query(source_product)
            
            # Get all handlers
            handlers = await get_all_handlers(db, active_only=True)
            
            # Filter out skip platforms
            handlers = [
                h for h in handlers
                if h.platform_name not in skip_platforms
            ]
            
            # Search concurrently
            search_tasks = [
                self._search_with_semaphore(handler, search_query, source_product)
                for handler in handlers
            ]
            
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Process results
            for result in search_results:
                if isinstance(result, Exception):
                    logger.error(f"Search error: {result}")
                    continue
                
                if result:
                    alternatives.append(result)
        
        # Sort by price (cheapest first)
        alternatives.sort(key=lambda x: x.current_price)
        
        logger.info(
            f"Found {len(alternatives)} total options for {source_product.title[:50]}"
        )
        
        return alternatives
    
    async def _find_in_database(
        self,
        fingerprint: str,
        db: AsyncSession,
        skip_platforms: List[str]
    ) -> List[ProductData]:
        """Find matching products in database"""
        # Find product by fingerprint
        result = await db.execute(
            select(Product)
            .where(Product.fingerprint == fingerprint)
            .options(selectinload(Product.listings))
        )
        product = result.scalar_one_or_none()
        
        if not product:
            return []
        
        # Convert listings to ProductData
        alternatives = []
        
        for listing in product.listings:
            # Get platform info
            platform_result = await db.execute(
                select(PlatformModel).where(PlatformModel.id == listing.platform_id)
            )
            platform = platform_result.scalar_one_or_none()
            
            if not platform or platform.name in skip_platforms:
                continue
            
            if not listing.in_stock:
                continue
            
            alternatives.append(ProductData(
                external_id=listing.external_id or str(listing.id),
                title=product.title,
                current_price=Decimal(str(listing.current_price)),
                original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
                discount_percent=listing.discount_percent,
                product_url=listing.product_url,
                platform_name=platform.name,
                image_url=product.image_url,
                rating=listing.rating,
                review_count=listing.review_count,
                in_stock=listing.in_stock,
                brand=product.brand,
                category=product.category,
                _fingerprint=product.fingerprint
            ))
        
        return alternatives
    
    async def _search_with_semaphore(
        self,
        handler,
        query: str,
        source_product: ProductData
    ) -> Optional[ProductData]:
        """Search with concurrency limit"""
        async with self._search_semaphore:
            try:
                logger.debug(f"Searching on {handler.platform_name}: {query}")
                
                search_result = await handler.search(query, page=1)
                
                if not search_result.success or not search_result.products:
                    return None
                
                # Find best match
                best_match = self._find_best_match(
                    source_product,
                    search_result.products
                )
                
                return best_match
            
            except Exception as e:
                logger.error(f"Search failed on {handler.platform_name}: {e}")
                return None
    
    def _extract_search_query(self, product: ProductData) -> str:
        """Extract optimal search query from product"""
        title = product.title
        
        # Remove common suffixes
        title = re.sub(r'\([^)]*\)', '', title)  # Remove parentheses
        title = re.sub(r'\[[^\]]*\]', '', title)  # Remove brackets
        title = re.sub(r'-\s*\d+\s*(GB|MB|TB)', '', title, flags=re.IGNORECASE)
        
        # Get important words
        words = title.lower().split()
        important_words = [
            w for w in words
            if w not in self.STOP_WORDS and len(w) > 2
        ]
        
        # Add brand if available
        if product.brand:
            brand_lower = product.brand.lower()
            if brand_lower not in important_words:
                important_words.insert(0, brand_lower)
        
        # Take first 5 important words
        query = ' '.join(important_words[:5])
        
        return query
    
    def _find_best_match(
        self,
        source: ProductData,
        candidates: List[ProductData]
    ) -> Optional[ProductData]:
        """Find best matching product from candidates"""
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            score = self._calculate_similarity(source, candidate)
            
            if score >= self.MIN_SIMILARITY_SCORE and score > best_score:
                best_match = candidate
                best_score = score
        
        if best_match:
            logger.debug(
                f"Best match: {best_match.title[:50]} "
                f"(score: {best_score:.2f})"
            )
        
        return best_match
    
    def _calculate_similarity(
        self,
        product_a: ProductData,
        product_b: ProductData
    ) -> float:
        """Calculate similarity score between two products"""
        score = 0.0
        
        # 1. Fingerprint match (exact)
        if product_a.fingerprint == product_b.fingerprint:
            return 1.0
        
        # 2. Title similarity (Jaccard)
        title_score = self._jaccard_similarity(
            product_a.title.lower(),
            product_b.title.lower()
        )
        score += title_score * 0.5  # 50% weight
        
        # 3. Brand match
        if product_a.brand and product_b.brand:
            if product_a.brand.lower() == product_b.brand.lower():
                score += 0.2  # 20% weight
        
        # 4. Price proximity (within 30%)
        price_ratio = float(min(product_a.current_price, product_b.current_price)) / \
                      float(max(product_a.current_price, product_b.current_price))
        
        if price_ratio >= 0.7:  # Within 30%
            score += 0.2 * price_ratio  # 20% weight
        
        # 5. Category match
        if product_a.category and product_b.category:
            if product_a.category.lower() == product_b.category.lower():
                score += 0.1  # 10% weight
        
        return min(score, 1.0)
    
    def _jaccard_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate Jaccard similarity between two texts"""
        # Tokenize
        words_a = set(re.findall(r'\w+', text_a.lower()))
        words_b = set(re.findall(r'\w+', text_b.lower()))
        
        # Remove stop words
        words_a = words_a - self.STOP_WORDS
        words_b = words_b - self.STOP_WORDS
        
        if not words_a or not words_b:
            return 0.0
        
        intersection = words_a & words_b
        union = words_a | words_b
        
        return len(intersection) / len(union)
    
    def calculate_savings(
        self,
        alternatives: List[ProductData]
    ) -> Dict[str, Any]:
        """Calculate potential savings from alternatives"""
        if len(alternatives) < 2:
            return {
                "has_savings": False,
                "best_price": float(alternatives[0].current_price) if alternatives else 0,
                "max_savings": 0,
                "best_platform": alternatives[0].platform_name if alternatives else None
            }
        
        # Sort by price
        sorted_products = sorted(alternatives, key=lambda x: x.current_price)
        
        cheapest = sorted_products[0]
        most_expensive = sorted_products[-1]
        
        max_savings = float(most_expensive.current_price - cheapest.current_price)
        savings_percent = (max_savings / float(most_expensive.current_price)) * 100
        
        return {
            "has_savings": max_savings > 0,
            "best_price": float(cheapest.current_price),
            "best_platform": cheapest.platform_name,
            "highest_price": float(most_expensive.current_price),
            "highest_price_platform": most_expensive.platform_name,
            "max_savings": max_savings,
            "savings_percent": round(savings_percent, 1)
        }


# Singleton instance
cross_platform_matcher = CrossPlatformMatcher()
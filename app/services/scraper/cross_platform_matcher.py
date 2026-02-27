"""
Cross-Platform Product Matcher - AI Essence Edition
Finds same product across multiple e-commerce platforms

Features:
- AI ESSENCE MATCHING: Uses normalized fingerprint for accurate deduplication
- Source-agnostic: Works with both API and Scraper data
- Category-aware platform routing
- Accessory filtering (no false positives)
- Price comparison and savings calculation
- Concurrent search with rate limiting
- Database + Live search hybrid

Author: DealHunt
Updated: AI Essence Integration + API Ready
"""

import logging
import asyncio
import hashlib
import re
from typing import Optional, List, Dict, Any, Tuple, Set
from decimal import Decimal
from datetime import datetime

from app.services.scraper.base import ProductData, SearchResult, ProductCategory, HandlerType
from app.core.config import settings

logger = logging.getLogger(__name__)

# Optional database imports
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models import Product, ProductListing, Platform as PlatformModel
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    AsyncSession = None


class CrossPlatformMatcher:
    """
    Find same product across different platforms using AI Essence
    
    MATCHING STRATEGY (Priority Order):
    1. EXACT: AI essence fingerprint match (100% confidence)
    2. HIGH: Same brand + similar title (90% confidence)
    3. MEDIUM: Jaccard similarity > 0.7 (70% confidence)
    4. LOW: Price + category match (50% confidence)
    
    SOURCE AGNOSTIC:
    - Works identically with API or Scraper data
    - ProductData.data_source indicates origin
    - Matching logic doesn't care about source
    
    API READY:
    - When you add API keys, Factory will prefer API
    - If API fails, falls back to Scraper
    - Matcher sees same ProductData regardless
    """
    
    # Matching thresholds
    MIN_SIMILARITY_SCORE = 0.55
    ESSENCE_MATCH_SCORE = 1.0
    BRAND_MATCH_BONUS = 0.20
    PRICE_MATCH_BONUS = 0.15
    CATEGORY_MATCH_BONUS = 0.10
    
    # Concurrency limits
    MAX_CONCURRENT_SEARCHES = 4
    SEARCH_TIMEOUT_SECONDS = 30
    
    # Stop words for title comparison
    STOP_WORDS: Set[str] = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'it', 'as', 'be', 'this', 'that',
        'are', 'was', 'were', 'been', 'being', 'have', 'has', 'had', 'do',
        'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
        'must', 'shall', 'can', 'need', 'new', 'best', 'top', 'latest',
        'pack', 'set', 'combo', 'offer', 'deal', 'buy', 'online', 'price',
        'india', 'sale', 'discount', 'off', 'free', 'shipping', 'delivery'
    }
    
    # Accessory keywords for filtering
    ACCESSORY_KEYWORDS: Set[str] = {
        "cover", "case", "screen guard", "protector", "tempered glass",
        "charger", "cable", "holder", "stand", "skin", "pouch", "adapter",
        "back cover", "flip cover", "screen protector", "earphone", "earbuds",
        "strap", "band", "sleeve", "bag", "mount", "dock", "hub", "dongle"
    }
    
    def __init__(self):
        self._search_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SEARCHES)
        self._ai_client = None  # Lazy load
    
    async def _get_ai_client(self):
        """Lazy load AI client to avoid circular imports"""
        if self._ai_client is None:
            try:
                from app.services.ai.groq_client import groq_client
                self._ai_client = groq_client
            except ImportError:
                logger.warning("AI client not available for matching")
        return self._ai_client
    
    async def find_alternatives(
        self,
        source_product: ProductData,
        db: Optional[Any] = None,
        search_if_not_found: bool = True,
        skip_platforms: List[str] = None,
        max_results: int = 10
    ) -> List[ProductData]:
        """
        Find same product on other platforms
        
        FLOW:
        1. Check database for existing matches (by fingerprint)
        2. If not found, search on relevant platforms
        3. Score matches using AI essence + similarity
        4. Filter accessories and low-confidence matches
        5. Return sorted by price
        
        Args:
            source_product: Product to find alternatives for
            db: Database session (optional)
            search_if_not_found: Search live if not in DB
            skip_platforms: Platforms to skip
            max_results: Maximum alternatives to return
        
        Returns:
            List of ProductData from all platforms (including source)
        """
        skip_platforms = set(skip_platforms or [])
        skip_platforms.add(source_product.platform_name.lower())
        
        alternatives = [source_product]
        found_fingerprints = {source_product.fingerprint}
        
        logger.info(
            f"Finding alternatives for: {source_product.title[:50]}... "
            f"(fingerprint: {source_product.fingerprint[:12]})"
        )
        
        # Step 1: Check database for existing matches
        if DB_AVAILABLE and db is not None:
            db_matches = await self._find_in_database(
                source_product,
                db,
                skip_platforms
            )
            
            for match in db_matches:
                if match.fingerprint not in found_fingerprints:
                    alternatives.append(match)
                    found_fingerprints.add(match.fingerprint)
            
            if db_matches:
                logger.info(f"Found {len(db_matches)} alternatives in database")
        
        # Step 2: Live search on relevant platforms
        if search_if_not_found and len(alternatives) < max_results:
            live_matches = await self._search_live_platforms(
                source_product,
                db,
                skip_platforms,
                found_fingerprints
            )
            
            for match in live_matches:
                if match.fingerprint not in found_fingerprints:
                    alternatives.append(match)
                    found_fingerprints.add(match.fingerprint)
                    
                    if len(alternatives) >= max_results:
                        break
        
        # Sort by price (lowest first)
        alternatives.sort(key=lambda x: float(x.current_price))
        
        logger.info(
            f"Found {len(alternatives)} total options "
            f"(source: {source_product.data_source.value})"
        )
        
        return alternatives[:max_results]
    
    async def _find_in_database(
        self,
        source_product: ProductData,
        db: Any,
        skip_platforms: Set[str]
    ) -> List[ProductData]:
        """Find matching products in database using fingerprint"""
        if not DB_AVAILABLE:
            return []
        
        try:
            # Strategy 1: Exact fingerprint match
            result = await db.execute(
                select(Product)
                .where(Product.fingerprint == source_product.fingerprint)
                .options(selectinload(Product.listings))
            )
            product = result.scalar_one_or_none()
            
            # Strategy 2: Try AI essence match if available
            if not product and source_product.ai_essence:
                # Search by essence hash
                essence_fp = hashlib.sha256(
                    source_product.ai_essence.encode()
                ).hexdigest()[:32]
                
                result = await db.execute(
                    select(Product)
                    .where(Product.fingerprint == essence_fp)
                    .options(selectinload(Product.listings))
                )
                product = result.scalar_one_or_none()
            
            if not product:
                return []
            
            alternatives = []
            
            for listing in product.listings:
                # Get platform name
                platform_result = await db.execute(
                    select(PlatformModel).where(PlatformModel.id == listing.platform_id)
                )
                platform = platform_result.scalar_one_or_none()
                
                if not platform:
                    continue
                
                if platform.name.lower() in skip_platforms:
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
                    subcategory=product.subcategory,
                    specifications=product.specifications or {},
                    ai_essence=product.ai_metadata.get("essence") if product.ai_metadata else None,
                    ai_tags=product.ai_metadata.get("tags", []) if product.ai_metadata else [],
                    ai_quality_score=product.ai_metadata.get("quality_score", 0) if product.ai_metadata else 0,
                    ai_processed=True,
                    data_source=HandlerType.SCRAPER,  # DB data originally from scraper
                    _fingerprint=product.fingerprint
                ))
            
            return alternatives
        
        except Exception as e:
            logger.error(f"Database query error: {e}")
            return []
    
    async def _search_live_platforms(
        self,
        source_product: ProductData,
        db: Optional[Any],
        skip_platforms: Set[str],
        found_fingerprints: Set[str]
    ) -> List[ProductData]:
        """Search for product on live platforms"""
        # Detect category for smart routing
        category = ProductCategory.detect_from_query(source_product.title)
        relevant_platforms = ProductCategory.get_platforms_for_category(category)
        
        logger.debug(f"Category: {category.value}, Target platforms: {relevant_platforms}")
        
        # Build search query
        search_query = self._build_search_query(source_product)
        
        # Get handlers from factory
        try:
            from app.services.scraper.factory import get_factory
            factory = get_factory()
        except ImportError:
            logger.error("Factory import failed")
            return []
        
        # Collect handlers (Factory will return API if available, else Scraper)
        handlers = []
        for platform_name in relevant_platforms:
            if platform_name.lower() in skip_platforms:
                continue
            
            try:
                # Factory automatically chooses API or Scraper based on config
                handler = await factory.get_handler(platform_name, db)
                handlers.append(handler)
            except Exception as e:
                logger.debug(f"Skip {platform_name}: {e}")
        
        if not handlers:
            return []
        
        # Search concurrently with timeout
        search_tasks = [
            self._search_with_timeout(handler, search_query, source_product)
            for handler in handlers
        ]
        
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Collect valid matches
        matches = []
        for result in results:
            if isinstance(result, Exception):
                logger.debug(f"Search task error: {result}")
                continue
            
            if result and result.fingerprint not in found_fingerprints:
                matches.append(result)
        
        return matches
    
    async def _search_with_timeout(
        self,
        handler,
        query: str,
        source_product: ProductData
    ) -> Optional[ProductData]:
        """Search with semaphore and timeout"""
        async with self._search_semaphore:
            try:
                # Timeout wrapper
                search_coro = handler.search(query, page=1)
                search_result = await asyncio.wait_for(
                    search_coro,
                    timeout=self.SEARCH_TIMEOUT_SECONDS
                )
                
                if not search_result.success or not search_result.products:
                    return None
                
                # Find best match from results
                best_match = await self._find_best_match(
                    source_product,
                    search_result.products
                )
                
                if best_match:
                    logger.debug(
                        f"Match found on {handler.platform_name}: "
                        f"{best_match.title[:40]}... "
                        f"(source: {best_match.data_source.value})"
                    )
                
                return best_match
            
            except asyncio.TimeoutError:
                logger.warning(f"Search timeout on {handler.platform_name}")
                return None
            except Exception as e:
                logger.error(f"Search failed on {handler.platform_name}: {e}")
                return None
    
    def _build_search_query(self, product: ProductData) -> str:
        """Build optimal search query from product"""
        # Start with title
        title = product.title
        
        # Remove noise patterns
        noise_patterns = [
            r'\([^)]*\)',           # (anything)
            r'\[[^\]]*\]',          # [anything]
            r'-\s*\d+\s*(GB|MB|TB)', # Storage specs
            r'with\s+\d+%\s+off',   # Discount text
            r'buy\s+',              # Buy
            r'online\s*',           # Online
            r'at\s+best\s+price',   # Best price
        ]
        
        for pattern in noise_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        # Tokenize and filter
        words = re.findall(r'\b[a-zA-Z0-9]+\b', title.lower())
        important_words = [
            w for w in words
            if w not in self.STOP_WORDS and len(w) > 2
        ]
        
        # Add brand if not in title
        if product.brand:
            brand_lower = product.brand.lower()
            if brand_lower not in important_words:
                important_words.insert(0, brand_lower)
        
        # Take first 5-6 words for focused search
        query = ' '.join(important_words[:6])
        
        return query if query else product.title[:50]
    
    async def _find_best_match(
        self,
        source: ProductData,
        candidates: List[ProductData]
    ) -> Optional[ProductData]:
        """Find best matching product using AI essence + similarity"""
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            # Skip accessories when searching for main product
            if self._is_accessory_mismatch(source.title, candidate.title):
                continue
            
            # Calculate similarity score
            score = await self._calculate_similarity(source, candidate)
            
            if score >= self.MIN_SIMILARITY_SCORE and score > best_score:
                best_match = candidate
                best_score = score
        
        if best_match:
            logger.debug(
                f"Best match: {best_match.title[:40]}... "
                f"(score: {best_score:.2f})"
            )
        
        return best_match
    
    def _is_accessory_mismatch(self, source_title: str, candidate_title: str) -> bool:
        """Check if candidate is accessory when source is main product"""
        source_lower = source_title.lower()
        candidate_lower = candidate_title.lower()
        
        source_is_accessory = any(kw in source_lower for kw in self.ACCESSORY_KEYWORDS)
        candidate_is_accessory = any(kw in candidate_lower for kw in self.ACCESSORY_KEYWORDS)
        
        # Source is main product, candidate is accessory = MISMATCH
        if not source_is_accessory and candidate_is_accessory:
            return True
        
        # Source is accessory, candidate is main product = MISMATCH
        if source_is_accessory and not candidate_is_accessory:
            return True
        
        return False
    
    async def _calculate_similarity(
        self,
        product_a: ProductData,
        product_b: ProductData
    ) -> float:
        """
        Calculate similarity score between two products
        
        SCORING:
        - Exact fingerprint/essence match: 1.0 (100%)
        - Brand match: +0.20
        - Title similarity (Jaccard): 0.0-0.50
        - Price within 30%: +0.15
        - Category match: +0.10
        """
        score = 0.0
        
        # =====================================================================
        # PRIORITY 1: AI Essence Match (THE KEY FIX)
        # =====================================================================
        
        # Check fingerprint match
        if product_a.fingerprint == product_b.fingerprint:
            return self.ESSENCE_MATCH_SCORE
        
        # Check AI essence match (case-insensitive)
        if product_a.ai_essence and product_b.ai_essence:
            essence_a = product_a.ai_essence.lower().strip()
            essence_b = product_b.ai_essence.lower().strip()
            
            # Exact essence match
            if essence_a == essence_b:
                return self.ESSENCE_MATCH_SCORE
            
            # High essence similarity (Jaccard > 0.8)
            essence_sim = self._jaccard_similarity(essence_a, essence_b)
            if essence_sim >= 0.8:
                return 0.95
        
        # =====================================================================
        # PRIORITY 2: Title Similarity
        # =====================================================================
        
        title_score = self._jaccard_similarity(
            product_a.title.lower(),
            product_b.title.lower()
        )
        score += title_score * 0.50  # Max 0.50 from title
        
        # =====================================================================
        # PRIORITY 3: Brand Match
        # =====================================================================
        
        if product_a.brand and product_b.brand:
            brand_a = product_a.brand.lower().strip()
            brand_b = product_b.brand.lower().strip()
            
            if brand_a == brand_b:
                score += self.BRAND_MATCH_BONUS
            elif brand_a in brand_b or brand_b in brand_a:
                score += self.BRAND_MATCH_BONUS * 0.5
        
        # =====================================================================
        # PRIORITY 4: Price Match (within 30% range)
        # =====================================================================
        
        try:
            price_a = float(product_a.current_price)
            price_b = float(product_b.current_price)
            
            if price_a > 0 and price_b > 0:
                price_ratio = min(price_a, price_b) / max(price_a, price_b)
                
                if price_ratio >= 0.70:  # Within 30%
                    score += self.PRICE_MATCH_BONUS * price_ratio
        except (ValueError, TypeError, ZeroDivisionError):
            pass
        
        # =====================================================================
        # PRIORITY 5: Category Match
        # =====================================================================
        
        if product_a.category and product_b.category:
            if product_a.category.lower() == product_b.category.lower():
                score += self.CATEGORY_MATCH_BONUS
        
        return min(score, 1.0)
    
    def _jaccard_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate Jaccard similarity between two texts"""
        # Tokenize
        words_a = set(re.findall(r'\b[a-z0-9]+\b', text_a.lower()))
        words_b = set(re.findall(r'\b[a-z0-9]+\b', text_b.lower()))
        
        # Remove stop words
        words_a = words_a - self.STOP_WORDS
        words_b = words_b - self.STOP_WORDS
        
        if not words_a or not words_b:
            return 0.0
        
        intersection = words_a & words_b
        union = words_a | words_b
        
        return len(intersection) / len(union) if union else 0.0
    
    def calculate_savings(
        self,
        alternatives: List[ProductData]
    ) -> Dict[str, Any]:
        """Calculate potential savings from alternatives"""
        if not alternatives:
            return {
                "has_savings": False,
                "best_price": 0,
                "max_savings": 0,
                "best_platform": None,
                "savings_percent": 0
            }
        
        if len(alternatives) == 1:
            return {
                "has_savings": False,
                "best_price": float(alternatives[0].current_price),
                "max_savings": 0,
                "best_platform": alternatives[0].platform_name,
                "savings_percent": 0
            }
        
        # Sort by price
        sorted_products = sorted(alternatives, key=lambda x: float(x.current_price))
        
        cheapest = sorted_products[0]
        most_expensive = sorted_products[-1]
        
        max_savings = float(most_expensive.current_price - cheapest.current_price)
        
        savings_percent = 0
        if float(most_expensive.current_price) > 0:
            savings_percent = (max_savings / float(most_expensive.current_price)) * 100
        
        return {
            "has_savings": max_savings > 0,
            "best_price": float(cheapest.current_price),
            "best_platform": cheapest.platform_name,
            "best_url": cheapest.product_url,
            "highest_price": float(most_expensive.current_price),
            "highest_price_platform": most_expensive.platform_name,
            "max_savings": round(max_savings, 2),
            "savings_percent": round(savings_percent, 1),
            "total_options": len(alternatives),
            "data_sources": list(set(p.data_source.value for p in alternatives))
        }
    
    async def enrich_with_ai(self, product: ProductData) -> ProductData:
        """
        Enrich product with AI if not already processed
        
        This ensures all products have AI essence for matching.
        """
        if product.ai_processed and product.ai_essence:
            return product
        
        ai_client = await self._get_ai_client()
        
        if not ai_client:
            return product
        
        try:
            enriched = await ai_client.process_product(product)
            
            # Update product with AI data
            product.ai_essence = enriched.get("essence")
            product.ai_tags = enriched.get("tags", [])
            product.ai_quality_score = enriched.get("quality_score", 0)
            product.category = enriched.get("category") or product.category
            product.subcategory = enriched.get("subcategory")
            
            if enriched.get("specifications"):
                product.specifications = {
                    **product.specifications,
                    **enriched["specifications"]
                }
            
            product.ai_processed = True
            
        except Exception as e:
            logger.error(f"AI enrichment failed: {e}")
        
        return product


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
cross_platform_matcher = CrossPlatformMatcher()
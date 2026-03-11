"""
Product Fingerprinting & Matching
AI-powered product deduplication across platforms

UPDATED: 
- Fixed field names to match models.py schema
- Delegates DB creation to product_service (no duplication)
- Keeps matching logic intact for seeding_matcher.py

Author: DealHunt
Version: 2.0 (Schema-Aligned)
"""

from typing import Optional, Tuple, List
import hashlib
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from dataclasses import dataclass
import logging

from app.models import Product
from app.services.scraper.base import ProductData

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MatchResult:
    """Result of product matching"""
    product: ProductData
    similarity_score: float
    match_reasons: List[str]


# =============================================================================
# PRODUCT MATCHER CLASS
# =============================================================================

class ProductMatcher:
    """
    Intelligent product matching and fingerprinting
    Prevents duplicate products in database
    
    Used by:
    - seeding_matcher.py (find_best_match)
    - cross_platform_matcher.py (similarity scoring)
    """
    
    # =========================================================================
    # FINGERPRINT GENERATION
    # =========================================================================
    
    @staticmethod
    def generate_fingerprint(title: str, brand: Optional[str] = None) -> str:
        """
        Generate basic fingerprint from product title
        
        Process:
        1. Lowercase
        2. Remove special characters
        3. Remove common filler words
        4. Sort words alphabetically
        5. Hash result
        
        Args:
            title: Product title
            brand: Optional brand name (adds to fingerprint)
            
        Returns:
            32-character hex fingerprint
        """
        # Lowercase and remove special chars
        normalized = title.lower()
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        
        # Remove filler words
        filler_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'including', 'until', 'against', 'among', 'throughout', 'despite',
            'towards', 'upon', 'concerning', 'new', 'latest', 'best', 'top',
            'original', 'genuine', 'authentic', 'official', 'pack', 'combo',
            'offer', 'deal', 'sale', 'discount', 'price', 'buy', 'get', 'free'
        }
        
        words = [w for w in normalized.split() if w not in filler_words]
        
        # Add brand if provided
        if brand:
            brand_normalized = brand.lower().strip()
            if brand_normalized and brand_normalized not in words:
                words.insert(0, brand_normalized)
        
        # Sort alphabetically for consistency
        words.sort()
        
        # Create fingerprint
        fingerprint_str = ' '.join(words)
        fingerprint = hashlib.md5(fingerprint_str.encode()).hexdigest()
        
        return fingerprint
    
    # =========================================================================
    # DATABASE SEARCH (FIXED FIELD NAMES)
    # =========================================================================
    
    @staticmethod
    async def find_by_fingerprint(
        fingerprint: str,
        db: AsyncSession
    ) -> Optional[Product]:
        """
        Find product by exact fingerprint match
        
        Args:
            fingerprint: Product fingerprint
            db: Database session
            
        Returns:
            Product or None
        """
        result = await db.execute(
            select(Product).where(Product.fingerprint == fingerprint)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def find_similar_product(
        essence: str,
        db: AsyncSession,
        similarity_threshold: float = 0.7
    ) -> Optional[Product]:
        """
        Find existing product by AI-generated essence (fuzzy match)
        
        ✅ FIXED: Uses correct field name (ai_metadata->>'essence')
        
        Args:
            essence: AI-generated product essence
            db: Database session
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            Matching Product or None
        """
        if not essence or len(essence) < 5:
            return None
        
        # Extract keywords for matching
        keywords = essence.lower().split()[:5]  # First 5 important words
        
        if not keywords:
            return None
        
        # Build OR query for keyword matching in ai_metadata->>'essence'
        # ✅ FIXED: Using correct JSONB field access
        conditions = []
        for keyword in keywords:
            if len(keyword) > 2:  # Skip short words
                conditions.append(
                    func.lower(Product.ai_metadata['essence'].astext).contains(keyword)
                )
        
        if not conditions:
            return None
        
        result = await db.execute(
            select(Product)
            .where(or_(*conditions))
            .limit(10)
        )
        candidates = result.scalars().all()
        
        # Manual similarity scoring
        best_match = None
        best_score = 0.0
        
        for candidate in candidates:
            # ✅ FIXED: Access essence from ai_metadata JSONB
            candidate_metadata = candidate.ai_metadata or {}
            candidate_essence = candidate_metadata.get('essence', '')
            
            if not candidate_essence:
                continue
            
            # Word overlap score
            candidate_words = set(candidate_essence.lower().split())
            essence_words = set(essence.lower().split())
            
            if not candidate_words or not essence_words:
                continue
            
            intersection = candidate_words & essence_words
            union = candidate_words | essence_words
            
            score = len(intersection) / len(union) if union else 0
            
            if score > best_score and score >= similarity_threshold:
                best_score = score
                best_match = candidate
        
        if best_match:
            logger.info(
                f"Found similar product: {best_match.id} "
                f"(similarity: {best_score:.2f})"
            )
        
        return best_match
    
    @staticmethod
    async def find_existing_product(
        title: str,
        db: AsyncSession,
        brand: Optional[str] = None,
        essence: Optional[str] = None
    ) -> Optional[Product]:
        """
        Find existing product by fingerprint OR essence similarity
        
        Args:
            title: Product title
            db: Database session
            brand: Optional brand name
            essence: Optional pre-computed essence
            
        Returns:
            Existing Product or None
        """
        # Step 1: Try exact fingerprint match
        fingerprint = ProductMatcher.generate_fingerprint(title, brand)
        
        existing = await ProductMatcher.find_by_fingerprint(fingerprint, db)
        if existing:
            logger.debug(f"Found by fingerprint: {existing.id}")
            return existing
        
        # Step 2: Try essence similarity match
        if essence:
            similar = await ProductMatcher.find_similar_product(essence, db)
            if similar:
                logger.debug(f"Found by essence similarity: {similar.id}")
                return similar
        
        return None
    
    # =========================================================================
    # BRAND EXTRACTION
    # =========================================================================
    
    @staticmethod
    def extract_brand_from_title(title: str) -> Optional[str]:
        """Extract brand name from product title"""
        title_lower = title.lower()
        
        # Common brands to look for
        brands = [
            # Electronics
            'apple', 'samsung', 'xiaomi', 'oneplus', 'oppo', 'vivo', 'realme',
            'motorola', 'nokia', 'lg', 'sony', 'panasonic', 'philips',
            'dell', 'hp', 'lenovo', 'asus', 'acer', 'microsoft', 'google',
            'iqoo', 'infinix', 'tecno', 'micromax', 'lava', 'karbonn',
            'boat', 'jbl', 'bose', 'skullcandy', 'sennheiser', 'marshall',
            
            # Fashion
            'nike', 'adidas', 'puma', 'reebok', 'woodland', 'bata',
            'tata', 'relaxo', 'liberty', 'paragon', 'action', 'sparx',
            'levis', 'wrangler', 'pepe', 'allen solly', 'van heusen',
            'peter england', 'louis philippe', 'arrow', 'us polo',
            
            # Beauty
            'lakme', 'maybelline', 'loreal', 'ponds', 'dove', 'nivea',
            'garnier', 'olay', 'neutrogena', 'himalaya', 'biotique',
            'mama earth', 'wow', 'plum', 'sugar', 'nykaa', 'faces',
            
            # Home
            'prestige', 'hawkins', 'bajaj', 'havells', 'crompton',
            'orient', 'usha', 'kent', 'aquaguard', 'eureka forbes',
        ]
        
        # Check if brand appears in title
        for brand in brands:
            if brand in title_lower:
                # Find actual brand (preserve case from title)
                brand_pattern = re.compile(r'\b' + re.escape(brand) + r'\b', re.IGNORECASE)
                match = brand_pattern.search(title)
                if match:
                    return match.group().title()
        
        # Fallback: Use first word if it looks like a brand (capitalized, > 2 chars)
        words = title.split()
        if words and len(words[0]) > 2 and words[0][0].isupper():
            first_word = words[0].strip(',.!?')
            # Avoid common non-brand words
            non_brands = {'new', 'buy', 'get', 'free', 'best', 'top', 'latest', 'original'}
            if first_word.lower() not in non_brands:
                return first_word
        
        return None
    
    # =========================================================================
    # PRODUCT DATA MATCHING (Used by seeding_matcher.py)
    # =========================================================================
    
    async def find_best_match(
        self, 
        source_product: ProductData, 
        candidates: List[ProductData]
    ) -> Optional[ProductData]:
        """
        Find the best matching product from candidates
        
        Used by seeding_matcher.py for cross-platform matching
        
        Args:
            source_product: The source product to match
            candidates: List of candidate products from other platforms
            
        Returns:
            Best matching ProductData or None
        """
        if not candidates:
            return None
        
        try:
            return await self._rule_based_match(source_product, candidates)
        except Exception as e:
            logger.error(f"Product matching error: {e}")
            return None
    
    async def _rule_based_match(
        self, 
        source_product: ProductData, 
        candidates: List[ProductData]
    ) -> Optional[ProductData]:
        """Rule-based product matching with scoring"""
        best_candidate = None
        best_score = 0.0
        
        for candidate in candidates:
            score = self._calculate_similarity_score(source_product, candidate)
            
            if score > best_score and score >= 0.65:  # Minimum threshold
                best_score = score
                best_candidate = candidate
        
        if best_candidate:
            logger.debug(
                f"Best match: {best_candidate.title[:40]}... "
                f"(score: {best_score:.2f})"
            )
        
        return best_candidate
    
    def _calculate_similarity_score(
        self, 
        product1: ProductData, 
        product2: ProductData
    ) -> float:
        """
        Calculate similarity score between two products
        
        Scoring weights:
        - Brand match: 30%
        - Title similarity: 40%
        - Price similarity: 20%
        - Category match: 10%
        """
        score = 0.0
        
        # Brand matching (30% weight)
        brand1 = getattr(product1, 'brand', None)
        brand2 = getattr(product2, 'brand', None)
        
        if brand1 and brand2:
            b1 = brand1.lower().strip()
            b2 = brand2.lower().strip()
            
            if b1 == b2:
                score += 0.30
            elif b1 in b2 or b2 in b1:
                score += 0.15
        
        # Title similarity (40% weight)
        title1 = getattr(product1, 'title', '') or ''
        title2 = getattr(product2, 'title', '') or ''
        
        title_similarity = self._text_similarity(title1, title2)
        score += title_similarity * 0.40
        
        # Price similarity (20% weight)
        price1 = getattr(product1, 'current_price', None)
        price2 = getattr(product2, 'current_price', None)
        
        if price1 and price2 and float(price1) > 0:
            price_diff = abs(float(price1) - float(price2))
            price_ratio = price_diff / float(price1)
            
            if price_ratio < 0.10:  # Within 10%
                score += 0.20
            elif price_ratio < 0.20:  # Within 20%
                score += 0.15
            elif price_ratio < 0.30:  # Within 30%
                score += 0.10
            elif price_ratio < 0.50:  # Within 50%
                score += 0.05
        
        # Category matching (10% weight)
        cat1 = getattr(product1, 'category', None)
        cat2 = getattr(product2, 'category', None)
        
        if cat1 and cat2:
            c1 = cat1.lower()
            c2 = cat2.lower()
            
            if c1 == c2:
                score += 0.10
            elif c1 in c2 or c2 in c1:
                score += 0.05
        
        return min(score, 1.0)
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text similarity using Jaccard index (word overlap)
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score 0-1
        """
        if not text1 or not text2:
            return 0.0
        
        # Normalize texts
        text1_normalized = re.sub(r'[^a-z0-9\s]', '', text1.lower())
        text2_normalized = re.sub(r'[^a-z0-9\s]', '', text2.lower())
        
        words1 = set(text1_normalized.split())
        words2 = set(text2_normalized.split())
        
        # Remove very short words
        words1 = {w for w in words1 if len(w) > 2}
        words2 = {w for w in words2 if len(w) > 2}
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    @staticmethod
    def normalize_title(title: str) -> str:
        """
        Normalize product title for comparison
        
        - Lowercase
        - Remove special characters
        - Remove extra whitespace
        """
        normalized = title.lower()
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    @staticmethod
    def extract_model_number(title: str) -> Optional[str]:
        """
        Extract model number from title if present
        
        Patterns: "Model X123", "X123-ABC", etc.
        """
        # Common model number patterns
        patterns = [
            r'\b([A-Z]{1,3}\d{2,4}[A-Z]?)\b',  # X123, AB1234, X123A
            r'\b(\d{2,4}[A-Z]{1,3})\b',         # 123X, 1234AB
            r'\b([A-Z]{2,4}-\d{2,4})\b',        # AB-1234
            r'\bmodel\s*[:\-]?\s*(\S+)\b',      # Model: X123
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
product_matcher = ProductMatcher()
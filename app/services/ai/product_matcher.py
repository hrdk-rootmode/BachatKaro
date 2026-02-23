"""
Product Fingerprinting & Matching
AI-powered product deduplication across platforms
"""

from typing import Optional, Tuple
import hashlib
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models import Product
from app.services.ai.groq_client import groq_client
import logging

logger = logging.getLogger(__name__)


class ProductMatcher:
    """
    Intelligent product matching and fingerprinting
    Prevents duplicate products in database
    """
    
    @staticmethod
    def generate_fingerprint(title: str) -> str:
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
        
        # Sort alphabetically for consistency
        words.sort()
        
        # Create fingerprint
        fingerprint_str = ' '.join(words)
        fingerprint = hashlib.md5(fingerprint_str.encode()).hexdigest()
        
        return fingerprint
    
    @staticmethod
    async def find_similar_product(
        essence: str,
        db: AsyncSession,
        similarity_threshold: float = 0.85
    ) -> Optional[Product]:
        """
        Find existing product by AI-generated essence (fuzzy match)
        
        Uses PostgreSQL trigram similarity
        
        Args:
            essence: AI-generated product essence
            db: Database session
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            Matching Product or None
        """
        # Note: Requires pg_trgm extension in PostgreSQL
        # For now, using simple string matching
        # In production, use: similarity(ai_generated_essence, essence) > threshold
        
        # Simple keyword-based matching for now
        keywords = essence.split()[:5]  # First 5 important words
        
        if not keywords:
            return None
        
        # Build OR query for keyword matching
        conditions = [
            Product.ai_generated_essence.ilike(f"%{keyword}%")
            for keyword in keywords
        ]
        
        result = await db.execute(
            select(Product)
            .where(or_(*conditions))
            .limit(10)
        )
        candidates = result.scalars().all()
        
        # Manual similarity check
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            if not candidate.ai_generated_essence:
                continue
            
            # Simple word overlap score
            candidate_words = set(candidate.ai_generated_essence.lower().split())
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
    async def find_or_create_product(
        title: str,
        db: AsyncSession,
        specs: Optional[dict] = None,
        force_create: bool = False
    ) -> Tuple[Product, bool]:
        """
        Find existing product or create new one with AI fingerprinting
        
        Process:
        1. Generate basic fingerprint
        2. Check database for exact fingerprint match
        3. If not found, generate AI essence
        4. Search for similar products by essence
        5. If still not found, create new product
        
        Args:
            title: Product title
            db: Database session
            specs: Optional product specifications
            force_create: Skip matching, always create new
            
        Returns:
            Tuple of (Product, is_new)
            is_new = True if product was just created
        """
        if force_create:
            # Skip all matching logic
            product = await ProductMatcher._create_new_product(title, db, specs)
            return product, True
        
        # Step 1: Generate fingerprint
        fingerprint = ProductMatcher.generate_fingerprint(title)
        
        # Step 2: Check for exact fingerprint match
        result = await db.execute(
            select(Product).where(Product.fingerprint == fingerprint)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.info(f"Found existing product by fingerprint: {existing.id}")
            return existing, False
        
        # Step 3: Generate AI essence for fuzzy matching
        essence = await groq_client.generate_product_essence(title, specs)
        
        # Step 4: Search for similar products
        similar = await ProductMatcher.find_similar_product(essence, db)
        
        if similar:
            logger.info(
                f"Matched to existing product {similar.id} via AI essence"
            )
            return similar, False
        
        # Step 5: Create new product
        product = await ProductMatcher._create_new_product(
            title, db, specs, fingerprint, essence
        )
        
        return product, True
    
    @staticmethod
    async def _create_new_product(
        title: str,
        db: AsyncSession,
        specs: Optional[dict] = None,
        fingerprint: Optional[str] = None,
        essence: Optional[str] = None
    ) -> Product:
        """
        Create new product record with AI-generated metadata
        
        Args:
            title: Product title
            db: Database session
            specs: Product specifications
            fingerprint: Pre-calculated fingerprint (optional)
            essence: Pre-calculated essence (optional)
            
        Returns:
            New Product object
        """
        # Generate fingerprint if not provided
        if not fingerprint:
            fingerprint = ProductMatcher.generate_fingerprint(title)
        
        # Generate essence if not provided
        if not essence:
            essence = await groq_client.generate_product_essence(title, specs)
        
        # Generate tags
        tags = await groq_client.generate_tags(title)
        
        # Extract specs if not provided
        if not specs:
            specs = {}
        
        # Create product
        product = Product(
            fingerprint=fingerprint,
            ai_generated_essence=essence,
            ai_extracted_specs=specs,
            ai_tags=tags,
            best_price=0,  # Will be updated when listing is added
            best_platform="amazon"  # Default, will be updated
        )
        
        db.add(product)
        await db.flush()  # Get product.id
        
        logger.info(
            f"Created new product: {product.id} | "
            f"Fingerprint: {fingerprint[:8]}... | "
            f"Essence: {essence[:50]}..."
        )
        
        return product


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
product_matcher = ProductMatcher()
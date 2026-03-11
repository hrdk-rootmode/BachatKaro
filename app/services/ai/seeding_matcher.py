"""
AI Product Matcher Wrapper for Seeding System
Provides compatibility layer for the seeding system
"""
from app.services.ai.product_matcher import ProductMatcher
from app.services.scraper.base import ProductData
from typing import List, Optional

class AIProductMatcher:
    """Wrapper for ProductMatcher to provide seeding system compatibility"""
    
    def __init__(self):
        self.matcher = ProductMatcher()
    
    async def find_best_match(
        self, 
        source_product: ProductData, 
        candidates: List[ProductData]
    ) -> Optional[ProductData]:
        """Find the best matching product from candidates"""
        return await self.matcher.find_best_match(source_product, candidates)

# Singleton instance
_ai_matcher = None

def get_ai_matcher() -> AIProductMatcher:
    """Get singleton AI matcher instance"""
    global _ai_matcher
    if _ai_matcher is None:
        _ai_matcher = AIProductMatcher()
    return _ai_matcher

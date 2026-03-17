"""
AI Enrichment Service
=====================

Centralized AI enrichment for product data.
Single source of truth - used by both API and Background Jobs.

Features:
- Groq AI integration for essence, tags, quality_score
- Graceful fallback when AI unavailable
- Specification merging
- Category/subcategory detection

Author: DealHunt
Version: 1.0 (Centralized)
"""

import logging
from typing import Dict, Any, Optional

from app.services.scraper.base import ProductData
from app.services.ai.groq_client import groq_client, GroqFeature

logger = logging.getLogger(__name__)


class AIEnrichmentService:
    """
    Centralized service for enriching scraped product data using AI.
    
    Used by:
    - app/api/v1/search.py (real-time user searches)
    - app/jobs/daily_scrape_trending.py (background jobs)
    - app/jobs/seed_products.py (seeding jobs)
    - scripts/*.py (CLI tools)
    """
    
    async def enrich_product(self, product_data: ProductData) -> ProductData:
        """
        Enrich product data using AI in-place.
        
        Adds:
        - ai_essence: Normalized fingerprint string
        - ai_tags: Searchable keywords list
        - ai_quality_score: 0-100 quality rating
        - category: Detected category
        - subcategory: Detected subcategory
        - specifications: Merged/enhanced specs
        
        Args:
            product_data: Raw ProductData from scraper
            
        Returns:
            Same ProductData object with AI fields populated
        """
        # Skip if already processed
        if product_data.ai_processed:
            logger.debug(f"Skipping already processed: {product_data.title[:40]}...")
            return product_data
        
        try:
            # Call the Groq AI client
            enriched = await groq_client.process_product(product_data)
            
            if enriched:
                # Update product_data with AI insights
                product_data.ai_essence = enriched.get("essence")
                product_data.ai_tags = enriched.get("tags", [])
                product_data.ai_quality_score = enriched.get("quality_score", 50)
                
                # Update category only if AI provides better data
                if enriched.get("category"):
                    product_data.category = enriched.get("category")
                if enriched.get("subcategory"):
                    product_data.subcategory = enriched.get("subcategory")
                
                # Merge specifications (existing + AI-extracted)
                if enriched.get("specifications"):
                    product_data.specifications = {
                        **(product_data.specifications or {}),
                        **enriched["specifications"]
                    }
                
                product_data.ai_processed = True
                
                logger.info(
                    f"🧠 AI Enriched: {product_data.title[:40]}... → "
                    f"essence={product_data.ai_essence[:30] if product_data.ai_essence else 'N/A'} | "
                    f"score={product_data.ai_quality_score}"
                )
            else:
                logger.warning(f"AI returned empty response for: {product_data.title[:40]}...")
                product_data.ai_processed = False
                
        except Exception as e:
            logger.error(f"⚠️ AI enrichment failed (continuing with raw data): {e}")
            product_data.ai_processed = False
        
        return product_data
    
    async def enrich_products_batch(
        self, 
        products: list[ProductData],
        skip_processed: bool = True
    ) -> list[ProductData]:
        """
        Enrich multiple products (for batch processing in jobs).
        
        Args:
            products: List of ProductData objects
            skip_processed: Skip already processed products
            
        Returns:
            List of enriched ProductData objects
        """
        enriched_products = []
        
        for product_data in products:
            if skip_processed and product_data.ai_processed:
                enriched_products.append(product_data)
                continue
            
            enriched = await self.enrich_product(product_data)
            enriched_products.append(enriched)
        
        logger.info(f"🧠 Batch enriched {len(enriched_products)} products")
        return enriched_products
    
    def get_fallback_essence(self, product_data: ProductData) -> str:
        """
        Generate fallback essence without AI (for when AI fails).
        
        Args:
            product_data: ProductData object
            
        Returns:
            Simple normalized string
        """
        import re
        
        title = product_data.title.lower()
        
        # Remove common noise patterns
        noise_patterns = [
            r'\(.*?\)',           # (anything in brackets)
            r'\[.*?\]',           # [anything in brackets]
            r'buy\s+',            # Buy
            r'online\s+',         # Online
            r'at\s+best\s+price', # at best price
            r'with\s+\d+%\s+off', # with X% off
            r'free\s+delivery',   # free delivery
        ]
        
        for pattern in noise_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        # Clean up
        title = re.sub(r'[^a-z0-9\s]', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Add brand if available
        if product_data.brand:
            brand = product_data.brand.lower()
            if brand not in title:
                title = f"{brand} {title}"
        
        # Limit to first 12 words
        words = title.split()[:12]
        return ' '.join(words)

    async def call_llm_raw(self, prompt: str) -> str:
        """
        Raw LLM call for custom prompts (used by matching script)
        
        Args:
            prompt: The prompt to send to LLM
            
        Returns:
            Raw text response from LLM
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            response = await groq_client._call_groq(messages, GroqFeature.HEALING)
            return response.get('content', '') or ''
        except Exception as e:
            logger.error(f"Raw LLM call failed: {e}")
            return ''


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
enrichment_service = AIEnrichmentService()
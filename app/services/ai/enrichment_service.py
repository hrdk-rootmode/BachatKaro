"""
AI Enrichment Service - Enhanced with Confidence Tracking
==========================================================

Centralized AI enrichment with confidence and provenance tracking.
Version 2.0 - Production Grade

Author: DealHunt
"""

import logging
from typing import Any, Optional

from app.services.scraper.base import ProductData
from app.services.ai.groq_client import groq_client, GroqFeature

logger = logging.getLogger(__name__)


SOURCE_CONFIDENCE_MAP = {
    "api": 0.95,
    "next_data": 0.90,
    "json_ld": 0.88,
    "dom": 0.70,
    "ai": 0.60,
    "title_heuristic": 0.35,
    "fallback": 0.20,
}


class AIEnrichmentService:
    """Centralized service for AI enrichment with confidence/provenance."""

    async def enrich_product(self, product_data: ProductData, force: bool = False) -> ProductData:
        """Enrich product data using AI with confidence tracking."""
        if product_data.ai_processed and not force:
            logger.debug(f"Skipping already processed: {product_data.title[:40]}...")
            return product_data

        try:
            enriched = await groq_client.process_product(product_data)

            if not enriched:
                logger.warning(f"AI returned empty for: {product_data.title[:40]}...")
                product_data.ai_processed = False
                return product_data

            product_data.ai_essence = enriched.get("essence")
            product_data.ai_tags = enriched.get("tags", [])
            product_data.ai_quality_score = enriched.get("quality_score", 50)
            product_data.ai_processed = True

            if enriched.get("category"):
                product_data.category = enriched.get("category")
            if enriched.get("subcategory"):
                product_data.subcategory = enriched.get("subcategory")

            ai_brand = enriched.get("brand")
            ai_brand_confidence = enriched.get("brand_confidence", 0.0)
            ai_brand_source = enriched.get("brand_source", "ai")
            current_brand_confidence = getattr(product_data, "brand_confidence", 0.0) or 0.0

            if ai_brand and ai_brand_confidence > current_brand_confidence:
                product_data.brand = ai_brand
                product_data.brand_confidence = ai_brand_confidence
                product_data.brand_source = ai_brand_source
                logger.debug(f"Updated brand: {ai_brand} (conf={ai_brand_confidence:.2f})")

            ai_color = enriched.get("color")
            ai_color_confidence = enriched.get("color_confidence", 0.0)
            ai_color_source = enriched.get("color_source", "ai")
            current_color_confidence = getattr(product_data, "color_confidence", 0.0) or 0.0

            if ai_color and ai_color_confidence > current_color_confidence:
                product_data.color = ai_color
                product_data.color_confidence = ai_color_confidence
                product_data.color_source = ai_color_source
                logger.debug(f"Updated color: {ai_color} (conf={ai_color_confidence:.2f})")

            ai_specs = enriched.get("specifications", {})
            ai_specs_confidence = enriched.get("specs_confidence", 0.0)
            ai_specs_source = enriched.get("specs_source", "ai")

            if ai_specs:
                current_specs = product_data.specifications or {}
                merged_specs = {**current_specs, **ai_specs}
                product_data.specifications = merged_specs
                product_data.specs_confidence = max(
                    getattr(product_data, "specs_confidence", 0.0) or 0.0,
                    ai_specs_confidence,
                )
                product_data.specs_source = ai_specs_source

            logger.info(
                f"🧠 AI Enriched: {product_data.title[:40]}... -> "
                f"essence={product_data.ai_essence[:30] if product_data.ai_essence else 'N/A'} | "
                f"score={product_data.ai_quality_score} | "
                f"brand_conf={float(getattr(product_data, 'brand_confidence', 0.0) or 0.0):.2f} | "
                f"color_conf={float(getattr(product_data, 'color_confidence', 0.0) or 0.0):.2f}"
            )

        except Exception as e:
            logger.error(f"⚠️ AI enrichment failed: {e}")
            product_data.ai_processed = False

        return product_data

    def set_attribute_confidence(
        self,
        product_data: ProductData,
        attribute: str,
        value: Any,
        source: str,
        override_confidence: Optional[float] = None,
    ) -> None:
        """Set attribute with confidence and source metadata."""
        if value is None:
            return

        confidence = override_confidence or SOURCE_CONFIDENCE_MAP.get(source, 0.5)

        setattr(product_data, attribute, value)
        setattr(product_data, f"{attribute}_confidence", confidence)
        setattr(product_data, f"{attribute}_source", source)

        logger.debug(f"Set {attribute}={value} (source={source}, conf={confidence:.2f})")

    async def enrich_products_batch(
        self,
        products: list[ProductData],
        skip_processed: bool = True,
    ) -> list[ProductData]:
        """Enrich multiple products in batch."""
        enriched_products = []

        for product_data in products:
            if skip_processed and product_data.ai_processed:
                enriched_products.append(product_data)
                continue

            enriched = await self.enrich_product(product_data)
            enriched_products.append(enriched)

        logger.info(f"🧠 Batch enriched {len(enriched_products)} products")
        return enriched_products

    async def call_llm_raw(self, prompt: str) -> str:
        """Raw LLM call for custom prompts."""
        try:
            messages = [{"role": "user", "content": prompt}]
            response = await groq_client._call_groq(messages, GroqFeature.HEALING)
            return response or ""
        except Exception as e:
            logger.error(f"Raw LLM call failed: {e}")
            return ""


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
enrichment_service = AIEnrichmentService()
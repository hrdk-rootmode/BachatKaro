"""
Generic AI-Powered Scraper
Scrapes ANY website using AI to extract product information

Features:
- No selectors needed (AI figures it out)
- Works on unsupported platforms
- Fallback when specific scrapers fail
- JSON-LD/Schema.org parsing

Limitations:
- Slower than specific scrapers
- Lower accuracy
- Uses AI quota
"""

import logging
import json
import re
import hashlib
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime

from app.services.scraper.base import (
    BasePlatformHandler,
    PlatformConfig,
    ProductData,
    SearchResult,
    HandlerType,
    StockStatus
)
from app.services.scraper.browser import get_browser_manager
from app.services.scraper.rate_limiter import RateLimiter, ThreatLevel
from app.services.ai.groq_client import groq_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class GenericAIScraper(BasePlatformHandler):
    """
    AI-powered generic scraper for unsupported platforms
    
    Uses Groq AI to:
    1. Parse page HTML
    2. Find JSON-LD structured data
    3. Extract product info intelligently
    
    Usage:
        scraper = GenericAIScraper("snapdeal")
        product = await scraper.get_product("https://snapdeal.com/product/...")
    """
    
    # JSON-LD product schema patterns
    JSON_LD_PATTERNS = [
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        r'<script[^>]*type="application/json"[^>]*data-product[^>]*>(.*?)</script>'
    ]
    
    def __init__(
        self,
        platform_name: str,
        rate_limiter: Optional[RateLimiter] = None
    ):
        """
        Initialize generic scraper
        
        Args:
            platform_name: Name of platform (for logging)
            rate_limiter: Optional rate limiter (will create if not provided)
        """
        # Create minimal config
        config = PlatformConfig(
            id=0,
            name=platform_name,
            base_url="",
            handler_type=HandlerType.SCRAPER
        )
        
        super().__init__(config)
        self.rate_limiter = rate_limiter
        
        logger.info(f"GenericAIScraper initialized for {platform_name}")
    
    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER
    
    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """
        Search is NOT supported for generic scraper
        Only single product scraping works
        """
        logger.warning(f"Search not supported for generic scraper ({self.platform_name})")
        return SearchResult(
            query=query,
            platform_name=self.platform_name,
            products=[],
            success=False,
            error_message="Search not supported for this platform. Only direct product URLs work."
        )
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """
        Extract product info using AI
        
        Strategy:
        1. Try JSON-LD first (fastest, most accurate)
        2. Fall back to AI extraction (slower, less accurate)
        """
        logger.info(f"GenericAIScraper: Scraping {product_url}")
        
        try:
            # Get browser manager
            browser_manager = await get_browser_manager()
            
            # Rate limit
            if self.rate_limiter:
                await self.rate_limiter.acquire(self.platform_name)
            
            # Fetch page
            async with browser_manager.get_page(
                block_resources=False,  # Need images for generic scraping
                stealth=True
            ) as page:
                # Navigate to page
                await page.goto(product_url, wait_until="domcontentloaded")
                
                # Wait for content
                await page.wait_for_timeout(2000)
                
                # Get HTML
                html_content = await page.content()
                
                # Try JSON-LD extraction first
                json_ld_data = self._extract_json_ld(html_content)
                
                if json_ld_data:
                    product = self._parse_json_ld(json_ld_data, product_url)
                    if product:
                        logger.info(f"GenericAIScraper: JSON-LD extraction successful")
                        self.record_success()
                        if self.rate_limiter:
                            await self.rate_limiter.record_success(self.platform_name)
                        return product
                
                # Fallback to AI extraction
                product = await self._ai_extract_product(html_content, product_url)
                
                if product:
                    logger.info(f"GenericAIScraper: AI extraction successful")
                    self.record_success()
                    if self.rate_limiter:
                        await self.rate_limiter.record_success(self.platform_name)
                    return product
                
                logger.warning(f"GenericAIScraper: Failed to extract product from {product_url}")
                self.record_failure("Extraction failed")
                return None
        
        except Exception as e:
            logger.error(f"GenericAIScraper error: {e}")
            self.record_failure(str(e))
            if self.rate_limiter:
                await self.rate_limiter.record_failure(
                    self.platform_name,
                    threat_level=ThreatLevel.WARNING
                )
            return None
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        """Not supported for generic scraper"""
        return None
    
    def _extract_json_ld(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract JSON-LD structured data from HTML"""
        for pattern in self.JSON_LD_PATTERNS:
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            
            for match in matches:
                try:
                    data = json.loads(match.strip())
                    
                    # Handle array of items
                    if isinstance(data, list):
                        for item in data:
                            if self._is_product_schema(item):
                                return item
                    elif self._is_product_schema(data):
                        return data
                
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _is_product_schema(self, data: Dict[str, Any]) -> bool:
        """Check if JSON-LD data is a Product schema"""
        if not isinstance(data, dict):
            return False
        
        schema_type = data.get("@type", "")
        
        if isinstance(schema_type, list):
            return any(t.lower() == "product" for t in schema_type)
        
        return schema_type.lower() == "product"
    
    def _parse_json_ld(
        self,
        data: Dict[str, Any],
        product_url: str
    ) -> Optional[ProductData]:
        """Parse JSON-LD Product schema into ProductData"""
        try:
            # Extract basic info
            title = data.get("name", "")
            
            if not title:
                return None
            
            # Extract price
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            
            price = offers.get("price") or offers.get("lowPrice")
            original_price = offers.get("highPrice")
            
            if not price:
                # Try nested format
                price = data.get("price")
            
            if not price:
                return None
            
            # Clean price
            current_price = self._clean_price(str(price))
            orig_price = self._clean_price(str(original_price)) if original_price else None
            
            if not current_price:
                return None
            
            # Extract other fields
            image = data.get("image", "")
            if isinstance(image, list):
                image = image[0] if image else ""
            elif isinstance(image, dict):
                image = image.get("url", "")
            
            brand = data.get("brand", {})
            if isinstance(brand, dict):
                brand = brand.get("name", "")
            
            rating_data = data.get("aggregateRating", {})
            rating = rating_data.get("ratingValue")
            review_count = rating_data.get("reviewCount") or rating_data.get("ratingCount")
            
            # Stock status
            availability = offers.get("availability", "")
            in_stock = "instock" in availability.lower() if availability else True
            
            # Generate external ID
            external_id = hashlib.md5(product_url.encode()).hexdigest()[:16]
            
            return ProductData(
                external_id=external_id,
                title=title,
                current_price=current_price,
                original_price=orig_price,
                product_url=product_url,
                platform_name=self.platform_name,
                image_url=image if isinstance(image, str) else None,
                brand=brand if isinstance(brand, str) else None,
                rating=float(rating) if rating else None,
                review_count=int(review_count) if review_count else None,
                in_stock=in_stock,
                stock_status=StockStatus.IN_STOCK if in_stock else StockStatus.OUT_OF_STOCK,
                data_source=HandlerType.SCRAPER,
                raw_data={"json_ld": data}
            )
        
        except Exception as e:
            logger.error(f"JSON-LD parsing error: {e}")
            return None
    
    async def _ai_extract_product(
        self,
        html: str,
        product_url: str
    ) -> Optional[ProductData]:
        """Use AI to extract product information from HTML"""
        # Truncate HTML to save tokens
        html_truncated = html[:15000]
        
        # Remove scripts and styles
        html_truncated = re.sub(r'<script[^>]*>.*?</script>', '', html_truncated, flags=re.DOTALL)
        html_truncated = re.sub(r'<style[^>]*>.*?</style>', '', html_truncated, flags=re.DOTALL)
        html_truncated = re.sub(r'<!--.*?-->', '', html_truncated, flags=re.DOTALL)
        
        prompt = f"""Extract product information from this e-commerce HTML.

URL: {product_url}

HTML:
{html_truncated}

Extract and return ONLY valid JSON (no explanation):
{{
    "title": "Product title/name",
    "price": 29999,
    "original_price": 39999,
    "brand": "Brand name or null",
    "rating": 4.5,
    "review_count": 1234,
    "image_url": "https://...",
    "in_stock": true,
    "currency": "INR"
}}

Rules:
- price must be NUMBER (not string)
- Remove currency symbols from price
- If field not found, use null
- Return ONLY JSON, nothing else"""
        
        try:
            response = await groq_client.generate(
                prompt=prompt,
                purpose="generic_scrape",
                max_tokens=500,
                temperature=0.1
            )
            
            if not response:
                return None
            
            # Parse JSON response
            response = response.strip()
            
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                logger.warning("AI did not return valid JSON")
                return None
            
            data = json.loads(json_match.group())
            
            # Validate required fields
            if not data.get("title") or not data.get("price"):
                logger.warning("AI response missing required fields")
                return None
            
            # Generate external ID
            external_id = hashlib.md5(product_url.encode()).hexdigest()[:16]
            
            return ProductData(
                external_id=external_id,
                title=data["title"],
                current_price=Decimal(str(data["price"])),
                original_price=Decimal(str(data["original_price"])) if data.get("original_price") else None,
                product_url=product_url,
                platform_name=self.platform_name,
                image_url=data.get("image_url"),
                brand=data.get("brand"),
                rating=float(data["rating"]) if data.get("rating") else None,
                review_count=int(data["review_count"]) if data.get("review_count") else None,
                in_stock=data.get("in_stock", True),
                data_source=HandlerType.SCRAPER,
                raw_data={"ai_extracted": data}
            )
        
        except json.JSONDecodeError as e:
            logger.error(f"AI response JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"AI extraction error: {e}")
            return None
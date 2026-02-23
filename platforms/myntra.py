"""
Myntra.com Scraper
Fashion-focused scraper for India's leading fashion platform

Features:
- Fashion product search
- Size availability
- Color variants
- Brand extraction
- Style recommendations
- Discount detection

Author: DealHunt
Complexity: MEDIUM
"""

import logging
import re
import hashlib
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlencode, urlparse

from app.services.scraper.base import (
    BasePlatformHandler,
    PlatformConfig,
    ProductData,
    SearchResult,
    HandlerType,
    StockStatus
)
from app.services.scraper.browser import get_browser_manager, BrowserManager
from app.services.scraper.rate_limiter import RateLimiter, ThreatLevel, RateLimitExceeded
from app.services.scraper.self_healing import SelfHealingEngine
from app.core.config import settings

logger = logging.getLogger(__name__)


class MyntraScraper(BasePlatformHandler):
    """
    Myntra.com scraper for fashion products
    
    Myntra specializes in:
    - Clothing (men, women, kids)
    - Footwear
    - Accessories
    - Beauty products
    
    Usage:
        scraper = MyntraScraper(config)
        results = await scraper.search("men casual shirt")
    """
    
    BASE_URL = "https://www.myntra.com"
    
    DEFAULT_SELECTORS = {
        # Search page
        "search_results": "li.product-base",
        "search_title": "h3.product-brand, h4.product-product",
        "search_price": "span.product-discountedPrice, div.product-price span",
        "search_original_price": "span.product-strike",
        "search_discount": "span.product-discountPercentage",
        "search_rating": "div.product-ratingsContainer span",
        "search_image": "img.img-responsive",
        "search_link": "a[data-reactid]",
        
        # Product page
        "product_title": "h1.pdp-title, h1.pdp-name",
        "product_brand": "h1.pdp-title, span.pdp-brand",
        "product_price": "span.pdp-price strong, span.pdp-discountedPrice",
        "original_price": "span.pdp-mrp s",
        "discount_percent": "span.pdp-discount",
        "product_image": "div.image-grid-image img",
        "product_rating": "div.index-overallRating",
        "review_count": "div.index-ratingsCount",
        "size_options": "div.size-buttons-size-button",
        "color_options": "div.colors-colorsContainer img",
        "product_details": "div.pdp-productDescriptorsContainer"
    }
    
    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self.healing_engine = SelfHealingEngine(
            platform_name="myntra",
            selectors=config.selectors or self.DEFAULT_SELECTORS
        )
        self.browser_manager: Optional[BrowserManager] = None
        
        self.affiliate_id = config.affiliate_tag or settings.AFFILIATE_MYNTRA_ID
        
        logger.info("MyntraScraper initialized")
    
    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER
    
    async def _get_browser(self) -> BrowserManager:
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager
    
    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """Search fashion products on Myntra"""
        start_time = datetime.utcnow()
        filters = filters or {}
        
        try:
            await self.rate_limiter.acquire("myntra")
            
            # Myntra uses path-based search
            search_query = query.replace(" ", "-").lower()
            search_url = f"{self.BASE_URL}/{search_query}"
            
            if page > 1:
                search_url = f"{search_url}?p={page}"
            
            logger.info(f"Myntra search: {query} (page {page})")
            
            browser = await self._get_browser()
            products = []
            
            async with browser.get_page(block_resources=True, stealth=True) as page_obj:
                await page_obj.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await page_obj.wait_for_timeout(2000)
                await browser.scroll_page(page_obj, scroll_count=3)
                
                # Find product cards
                cards = await page_obj.query_selector_all("li.product-base")
                
                for card in cards[:20]:
                    try:
                        product = await self._extract_search_result(card, page_obj)
                        if product:
                            products.append(product)
                    except Exception as e:
                        logger.debug(f"Extract error: {e}")
                        continue
            
            await self.rate_limiter.record_success("myntra")
            self.record_success()
            
            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return SearchResult(
                query=query,
                platform_name="myntra",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 15,
                search_time_ms=search_time,
                success=True
            )
        
        except RateLimitExceeded as e:
            return SearchResult(
                query=query,
                platform_name="myntra",
                success=False,
                error_message=f"Rate limited: {e.retry_after}s"
            )
        
        except Exception as e:
            logger.error(f"Myntra search error: {e}")
            await self.rate_limiter.record_failure("myntra", ThreatLevel.WARNING)
            return SearchResult(
                query=query,
                platform_name="myntra",
                success=False,
                error_message=str(e)
            )
    
    async def _extract_search_result(self, card, page_obj) -> Optional[ProductData]:
        """Extract product from search card"""
        try:
            # Get link
            link_el = await card.query_selector("a")
            href = await link_el.get_attribute("href") if link_el else None
            
            if not href:
                return None
            
            product_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            product_id = self.extract_product_id(product_url)
            
            if not product_id:
                product_id = hashlib.md5(product_url.encode()).hexdigest()[:16]
            
            # Brand
            brand_el = await card.query_selector("h3.product-brand")
            brand = await brand_el.text_content() if brand_el else None
            
            # Title/Product name
            title_el = await card.query_selector("h4.product-product")
            title = await title_el.text_content() if title_el else None
            
            # Combine brand + title
            if brand and title:
                full_title = f"{brand.strip()} {title.strip()}"
            else:
                full_title = (brand or title or "").strip()
            
            if not full_title:
                return None
            
            # Price
            price_el = await card.query_selector("span.product-discountedPrice, div.product-price span")
            price_text = await price_el.text_content() if price_el else None
            current_price = self._clean_price(price_text)
            
            if not current_price:
                return None
            
            # Original price
            original_el = await card.query_selector("span.product-strike")
            original_text = await original_el.text_content() if original_el else None
            original_price = self._clean_price(original_text) if original_text else None
            
            # Discount
            discount_el = await card.query_selector("span.product-discountPercentage")
            discount_text = await discount_el.text_content() if discount_el else None
            discount = None
            if discount_text:
                match = re.search(r'(\d+)%', discount_text)
                if match:
                    discount = float(match.group(1))
            
            # Rating
            rating_el = await card.query_selector("div.product-ratingsContainer span")
            rating_text = await rating_el.text_content() if rating_el else None
            rating = self._clean_rating(rating_text)
            
            # Image
            image_el = await card.query_selector("img")
            image_url = await image_el.get_attribute("src") if image_el else None
            
            # If lazy loaded
            if not image_url or "blank" in image_url:
                image_url = await image_el.get_attribute("data-src") if image_el else None
            
            return ProductData(
                external_id=product_id,
                title=full_title,
                current_price=current_price,
                original_price=original_price,
                discount_percent=discount,
                product_url=product_url,
                platform_name="myntra",
                image_url=image_url,
                rating=rating,
                brand=brand.strip() if brand else None,
                category="Fashion",
                in_stock=True,
                data_source=HandlerType.SCRAPER
            )
        
        except Exception as e:
            logger.debug(f"Extract error: {e}")
            return None
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get detailed product information"""
        try:
            await self.rate_limiter.acquire("myntra")
            
            product_id = self.extract_product_id(product_url)
            
            browser = await self._get_browser()
            
            async with browser.get_page(block_resources=False, stealth=True) as page:
                await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                
                # Brand
                brand_el = await page.query_selector("h1.pdp-title, span.pdp-brand")
                brand = await brand_el.text_content() if brand_el else None
                
                # Title
                title_el = await page.query_selector("h1.pdp-name, span.pdp-name")
                title = await title_el.text_content() if title_el else None
                
                # Combine
                if brand and title:
                    full_title = f"{brand.strip()} {title.strip()}"
                else:
                    full_title = (brand or title or "").strip()
                
                if not full_title:
                    return None
                
                # Price
                price_el = await page.query_selector("span.pdp-price strong, span.pdp-discountedPrice")
                price_text = await price_el.text_content() if price_el else None
                current_price = self._clean_price(price_text)
                
                if not current_price:
                    return None
                
                # Original price
                original_el = await page.query_selector("span.pdp-mrp s")
                original_text = await original_el.text_content() if original_el else None
                original_price = self._clean_price(original_text) if original_text else None
                
                # Discount
                discount = self._calculate_discount(current_price, original_price)
                
                # Image
                image_el = await page.query_selector("div.image-grid-image img, img.image-grid-image")
                image_url = await image_el.get_attribute("src") if image_el else None
                
                # Rating
                rating_el = await page.query_selector("div.index-overallRating")
                rating_text = await rating_el.text_content() if rating_el else None
                rating = self._clean_rating(rating_text)
                
                # Review count
                review_el = await page.query_selector("div.index-ratingsCount")
                review_text = await review_el.text_content() if review_el else None
                review_count = self._clean_review_count(review_text)
                
                # Sizes
                size_elements = await page.query_selector_all("div.size-buttons-size-button")
                sizes = []
                for size_el in size_elements:
                    size_text = await size_el.text_content()
                    if size_text:
                        sizes.append(size_text.strip())
                
                await self.rate_limiter.record_success("myntra")
                self.record_success()
                
                return ProductData(
                    external_id=product_id or hashlib.md5(product_url.encode()).hexdigest()[:16],
                    title=full_title,
                    current_price=current_price,
                    original_price=original_price,
                    discount_percent=discount,
                    product_url=self.build_affiliate_url(product_url),
                    platform_name="myntra",
                    image_url=image_url,
                    rating=rating,
                    review_count=review_count,
                    brand=brand.strip() if brand else None,
                    category="Fashion",
                    in_stock=True,
                    specifications={"sizes": sizes} if sizes else {},
                    data_source=HandlerType.SCRAPER
                )
        
        except Exception as e:
            logger.error(f"Myntra product error: {e}")
            await self.rate_limiter.record_failure("myntra", ThreatLevel.WARNING)
            return None
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        url = f"{self.BASE_URL}/product/{external_id}"
        return await self.get_product(url)
    
    def extract_product_id(self, url: str) -> Optional[str]:
        """Extract product ID from Myntra URL"""
        try:
            # Pattern: /product-name/12345678/buy
            match = re.search(r'/(\d{6,10})(?:/|$)', url)
            if match:
                return match.group(1)
            
            # Alternative
            match = re.search(r'/buy/(\d+)', url)
            if match:
                return match.group(1)
        except Exception:
            pass
        
        return None
    
    def build_affiliate_url(self, product_url: str) -> str:
        if not self.affiliate_id:
            return product_url
        
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}utm_source={self.affiliate_id}"
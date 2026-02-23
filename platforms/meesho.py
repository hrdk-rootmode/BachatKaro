"""
Meesho.com Scraper
Simple scraper for India's social commerce platform

Features:
- Product search
- Low price focus
- COD availability
- Supplier ratings
- Simple selectors (stable website)

Author: DealHunt
Complexity: LOW (Meesho has simpler structure)
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


class MeeshoScraper(BasePlatformHandler):
    """
    Meesho.com scraper
    
    Meesho is simpler to scrape because:
    - Less anti-bot protection
    - More stable HTML structure
    - API-like responses in some cases
    
    Usage:
        scraper = MeeshoScraper(config)
        results = await scraper.search("cotton shirt")
    """
    
    BASE_URL = "https://www.meesho.com"
    SEARCH_URL = "https://www.meesho.com/search"
    
    DEFAULT_SELECTORS = {
        # Search page
        "search_results": "div[data-testid='product-card'], .ProductCard__ProductCardContainer",
        "search_title": "p.ProductCard__ProductTitle, .sc-dkzDqf",
        "search_price": "h5.ProductCard__ProductPrice, .sc-eDvSVe",
        "search_original_price": "span.ProductCard__OldPrice",
        "search_discount": "span.ProductCard__Discount",
        "search_rating": "span.ProductCard__Rating",
        "search_image": "img.ProductCard__ProductImage, img[data-testid='product-image']",
        
        # Product page
        "product_title": "h1.ProductTitle, .sc-eDvSVe.bYcJKV",
        "product_price": "h4.ProductPrice, .sc-eDvSVe.dEXVIf",
        "original_price": "span.OldPrice",
        "product_image": "img.ProductImage",
        "product_rating": "span.Rating",
        "review_count": "span.ReviewCount",
        "product_description": "div.ProductDescription",
        "delivery_info": "div.DeliveryInfo",
        "supplier_name": "div.SupplierName",
        "supplier_rating": "div.SupplierRating"
    }
    
    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self.healing_engine = SelfHealingEngine(
            platform_name="meesho",
            selectors=config.selectors or self.DEFAULT_SELECTORS
        )
        self.browser_manager: Optional[BrowserManager] = None
        
        self.affiliate_id = config.affiliate_tag or settings.MEESHO_AFFILIATE_ID
        
        logger.info("MeeshoScraper initialized")
    
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
        """Search products on Meesho"""
        start_time = datetime.utcnow()
        filters = filters or {}
        
        try:
            await self.rate_limiter.acquire("meesho")
            
            # Build URL - Meesho uses path-based search
            search_query = query.replace(" ", "-").lower()
            search_url = f"{self.BASE_URL}/{search_query}"
            
            if page > 1:
                search_url = f"{search_url}?page={page}"
            
            logger.info(f"Meesho search: {query} (page {page})")
            
            browser = await self._get_browser()
            products = []
            
            async with browser.get_page(block_resources=True, stealth=True) as page_obj:
                await page_obj.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await page_obj.wait_for_timeout(2000)
                await browser.scroll_page(page_obj, scroll_count=3)
                
                # Meesho loads more on scroll
                await page_obj.wait_for_timeout(1000)
                
                # Find product cards
                cards = await page_obj.query_selector_all(
                    "div[data-testid='product-card'], .ProductCard__ProductCardContainer, a[href*='/product/']"
                )
                
                for card in cards[:20]:
                    try:
                        product = await self._extract_search_result(card, page_obj)
                        if product:
                            products.append(product)
                    except Exception as e:
                        logger.debug(f"Extract error: {e}")
                        continue
            
            await self.rate_limiter.record_success("meesho")
            self.record_success()
            
            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return SearchResult(
                query=query,
                platform_name="meesho",
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
                platform_name="meesho",
                success=False,
                error_message=f"Rate limited: {e.retry_after}s"
            )
        
        except Exception as e:
            logger.error(f"Meesho search error: {e}")
            await self.rate_limiter.record_failure("meesho", ThreatLevel.WARNING)
            return SearchResult(
                query=query,
                platform_name="meesho",
                success=False,
                error_message=str(e)
            )
    
    async def _extract_search_result(self, card, page_obj) -> Optional[ProductData]:
        """Extract product from search card"""
        try:
            # Get link
            link = await card.get_attribute("href")
            if not link:
                link_el = await card.query_selector("a[href*='/product/']")
                if link_el:
                    link = await link_el.get_attribute("href")
            
            if not link:
                return None
            
            product_url = link if link.startswith("http") else f"{self.BASE_URL}{link}"
            product_id = self.extract_product_id(product_url)
            
            if not product_id:
                product_id = hashlib.md5(product_url.encode()).hexdigest()[:16]
            
            # Title
            title_el = await card.query_selector("p, h5, span")
            title = await title_el.text_content() if title_el else None
            
            if not title or len(title) < 5:
                return None
            
            # Price - look for ₹ symbol
            price_text = None
            price_elements = await card.query_selector_all("h5, span, p")
            for el in price_elements:
                text = await el.text_content()
                if text and "₹" in text:
                    price_text = text
                    break
            
            current_price = self._clean_price(price_text) if price_text else None
            
            if not current_price:
                return None
            
            # Image
            image_el = await card.query_selector("img")
            image_url = await image_el.get_attribute("src") if image_el else None
            
            # Rating
            rating_el = await card.query_selector("span[class*='Rating'], span.sc-")
            rating_text = await rating_el.text_content() if rating_el else None
            rating = self._clean_rating(rating_text)
            
            return ProductData(
                external_id=product_id,
                title=title.strip()[:200],
                current_price=current_price,
                product_url=product_url,
                platform_name="meesho",
                image_url=image_url,
                rating=rating,
                in_stock=True,
                data_source=HandlerType.SCRAPER
            )
        
        except Exception as e:
            logger.debug(f"Extract error: {e}")
            return None
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get product details"""
        try:
            await self.rate_limiter.acquire("meesho")
            
            product_id = self.extract_product_id(product_url)
            
            browser = await self._get_browser()
            
            async with browser.get_page(block_resources=False, stealth=True) as page:
                await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                
                # Title
                title_el = await page.query_selector("h1, span.ProductTitle")
                title = await title_el.text_content() if title_el else None
                
                if not title:
                    return None
                
                # Price
                price_el = await page.query_selector("h4, span.ProductPrice")
                price_text = await price_el.text_content() if price_el else None
                
                # Fallback - find any element with ₹
                if not price_text:
                    elements = await page.query_selector_all("h4, h5, span")
                    for el in elements:
                        text = await el.text_content()
                        if text and "₹" in text:
                            price_text = text
                            break
                
                current_price = self._clean_price(price_text)
                
                if not current_price:
                    return None
                
                # Image
                image_el = await page.query_selector("img[src*='images.meesho.com']")
                image_url = await image_el.get_attribute("src") if image_el else None
                
                # Rating
                rating_el = await page.query_selector("span[class*='Rating']")
                rating_text = await rating_el.text_content() if rating_el else None
                rating = self._clean_rating(rating_text)
                
                await self.rate_limiter.record_success("meesho")
                self.record_success()
                
                return ProductData(
                    external_id=product_id or hashlib.md5(product_url.encode()).hexdigest()[:16],
                    title=title.strip(),
                    current_price=current_price,
                    product_url=self.build_affiliate_url(product_url),
                    platform_name="meesho",
                    image_url=image_url,
                    rating=rating,
                    in_stock=True,
                    data_source=HandlerType.SCRAPER
                )
        
        except Exception as e:
            logger.error(f"Meesho product error: {e}")
            await self.rate_limiter.record_failure("meesho", ThreatLevel.WARNING)
            return None
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        url = f"{self.BASE_URL}/product/{external_id}"
        return await self.get_product(url)
    
    def extract_product_id(self, url: str) -> Optional[str]:
        """Extract product ID from Meesho URL"""
        try:
            # Pattern: /product/title-string/pid
            match = re.search(r'/product/[^/]+/([a-zA-Z0-9]+)', url)
            if match:
                return match.group(1)
            
            # Alternative pattern
            match = re.search(r'/([0-9]+)/?$', url)
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
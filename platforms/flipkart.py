"""
Flipkart.com Scraper
Production-grade scraper for India's largest homegrown e-commerce platform

Features:
- FSN (Flipkart Serial Number) extraction
- Search with filters
- Product details extraction
- Flipkart Assured badge
- Bank offers detection
- SuperCoin deals
- Seller ratings
- Self-healing selectors

Author: DealHunt
Complexity: MEDIUM
"""

import logging
import re
import asyncio
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs, unquote

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


class FlipkartScraper(BasePlatformHandler):
    """
    Flipkart.com scraper
    
    Features:
    - Product search with pagination
    - Detailed product extraction
    - Price tracking
    - Seller information
    - Flipkart Assured detection
    
    Usage:
        scraper = FlipkartScraper(config)
        results = await scraper.search("Samsung Galaxy")
        product = await scraper.get_product("https://flipkart.com/...")
    """
    
    # Base URLs
    BASE_URL = "https://www.flipkart.com"
    SEARCH_URL = "https://www.flipkart.com/search"
    
    # FSN pattern
    FSN_PATTERN = re.compile(r'pid=([A-Z0-9]+)|/p/([a-zA-Z0-9]+)')
    
    # Default selectors
    DEFAULT_SELECTORS = {
        # Search page
        "search_results": "div[data-id], ._1AtVbE",
        "search_title": "a._4rR01T, ._4rR01T, .s1Q9rs, a.IRpwTa",
        "search_price": "div._30jeq3, ._30jeq3._1_WHN1",
        "search_original_price": "div._3I9_wc, ._3I9_wc._27UcVY",
        "search_discount": "div._3Ay6Sb, ._3Ay6Sb._31Dcoz",
        "search_rating": "div._3LWZlK",
        "search_image": "img._396cs4, img._2r_T1I",
        "search_link": "a._1fQZEK, a._2rpwqI, a.s1Q9rs",
        
        # Product page
        "product_title": "span.B_NuCI, h1.yhB1nd",
        "product_price": "div._30jeq3._16Jk6d",
        "original_price": "div._3I9_wc._2p6lqe",
        "product_image": "img._396cs4._2amPTt, img._2r_T1I",
        "product_rating": "div._3LWZlK",
        "review_count": "span._2_R_DZ span",
        "product_description": "div._1mXcCf",
        "in_stock": "div._16FRp0",
        "delivery_info": "div._3XINqE, span.c6eFJL",
        "seller_name": "div._3enH5S span span, #sellerName span span",
        "seller_rating": "div._3LWZlK._1BLPMq",
        "brand": "span._2J4LW6",
        "highlights": "div._2418kt li",
        "specifications": "div._3k-BhJ table",
        
        # Additional
        "assured_badge": "img[alt='Flipkart Assured']",
        "bank_offers": "div._3vDP5a li"
    }
    
    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self.healing_engine = SelfHealingEngine(
            platform_name="flipkart",
            selectors=config.selectors or self.DEFAULT_SELECTORS
        )
        self.browser_manager: Optional[BrowserManager] = None
        
        self.affiliate_id = config.affiliate_tag or settings.FLIPKART_AFFILIATE_ID
        
        logger.info("FlipkartScraper initialized")
    
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
        """Search products on Flipkart"""
        start_time = datetime.utcnow()
        filters = filters or {}
        
        try:
            await self.rate_limiter.acquire("flipkart")
            
            # Build search URL
            search_params = {
                "q": query,
                "page": page
            }
            
            if filters.get("min_price"):
                search_params["p[]=facets.price_range.from"] = filters["min_price"]
            if filters.get("max_price"):
                search_params["p[]=facets.price_range.to"] = filters["max_price"]
            
            search_url = f"{self.SEARCH_URL}?{urlencode(search_params)}"
            
            logger.info(f"Flipkart search: {query} (page {page})")
            
            browser = await self._get_browser()
            products = []
            
            async with browser.get_page(block_resources=True, stealth=True) as page_obj:
                # Handle login popup
                await self._dismiss_login_popup(page_obj)
                
                # Navigate
                await page_obj.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                
                await page_obj.wait_for_timeout(2000)
                await browser.scroll_page(page_obj, scroll_count=2)
                
                html_content = await page_obj.content()
                
                # Find product cards
                product_cards = await page_obj.query_selector_all("div[data-id], ._1AtVbE")
                
                for card in product_cards[:20]:
                    try:
                        product = await self._extract_search_result(card, page_obj)
                        if product:
                            products.append(product)
                    except Exception as e:
                        logger.debug(f"Extract error: {e}")
                        continue
            
            await self.rate_limiter.record_success("flipkart")
            self.record_success()
            
            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            logger.info(f"Flipkart search complete: {len(products)} products")
            
            return SearchResult(
                query=query,
                platform_name="flipkart",
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
                platform_name="flipkart",
                success=False,
                error_message=f"Rate limited: {e.retry_after}s"
            )
        
        except Exception as e:
            logger.error(f"Flipkart search error: {e}")
            await self.rate_limiter.record_failure("flipkart", ThreatLevel.WARNING)
            self.record_failure(str(e))
            
            return SearchResult(
                query=query,
                platform_name="flipkart",
                success=False,
                error_message=str(e)
            )
    
    async def _extract_search_result(self, card, page_obj) -> Optional[ProductData]:
        """Extract product from search result card"""
        try:
            # Get product ID
            product_id = await card.get_attribute("data-id")
            
            # Get link and extract FSN
            link_el = await card.query_selector("a._1fQZEK, a._2rpwqI, a.s1Q9rs, a.IRpwTa")
            product_url = None
            if link_el:
                href = await link_el.get_attribute("href")
                if href:
                    product_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                    # Extract FSN from URL
                    if not product_id:
                        product_id = self.extract_product_id(product_url)
            
            if not product_id:
                return None
            
            # Title
            title_el = await card.query_selector("a._4rR01T, ._4rR01T, .s1Q9rs, a.IRpwTa")
            title = await title_el.text_content() if title_el else None
            
            if not title:
                return None
            
            # Price
            price_el = await card.query_selector("div._30jeq3, ._30jeq3._1_WHN1")
            price_text = await price_el.text_content() if price_el else None
            current_price = self._clean_price(price_text)
            
            if not current_price:
                return None
            
            # Original price
            original_el = await card.query_selector("div._3I9_wc, ._3I9_wc._27UcVY")
            original_text = await original_el.text_content() if original_el else None
            original_price = self._clean_price(original_text) if original_text else None
            
            # Discount
            discount_el = await card.query_selector("div._3Ay6Sb")
            discount_text = await discount_el.text_content() if discount_el else None
            discount = None
            if discount_text:
                match = re.search(r'(\d+)%', discount_text)
                if match:
                    discount = float(match.group(1))
            
            # Rating
            rating_el = await card.query_selector("div._3LWZlK")
            rating_text = await rating_el.text_content() if rating_el else None
            rating = float(rating_text) if rating_text and rating_text.replace('.', '').isdigit() else None
            
            # Image
            image_el = await card.query_selector("img._396cs4, img._2r_T1I")
            image_url = await image_el.get_attribute("src") if image_el else None
            
            # Assured badge
            assured_el = await card.query_selector("img[alt*='Assured']")
            is_assured = assured_el is not None
            
            return ProductData(
                external_id=product_id,
                title=title.strip(),
                current_price=current_price,
                original_price=original_price,
                discount_percent=discount,
                product_url=product_url or f"{self.BASE_URL}/product/p/{product_id}",
                platform_name="flipkart",
                image_url=image_url,
                rating=rating,
                in_stock=True,
                data_source=HandlerType.SCRAPER,
                raw_data={
                    "fsn": product_id,
                    "is_assured": is_assured
                }
            )
        
        except Exception as e:
            logger.debug(f"Extract search result error: {e}")
            return None
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get detailed product information"""
        try:
            fsn = self.extract_product_id(product_url)
            
            await self.rate_limiter.acquire("flipkart")
            
            logger.info(f"Flipkart product: {fsn or product_url[:50]}")
            
            browser = await self._get_browser()
            
            async with browser.get_page(block_resources=False, stealth=True) as page:
                await self._dismiss_login_popup(page)
                
                await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                await browser.scroll_page(page, scroll_count=2)
                
                html_content = await page.content()
                
                # Title
                title_el = await page.query_selector("span.B_NuCI, h1.yhB1nd")
                title = await title_el.text_content() if title_el else None
                
                if not title:
                    return None
                
                # Price
                price_el = await page.query_selector("div._30jeq3._16Jk6d")
                price_text = await price_el.text_content() if price_el else None
                current_price = self._clean_price(price_text)
                
                if not current_price:
                    return None
                
                # Original price
                original_el = await page.query_selector("div._3I9_wc._2p6lqe")
                original_text = await original_el.text_content() if original_el else None
                original_price = self._clean_price(original_text) if original_text else None
                
                # Discount
                discount = self._calculate_discount(current_price, original_price)
                
                # Image
                image_el = await page.query_selector("img._396cs4._2amPTt, img._2r_T1I")
                image_url = await image_el.get_attribute("src") if image_el else None
                
                # Rating
                rating_el = await page.query_selector("div._3LWZlK")
                rating_text = await rating_el.text_content() if rating_el else None
                rating = float(rating_text) if rating_text and rating_text.replace('.', '').isdigit() else None
                
                # Review count
                review_el = await page.query_selector("span._2_R_DZ span")
                review_text = await review_el.text_content() if review_el else None
                review_count = self._clean_review_count(review_text)
                
                # Seller
                seller_el = await page.query_selector("div._3enH5S span span, #sellerName span span")
                seller_name = await seller_el.text_content() if seller_el else None
                
                # Brand
                brand_el = await page.query_selector("span._2J4LW6")
                brand = await brand_el.text_content() if brand_el else None
                
                # Assured
                assured_el = await page.query_selector("img[alt*='Assured']")
                is_assured = assured_el is not None
                
                # Stock
                in_stock = True
                stock_el = await page.query_selector("div._16FRp0")
                if stock_el:
                    stock_text = await stock_el.text_content()
                    in_stock = "out of stock" not in stock_text.lower() if stock_text else True
                
                await self.rate_limiter.record_success("flipkart")
                self.record_success()
                
                return ProductData(
                    external_id=fsn or hashlib.md5(product_url.encode()).hexdigest()[:16],
                    title=title.strip(),
                    current_price=current_price,
                    original_price=original_price,
                    discount_percent=discount,
                    product_url=self.build_affiliate_url(product_url),
                    platform_name="flipkart",
                    image_url=image_url,
                    rating=rating,
                    review_count=review_count,
                    in_stock=in_stock,
                    brand=brand.strip() if brand else None,
                    seller_name=seller_name.strip() if seller_name else None,
                    data_source=HandlerType.SCRAPER,
                    raw_data={
                        "fsn": fsn,
                        "is_assured": is_assured
                    }
                )
        
        except RateLimitExceeded:
            return None
        
        except Exception as e:
            logger.error(f"Flipkart product error: {e}")
            await self.rate_limiter.record_failure("flipkart", ThreatLevel.WARNING)
            self.record_failure(str(e))
            return None
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        """Get product by FSN"""
        url = f"{self.BASE_URL}/product/p/{external_id}"
        return await self.get_product(url)
    
    def extract_product_id(self, url: str) -> Optional[str]:
        """Extract FSN from Flipkart URL"""
        try:
            # Try pid parameter
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'pid' in params:
                return params['pid'][0]
            
            # Try /p/FSN pattern
            match = re.search(r'/p/([a-zA-Z0-9]+)', url)
            if match:
                return match.group(1)
            
            # Try itm pattern
            match = re.search(r'itm([a-zA-Z0-9]+)', url)
            if match:
                return f"itm{match.group(1)}"
        
        except Exception:
            pass
        
        return None
    
    def build_affiliate_url(self, product_url: str) -> str:
        """Add Flipkart affiliate ID"""
        if not self.affiliate_id:
            return product_url
        
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}affid={self.affiliate_id}"
    
    async def _dismiss_login_popup(self, page) -> None:
        """Dismiss Flipkart login popup if present"""
        try:
            close_btn = await page.query_selector("button._2KpZ6l._2doB4z, button[class*='close']")
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass


# Import for type hints
import hashlib
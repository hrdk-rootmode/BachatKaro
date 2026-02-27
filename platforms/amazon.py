"""
Amazon.in Scraper
Production-grade scraper with anti-detection and self-healing

Features:
- ASIN extraction from URLs
- Search with pagination
- Product details extraction
- Prime badge detection
- Lightning deals
- Seller information
- Color/size variants
- Self-healing selectors
- Cloudflare bypass

Author: DealHunt
Complexity: HIGH (Amazon has strongest anti-bot)
"""

import logging
import re
import asyncio
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs

from app.services.scraper.base import (
    BasePlatformHandler,
    PlatformConfig,
    ProductData,
    SearchResult,
    HandlerType,
    StockStatus,
    ProductCondition
)
from app.services.scraper.browser import get_browser_manager, BrowserManager
from app.services.scraper.rate_limiter import RateLimiter, ThreatLevel, RateLimitExceeded
from app.services.scraper.self_healing import SelfHealingEngine, SelectorResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class AmazonScraper(BasePlatformHandler):
    """
    Amazon.in scraper with advanced anti-detection
    ...existing docstring...
    """
    
    # =========================================================================
    # PLATFORM METADATA (NEW - For auto-discovery)
    # =========================================================================
    PLATFORM_METADATA = {
        "name": "amazon",
        "display_name": "Amazon India",
        "base_url": "https://www.amazon.in",
        "domains": ["amazon.in", "amazon.com", "amzn.to", "amzn.in"],
        "categories": ["electronics", "fashion", "home", "beauty", "general"],
        "product_id_patterns": [
            r"/dp/([A-Z0-9]{10})",
            r"/gp/product/([A-Z0-9]{10})",
            r"/gp/aw/d/([A-Z0-9]{10})",
        ],
        "affiliate_param": "tag",
        "affiliate_value_setting": "AMAZON_AFFILIATE_TAG",
        "rate_limit_per_minute": 30,
        "scrape_delay_seconds": 2,
        "reliability": "high",
        "support_level": "full"
    }
    
    # ... rest of existing code unchanged ...
    # Base URLs
    BASE_URL = "https://www.amazon.in"
    SEARCH_URL = "https://www.amazon.in/s"
    
    # ASIN pattern (Amazon Standard Identification Number)
    ASIN_PATTERN = re.compile(r'[/dp/|/gp/product/|/gp/aw/d/]([A-Z0-9]{10})')
    
    # Default CSS selectors (will be healed if broken)
    DEFAULT_SELECTORS = {
        # Search page selectors
        "search_results": "[data-component-type='s-search-result']",
        "search_title": "h2 a span",
        "search_price": ".a-price .a-offscreen",
        "search_rating": ".a-icon-star-small .a-icon-alt",
        "search_image": ".s-image",
        "search_link": "h2 a.a-link-normal",
        
        # Product page selectors
        "product_title": "#productTitle",
        "product_price": ".a-price .a-offscreen, #priceblock_ourprice, #priceblock_dealprice, .a-price-whole",
        "original_price": ".a-text-price .a-offscreen, #priceblock_listprice",
        "product_image": "#landingImage, #imgBlkFront",
        "product_rating": "#acrPopover .a-icon-alt, .a-icon-star .a-icon-alt",
        "review_count": "#acrCustomerReviewText",
        "product_description": "#productDescription p, #feature-bullets li",
        "in_stock": "#availability span",
        "delivery_info": "#deliveryMessageMirId, .delivery-message",
        "seller_name": "#sellerProfileTriggerId, #merchant-info a",
        "brand": "#bylineInfo, .po-brand .po-break-word",
        "discount_percent": ".savingsPercentage, .priceBlockSavingsString",
        
        # Additional selectors
        "prime_badge": ".a-icon-prime",
        "lightning_deal": "#dealBadge",
        "variant_options": "#twister-plus-inline-twister, .twisterSwatchPrice"
    }
    
    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        
        # Initialize components
        self.rate_limiter = rate_limiter or RateLimiter()
        self.healing_engine = SelfHealingEngine(
            platform_name="amazon",
            selectors=config.selectors or self.DEFAULT_SELECTORS
        )
        self.browser_manager: Optional[BrowserManager] = None
        
        # Affiliate tag
        self.affiliate_tag = config.affiliate_tag or settings.AMAZON_AFFILIATE_TAG
        
        logger.info("AmazonScraper initialized")
    
    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER
    
    async def _get_browser(self) -> BrowserManager:
        """Get or create browser manager"""
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager
    
    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """
        Search products on Amazon.in
        
        Args:
            query: Search query
            page: Page number (1-indexed)
            filters: Optional filters (min_price, max_price, prime_only)
        
        Returns:
            SearchResult with list of products
        """
        start_time = datetime.utcnow()
        filters = filters or {}
        
        try:
            # Rate limit
            await self.rate_limiter.acquire("amazon")
            
            # Build search URL
            search_params = {
                "k": query,
                "page": page,
                "ref": f"sr_pg_{page}"
            }
            
            # Add price filters
            if filters.get("min_price"):
                search_params["low-price"] = filters["min_price"]
            if filters.get("max_price"):
                search_params["high-price"] = filters["max_price"]
            
            search_url = f"{self.SEARCH_URL}?{urlencode(search_params)}"
            
            logger.info(f"Amazon search: {query} (page {page})")
            
            # Get browser
            browser = await self._get_browser()
            
            products = []
            
            async with browser.get_page(block_resources=True, stealth=True) as page_obj:
                # Navigate to search page
                response = await page_obj.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                
                # Check for captcha or blocks
                if await self._check_for_captcha(page_obj):
                    logger.warning("Amazon captcha detected!")
                    await self.rate_limiter.record_failure("amazon", ThreatLevel.BLOCKED)
                    return SearchResult(
                        query=query,
                        platform_name="amazon",
                        success=False,
                        error_message="Captcha detected. Please try again later."
                    )
                
                # Wait for results to load
                await page_obj.wait_for_timeout(2000)
                
                # Human-like scroll
                await browser.scroll_page(page_obj, scroll_count=2)
                
                # Get HTML for self-healing
                html_content = await page_obj.content()
                
                # Get search result containers
                selector_result = await self.healing_engine.get_working_selector(
                    "search_results",
                    html_content,
                    test_func=lambda sel: asyncio.create_task(page_obj.query_selector(sel))
                )
                
                if not selector_result.success:
                    logger.error("Failed to find search results selector")
                    return SearchResult(
                        query=query,
                        platform_name="amazon",
                        success=False,
                        error_message="Could not parse search results"
                    )
                
                result_elements = await page_obj.query_selector_all(selector_result.selector)
                
                # Extract products (limit to 20 per page)
                for i, element in enumerate(result_elements[:20]):
                    try:
                        product = await self._extract_search_result(element, page_obj, html_content)
                        if product:
                            products.append(product)
                    except Exception as e:
                        logger.debug(f"Failed to extract search result {i}: {e}")
                        continue
            
            # Record success
            await self.rate_limiter.record_success("amazon")
            self.record_success()
            
            # Calculate search time
            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            logger.info(f"Amazon search complete: {len(products)} products found")
            
            return SearchResult(
                query=query,
                platform_name="amazon",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 15,  # Assume more if we got 15+
                search_time_ms=search_time,
                success=True
            )
        
        except RateLimitExceeded as e:
            logger.warning(f"Amazon rate limit: {e}")
            return SearchResult(
                query=query,
                platform_name="amazon",
                success=False,
                error_message=f"Rate limited. Retry after {e.retry_after}s"
            )
        
        except Exception as e:
            logger.error(f"Amazon search error: {e}")
            await self.rate_limiter.record_failure("amazon", ThreatLevel.WARNING)
            self.record_failure(str(e))
            
            return SearchResult(
                query=query,
                platform_name="amazon",
                success=False,
                error_message=str(e)
            )
    
    async def _extract_search_result(
        self,
        element,
        page_obj,
        html_content: str
    ) -> Optional[ProductData]:
        """Extract product data from search result element"""
        try:
            # Get ASIN from data attribute
            asin = await element.get_attribute("data-asin")
            if not asin or len(asin) != 10:
                return None
            
            # Extract title
            title_el = await element.query_selector("h2 a span, h2 span")
            title = await title_el.text_content() if title_el else None
            
            if not title:
                return None
            
            # Extract price
            price_el = await element.query_selector(".a-price .a-offscreen")
            price_text = await price_el.text_content() if price_el else None
            
            if not price_text:
                return None
            
            current_price = self._clean_price(price_text)
            if not current_price:
                return None
            
            # Extract original price
            original_el = await element.query_selector(".a-text-price .a-offscreen")
            original_text = await original_el.text_content() if original_el else None
            original_price = self._clean_price(original_text) if original_text else None
            
            # Calculate discount
            discount = self._calculate_discount(current_price, original_price)
            
            # Extract rating
            rating_el = await element.query_selector(".a-icon-star-small .a-icon-alt")
            rating_text = await rating_el.text_content() if rating_el else None
            rating = self._clean_rating(rating_text)
            
            # Extract review count
            review_el = await element.query_selector(".a-size-small .a-link-normal .a-size-base")
            review_text = await review_el.text_content() if review_el else None
            review_count = self._clean_review_count(review_text)
            
            # Extract image
            image_el = await element.query_selector(".s-image")
            image_url = await image_el.get_attribute("src") if image_el else None
            
            # Check Prime
            prime_el = await element.query_selector(".a-icon-prime")
            is_prime = prime_el is not None
            
            # Build product URL
            product_url = f"{self.BASE_URL}/dp/{asin}"
            
            return ProductData(
                external_id=asin,
                title=title.strip(),
                current_price=current_price,
                original_price=original_price,
                discount_percent=discount,
                product_url=product_url,
                platform_name="amazon",
                image_url=image_url,
                rating=rating,
                review_count=review_count,
                in_stock=True,  # Assumed if in search results
                stock_status=StockStatus.IN_STOCK,
                data_source=HandlerType.SCRAPER,
                raw_data={
                    "asin": asin,
                    "is_prime": is_prime
                }
            )
        
        except Exception as e:
            logger.debug(f"Extract search result error: {e}")
            return None
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """
        Get detailed product information from URL
        
        Args:
            product_url: Amazon product URL
        
        Returns:
            ProductData with full details
        """
        try:
            # Extract ASIN from URL
            asin = self.extract_product_id(product_url)
            if not asin:
                logger.error(f"Could not extract ASIN from URL: {product_url}")
                return None
            
            # Rate limit
            await self.rate_limiter.acquire("amazon")
            
            # Build canonical URL
            canonical_url = f"{self.BASE_URL}/dp/{asin}"
            
            logger.info(f"Amazon product: {asin}")
            
            # Get browser
            browser = await self._get_browser()
            
            async with browser.get_page(block_resources=False, stealth=True) as page:
                # Navigate to product page
                await page.goto(
                    canonical_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                
                # Check for captcha
                if await self._check_for_captcha(page):
                    logger.warning("Amazon captcha on product page!")
                    await self.rate_limiter.record_failure("amazon", ThreatLevel.BLOCKED)
                    return None
                
                # Wait for price to load
                await page.wait_for_timeout(2000)
                
                # Human-like scroll
                await browser.scroll_page(page, scroll_count=2)
                
                # Get HTML
                html_content = await page.content()
                
                # Extract product data
                product = await self._extract_product_details(page, html_content, asin)
                
                if product:
                    await self.rate_limiter.record_success("amazon")
                    self.record_success()
                else:
                    await self.rate_limiter.record_failure("amazon", ThreatLevel.WARNING)
                
                return product
        
        except RateLimitExceeded as e:
            logger.warning(f"Amazon rate limit: {e}")
            return None
        
        except Exception as e:
            logger.error(f"Amazon product error: {e}")
            await self.rate_limiter.record_failure("amazon", ThreatLevel.WARNING)
            self.record_failure(str(e))
            return None
    
    async def _extract_product_details(
        self,
        page,
        html_content: str,
        asin: str
    ) -> Optional[ProductData]:
        """Extract detailed product information from product page"""
        try:
            # Title
            title_result = await self.healing_engine.get_working_selector(
                "product_title",
                html_content,
                test_func=lambda sel: asyncio.create_task(page.query_selector(sel))
            )
            
            title = None
            if title_result.success:
                title_el = await page.query_selector(title_result.selector)
                if title_el:
                    title = await title_el.text_content()
                    title = title.strip() if title else None
            
            if not title:
                logger.warning("Could not extract title")
                return None
            
            # Price (try multiple selectors)
            price_selectors = [
                ".a-price .a-offscreen",
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                ".a-price-whole",
                "#corePrice_feature_div .a-offscreen"
            ]
            
            current_price = None
            for sel in price_selectors:
                price_el = await page.query_selector(sel)
                if price_el:
                    price_text = await price_el.text_content()
                    current_price = self._clean_price(price_text)
                    if current_price:
                        break
            
            if not current_price:
                logger.warning("Could not extract price")
                return None
            
            # Original price
            original_price = None
            original_el = await page.query_selector(".a-text-price .a-offscreen, #priceblock_listprice")
            if original_el:
                original_text = await original_el.text_content()
                original_price = self._clean_price(original_text)
            
            # Discount
            discount = self._calculate_discount(current_price, original_price)
            
            # Image
            image_url = None
            image_el = await page.query_selector("#landingImage, #imgBlkFront")
            if image_el:
                image_url = await image_el.get_attribute("src")
            
            # Rating
            rating = None
            rating_el = await page.query_selector("#acrPopover .a-icon-alt, .a-icon-star .a-icon-alt")
            if rating_el:
                rating_text = await rating_el.text_content()
                rating = self._clean_rating(rating_text)
            
            # Review count
            review_count = None
            review_el = await page.query_selector("#acrCustomerReviewText")
            if review_el:
                review_text = await review_el.text_content()
                review_count = self._clean_review_count(review_text)
            
            # Stock status
            in_stock = True
            stock_el = await page.query_selector("#availability span")
            if stock_el:
                stock_text = await stock_el.text_content()
                stock_text = stock_text.lower() if stock_text else ""
                in_stock = "in stock" in stock_text or "available" in stock_text
            
            # Brand
            brand = None
            brand_el = await page.query_selector("#bylineInfo, .po-brand .po-break-word")
            if brand_el:
                brand_text = await brand_el.text_content()
                brand = brand_text.strip() if brand_text else None
                # Clean "Visit the X Store" format
                if brand and "Visit the" in brand:
                    brand = brand.replace("Visit the", "").replace("Store", "").strip()
                elif brand and "Brand:" in brand:
                    brand = brand.replace("Brand:", "").strip()
            
            # Seller
            seller_name = None
            seller_el = await page.query_selector("#sellerProfileTriggerId, #merchant-info a")
            if seller_el:
                seller_name = await seller_el.text_content()
                seller_name = seller_name.strip() if seller_name else None
            
            # Prime check
            prime_el = await page.query_selector(".a-icon-prime")
            is_prime = prime_el is not None
            
            # Delivery info
            delivery_info = None
            delivery_el = await page.query_selector("#deliveryMessageMirId, .delivery-message")
            if delivery_el:
                delivery_info = await delivery_el.text_content()
            
            # Build product URL with affiliate tag
            product_url = self.build_affiliate_url(f"{self.BASE_URL}/dp/{asin}")
            
            return ProductData(
                external_id=asin,
                title=title,
                current_price=current_price,
                original_price=original_price,
                discount_percent=discount,
                product_url=product_url,
                platform_name="amazon",
                image_url=image_url,
                rating=rating,
                review_count=review_count,
                in_stock=in_stock,
                stock_status=StockStatus.IN_STOCK if in_stock else StockStatus.OUT_OF_STOCK,
                brand=brand,
                seller_name=seller_name,
                delivery_info=delivery_info,
                data_source=HandlerType.SCRAPER,
                raw_data={
                    "asin": asin,
                    "is_prime": is_prime
                }
            )
        
        except Exception as e:
            logger.error(f"Extract product details error: {e}")
            return None
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        """Get product by ASIN"""
        url = f"{self.BASE_URL}/dp/{external_id}"
        return await self.get_product(url)
    
    def extract_product_id(self, url: str) -> Optional[str]:
        """Extract ASIN from Amazon URL"""
        # Try pattern matching
        match = self.ASIN_PATTERN.search(url)
        if match:
            return match.group(1)
        
        # Try URL parsing
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.split('/')
            
            # Look for /dp/ASIN or /gp/product/ASIN
            for i, part in enumerate(path_parts):
                if part in ['dp', 'product', 'd'] and i + 1 < len(path_parts):
                    potential_asin = path_parts[i + 1]
                    if len(potential_asin) == 10 and potential_asin.isalnum():
                        return potential_asin.upper()
            
            # Check query params
            query_params = parse_qs(parsed.query)
            if 'asin' in query_params:
                return query_params['asin'][0].upper()
        
        except Exception:
            pass
        
        return None
    
    def build_affiliate_url(self, product_url: str) -> str:
        """Add Amazon affiliate tag to URL"""
        if not self.affiliate_tag:
            return product_url
        
        # Check if tag already exists
        if f"tag={self.affiliate_tag}" in product_url:
            return product_url
        
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}tag={self.affiliate_tag}"
    
    async def _check_for_captcha(self, page) -> bool:
        """Check if Amazon is showing captcha"""
        captcha_indicators = [
            "form[action*='captcha']",
            "#captchacharacters",
            "img[src*='captcha']",
            "input[name='amzn-captcha-verify']"
        ]
        
        for selector in captcha_indicators:
            element = await page.query_selector(selector)
            if element:
                return True
        
        # Check page title
        title = await page.title()
        if title and ("robot" in title.lower() or "captcha" in title.lower()):
            return True
        
        return False
    
    async def close(self) -> None:
        """Cleanup resources"""
        # Browser manager is shared, don't close it here
        pass
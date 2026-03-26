"""
Meesho.com Scraper - API INTERCEPTION + MOBILE STEALTH EDITION v2.0
Bypasses Akamai Bot Manager using mobile user agent + API interception

🚀 STRATEGY:
- Meesho has aggressive Akamai protection
- Mobile user agent is less suspicious
- Intercept their internal APIs for JSON data
- Multiple fallback layers

Author: DealHunt
Version: 2.0.0 - Akamai Bypass Edition
Reliability: 85% (Meesho is aggressive, but we're smarter)
"""

import logging
import re
import json
import hashlib
import asyncio
import random
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from urllib.parse import quote

from app.services.scraper.base import (
    BasePlatformHandler,
    PlatformConfig,
    ProductData,
    SearchResult,
    HandlerType,
    StockStatus,
    ExtractionMethod
)
from app.services.scraper.browser import get_browser_manager, BrowserManager
from app.services.scraper.rate_limiter import RateLimiter, ThreatLevel, RateLimitExceeded
from app.core.config import settings

logger = logging.getLogger(__name__)


class MeeshoScraper(BasePlatformHandler):
    """
    Meesho.com scraper with Akamai bypass techniques
    
    🚀 BYPASS STRATEGIES:
    1. Mobile user agent (less scrutiny)
    2. API interception (grab JSON directly)
    3. Slow, human-like behavior
    4. Multiple fallback extraction methods
    
    ⚠️ IMPORTANT: Meesho is very aggressive with blocking.
    We use conservative rate limiting and human simulation.
    """
    
    PLATFORM_METADATA = {
        "name": "meesho",
        "display_name": "Meesho",
        "base_url": "https://www.meesho.com",
        "domains": ["meesho.com"],
        "categories": ["fashion", "home", "budget"],
        "product_id_patterns": [r"/p/([a-zA-Z0-9]+)"],
        "affiliate_param": "utm_source",
        "rate_limit_per_minute": 8,  # Very conservative!
        "scrape_delay_seconds": 5,   # Slow down!
        "reliability": "medium",
        "support_level": "partial",
        "anti_bot": "akamai",
        "supports_api_interception": True
    }
    
    BASE_URL = "https://www.meesho.com"
    
    # API patterns to intercept
    API_PATTERNS = [
        '/api/v1/',
        '/api/v2/',
        '/graphql',
        '/product/',
        '/search/',
        '/catalog/',
    ]
    
    # Keywords to filter out accessories
    ACCESSORY_KEYWORDS = [
        "cover", "case", "screen guard", "protector", "tempered glass",
        "charger", "cable", "holder", "stand", "skin", "pouch"
    ]
    
    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self.browser_manager: Optional[BrowserManager] = None
        self.affiliate_id = config.affiliate_tag or getattr(settings, 'MEESHO_AFFILIATE_ID', 'dealhunt')
        
        logger.info(f"✅ MeeshoScraper v2.0 initialized (Akamai Bypass: Active)")
    
    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER
    
    def _is_accessory(self, title: str) -> bool:
        """Filter out accessory products"""
        if not title:
            return False
        return any(kw in title.lower() for kw in self.ACCESSORY_KEYWORDS)
    
    async def _get_browser(self) -> BrowserManager:
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager
    
    async def _check_blocked(self, page_obj) -> bool:
        """Check if we're blocked by Akamai"""
        try:
            content = await page_obj.content()
            body_text = await page_obj.evaluate('() => document.body ? document.body.innerText : ""')
            
            block_indicators = [
                "access denied",
                "access to this page has been denied",
                "reference #",
                "your request has been blocked",
                "unusual traffic",
                "captcha"
            ]
            
            combined = (content + body_text).lower()
            return any(indicator in combined for indicator in block_indicators)
        except:
            return False
    
    # =========================================================================
    # SEARCH
    # =========================================================================
    
    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """
        Search products on Meesho with stealth + API interception
        
        Strategy:
        1. Use mobile mode for less detection
        2. Intercept search API responses
        3. Fallback to DOM if needed
        """
        start_time = datetime.utcnow()
        
        try:
            await self.rate_limiter.acquire("meesho")
            
            # Meesho uses path-based search
            search_query = query.replace(" ", "-").lower()
            search_url = f"{self.BASE_URL}/search?q={quote(query)}"
            if page > 1:
                search_url += f"?page={page}"
            
            logger.info(f"🔍 Meesho search: {query} (page {page})")
            
            browser = await self._get_browser()
            products = []
            extraction_method = ExtractionMethod.DOM_SELECTOR
            
            # 🚀 USE MOBILE MODE + API INTERCEPTION
            async with browser.get_page(
                block_resources=False,
                stealth=True,
                mobile=True,  # Mobile mode for Akamai bypass!
                intercept_api=True
            ) as page_obj:
                
                browser.set_interception_patterns(self.API_PATTERNS)
                
                # Random delay before navigation (human-like)
                await asyncio.sleep(random.uniform(1, 3))
                
                # Navigate with retry
                success = await browser.safe_goto(
                    page_obj, 
                    search_url, 
                    wait_until='domcontentloaded',
                    timeout=45000,
                    retries=2
                )
                
                if not success:
                    return SearchResult(
                        query=query,
                        platform_name="meesho",
                        success=False,
                        error_message="Navigation failed"
                    )
                
                # Check for block
                if await self._check_blocked(page_obj):
                    logger.warning("🚫 Meesho blocked this request")
                    await self.rate_limiter.record_failure("meesho", ThreatLevel.BLOCKED)
                    return SearchResult(
                        query=query,
                        platform_name="meesho",
                        success=False,
                        error_message="Access blocked by Akamai"
                    )
                
                # Wait for content to load
                await page_obj.wait_for_timeout(4000)
                
                # Human-like scrolling
                await browser.scroll_page(page_obj, scroll_count=3, delay_ms=800)
                await page_obj.wait_for_timeout(2000)
                
                # 🚀 STRATEGY 1: Intercepted JSON
                search_json = (
                    browser.get_intercepted_json('/search/') or
                    browser.get_intercepted_json('/catalog/') or
                    browser.get_intercepted_json('/api/')
                )
                
                if search_json:
                    logger.info("✅ Got search results from intercepted JSON")
                    products = self._parse_search_json(search_json)
                    extraction_method = ExtractionMethod.API_INTERCEPTED
                
                # 🔄 STRATEGY 2: __NEXT_DATA__ (Meesho uses Next.js)
                if not products:
                    html_content = await page_obj.content()
                    next_data = await self.extract_from_next_data(html_content)
                    
                    if next_data:
                        products = self._parse_next_data_search(next_data)
                        extraction_method = ExtractionMethod.NEXT_DATA
                        if products:
                            logger.info(f"✅ Got {len(products)} products from __NEXT_DATA__")
                
                # 🔄 STRATEGY 3: DOM fallback
                if not products:
                    logger.warning("⚠️ Using DOM fallback")
                    products = await self._extract_search_dom(page_obj)
                    extraction_method = ExtractionMethod.DOM_JAVASCRIPT
            
            # Filter out accessories
            products = [p for p in products if not self._is_accessory(p.title)]
            
            await self.rate_limiter.record_success("meesho")
            self.record_success()
            
            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            logger.info(f"✅ Meesho search: {len(products)} products ({extraction_method.value})")
            
            return SearchResult(
                query=query,
                platform_name="meesho",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 10,
                search_time_ms=search_time,
                extraction_method=extraction_method,
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
            logger.error(f"❌ Meesho search error: {e}")
            await self.rate_limiter.record_failure("meesho", ThreatLevel.WARNING)
            return SearchResult(
                query=query,
                platform_name="meesho",
                success=False,
                error_message=str(e)
            )
    
    def _parse_search_json(self, json_data: Dict[str, Any]) -> List[ProductData]:
        """Parse intercepted search JSON"""
        products = []
        
        try:
            # Find products array
            product_list = self._find_products_in_json(json_data)
            
            if not product_list:
                logger.warning("Could not find products in JSON")
                return []
            
            for item in product_list[:25]:
                try:
                    product = self._parse_product_item(item)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.debug(f"Parse item error: {e}")
        
        except Exception as e:
            logger.error(f"Parse search JSON error: {e}")
        
        return products
    
    def _find_products_in_json(self, data: Any, depth: int = 0) -> Optional[List]:
        """Recursively find products array"""
        if depth > 6:
            return None
        
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if isinstance(first_item, dict):
                if any(k in first_item for k in ['product_id', 'productId', 'id', 'name', 'product_name']):
                    return data
        
        if isinstance(data, dict):
            for key, value in data.items():
                if key.lower() in ['products', 'catalogs', 'items', 'results', 'data']:
                    if isinstance(value, list) and len(value) > 0:
                        return value
                result = self._find_products_in_json(value, depth + 1)
                if result:
                    return result
        
        return None
    
    def _parse_product_item(self, item: Dict[str, Any]) -> Optional[ProductData]:
        """Parse single product from JSON with confidence"""
        try:
            # Product ID
            product_id = str(
                item.get('product_id') or 
                item.get('productId') or 
                item.get('catalog_id') or
                item.get('id') or ''
            )
            
            if not product_id:
                return None
            
            # Title
            title = (
                item.get('name') or 
                item.get('product_name') or 
                item.get('title') or ''
            )
            
            if not title or len(title) < 5:
                return None
            
            # Price
            price = (
                item.get('price') or
                item.get('min_catalog_price') or
                item.get('discounted_price') or
                item.get('selling_price') or 0
            )
            
            if isinstance(price, dict):
                price = price.get('value') or price.get('amount') or 0
            
            if not price or float(price) <= 0:
                return None
            
            # Original price
            original_price = (
                item.get('original_price') or
                item.get('mrp') or
                item.get('max_catalog_price') or 0
            )
            
            # Discount
            discount = item.get('discount') or item.get('discount_percent') or 0
            if isinstance(discount, str):
                match = re.search(r'(\d+)', discount)
                discount = int(match.group(1)) if match else 0
            
            # Image
            images = item.get('images') or item.get('product_images') or []
            if isinstance(images, list) and images:
                image_url = images[0].get('url') if isinstance(images[0], dict) else images[0]
            else:
                image_url = item.get('image') or item.get('image_url')
            
            # Fix image URL
            if image_url and not image_url.startswith('http'):
                image_url = f"https://images.meesho.com{image_url}"

            # Brand with confidence (often noisy on Meesho)
            brand = item.get('brand') or item.get('supplier_name')
            brand_confidence = 0.70 if brand else 0.0
            brand_source = "api" if brand else None

            # Color with confidence
            color = None
            color_confidence = 0.0
            color_source = None

            attributes = item.get('attributes') or {}
            if isinstance(attributes, dict):
                color = attributes.get('color') or attributes.get('colour')
                if color:
                    color_confidence = 0.82
                    color_source = "api"

            if not color:
                color = item.get('color') or item.get('colour')
                if color:
                    color_confidence = 0.75
                    color_source = "api"
            
            # Rating
            rating = item.get('rating') or item.get('average_rating')
            if isinstance(rating, dict):
                rating = rating.get('average') or rating.get('value')
            
            review_count = item.get('review_count') or item.get('rating_count')
            try:
                parsed_review_count = int(str(review_count).replace(',', '').strip()) if review_count is not None else None
            except (TypeError, ValueError):
                parsed_review_count = None
            
            # Build URL
            product_url = f"{self.BASE_URL}/p/{product_id}"
            
            product = ProductData(
                external_id=product_id,
                title=title.strip()[:200],
                current_price=Decimal(str(price)),
                original_price=Decimal(str(original_price)) if original_price else None,
                discount_percent=float(discount) if discount else None,
                product_url=self.build_affiliate_url(product_url),
                platform_name="meesho",
                image_url=image_url,
                rating=float(rating) if rating else None,
                review_count=parsed_review_count,
                category="Fashion",
                in_stock=True,
                stock_status=StockStatus.IN_STOCK,
                extraction_method=ExtractionMethod.API_INTERCEPTED,
                data_source=HandlerType.SCRAPER
            )

            if brand:
                product.set_attribute_with_confidence("brand", brand, brand_source, brand_confidence)

            if color:
                product.set_attribute_with_confidence("color", color, color_source, color_confidence)

            return product
        
        except Exception as e:
            logger.debug(f"Parse product error: {e}")
            return None
    
    def _parse_next_data_search(self, next_data: Dict[str, Any]) -> List[ProductData]:
        """Parse products from __NEXT_DATA__"""
        products = []
        
        try:
            props = next_data.get('props', {})
            page_props = props.get('pageProps', {})
            
            # Try different paths
            product_list = (
                page_props.get('products') or
                page_props.get('catalogs') or
                page_props.get('initialData', {}).get('products') or
                []
            )
            
            if not product_list:
                product_list = self._find_products_in_json(page_props)
            
            if product_list:
                for item in product_list[:25]:
                    product = self._parse_product_item(item)
                    if product:
                        product.extraction_method = ExtractionMethod.NEXT_DATA
                        products.append(product)
        
        except Exception as e:
            logger.error(f"Parse __NEXT_DATA__ error: {e}")
        
        return products
    
    async def _extract_search_dom(self, page_obj) -> List[ProductData]:
        """Fallback: DOM extraction"""
        products = []
        
        try:
            products_data = await page_obj.evaluate('''() => {
                const products = [];
                const links = document.querySelectorAll('a[href*="/p/"]');
                const seen = new Set();
                
                links.forEach(link => {
                    const href = link.getAttribute('href');
                    if (seen.has(href) || !href) return;
                    seen.add(href);
                    
                    const container = link.closest('div') || link;
                    const text = container.innerText || '';
                    
                    // Find price
                    const priceMatch = text.match(/₹\\s*([0-9,]+)/);
                    if (!priceMatch) return;
                    
                    // Find title
                    const lines = text.split('\\n').filter(l => l.trim().length > 5);
                    let title = null;
                    for (const line of lines) {
                        if (!line.includes('₹') && line.length > 10 && line.length < 150) {
                            title = line.trim();
                            break;
                        }
                    }
                    
                    if (!title) return;
                    
                    const img = container.querySelector('img');
                    
                    products.push({
                        title: title,
                        price: priceMatch[1].replace(/,/g, ''),
                        url: href,
                        image: img ? img.src : null
                    });
                });
                
                return products.slice(0, 20);
            }''')
            
            for item in products_data:
                try:
                    price = Decimal(item.get('price', '0'))
                    if not price or price <= 0:
                        continue
                    
                    url = item.get('url', '')
                    if url and not url.startswith('http'):
                        url = f"{self.BASE_URL}{url}"
                    
                    product_id = self.extract_product_id(url)
                    if not product_id:
                        product_id = hashlib.md5(url.encode()).hexdigest()[:16]
                    
                    products.append(ProductData(
                        external_id=product_id,
                        title=item.get('title', '')[:200],
                        current_price=price,
                        product_url=self.build_affiliate_url(url),
                        platform_name="meesho",
                        image_url=item.get('image'),
                        in_stock=True,
                        extraction_method=ExtractionMethod.DOM_JAVASCRIPT,
                        data_source=HandlerType.SCRAPER
                    ))
                except:
                    continue

            if not products:
                healed_product = await self._extract_search_with_ai_healing(page_obj)
                if healed_product:
                    products.append(healed_product)
            
            logger.info(f"✅ DOM extracted {len(products)} products")
        
        except Exception as e:
            logger.error(f"DOM extraction error: {e}")
        
        return products

    async def _extract_search_with_ai_healing(self, page_obj) -> Optional[ProductData]:
        """Last-resort search extraction using universal self-healing selectors."""
        try:
            healed = await self.auto_healing_extraction(
                page_obj,
                await page_obj.content(),
                fields=["product_title", "product_price", "product_url", "product_image", "brand", "product_rating", "review_count"],
                test_timeout=4.0,
            )

            title = healed.get("product_title")
            price = healed.get("product_price")
            if not title or price is None:
                return None

            price_value = Decimal(str(price))
            if price_value <= 0:
                return None

            url = healed.get("product_url") or ""
            if url and not str(url).startswith("http"):
                url = f"{self.BASE_URL}{url}" if str(url).startswith("/") else f"{self.BASE_URL}/{url}"

            product_id = self.extract_product_id(url) if url else None
            if not product_id:
                product_id = hashlib.md5(f"{title}-{price_value}".encode()).hexdigest()[:16]

            rating = healed.get("product_rating")
            review_count = healed.get("review_count")
            try:
                review_count = int(str(review_count).replace(",", "").strip()) if review_count is not None else None
            except (TypeError, ValueError):
                review_count = None

            logger.info("🤖 Meesho AI healing recovered a search result")
            return ProductData(
                external_id=product_id,
                title=str(title)[:200],
                current_price=price_value,
                product_url=self.build_affiliate_url(url) if url else "",
                platform_name="meesho",
                image_url=healed.get("product_image"),
                brand=healed.get("brand"),
                rating=float(rating) if rating is not None else None,
                review_count=review_count,
                category="Fashion",
                in_stock=True,
                extraction_method=ExtractionMethod.AI_HEALED,
                data_source=HandlerType.SCRAPER,
                raw_data={"source": "ai_healed_search", "stats": healed.get("_extraction_stats", {})},
            )
        except Exception as e:
            logger.debug(f"AI-healed Meesho search extraction failed: {e}")
            return None
    
    # =========================================================================
    # PRODUCT DETAILS
    # =========================================================================
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get product with mobile stealth + API interception"""
        try:
            await self.rate_limiter.acquire("meesho")
            
            product_id = self.extract_product_id(product_url)
            logger.info(f"🛒 Meesho product: {product_id or product_url[:50]}")
            
            browser = await self._get_browser()
            
            async with browser.get_page(
                block_resources=False,
                stealth=True,
                mobile=True,
                intercept_api=True
            ) as page_obj:
                
                browser.set_interception_patterns(self.API_PATTERNS)
                
                # Human delay
                await asyncio.sleep(random.uniform(1, 2))
                
                success = await browser.safe_goto(
                    page_obj,
                    product_url,
                    wait_until='domcontentloaded',
                    timeout=45000,
                    retries=2
                )
                
                if not success:
                    return None
                
                # Check block
                if await self._check_blocked(page_obj):
                    logger.warning("🚫 Meesho blocked product request")
                    await self.rate_limiter.record_failure("meesho", ThreatLevel.BLOCKED)
                    return None
                
                await page_obj.wait_for_timeout(4000)
                
                product = None
                
                # 🚀 STRATEGY 1: Intercepted JSON
                product_json = (
                    browser.get_intercepted_json('/product/') or
                    browser.get_intercepted_json(f'/{product_id}') or
                    browser.get_intercepted_json('/api/')
                )
                
                if product_json:
                    product = self._parse_product_json(product_json, product_url)
                    if product:
                        logger.info("✅ Got product from intercepted JSON")
                
                # 🔄 STRATEGY 2: __NEXT_DATA__
                if not product:
                    html_content = await page_obj.content()
                    next_data = await self.extract_from_next_data(html_content)
                    
                    if next_data:
                        product = self._parse_next_data_product(next_data, product_url, product_id)
                        if product:
                            logger.info("✅ Got product from __NEXT_DATA__")
                
                # 🔄 STRATEGY 3: DOM fallback
                if not product:
                    product = await self._extract_product_dom(page_obj, product_url, product_id)
                    if product:
                        logger.info("✅ Got product from DOM")
                
                if product:
                    await self.rate_limiter.record_success("meesho")
                    self.record_success()
                    return product
                
                return None
        
        except RateLimitExceeded:
            return None
        
        except Exception as e:
            logger.error(f"❌ Meesho product error: {e}")
            await self.rate_limiter.record_failure("meesho", ThreatLevel.WARNING)
            return None
    
    def _parse_product_json(self, json_data: Dict[str, Any], product_url: str) -> Optional[ProductData]:
        """Parse product from intercepted JSON"""
        try:
            product_data = (
                json_data.get('product') or
                json_data.get('catalog') or
                json_data.get('data', {}).get('product') or
                json_data
            )
            
            return self._parse_product_item(product_data)
        except Exception as e:
            logger.error(f"Parse product JSON error: {e}")
            return None
    
    def _parse_next_data_product(
        self, 
        next_data: Dict[str, Any], 
        product_url: str,
        product_id: Optional[str]
    ) -> Optional[ProductData]:
        """Parse product from __NEXT_DATA__"""
        try:
            props = next_data.get('props', {})
            page_props = props.get('pageProps', {})
            
            product_data = (
                page_props.get('product') or
                page_props.get('catalog') or
                page_props.get('productDetails') or
                {}
            )
            
            if product_data:
                product = self._parse_product_item(product_data)
                if product:
                    product.extraction_method = ExtractionMethod.NEXT_DATA
                    return product
        except Exception as e:
            logger.error(f"Parse __NEXT_DATA__ product error: {e}")
        
        return None
    
    async def _extract_product_dom(
        self, 
        page_obj, 
        product_url: str,
        product_id: Optional[str]
    ) -> Optional[ProductData]:
        """Fallback: DOM extraction for product"""
        try:
            used_ai_healing = False
            product_data = await page_obj.evaluate('''() => {
                const result = {
                    title: null,
                    price: null,
                    image: null,
                    rating: null
                };
                
                const bodyText = document.body.innerText;
                
                // Title - find longest reasonable line
                const lines = bodyText.split('\\n').filter(l => l.trim());
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (trimmed.length > 20 && trimmed.length < 250 && 
                        !trimmed.includes('₹') && 
                        !trimmed.includes('Meesho') &&
                        !trimmed.includes('Access')) {
                        result.title = trimmed;
                        break;
                    }
                }
                
                // Price
                const priceMatches = bodyText.match(/₹\\s*([0-9,]+)/g);
                if (priceMatches && priceMatches.length > 0) {
                    result.price = priceMatches[0].replace(/[₹,\\s]/g, '');
                }
                
                // Image
                const imgs = document.querySelectorAll('img[src*="meesho"], img[src*="images"]');
                for (const img of imgs) {
                    if (img.src && img.naturalWidth > 100) {
                        result.image = img.src;
                        break;
                    }
                }
                
                // Rating
                const ratingMatch = bodyText.match(/([1-5]\\.\\d)\\s*(?:★|star|rating)/i);
                if (ratingMatch) result.rating = ratingMatch[1];
                
                return result;
            }''')
            
            if not product_data.get('title') or not product_data.get('price'):
                healed = await self.auto_healing_extraction(
                    page_obj,
                    await page_obj.content(),
                    fields=["product_title", "product_price", "product_image", "brand", "product_rating", "review_count"],
                    test_timeout=4.0,
                )
                if healed.get("product_title") and healed.get("product_price"):
                    used_ai_healing = True
                    product_data["title"] = healed.get("product_title")
                    product_data["price"] = str(healed.get("product_price"))
                    product_data["image"] = healed.get("product_image") or product_data.get("image")
                    product_data["rating"] = healed.get("product_rating") or product_data.get("rating")
                    product_data["brand"] = healed.get("brand")
                    product_data["reviewCount"] = healed.get("review_count")
                else:
                    return None
            
            if not product_id:
                product_id = hashlib.md5(product_url.encode()).hexdigest()[:16]
            
            return ProductData(
                external_id=product_id,
                title=product_data['title'][:200],
                current_price=Decimal(product_data['price']),
                product_url=self.build_affiliate_url(product_url),
                platform_name="meesho",
                image_url=product_data.get('image'),
                brand=product_data.get('brand'),
                rating=float(product_data['rating']) if product_data.get('rating') else None,
                review_count=int(str(product_data['reviewCount']).replace(',', '')) if product_data.get('reviewCount') else None,
                in_stock=True,
                extraction_method=ExtractionMethod.AI_HEALED if used_ai_healing else ExtractionMethod.DOM_JAVASCRIPT,
                data_source=HandlerType.SCRAPER
            )
        
        except Exception as e:
            logger.error(f"DOM product extraction error: {e}")
            return None
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        return await self.get_product(f"{self.BASE_URL}/p/{external_id}")
    
    def extract_product_id(self, url: str) -> Optional[str]:
        try:
            match = re.search(r'/p/([a-zA-Z0-9]+)', url)
            if match:
                return match.group(1)
        except:
            pass
        return None
    
    def build_affiliate_url(self, product_url: str) -> str:
        if not self.affiliate_id:
            return product_url
        sep = "&" if "?" in product_url else "?"
        return f"{product_url}{sep}utm_source={self.affiliate_id}"
    
    async def close(self) -> None:
        pass
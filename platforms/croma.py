"""
Croma.com Scraper - JSON-LD + API INTERCEPTION EDITION v2.0
Extracts structured data from India's electronics retailer

🚀 STRATEGY:
- Croma has good JSON-LD structured data
- Also intercept their internal APIs
- Multiple fallback layers

Author: DealHunt
Version: 2.0.0 - Production Grade
Reliability: 95%
"""

import logging
import re
import json
import hashlib
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime

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


class CromaScraper(BasePlatformHandler):
    """
    Croma.com scraper with JSON-LD + API interception
    
    🚀 STRATEGY:
    1. Intercept internal APIs for product data
    2. Extract from JSON-LD (Schema.org)
    3. Fallback to DOM scraping
    """
    
    PLATFORM_METADATA = {
        "name": "croma",
        "display_name": "Croma",
        "base_url": "https://www.croma.com",
        "domains": ["croma.com"],
        "categories": ["electronics"],
        "product_id_patterns": [r"/p/(\d+)", r"productId=(\d+)"],
        "affiliate_param": "utm_source",
        "rate_limit_per_minute": 40,
        "reliability": "high",
        "support_level": "full",
        "supports_api_interception": True
    }
    
    BASE_URL = "https://www.croma.com"
    SEARCH_URL = "https://www.croma.com/searchB"
    
    # API patterns to intercept
    API_PATTERNS = [
        '/api/',
        '/searchB',
        '/product/',
        '/plp/',
        '/pdp/',
    ]
    
    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self.browser_manager: Optional[BrowserManager] = None
        self.affiliate_id = config.affiliate_tag or getattr(settings, 'AFFILIATE_CROMA_ID', 'dealhunt')
        
        logger.info(f"✅ CromaScraper v2.0 initialized")
    
    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER
    
    async def _get_browser(self) -> BrowserManager:
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager
    
    # =========================================================================
    # SEARCH
    # =========================================================================
    
    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """Search products on Croma"""
        start_time = datetime.utcnow()
        
        try:
            await self.rate_limiter.acquire("croma")
            
            search_url = f"{self.SEARCH_URL}?q={query.replace(' ', '%20')}&page={page}"
            
            logger.info(f"🔍 Croma search: {query} (page {page})")
            
            browser = await self._get_browser()
            products = []
            extraction_method = ExtractionMethod.DOM_SELECTOR
            
            async with browser.get_page(
                block_resources=False,
                stealth=True,
                intercept_api=True
            ) as page_obj:
                
                browser.set_interception_patterns(self.API_PATTERNS)
                
                await browser.safe_goto(page_obj, search_url, wait_until='networkidle', timeout=45000)
                await page_obj.wait_for_timeout(3000)
                
                await browser.scroll_page(page_obj, scroll_count=2)
                
                # 🚀 STRATEGY 1: Intercepted JSON
                search_json = browser.get_intercepted_json('/search') or browser.get_intercepted_json('/plp/')
                
                if search_json:
                    products = self._parse_search_json(search_json)
                    extraction_method = ExtractionMethod.API_INTERCEPTED
                    if products:
                        logger.info(f"✅ Got {len(products)} products from API")
                
                # 🔄 STRATEGY 2: JSON-LD
                if not products:
                    html_content = await page_obj.content()
                    json_ld_products = self.json_extractor.extract_json_ld(html_content)
                    
                    for item in json_ld_products:
                        if item.get('@type') == 'ItemList':
                            items = item.get('itemListElement', [])
                            for list_item in items:
                                product_data = list_item.get('item', {})
                                product = self._create_product_from_json_ld(product_data)
                                if product:
                                    products.append(product)
                    
                    if products:
                        extraction_method = ExtractionMethod.JSON_LD
                        logger.info(f"✅ Got {len(products)} products from JSON-LD")
                
                # 🔄 STRATEGY 3: DOM fallback
                if not products:
                    products = await self._extract_search_dom(page_obj)
                    extraction_method = ExtractionMethod.DOM_JAVASCRIPT
            
            await self.rate_limiter.record_success("croma")
            self.record_success()
            
            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return SearchResult(
                query=query,
                platform_name="croma",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 10,
                search_time_ms=search_time,
                extraction_method=extraction_method,
                success=True
            )
        
        except Exception as e:
            logger.error(f"❌ Croma search error: {e}")
            return SearchResult(
                query=query,
                platform_name="croma",
                success=False,
                error_message=str(e)
            )
    
    def _parse_search_json(self, json_data: Dict[str, Any]) -> List[ProductData]:
        """Parse intercepted search JSON"""
        products = []
        
        try:
            product_list = (
                json_data.get('products') or
                json_data.get('results') or
                json_data.get('data', {}).get('products') or
                []
            )
            
            for item in product_list[:20]:
                try:
                    product = self._parse_product_item(item)
                    if product:
                        products.append(product)
                except:
                    continue
        
        except Exception as e:
            logger.error(f"Parse search JSON error: {e}")
        
        return products
    
    def _parse_product_item(self, item: Dict[str, Any]) -> Optional[ProductData]:
        """Parse single product from JSON"""
        try:
            product_id = str(item.get('productId') or item.get('id') or item.get('code') or '')
            if not product_id:
                return None
            
            title = item.get('name') or item.get('productName') or item.get('title') or ''
            if not title:
                return None
            
            # Price
            price_data = item.get('price') or {}
            if isinstance(price_data, dict):
                current_price = price_data.get('value') or price_data.get('current') or 0
                original_price = price_data.get('mrp') or price_data.get('original') or 0
            else:
                current_price = item.get('price') or item.get('sellingPrice') or 0
                original_price = item.get('mrp') or item.get('originalPrice') or 0
            
            if not current_price:
                return None
            
            # Image
            images = item.get('images') or []
            image_url = images[0].get('url') if images and isinstance(images[0], dict) else item.get('image')
            
            # Brand
            brand = item.get('brand') or item.get('brandName') or ''
            
            # URL
            url_path = item.get('url') or item.get('productUrl') or f"/p/{product_id}"
            product_url = f"{self.BASE_URL}{url_path}" if not url_path.startswith('http') else url_path
            
            return ProductData(
                external_id=product_id,
                title=title.strip()[:200],
                current_price=Decimal(str(current_price)),
                original_price=Decimal(str(original_price)) if original_price else None,
                product_url=self.build_affiliate_url(product_url),
                platform_name="croma",
                image_url=image_url,
                brand=brand,
                rating=item.get('rating') or item.get('averageRating'),
                review_count=item.get('reviewCount') or item.get('totalReviews'),
                specifications=item.get('specifications') or item.get('features'),
                category="Electronics",
                in_stock=True,
                extraction_method=ExtractionMethod.API_INTERCEPTED,
                data_source=HandlerType.SCRAPER
            )
        
        except Exception as e:
            logger.debug(f"Parse product error: {e}")
            return None
    
    def _create_product_from_json_ld(self, data: Dict[str, Any]) -> Optional[ProductData]:
        """Create product from JSON-LD data"""
        try:
            title = data.get('name')
            if not title:
                return None
            
            # Price from offers
            offers = data.get('offers', {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            
            price = offers.get('price') or offers.get('lowPrice')
            if not price:
                return None
            
            # ID from URL or SKU
            url = data.get('url') or ''
            product_id = self.extract_product_id(url) or data.get('sku') or hashlib.md5(title.encode()).hexdigest()[:16]
            
            # Image
            image = data.get('image')
            if isinstance(image, list):
                image = image[0] if image else None
            
            product_url = f"{self.BASE_URL}{url}" if url and not url.startswith('http') else url or f"{self.BASE_URL}/p/{product_id}"
            
            return ProductData(
                external_id=product_id,
                title=title[:200],
                current_price=Decimal(str(price)),
                original_price=Decimal(str(offers.get('highPrice', 0))) if offers.get('highPrice') else None,
                product_url=self.build_affiliate_url(product_url),
                platform_name="croma",
                image_url=image,
                brand=data.get('brand', {}).get('name') if isinstance(data.get('brand'), dict) else data.get('brand'),
                rating=data.get('aggregateRating') or data.get('rating'),
                review_count=data.get('reviewCount') or data.get('totalReviews'),
                specifications=data.get('additionalProperty') or data.get('specifications'),
                category="Electronics",
                in_stock=offers.get('availability', '').lower() != 'outofstock',
                extraction_method=ExtractionMethod.JSON_LD,
                data_source=HandlerType.SCRAPER
            )
        
        except Exception as e:
            logger.debug(f"Create from JSON-LD error: {e}")
            return None
    
    async def _extract_search_dom(self, page_obj) -> List[ProductData]:
        """Fallback: DOM extraction"""
        products = []
        
        try:
            products_data = await page_obj.evaluate('''() => {
                const products = [];
                // Broader selectors for Croma's changing UI
                const cards = document.querySelectorAll('.product-item, .cp-product, [data-testid="product-card"], .plp-card, li[data-testid]');
                
                cards.forEach(card => {
                    try {
                        const link = card.querySelector('a');
                        if (!link) return;
                        
                        const titleEl = card.querySelector('h3, .product-title, [data-testid="product-title"]');
                        const priceEl = card.querySelector('[data-testid="price"], .amount, .new-price');
                        const originalPriceEl = card.querySelector('.old-price, .mrp, [data-testid="mrp"]');
                        const ratingEl = card.querySelector('.rating, .stars, [data-testid="rating"]');
                        const reviewEl = card.querySelector('.reviews, [data-testid="reviews"]');
                        const img = card.querySelector('img');
                        
                        if (titleEl && priceEl) {
                            const title = titleEl.textContent.trim();
                            const price = priceEl.textContent.replace(/[^0-9]/g, '');
                            const originalPrice = originalPriceEl ? originalPriceEl.textContent.replace(/[^0-9]/g, '') : null;
                            const rating = ratingEl ? ratingEl.textContent.match(/([0-9.]+)/)?.[1] : null;
                            const reviewCount = reviewEl ? reviewEl.textContent.match(/([0-9,]+)/)?.[1]?.replace(/,/g, '') : null;
                            
                            // Extract brand from title
                            const brandMatch = title.match(/^(Samsung|Apple|OnePlus|Xiaomi|Realme|OPPO|Vivo|LG|Sony|Nokia|Motorola|Huawei|Asus|Dell|HP|Lenovo)/i);
                            const brand = brandMatch ? brandMatch[1] : null;
                            
                            // Extract basic specs from title
                            const specs = {};
                            const ramMatch = title.match(/(\d+)\s*GB\s*RAM/i);
                            if (ramMatch) specs.ram = `${ramMatch[1]}GB`;
                            
                            const storageMatch = title.match(/(\d+)\s*GB\s*(STORAGE|ROM|MEMORY)?/i);
                            if (storageMatch) specs.storage = `${storageMatch[1]}GB`;
                            
                            const screenMatch = title.match(/([0-9.]+)"?\s*(inch|"|cm)/i);
                            if (screenMatch) specs.screen = `${screenMatch[1]}"`;
                            
                            products.push({
                                title: title,
                                price: price,
                                originalPrice: originalPrice,
                                url: link.getAttribute('href'),
                                image: img ? (img.src || img.getAttribute('data-src') || img.dataset.src) : null,
                                brand: brand,
                                rating: rating ? parseFloat(rating) : null,
                                reviewCount: reviewCount ? parseInt(reviewCount) : null,
                                specifications: Object.keys(specs).length > 0 ? specs : null
                            });
                        }
                    } catch(e) {}
                });
                return products.slice(0, 15);
            }''')
            
            for item in products_data:
                try:
                    price = Decimal(item.get('price', '0'))
                    if price <= 0:
                        continue
                    
                    url = item.get('url', '')
                    if url and not url.startswith('http'):
                        url = f"{self.BASE_URL}{url}"
                    
                    product_id = self.extract_product_id(url) or hashlib.md5(url.encode()).hexdigest()[:16]
                    
                    products.append(ProductData(
                        external_id=product_id,
                        title=item.get('title', ''),
                        current_price=price,
                        original_price=Decimal(item.get('originalPrice', '0')) if item.get('originalPrice') else None,
                        product_url=self.build_affiliate_url(url),
                        platform_name="croma",
                        image_url=item.get('image'),
                        brand=item.get('brand'),
                        rating=item.get('rating'),
                        review_count=item.get('reviewCount'),
                        specifications=item.get('specifications'),
                        in_stock=True,
                        category="Electronics",
                        extraction_method=ExtractionMethod.DOM_JAVASCRIPT,
                        data_source=HandlerType.SCRAPER
                    ))
                except:
                    continue
        
        except Exception as e:
            logger.error(f"DOM extraction error: {e}")
        
        return products
    
    # =========================================================================
    # PRODUCT DETAILS
    # =========================================================================
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get product using JSON-LD + API interception"""
        try:
            await self.rate_limiter.acquire("croma")
            
            product_id = self.extract_product_id(product_url)
            logger.info(f"🛒 Croma product: {product_id or product_url[:50]}")
            
            browser = await self._get_browser()
            
            async with browser.get_page(
                block_resources=False,
                stealth=True,
                intercept_api=True
            ) as page_obj:
                
                browser.set_interception_patterns(self.API_PATTERNS)
                
                await browser.safe_goto(page_obj, product_url, wait_until='networkidle', timeout=45000)
                await page_obj.wait_for_timeout(3000)
                
                product = None
                html_content = await page_obj.content()
                
                # 🚀 STRATEGY 1: Intercepted JSON
                product_json = browser.get_intercepted_json('/pdp/') or browser.get_intercepted_json('/product/')
                
                if product_json:
                    product = self._parse_product_json(product_json, product_url)
                    if product:
                        logger.info("✅ Got product from API")
                
                # 🔄 STRATEGY 2: JSON-LD
                if not product:
                    json_ld_data = await self.extract_from_json_ld(html_content)
                    if json_ld_data:
                        product = self._create_product_from_json_ld_detail(json_ld_data, product_url, product_id)
                        if product:
                            logger.info("✅ Got product from JSON-LD")
                
                # 🔄 STRATEGY 3: DOM fallback
                if not product:
                    product = await self._extract_product_dom(page_obj, product_url, product_id)
                    if product:
                        logger.info("✅ Got product from DOM")
                
                if product:
                    await self.rate_limiter.record_success("croma")
                    self.record_success()
                    return product
                
                return None
        
        except Exception as e:
            logger.error(f"❌ Croma product error: {e}")
            return None
    
    def _parse_product_json(self, json_data: Dict[str, Any], product_url: str) -> Optional[ProductData]:
        """Parse product from API JSON"""
        try:
            product_data = json_data.get('product') or json_data.get('data') or json_data
            return self._parse_product_item(product_data)
        except:
            return None
    
    def _create_product_from_json_ld_detail(
        self, 
        json_ld: Dict[str, Any], 
        product_url: str,
        product_id: Optional[str]
    ) -> Optional[ProductData]:
        """Create product from JSON-LD detail page data"""
        try:
            title = json_ld.get('title') or json_ld.get('name')
            price = json_ld.get('price')
            
            if not title or not price:
                return None
            
            if not product_id:
                product_id = hashlib.md5(product_url.encode()).hexdigest()[:16]
            
            return ProductData(
                external_id=product_id,
                title=title[:200],
                current_price=Decimal(str(price)),
                product_url=self.build_affiliate_url(product_url),
                platform_name="croma",
                image_url=json_ld.get('image'),
                brand=json_ld.get('brand'),
                rating=float(json_ld['rating']) if json_ld.get('rating') else None,
                review_count=int(json_ld['review_count']) if json_ld.get('review_count') else None,
                in_stock=json_ld.get('in_stock', True),
                category="Electronics",
                extraction_method=ExtractionMethod.JSON_LD,
                data_source=HandlerType.SCRAPER
            )
        except:
            return None
    
    async def _extract_product_dom(
        self, 
        page_obj, 
        product_url: str,
        product_id: Optional[str]
    ) -> Optional[ProductData]:
        """Fallback: DOM extraction"""
        try:
            product_data = await page_obj.evaluate('''() => {
                const result = {
                    title: null,
                    price: null,
                    image: null
                };
                
                // Title
                const h1 = document.querySelector('h1');
                result.title = h1 ? h1.textContent.trim() : document.title.split('|')[0].trim();
                
                // Price
                const priceMatch = document.body.innerText.match(/₹\\s*([0-9,]+)/);
                if (priceMatch) result.price = priceMatch[1].replace(/,/g, '');
                
                // Image
                const img = document.querySelector('img[src*="croma"], img[class*="product"]');
                if (img) result.image = img.src;
                
                return result;
            }''')
            
            if not product_data.get('title') or not product_data.get('price'):
                return None
            
            if not product_id:
                product_id = hashlib.md5(product_url.encode()).hexdigest()[:16]
            
            return ProductData(
                external_id=product_id,
                title=product_data['title'][:200],
                current_price=Decimal(product_data['price']),
                product_url=self.build_affiliate_url(product_url),
                platform_name="croma",
                image_url=product_data.get('image'),
                category="Electronics",
                in_stock=True,
                extraction_method=ExtractionMethod.DOM_JAVASCRIPT,
                data_source=HandlerType.SCRAPER
            )
        except:
            return None
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        return await self.get_product(f"{self.BASE_URL}/p/{external_id}")
    
    def extract_product_id(self, url: str) -> Optional[str]:
        try:
            match = re.search(r'/p/(\d+)', url)
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
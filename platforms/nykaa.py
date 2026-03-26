"""
Nykaa.com Scraper - JSON-LD + API INTERCEPTION EDITION v2.0
Beauty products scraper with multiple extraction strategies

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
from app.services.scraper.rate_limiter import RateLimiter, ThreatLevel
from app.core.config import settings

logger = logging.getLogger(__name__)


class NykaaScraper(BasePlatformHandler):
    """
    Nykaa.com scraper with JSON-LD + API interception
    
    🚀 STRATEGY:
    1. Intercept internal APIs
    2. Extract from JSON-LD
    3. Fallback to DOM
    """
    
    PLATFORM_METADATA = {
        "name": "nykaa",
        "display_name": "Nykaa",
        "base_url": "https://www.nykaa.com",
        "domains": ["nykaa.com"],
        "categories": ["beauty"],
        "product_id_patterns": [r"/p/(\d+)", r"productId=(\d+)"],
        "affiliate_param": "utm_source",
        "rate_limit_per_minute": 40,
        "reliability": "high",
        "support_level": "full",
        "supports_api_interception": True
    }
    
    BASE_URL = "https://www.nykaa.com"
    SEARCH_URL = "https://www.nykaa.com/search/result"
    
    API_PATTERNS = [
        '/api/',
        '/gateway/',
        '/search/',
        '/product/',
        '/catalog/',
    ]
    
    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self.browser_manager: Optional[BrowserManager] = None
        self.affiliate_id = config.affiliate_tag or getattr(settings, 'AFFILIATE_NYKAA_ID', 'dealhunt')
        
        logger.info(f"✅ NykaaScraper v2.0 initialized")
    
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
        """Search products on Nykaa"""
        start_time = datetime.utcnow()
        
        try:
            await self.rate_limiter.acquire("nykaa")
            
            search_url = f"{self.SEARCH_URL}?q={query.replace(' ', '%20')}&root=search&page_no={page}"
            
            logger.info(f"🔍 Nykaa search: {query} (page {page})")
            
            browser = await self._get_browser()
            products = []
            extraction_method = ExtractionMethod.DOM_SELECTOR
            
            async with browser.get_page(
                block_resources=True,
                stealth=True,
                intercept_api=True
            ) as page_obj:
                
                browser.set_interception_patterns(self.API_PATTERNS)
                
                await browser.safe_goto(page_obj, search_url, wait_until='domcontentloaded', timeout=30000)
                await page_obj.wait_for_timeout(3000)
                
                await browser.scroll_page(page_obj, scroll_count=2)
                
                # 🚀 STRATEGY 1: Intercepted JSON
                search_json = browser.get_intercepted_json('/search/') or browser.get_intercepted_json('/catalog/')
                
                if search_json:
                    products = self._parse_search_json(search_json)
                    extraction_method = ExtractionMethod.API_INTERCEPTED
                    if products:
                        logger.info(f"✅ Got {len(products)} products from API")
                
                # 🔄 STRATEGY 2: __NEXT_DATA__ (Nykaa also uses Next.js)
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
                    products = await self._extract_search_dom(page_obj)
                    extraction_method = ExtractionMethod.DOM_JAVASCRIPT
            
            await self.rate_limiter.record_success("nykaa")
            self.record_success()
            
            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return SearchResult(
                query=query,
                platform_name="nykaa",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 10,
                search_time_ms=search_time,
                extraction_method=extraction_method,
                success=True
            )
        
        except Exception as e:
            logger.error(f"❌ Nykaa search error: {e}")
            return SearchResult(
                query=query,
                platform_name="nykaa",
                success=False,
                error_message=str(e)
            )
    
    def _parse_search_json(self, json_data: Dict[str, Any]) -> List[ProductData]:
        """Parse intercepted search JSON"""
        products = []
        
        try:
            product_list = (
                json_data.get('products') or
                json_data.get('response', {}).get('products') or
                json_data.get('data', {}).get('products') or
                []
            )
            
            for item in product_list[:20]:
                product = self._parse_product_item(item)
                if product:
                    products.append(product)
        
        except Exception as e:
            logger.error(f"Parse search JSON error: {e}")
        
        return products
    
    def _parse_product_item(self, item: Dict[str, Any]) -> Optional[ProductData]:
        """Parse single product from JSON with confidence"""
        try:
            product_id = str(item.get('id') or item.get('productId') or item.get('sku') or '')
            if not product_id:
                return None
            
            title = item.get('name') or item.get('title') or item.get('productName') or ''
            if not title:
                return None
            
            # Price
            price = (
                item.get('price') or
                item.get('discountedPrice') or
                item.get('offerPrice') or
                item.get('finalPrice') or 0
            )
            
            original_price = item.get('mrp') or item.get('originalPrice') or 0
            
            if not price:
                return None
            
            # Image
            image_url = (
                item.get('imageUrl') or
                item.get('image') or
                item.get('thumbnail') or
                item.get('primaryImage')
            )

            # Brand with confidence
            brand = item.get('brandName') or item.get('brand') or ''
            brand_confidence = 0.90 if brand else 0.0
            brand_source = "api" if brand else None

            # Color/Shade with confidence
            color = None
            color_confidence = 0.0
            color_source = None

            shades = item.get('shades') or item.get('variants') or []
            if shades and isinstance(shades, list):
                shade_info = shades[0] if isinstance(shades[0], dict) else {}
                color = shade_info.get('name') or shade_info.get('shade') or shade_info.get('color')
                if color:
                    color_confidence = 0.88
                    color_source = "api"

            if not color:
                color = item.get('shade') or item.get('color') or item.get('variant')
                if color:
                    color_confidence = 0.85
                    color_source = "api"
            
            # Rating
            rating = item.get('rating') or item.get('averageRating')
            review_count = item.get('reviewCount') or item.get('ratingCount')
            try:
                parsed_review_count = int(str(review_count).replace(',', '').strip()) if review_count is not None else None
            except (TypeError, ValueError):
                parsed_review_count = None
            
            # URL
            slug = item.get('slug') or item.get('productUrl') or ''
            if slug:
                product_url = f"{self.BASE_URL}/{slug}" if not slug.startswith('http') else slug
            else:
                product_url = f"{self.BASE_URL}/p/{product_id}"
            
            product = ProductData(
                external_id=product_id,
                title=title.strip()[:200],
                current_price=Decimal(str(price)),
                original_price=Decimal(str(original_price)) if original_price else None,
                product_url=self.build_affiliate_url(product_url),
                platform_name="nykaa",
                image_url=image_url,
                rating=float(rating) if rating else None,
                review_count=parsed_review_count,
                category="Beauty",
                in_stock=True,
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
            
            product_list = (
                page_props.get('products') or
                page_props.get('searchResults', {}).get('products') or
                page_props.get('catalogProducts') or
                []
            )
            
            for item in product_list[:20]:
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
                    if (seen.has(href)) return;
                    seen.add(href);
                    
                    const container = link.closest('div') || link;
                    const text = container.innerText;
                    const priceMatch = text.match(/₹\\s*([0-9,]+)/);
                    if (!priceMatch) return;
                    
                    // Get title - prefer link text
                    let title = link.textContent.trim();
                    if (title.length < 10) {
                        const lines = text.split('\\n').filter(l => l.length > 10 && !l.includes('₹'));
                        title = lines[0] || "Nykaa Product";
                    }
                    
                    products.push({
                        title: title.substring(0, 200),
                        price: priceMatch[1].replace(/,/g, ''),
                        url: href
                    });
                });
                
                return products.slice(0, 15);
            }''')
            
            for item in products_data:
                try:
                    price = Decimal(item.get('price', '0'))
                    if price <= 0:
                        continue
                    
                    url = item.get('url', '')
                    if url.startswith('/'):
                        url = f"{self.BASE_URL}{url}"
                    
                    product_id = self.extract_product_id(url) or hashlib.md5(url.encode()).hexdigest()[:16]
                    
                    products.append(ProductData(
                        external_id=product_id,
                        title=item.get('title', ''),
                        current_price=price,
                        product_url=self.build_affiliate_url(url),
                        platform_name="nykaa",
                        category="Beauty",
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

            logger.info("🤖 Nykaa AI healing recovered a search result")
            return ProductData(
                external_id=product_id,
                title=str(title)[:200],
                current_price=price_value,
                product_url=self.build_affiliate_url(url) if url else "",
                platform_name="nykaa",
                image_url=healed.get("product_image"),
                brand=healed.get("brand"),
                rating=float(rating) if rating is not None else None,
                review_count=review_count,
                category="Beauty",
                in_stock=True,
                extraction_method=ExtractionMethod.AI_HEALED,
                data_source=HandlerType.SCRAPER,
                raw_data={"source": "ai_healed_search", "stats": healed.get("_extraction_stats", {})},
            )
        except Exception as e:
            logger.debug(f"AI-healed Nykaa search extraction failed: {e}")
            return None
    
    # =========================================================================
    # PRODUCT DETAILS
    # =========================================================================
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get product using JSON-LD + API interception"""
        try:
            await self.rate_limiter.acquire("nykaa")
            
            product_id = self.extract_product_id(product_url)
            logger.info(f"🛒 Nykaa product: {product_id or product_url[:50]}")
            
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
                product_json = browser.get_intercepted_json('/product/')
                
                if product_json:
                    product = self._parse_product_detail_json(product_json, product_url)
                    if product:
                        logger.info("✅ Got product from API")
                
                # 🔄 STRATEGY 2: JSON-LD
                if not product:
                    json_ld_data = await self.extract_from_json_ld(html_content)
                    if json_ld_data:
                        product = self._create_product_from_json_ld(json_ld_data, product_url, product_id)
                        if product:
                            logger.info("✅ Got product from JSON-LD")
                
                # 🔄 STRATEGY 3: __NEXT_DATA__
                if not product:
                    next_data = await self.extract_from_next_data(html_content)
                    if next_data:
                        product = self._parse_next_data_product(next_data, product_url, product_id)
                        if product:
                            logger.info("✅ Got product from __NEXT_DATA__")
                
                # 🔄 STRATEGY 4: DOM fallback
                if not product:
                    product = await self._extract_product_dom(page_obj, product_url, product_id)
                    if product:
                        logger.info("✅ Got product from DOM")
                
                if product:
                    await self.rate_limiter.record_success("nykaa")
                    self.record_success()
                    return product
                
                return None
        
        except Exception as e:
            logger.error(f"❌ Nykaa product error: {e}")
            return None
    
    def _parse_product_detail_json(self, json_data: Dict[str, Any], product_url: str) -> Optional[ProductData]:
        """Parse product from API JSON"""
        try:
            product_data = json_data.get('product') or json_data.get('data') or json_data
            return self._parse_product_item(product_data)
        except:
            return None
    
    def _create_product_from_json_ld(
        self, 
        json_ld: Dict[str, Any], 
        product_url: str,
        product_id: Optional[str]
    ) -> Optional[ProductData]:
        """Create product from JSON-LD"""
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
                platform_name="nykaa",
                image_url=json_ld.get('image'),
                brand=json_ld.get('brand'),
                rating=float(json_ld['rating']) if json_ld.get('rating') else None,
                review_count=int(json_ld['review_count']) if json_ld.get('review_count') else None,
                in_stock=json_ld.get('in_stock', True),
                category="Beauty",
                extraction_method=ExtractionMethod.JSON_LD,
                data_source=HandlerType.SCRAPER
            )
        except:
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
            
            product_data = page_props.get('product') or page_props.get('productDetails') or {}
            
            if product_data:
                product = self._parse_product_item(product_data)
                if product:
                    product.extraction_method = ExtractionMethod.NEXT_DATA
                    return product
        except:
            pass
        return None
    
    async def _extract_product_dom(
        self, 
        page_obj, 
        product_url: str,
        product_id: Optional[str]
    ) -> Optional[ProductData]:
        """Fallback: DOM extraction"""
        try:
            used_ai_healing = False
            product_data = await page_obj.evaluate('''() => {
                const result = { title: null, price: null, image: null };
                
                const h1 = document.querySelector('h1');
                result.title = h1 ? h1.textContent.trim() : document.title.split('|')[0].trim();
                
                const priceMatch = document.body.innerText.match(/₹\\s*([0-9,]+)/);
                if (priceMatch) result.price = priceMatch[1].replace(/,/g, '');
                
                const img = document.querySelector('img[src*="nykaa"], img[class*="product"]');
                if (img) result.image = img.src;
                
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
                    product_data["brand"] = healed.get("brand")
                    product_data["rating"] = healed.get("product_rating")
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
                platform_name="nykaa",
                image_url=product_data.get('image'),
                brand=product_data.get('brand'),
                rating=float(product_data['rating']) if product_data.get('rating') else None,
                review_count=int(str(product_data['reviewCount']).replace(',', '')) if product_data.get('reviewCount') else None,
                category="Beauty",
                in_stock=True,
                extraction_method=ExtractionMethod.AI_HEALED if used_ai_healing else ExtractionMethod.DOM_JAVASCRIPT,
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
            
            match = re.search(r'productId=(\d+)', url)
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
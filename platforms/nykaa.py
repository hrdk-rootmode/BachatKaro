"""
Nykaa.com Scraper - JSON-LD VERSION (Most Reliable)
Extracts hidden SEO data to get product details

Author: DealHunt
"""

import logging
import re
import json
import hashlib
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from app.services.scraper.base import (
    BasePlatformHandler, PlatformConfig, ProductData, SearchResult, HandlerType
)
from app.services.scraper.browser import get_browser_manager, BrowserManager
from app.services.scraper.rate_limiter import RateLimiter, ThreatLevel, RateLimitExceeded
from app.services.scraper.self_healing import SelfHealingEngine
from app.core.config import settings

logger = logging.getLogger(__name__)

class NykaaScraper(BasePlatformHandler):
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
        "support_level": "full"
    }
    
    BASE_URL = "https://www.nykaa.com"
    SEARCH_URL = "https://www.nykaa.com/search/result"
    
    def __init__(self, config: PlatformConfig, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(config)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.healing_engine = SelfHealingEngine(platform_name="nykaa", selectors=config.selectors or {})
        self.browser_manager: Optional[BrowserManager] = None
        self.affiliate_id = config.affiliate_tag or getattr(settings, 'AFFILIATE_NYKAA_ID', 'dealhunt')
        logger.info("NykaaScraper initialized")
    
    @property
    def handler_type(self) -> HandlerType: return HandlerType.SCRAPER
    
    async def _get_browser(self) -> BrowserManager:
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager
    
    async def search(self, query: str, page: int = 1, filters: Optional[Dict[str, Any]] = None) -> SearchResult:
        """Search using text extraction"""
        start_time = datetime.utcnow()
        try:
            await self.rate_limiter.acquire("nykaa")
            search_url = f"{self.SEARCH_URL}?q={query.replace(' ', '%20')}&root=search&page_no={page}"
            browser = await self._get_browser()
            products = []
            
            async with browser.get_page(block_resources=False, stealth=True) as page_obj:
                await page_obj.goto(search_url, wait_until="networkidle", timeout=45000)
                await page_obj.wait_for_timeout(2000)
                
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
                        const priceMatch = text.match(/₹([0-9,]+)/);
                        if (!priceMatch) return;
                        products.push({
                            title: link.textContent.trim() || "Nykaa Product",
                            price: priceMatch[1],
                            url: href
                        });
                    });
                    return products.slice(0, 15);
                }''')
                
                for item in products_data:
                    price = self._clean_price(item.get('price'))
                    if price:
                        products.append(ProductData(
                            external_id=hashlib.md5(item.get('url').encode()).hexdigest()[:16],
                            title=item.get('title'),
                            current_price=price,
                            product_url=f"{self.BASE_URL}{item.get('url')}" if item.get('url').startswith('/') else item.get('url'),
                            platform_name="nykaa",
                            in_stock=True,
                            data_source=HandlerType.SCRAPER
                        ))
            
            await self.rate_limiter.record_success("nykaa")
            self.record_success()
            return SearchResult(query=query, platform_name="nykaa", products=products, success=True, total_results=len(products), search_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000))
        except Exception as e:
            return SearchResult(query=query, platform_name="nykaa", success=False, error_message=str(e))

    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get product using JSON-LD Structured Data"""
        try:
            await self.rate_limiter.acquire("nykaa")
            browser = await self._get_browser()
            
            async with browser.get_page(block_resources=False, stealth=True) as page:
                await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)
                
                # Extract JSON-LD
                data = await page.evaluate('''() => {
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const script of scripts) {
                        try {
                            const json = JSON.parse(script.innerText);
                            if (json['@type'] === 'Product') return json;
                        } catch(e) {}
                    }
                    return null;
                }''')
                
                title, price, image = None, None, None
                
                if data:
                    title = data.get('name')
                    image = data.get('image')
                    if isinstance(image, list): image = image[0]
                    
                    offers = data.get('offers')
                    if offers:
                        if isinstance(offers, list): offers = offers[0]
                        price = offers.get('price')
                
                # Fallback to text
                if not title or not price:
                    fallback = await page.evaluate('''() => {
                        const h1 = document.querySelector('h1');
                        const priceEl = document.body.innerText.match(/₹([0-9,]+)/);
                        return {
                            title: h1 ? h1.innerText : document.title,
                            price: priceEl ? priceEl[1] : null
                        }
                    }''')
                    if not title: title = fallback['title']
                    if not price: price = fallback['price']

                if not title or not price:
                    logger.warning("Nykaa extraction failed")
                    return None

                product_id = self.extract_product_id(product_url)
                current_price = self._clean_price(str(price))
                
                await self.rate_limiter.record_success("nykaa")
                self.record_success()
                
                return ProductData(
                    external_id=product_id or hashlib.md5(product_url.encode()).hexdigest()[:16],
                    title=title.strip(),
                    current_price=current_price,
                    product_url=self.build_affiliate_url(product_url),
                    platform_name="nykaa",
                    image_url=image,
                    in_stock=True,
                    category="Beauty",
                    data_source=HandlerType.SCRAPER
                )
        except Exception as e:
            logger.error(f"Nykaa error: {e}")
            return None

    def extract_product_id(self, url: str) -> Optional[str]:
        try:
            match = re.search(r'/p/(\d+)', url)
            if match: return match.group(1)
        except: pass
        return None

    def build_affiliate_url(self, product_url: str) -> str:
        if not self.affiliate_id: return product_url
        sep = "&" if "?" in product_url else "?"
        return f"{product_url}{sep}utm_source={self.affiliate_id}"
        
    async def close(self) -> None: pass
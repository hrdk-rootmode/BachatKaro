"""
Meesho.com Scraper - MOBILE VERSION
Uses mobile site to avoid blocking

Author: DealHunt
"""

import logging
import re
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
)
from app.services.scraper.browser import get_browser_manager, BrowserManager
from app.services.scraper.rate_limiter import RateLimiter, ThreatLevel, RateLimitExceeded
from app.services.scraper.self_healing import SelfHealingEngine
from app.core.config import settings

logger = logging.getLogger(__name__)


class MeeshoScraper(BasePlatformHandler):
    """Meesho scraper with mobile user agent to avoid blocking"""
    
    PLATFORM_METADATA = {
        "name": "meesho",
        "display_name": "Meesho",
        "base_url": "https://www.meesho.com",
        "domains": ["meesho.com"],
        "categories": ["fashion", "home", "budget"],
        "product_id_patterns": [r"/p/([a-z0-9]+)"],
        "affiliate_param": "utm_source",
        "rate_limit_per_minute": 10,  # Lower rate limit
        "reliability": "low",  # Mark as unreliable
        "support_level": "partial",  # Partial support
        "blocked_reason": "Akamai Bot Manager"  # Document why
    }
    
    BASE_URL = "https://www.meesho.com"
    
    # Mobile user agent (less likely to be blocked)
    MOBILE_USER_AGENT = "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    
    ACCESSORY_KEYWORDS = [
        "cover", "case", "screen guard", "protector", "tempered glass",
        "charger", "cable", "holder", "stand", "skin", "pouch"
    ]
    
    def __init__(self, config: PlatformConfig, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(config)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.healing_engine = SelfHealingEngine(
            platform_name="meesho",
            selectors=config.selectors or {}
        )
        self.browser_manager: Optional[BrowserManager] = None
        self.affiliate_id = config.affiliate_tag or getattr(settings, 'MEESHO_AFFILIATE_ID', 'dealhunt')
        logger.info("MeeshoScraper initialized")
    
    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER
    
    def _is_accessory(self, title: str) -> bool:
        if not title:
            return False
        return any(kw in title.lower() for kw in self.ACCESSORY_KEYWORDS)
    
    async def _get_browser(self) -> BrowserManager:
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager
    
    async def search(self, query: str, page: int = 1, filters: Optional[Dict[str, Any]] = None) -> SearchResult:
        """Search products on Meesho"""
        start_time = datetime.utcnow()
        
        try:
            await self.rate_limiter.acquire("meesho")
            
            search_query = query.replace(" ", "-").lower()
            search_url = f"{self.BASE_URL}/{search_query}"
            if page > 1:
                search_url += f"?page={page}"
            
            browser = await self._get_browser()
            products = []
            
            async with browser.get_page(block_resources=False, stealth=True) as page_obj:
                # Set mobile user agent
                await page_obj.set_extra_http_headers({
                    "User-Agent": self.MOBILE_USER_AGENT,
                    "Accept-Language": "en-IN,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
                })
                
                await page_obj.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await page_obj.wait_for_timeout(3000)
                
                # Check for block
                content = await page_obj.content()
                if "access denied" in content.lower():
                    logger.warning("Meesho access denied on search")
                    return SearchResult(
                        query=query, 
                        platform_name="meesho", 
                        success=False, 
                        error_message="Access blocked"
                    )
                
                # Scroll to load
                for _ in range(3):
                    await page_obj.evaluate('window.scrollBy(0, 600)')
                    await page_obj.wait_for_timeout(800)
                
                # Extract using text-based approach
                products_data = await page_obj.evaluate('''() => {
                    const products = [];
                    const links = document.querySelectorAll('a[href*="/p/"]');
                    const seen = new Set();
                    
                    links.forEach(link => {
                        const href = link.getAttribute('href');
                        if (seen.has(href)) return;
                        seen.add(href);
                        
                        const container = link.closest('div') || link;
                        const text = container.innerText || '';
                        
                        // Find price
                        const priceMatch = text.match(/₹([0-9,]+)/);
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
                            price: priceMatch[1],
                            url: href,
                            image: img ? img.src : null
                        });
                    });
                    
                    return products.slice(0, 20);
                }''')
                
                for item in products_data:
                    try:
                        if self._is_accessory(item.get('title', '')):
                            continue
                        
                        price_str = item.get('price', '').replace(',', '')
                        price = Decimal(price_str) if price_str else None
                        if not price:
                            continue
                        
                        url = item.get('url', '')
                        if url and not url.startswith('http'):
                            url = f"{self.BASE_URL}{url}"
                        
                        product_id = self.extract_product_id(url)
                        
                        products.append(ProductData(
                            external_id=product_id or hashlib.md5(url.encode()).hexdigest()[:16],
                            title=item.get('title', '')[:200],
                            current_price=price,
                            product_url=url,
                            platform_name="meesho",
                            image_url=item.get('image'),
                            in_stock=True,
                            data_source=HandlerType.SCRAPER
                        ))
                    except Exception as e:
                        logger.debug(f"Extract error: {e}")
            
            await self.rate_limiter.record_success("meesho")
            self.record_success()
            
            return SearchResult(
                query=query,
                platform_name="meesho",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 10,
                search_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                success=True
            )
        
        except Exception as e:
            logger.error(f"Meesho search error: {e}")
            return SearchResult(query=query, platform_name="meesho", success=False, error_message=str(e))
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get product with mobile user agent"""
        try:
            await self.rate_limiter.acquire("meesho")
            product_id = self.extract_product_id(product_url)
            
            logger.info(f"Meesho product: {product_id or product_url[:50]}")
            
            browser = await self._get_browser()
            
            async with browser.get_page(block_resources=False, stealth=True) as page:
                # Use mobile user agent to avoid blocking
                await page.set_extra_http_headers({
                    "User-Agent": self.MOBILE_USER_AGENT,
                    "Accept-Language": "en-IN,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache"
                })
                
                # Add random delay to appear more human
                import random
                await page.wait_for_timeout(random.randint(1000, 2000))
                
                await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(4000)
                
                # Check for block
                content = await page.content()
                body_text = await page.evaluate('document.body.innerText')
                
                if "access denied" in content.lower() or "access denied" in body_text.lower():
                    logger.warning("Meesho blocked this request")
                    await self.rate_limiter.record_failure("meesho", ThreatLevel.BLOCKED)
                    return None
                
                # Extract data from page text
                product_data = await page.evaluate('''() => {
                    const result = {
                        title: null,
                        price: null,
                        image: null,
                        rating: null
                    };
                    
                    const bodyText = document.body.innerText;
                    
                    // Extract title - find longest reasonable text
                    const lines = bodyText.split('\\n').filter(l => l.trim());
                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (trimmed.length > 20 && trimmed.length < 250 && 
                            !trimmed.includes('₹') && 
                            !trimmed.includes('Meesho') &&
                            !trimmed.includes('Access') &&
                            !trimmed.includes('http')) {
                            result.title = trimmed;
                            break;
                        }
                    }
                    
                    // Extract price
                    const priceMatches = bodyText.match(/₹\\s*([0-9,]+)/g);
                    if (priceMatches && priceMatches.length > 0) {
                        result.price = priceMatches[0];
                    }
                    
                    // Extract image
                    const imgs = document.querySelectorAll('img[src*="meesho"], img[src*="cdn"]');
                    for (const img of imgs) {
                        if (img.src && img.naturalWidth > 100) {
                            result.image = img.src;
                            break;
                        }
                    }
                    
                    // Extract rating
                    const ratingMatch = bodyText.match(/([1-5]\\.\\d)\\s*(?:★|star|rating)/i);
                    if (ratingMatch) {
                        result.rating = ratingMatch[1];
                    }
                    
                    return result;
                }''')
                
                title = product_data.get('title')
                price_text = product_data.get('price')
                
                if not title or len(title) < 10:
                    logger.warning("Could not extract Meesho title")
                    return None
                
                current_price = self._clean_price(price_text)
                if not current_price:
                    logger.warning("Could not extract Meesho price")
                    return None
                
                rating = None
                if product_data.get('rating'):
                    try:
                        rating = float(product_data.get('rating'))
                    except:
                        pass
                
                await self.rate_limiter.record_success("meesho")
                self.record_success()
                
                return ProductData(
                    external_id=product_id or hashlib.md5(product_url.encode()).hexdigest()[:16],
                    title=title[:200],
                    current_price=current_price,
                    product_url=self.build_affiliate_url(product_url),
                    platform_name="meesho",
                    image_url=product_data.get('image'),
                    rating=rating,
                    in_stock=True,
                    data_source=HandlerType.SCRAPER
                )
        
        except RateLimitExceeded:
            return None
        except Exception as e:
            logger.error(f"Meesho product error: {e}")
            await self.rate_limiter.record_failure("meesho", ThreatLevel.WARNING)
            return None
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        return await self.get_product(f"{self.BASE_URL}/product/{external_id}")
    
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
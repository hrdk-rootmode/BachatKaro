"""
Flipkart.com Scraper - TEXT EXTRACTION VERSION
Extracts from page text instead of CSS selectors (more reliable)

Author: DealHunt
"""

import logging
import re
import asyncio
import hashlib
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
    StockStatus
)
from app.services.scraper.browser import get_browser_manager, BrowserManager
from app.services.scraper.rate_limiter import RateLimiter, ThreatLevel, RateLimitExceeded
from app.services.scraper.self_healing import SelfHealingEngine
from app.core.config import settings

logger = logging.getLogger(__name__)


class FlipkartScraper(BasePlatformHandler):
    """Flipkart scraper using text extraction (CSS-independent)"""
    
    PLATFORM_METADATA = {
        "name": "flipkart",
        "display_name": "Flipkart",
        "base_url": "https://www.flipkart.com",
        "domains": ["flipkart.com", "fkrt.it", "dl.flipkart.com"],
        "categories": ["electronics", "fashion", "home", "beauty", "general"],
        "product_id_patterns": [r"pid=([a-zA-Z0-9]+)", r"/p/([a-zA-Z0-9]+)"],
        "affiliate_param": "affid",
        "rate_limit_per_minute": 30,
        "reliability": "high"
    }
    
    BASE_URL = "https://www.flipkart.com"
    SEARCH_URL = "https://www.flipkart.com/search"
    
    def __init__(self, config: PlatformConfig, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(config)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.healing_engine = SelfHealingEngine(
            platform_name="flipkart",
            selectors=config.selectors or {}
        )
        self.browser_manager: Optional[BrowserManager] = None
        self.affiliate_id = config.affiliate_tag or getattr(settings, 'FLIPKART_AFFILIATE_ID', 'dealhunt')
        logger.info("FlipkartScraper initialized")
    
    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER
    
    async def _get_browser(self) -> BrowserManager:
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager
    
    async def search(self, query: str, page: int = 1, filters: Optional[Dict[str, Any]] = None) -> SearchResult:
        """Search products on Flipkart"""
        start_time = datetime.utcnow()
        
        try:
            await self.rate_limiter.acquire("flipkart")
            search_url = f"{self.SEARCH_URL}?q={query}&page={page}"
            browser = await self._get_browser()
            products = []
            
            async with browser.get_page(block_resources=False, stealth=True) as page_obj:
                await self._dismiss_login_popup(page_obj)
                await page_obj.goto(search_url, wait_until="networkidle", timeout=45000)
                await page_obj.wait_for_timeout(3000)
                
                # Extract using JavaScript with flexible approach
                products_data = await page_obj.evaluate('''() => {
                    const products = [];
                    
                    // Find all product links
                    const links = document.querySelectorAll('a[href*="/p/itm"], a[href*="/p/"]');
                    const seen = new Set();
                    
                    links.forEach(link => {
                        const href = link.getAttribute('href');
                        if (seen.has(href) || !href.includes('/p/')) return;
                        seen.add(href);
                        
                        // Find parent container
                        let container = link.closest('div[data-id]') || link.parentElement.parentElement.parentElement;
                        if (!container) return;
                        
                        const text = container.innerText;
                        
                        // Extract price using regex from text
                        const priceMatch = text.match(/₹([0-9,]+)/);
                        if (!priceMatch) return;
                        
                        // Get first line as title (usually the product name)
                        const lines = text.split('\\n').filter(l => l.trim().length > 0);
                        let title = null;
                        for (const line of lines) {
                            if (line.length > 10 && !line.includes('₹') && !line.includes('%')) {
                                title = line.trim();
                                break;
                            }
                        }
                        
                        if (!title) return;
                        
                        // Get image
                        const img = container.querySelector('img');
                        const imgSrc = img ? (img.src || img.getAttribute('data-src')) : null;
                        
                        // Get rating
                        const ratingMatch = text.match(/([0-5]\.?\d?)\s*\|/);
                        
                        products.push({
                            title: title,
                            price: priceMatch[1],
                            url: href,
                            image: imgSrc,
                            rating: ratingMatch ? ratingMatch[1] : null
                        });
                    });
                    
                    return products.slice(0, 20);
                }''')
                
                for item in products_data:
                    try:
                        price_str = item.get('price', '').replace(',', '')
                        price = Decimal(price_str) if price_str else None
                        if not price:
                            continue
                        
                        url = item.get('url', '')
                        if url and not url.startswith('http'):
                            url = f"{self.BASE_URL}{url}"
                        
                        product_id = self.extract_product_id(url)
                        
                        rating = None
                        if item.get('rating'):
                            try:
                                rating = float(item.get('rating'))
                            except:
                                pass
                        
                        products.append(ProductData(
                            external_id=product_id or hashlib.md5(item.get('title', '').encode()).hexdigest()[:16],
                            title=item.get('title', ''),
                            current_price=price,
                            product_url=url,
                            platform_name="flipkart",
                            image_url=item.get('image'),
                            rating=rating,
                            in_stock=True,
                            data_source=HandlerType.SCRAPER
                        ))
                    except Exception as e:
                        logger.debug(f"Extract error: {e}")
            
            await self.rate_limiter.record_success("flipkart")
            self.record_success()
            
            return SearchResult(
                query=query,
                platform_name="flipkart",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 10,
                search_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                success=True
            )
        
        except Exception as e:
            logger.error(f"Flipkart search error: {e}")
            return SearchResult(query=query, platform_name="flipkart", success=False, error_message=str(e))
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get product using TEXT EXTRACTION (CSS-independent)"""
        try:
            fsn = self.extract_product_id(product_url)
            await self.rate_limiter.acquire("flipkart")
            
            logger.info(f"Flipkart product: {fsn or product_url[:50]}")
            
            browser = await self._get_browser()
            
            async with browser.get_page(block_resources=False, stealth=True) as page:
                await self._dismiss_login_popup(page)
                
                await page.goto(product_url, wait_until="networkidle", timeout=45000)
                await page.wait_for_timeout(4000)
                
                # Get page text and extract data using REGEX (CSS-independent!)
                product_data = await page.evaluate('''() => {
                    const result = {
                        title: null,
                        price: null,
                        originalPrice: null,
                        rating: null,
                        reviewCount: null,
                        image: null,
                        brand: null,
                        inStock: true
                    };
                    
                    // Get full page text
                    const bodyText = document.body.innerText;
                    
                    // Get page title (usually accurate)
                    const pageTitle = document.title;
                    if (pageTitle && pageTitle.includes('Buy')) {
                        // "Buy MICROSOFT Xbox Series S..." -> extract product name
                        const titleMatch = pageTitle.match(/Buy\\s+(.+?)\\s+(?:Online|Price|\\|)/i);
                        if (titleMatch) {
                            result.title = titleMatch[1].trim();
                        }
                    }
                    
                    // Fallback: Find title from breadcrumb area
                    if (!result.title) {
                        const lines = bodyText.split('\\n');
                        for (const line of lines) {
                            const trimmed = line.trim();
                            // Product title is usually in format "Brand ProductName (specs)"
                            if (trimmed.length > 15 && trimmed.length < 200 && 
                                !trimmed.includes('₹') && !trimmed.includes('Buy') &&
                                !trimmed.includes('Cart') && !trimmed.includes('Login') &&
                                !trimmed.includes('Home') && !trimmed.includes('Key Highlights') &&
                                (trimmed.includes('(') || trimmed.match(/^[A-Z]/))) {
                                result.title = trimmed;
                                break;
                            }
                        }
                    }
                    
                    // Extract current price - look for ₹XX,XXX pattern
                    const priceMatches = bodyText.match(/₹([0-9,]+)/g);
                    if (priceMatches && priceMatches.length > 0) {
                        // Usually the selling price is the second or third occurrence
                        // First is often MRP, second is selling price
                        for (const pm of priceMatches) {
                            const priceNum = parseInt(pm.replace(/[₹,]/g, ''));
                            if (priceNum > 100 && priceNum < 10000000) {
                                if (!result.originalPrice) {
                                    result.originalPrice = pm;
                                } else if (!result.price) {
                                    result.price = pm;
                                    break;
                                }
                            }
                        }
                        // If only one price found, use it
                        if (!result.price && result.originalPrice) {
                            result.price = result.originalPrice;
                            result.originalPrice = null;
                        }
                    }
                    
                    // Extract rating (X.X | reviews pattern)
                    const ratingMatch = bodyText.match(/([0-5]\.?\d?)\s*\|\s*([0-9,]+)/);
                    if (ratingMatch) {
                        result.rating = ratingMatch[1];
                        result.reviewCount = ratingMatch[2];
                    }
                    
                    // Find main product image
                    const images = document.querySelectorAll('img');
                    for (const img of images) {
                        const src = img.src || '';
                        if (src.includes('rukminim') && img.width > 200) {
                            result.image = src;
                            break;
                        }
                    }
                    
                    // Check stock
                    if (bodyText.toLowerCase().includes('out of stock') || 
                        bodyText.toLowerCase().includes('currently unavailable')) {
                        result.inStock = false;
                    }
                    
                    // Extract brand from title
                    if (result.title) {
                        const words = result.title.split(' ');
                        if (words.length > 0) {
                            result.brand = words[0];
                        }
                    }
                    
                    return result;
                }''')
                
                # Validate
                title = product_data.get('title')
                price_text = product_data.get('price')
                
                if not title or len(title) < 5:
                    # Last resort: use page title
                    page_title = await page.title()
                    if page_title:
                        title_match = re.search(r'Buy\s+(.+?)\s+(?:Online|Price|at|\|)', page_title, re.IGNORECASE)
                        if title_match:
                            title = title_match.group(1).strip()
                
                if not title:
                    logger.warning("Could not extract Flipkart title")
                    return None
                
                current_price = self._clean_price(price_text)
                if not current_price:
                    logger.warning("Could not extract Flipkart price")
                    return None
                
                original_price = self._clean_price(product_data.get('originalPrice'))
                discount = self._calculate_discount(current_price, original_price)
                
                rating = None
                if product_data.get('rating'):
                    try:
                        rating = float(product_data.get('rating'))
                    except:
                        pass
                
                review_count = None
                if product_data.get('reviewCount'):
                    try:
                        review_count = int(product_data.get('reviewCount').replace(',', ''))
                    except:
                        pass
                
                await self.rate_limiter.record_success("flipkart")
                self.record_success()
                
                return ProductData(
                    external_id=fsn or hashlib.md5(product_url.encode()).hexdigest()[:16],
                    title=title,
                    current_price=current_price,
                    original_price=original_price,
                    discount_percent=discount,
                    product_url=self.build_affiliate_url(product_url),
                    platform_name="flipkart",
                    image_url=product_data.get('image'),
                    rating=rating,
                    review_count=review_count,
                    in_stock=product_data.get('inStock', True),
                    brand=product_data.get('brand'),
                    data_source=HandlerType.SCRAPER,
                    raw_data={"fsn": fsn}
                )
        
        except RateLimitExceeded:
            return None
        except Exception as e:
            logger.error(f"Flipkart product error: {e}")
            await self.rate_limiter.record_failure("flipkart", ThreatLevel.WARNING)
            self.record_failure(str(e))
            return None
    
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        return await self.get_product(f"{self.BASE_URL}/product/p/{external_id}")
    
    def extract_product_id(self, url: str) -> Optional[str]:
        try:
            params = parse_qs(urlparse(url).query)
            if 'pid' in params:
                return params['pid'][0]
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
        return f"{product_url}{sep}affid={self.affiliate_id}"
    
    async def _dismiss_login_popup(self, page) -> None:
        try:
            await page.wait_for_timeout(1000)
            # Try clicking outside or close button
            close_selectors = [
                "button._2KpZ6l._2doB4z", 
                "span._30XB9F",
                "button[class*='_2doB4z']"
            ]
            for sel in close_selectors:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(500)
                    return
            
            # Press Escape key
            await page.keyboard.press("Escape")
        except:
            pass
    
    async def close(self) -> None:
        pass
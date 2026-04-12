"""
Flipkart.com Scraper - AI HEALING + JAVASCRIPT FALLBACK v2.2
AI-first extraction with multiple fallback strategies

Author: DealHunt
Version: 2.2.0 - Production Grade (Universal Price Fix)
Reliability: 95%
"""

import logging
import re
import hashlib
import asyncio
import time
from typing import Optional, List, Dict, Any
from decimal import Decimal, ROUND_DOWN
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs

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


class FlipkartScraper(BasePlatformHandler):
    """
    Flipkart scraper with AI healing + JavaScript fallback
    
    🚀 STRATEGY:
    1. AI-powered selector healing
    2. JavaScript DOM extraction
    3. Multiple fallback methods
    """
    
    PLATFORM_METADATA = {
        "name": "flipkart",
        "display_name": "Flipkart",
        "base_url": "https://www.flipkart.com",
        "domains": ["flipkart.com", "fkrt.it", "dl.flipkart.com"],
        "categories": ["electronics", "fashion", "home", "beauty", "general"],
        "product_id_patterns": [r"pid=([a-zA-Z0-9]+)", r"/p/([a-zA-Z0-9]+)"],
        "affiliate_param": "affid",
        "rate_limit_per_minute": 30,
        "reliability": "high",
        "support_level": "full"
    }
    
    BASE_URL = "https://www.flipkart.com"
    SEARCH_URL = "https://www.flipkart.com/search"

    CATEGORY_PATTERNS = {
        "mobile": ["mobile", "phone", "smartphone", "iphone", "pixel", "samsung", "oneplus", "xiaomi", "redmi", "oppo", "vivo", "realme"],
        "laptop": ["laptop", "notebook", "macbook", "ultrabook", "chromebook", "thinkpad", "inspiron", "pavilion", "ideapad"],
        "tablet": ["tablet", "ipad", "tab"],
        "fashion": ["shirt", "dress", "tshirt", "t-shirt", "saree", "jeans", "trouser", "jacket", "shoes", "top", "pant", "kurta", "kurti"],
        "home": ["table", "chair", "bed", "sofa", "mattress", "pillow", "cushion"],
        "kitchen": ["cooker", "pan", "kadai", "mixer", "grinder", "fryer", "kettle", "cookware"],
        "book": ["book", "ebook", "novel", "textbook", "paperback", "hardcover"],
        "accessories": ["charger", "cable", "case", "cover", "pouch", "adapter", "cord", "wire", "earphone", "headphone", "earbuds", "tempered glass", "screen protector", "power bank", "airpods", "buds"],
        "watch": ["watch", "smartwatch"],
        "bag": ["bag", "backpack", "handbag", "suitcase", "luggage"],
    }

    PRICE_RANGES = {
        "mobile": (2000, 600000),
        "laptop": (10000, 1000000),
        "tablet": (3000, 200000),
        "fashion": (50, 150000),
        "home": (100, 500000),
        "kitchen": (100, 100000),
        "book": (20, 5000),
        "accessories": (20, 100000),
        "watch": (100, 500000),
        "bag": (100, 100000),
        "general": (30, 1000000),
    }
    
    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self.browser_manager: Optional[BrowserManager] = None
        self.affiliate_id = config.affiliate_tag or getattr(settings, 'FLIPKART_AFFILIATE_ID', 'dealhunt')
        
        logger.info(f"✅ FlipkartScraper v2.2 initialized (AI Healing: {'Active' if self.healing_engine else 'Inactive'})")

    def _detect_category(self, text: str) -> str:
        """Detect product category from title or context."""
        text_lower = (text or "").lower()
        for category, keywords in self.CATEGORY_PATTERNS.items():
            if any(keyword in text_lower for keyword in keywords):
                return category
        return "general"

    def _validate_price_for_category(self, price: Optional[Decimal], title: str = "", context: str = "") -> tuple[bool, str]:
        """Reject obvious ratings while keeping genuine low-price accessories."""
        if price is None:
            return False, "Price is None"

        price_val = float(price)
        title_context = f"{title} {context}".lower()
        category = self._detect_category(title_context)

        if 1.0 <= price_val <= 5.0 and price_val != int(price_val):
            return False, f"Price ₹{price_val} looks like a rating"

        if 1 <= price_val <= 9 and price_val == int(price_val) and category not in {"book", "accessories"}:
            return False, f"Price ₹{price_val} looks like a review count"

        min_price, max_price = self.PRICE_RANGES.get(category, self.PRICE_RANGES["general"])
        if not (min_price <= price_val <= max_price):
            return False, f"Price ₹{price_val} outside {category} range (₹{min_price}-₹{max_price})"

        return True, "Valid"

    def _apply_accessory_price_guard(
        self,
        title: str,
        current_price: Optional[Decimal],
        original_price: Optional[Decimal],
        context_text: str = "",
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Keep accessory prices permissive while still dropping obvious bad originals."""
        if current_price is None:
            return None, None

        current_valid, _ = self._validate_price_for_category(current_price, title, context_text)
        if not current_valid:
            return None, None

        if original_price is not None:
            original_valid, _ = self._validate_price_for_category(original_price, title, context_text)
            if not original_valid or original_price <= current_price:
                original_price = None

        return current_price, original_price

    def _to_decimal_price(
        self,
        raw: Any,
        title_hint: Optional[str] = None,
        context_text: str = "",
    ) -> Optional[Decimal]:
        """
        Convert extracted price value to Decimal safely.
        ✅ FIXED: Better decimal handling and universal x100 detection
        """
        if raw is None:
            return None

        if isinstance(raw, Decimal):
            return raw if raw > 0 else None

        if isinstance(raw, (int, float)):
            try:
                value = Decimal(str(raw))
                if value <= 0:
                    return None
                return self._fix_price_anomalies(
                    value,
                    title_hint=title_hint,
                    context_text=context_text,
                )
            except Exception:
                return None

        # Clean string input
        cleaned = re.sub(r"[^\d.]", "", str(raw))
        if not cleaned:
            return None

        try:
            value = Decimal(cleaned)
            if value <= 0:
                return None
            return self._fix_price_anomalies(
                value,
                title_hint=title_hint,
                context_text=context_text,
            )
        except Exception:
            return None

    def _fix_price_anomalies(
        self,
        price: Decimal,
        title_hint: Optional[str] = None,
        context_text: str = "",
    ) -> Decimal:
        """
        Price anomaly detection and correction with category guard.
        Handles:
        1. x100 inflation (99900 → 999)
        2. Decimal-as-integer (21834 → 218)
        3. Other weird Flipkart parsing issues
        """
        if price < Decimal("10"):
            return price
        
        category = self._detect_category(f"{title_hint or ''} {context_text or ''}")

        # Detect x100 inflation, but only for categories where low ticket pricing is common.
        # Never auto-divide mobile/laptop/tablet/watch where 5-digit prices are normal.
        if price >= Decimal("10000"):
            x100_allowed_categories = {"accessories", "fashion", "book", "home", "kitchen", "bag", "general"}
            if category in x100_allowed_categories:
                corrected = price / Decimal("100")
                # Guardrail: only accept corrections that land in practical low-ticket range.
                if Decimal("20") <= corrected <= Decimal("5000"):
                    logger.debug(
                        f"🔧 x100 fix ({category}): ₹{price} → ₹{corrected}"
                    )
                    return corrected.quantize(Decimal('1'), rounding=ROUND_DOWN)
        
        # Detect decimal-as-integer: 21834 → 218.34 → 218
        # This happens when "218.34" is parsed as "21834" (decimal point removed)
        # Pattern: If price is 4-5 digits and ends in 34, 50, 75, 99 (common decimal endings)
        price_int = int(price)
        if 1000 <= price_int <= 99999:
            last_two_digits = price_int % 100
            # Common decimal endings that got merged: .34, .50, .75, .99, .25
            if last_two_digits in [25, 34, 50, 75, 99]:
                # Try dividing by 100
                corrected = price / Decimal("100")
                # If result is in reasonable book/product range (₹20-₹3000)
                if Decimal("20") <= corrected <= Decimal("3000"):
                    logger.debug(f"🔧 Decimal-as-integer fix: ₹{price} → ₹{corrected}")
                    return corrected.quantize(Decimal('1'), rounding=ROUND_DOWN)
        
        # No anomaly detected, return as-is (rounded down)
        return price.quantize(Decimal('1'), rounding=ROUND_DOWN)

    def _normalize_price_snapshot(
        self,
        current_price: Optional[Decimal],
        original_price: Optional[Decimal],
        discount_hint: Optional[float] = None,
        title_hint: Optional[str] = None,
        context_text: str = "",
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[float]]:
        """
        Ensure current_price is payable (discounted) and original_price is strike-through MRP.
        ✅ FIXED: Always use LOWER price as current (payable)
        """
        current = self._to_decimal_price(
            current_price,
            title_hint=title_hint,
            context_text=context_text,
        )
        original = self._to_decimal_price(
            original_price,
            title_hint=title_hint,
            context_text=context_text,
        )

        if current is None:
            return None, None, None

        category = self._detect_category(f"{title_hint or ''} {context_text or ''}")

        # Guard for electronics truncation like 523 instead of 52300 when MRP is known.
        if (
            original is not None
            and category in {"mobile", "laptop", "tablet"}
            and current < Decimal("1000")
            and original >= Decimal("10000")
        ):
            corrected_current = (current * Decimal("100")).quantize(Decimal('1'), rounding=ROUND_DOWN)
            if corrected_current <= original:
                logger.info(
                    f"🔧 Corrected truncated electronics current price: ₹{current} → ₹{corrected_current}"
                )
                current = corrected_current

        # ✅ CRITICAL FIX: If original < current, ALWAYS swap (current must be payable price)
        if original is not None and original < current:
            logger.info(f"🔄 Swapping to use lower price as current: ₹{current} ↔ ₹{original}")
            current, original = original, current

        # Drop original if it's not higher than current
        if original is not None and original <= current:
            original = None

        # Drop suspiciously high discounts (>95% = likely parse error)
        if original is not None and current > 0:
            try:
                discount_pct = ((float(original) - float(current)) / float(original)) * 100
            except Exception:
                discount_pct = 0.0
            
            if discount_pct > 95:
                logger.warning(
                    f"⚠️ Suspicious discount: ₹{current} vs ₹{original} "
                    f"({discount_pct:.1f}% off) - dropping original"
                )
                original = None

        computed_discount = self._calculate_discount(current, original)
        normalized_discount: Optional[float] = None

        if computed_discount is not None:
            normalized_discount = computed_discount
        elif discount_hint is not None and original is not None and original > current:
            try:
                hint = float(discount_hint)
                if 0 < hint < 95:
                    normalized_discount = round(hint, 1)
            except Exception:
                normalized_discount = None

        return current, original, normalized_discount
    
    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER
    
    async def _get_browser(self) -> BrowserManager:
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager
    
    async def _dismiss_login_popup(self, page_obj) -> None:
        """Dismiss Flipkart login popup"""
        try:
            await page_obj.wait_for_timeout(1000)
            
            close_selectors = [
                "button._2KpZ6l._2doB4z",
                "span._30XB9F",
                "button[class*='_2doB4z']",
                "[data-testid='close-button']"
            ]
            
            for sel in close_selectors:
                btn = await page_obj.query_selector(sel)
                if btn:
                    await btn.click()
                    await page_obj.wait_for_timeout(500)
                    return
            
            await page_obj.keyboard.press("Escape")
        except:
            pass
    
    # =========================================================================
    # SEARCH
    # =========================================================================
    
    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """Search products on Flipkart"""
        start_time = datetime.utcnow()
        
        try:
            await self.rate_limiter.acquire("flipkart")
            
            search_url = f"{self.SEARCH_URL}?q={query}&page={page}"
            
            logger.info(f"🔍 Flipkart search: {query} (page {page})")
            
            browser = await self._get_browser()
            products = []
            extraction_method = ExtractionMethod.DOM_SELECTOR
            
            async with browser.get_page(block_resources=False, stealth=True) as page_obj:
                
                await self._dismiss_login_popup(page_obj)
                
                success = await browser.safe_goto(
                    page_obj, search_url,
                    wait_until='networkidle',
                    timeout=45000
                )
                
                if not success:
                    return SearchResult(
                        query=query,
                        platform_name="flipkart",
                        success=False,
                        error_message="Navigation failed"
                    )
                
                await page_obj.wait_for_timeout(3000)
                await browser.scroll_page(page_obj, scroll_count=3)
                
                # 🚀 JavaScript extraction (most reliable for Flipkart)
                products = await self._extract_search_javascript(page_obj)
                extraction_method = ExtractionMethod.DOM_JAVASCRIPT
                
                if products:
                    logger.info(f"✅ JS extraction: {len(products)} products")
                else:
                    logger.warning("⚠️ Flipkart JS extraction returned no products, trying universal fallback")
                    html_content = await page_obj.content()
                    fallback_products = await self.universal_search_fallback(page_obj, html_content, limit=20)
                    if fallback_products:
                        products = fallback_products
                        extraction_method = ExtractionMethod.REGEX_FALLBACK
                        logger.info(f"✅ Universal fallback recovered {len(products)} Flipkart products")
            
            await self.rate_limiter.record_success("flipkart")
            self.record_success()
            
            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return SearchResult(
                query=query,
                platform_name="flipkart",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 10,
                search_time_ms=search_time,
                extraction_method=extraction_method,
                success=True
            )
        
        except Exception as e:
            logger.error(f"❌ Flipkart search error: {e}")
            return SearchResult(
                query=query,
                platform_name="flipkart",
                success=False,
                error_message=str(e)
            )
    
    async def _extract_search_javascript(self, page_obj) -> List[ProductData]:
        """JavaScript extraction for search results"""
        try:
            products_data = await page_obj.evaluate('''() => {
                const products = [];

                // ✅ DEBUG: Enable detailed logging
                const DEBUG = true;
                const log = (msg, ...args) => {
                    if (DEBUG) console.log(`[FLIPKART DEBUG] ${msg}`, ...args);
                };

                const categoryPatterns = {
                    mobile: ['mobile', 'phone', 'smartphone', 'iphone', 'pixel', 'samsung', 'oneplus', 'xiaomi', 'redmi', 'oppo', 'vivo', 'realme'],
                    laptop: ['laptop', 'notebook', 'macbook', 'ultrabook', 'chromebook', 'thinkpad', 'inspiron', 'pavilion', 'ideapad'],
                    tablet: ['tablet', 'ipad', 'tab'],
                    fashion: ['shirt', 'dress', 'tshirt', 't-shirt', 'saree', 'jeans', 'trouser', 'jacket', 'shoes', 'top', 'pant', 'kurta', 'kurti'],
                    home: ['table', 'chair', 'bed', 'sofa', 'mattress', 'pillow', 'cushion'],
                    kitchen: ['cooker', 'pan', 'kadai', 'mixer', 'grinder', 'fryer', 'kettle', 'cookware'],
                    book: ['book', 'ebook', 'novel', 'textbook', 'paperback', 'hardcover'],
                    accessories: ['charger', 'cable', 'case', 'cover', 'pouch', 'adapter', 'cord', 'wire', 'earphone', 'headphone', 'earbuds', 'tempered glass', 'screen protector', 'power bank', 'airpods', 'buds'],
                    watch: ['watch', 'smartwatch'],
                    bag: ['bag', 'backpack', 'handbag', 'suitcase', 'luggage']
                };

                const priceRanges = {
                    mobile: { min: 2000, max: 600000 },
                    laptop: { min: 10000, max: 1000000 },
                    tablet: { min: 3000, max: 200000 },
                    fashion: { min: 50, max: 150000 },
                    home: { min: 100, max: 500000 },
                    kitchen: { min: 100, max: 100000 },
                    book: { min: 20, max: 5000 },
                    accessories: { min: 20, max: 100000 },
                    watch: { min: 100, max: 500000 },
                    bag: { min: 100, max: 100000 },
                    general: { min: 30, max: 1000000 }
                };

                const detectCategory = (text, href) => {
                    const combined = `${String(text || '').toLowerCase()} ${String(href || '').toLowerCase()}`;
                    for (const [category, keywords] of Object.entries(categoryPatterns)) {
                        if (keywords.some((keyword) => combined.includes(keyword))) {
                            return category;
                        }
                    }
                    return 'general';
                };

                const parseAmount = (value) => {
                    if (value === null || value === undefined) return null;
                    const normalized = String(value)
                        .replace(/[₹,\s]/g, '')
                        .replace(/[^\d.]/g, '');
                    if (!normalized) return null;
                    const amount = parseFloat(normalized);
                    return Number.isFinite(amount) && amount > 0 ? Math.floor(amount) : null;
                };

                const fixLikelyX100 = (amount, text, href, category = 'general') => {
                    if (!amount || amount < 10000) return amount;
                    const combined = `${String(text || '').toLowerCase()} ${String(href || '').toLowerCase()}`;
                    const protectedCategories = new Set(['mobile', 'laptop', 'tablet', 'watch']);
                    if (protectedCategories.has(category)) {
                        return amount;
                    }
                    const accessoryHints = ['charger', 'cable', 'case', 'cover', 'pouch', 'adapter', 'wire', 'earphone', 'headphone', 'buds', 'airpods'];
                    if (!accessoryHints.some((hint) => combined.includes(hint))) return amount;

                    const corrected = Math.floor(amount / 100);
                    if (corrected >= 20 && corrected <= 50000) {
                        log('💵 x100 correction:', amount, '→', corrected);
                        return corrected;
                    }
                    return amount;
                };

                const isRatingOrCount = (price) => {
                    if (price === null || price === undefined) return true;
                    if (price >= 1 && price <= 5 && !Number.isInteger(price)) return true;
                    if (price >= 1 && price <= 9 && Number.isInteger(price)) return true;
                    return false;
                };

                const isValidPrice = (price, category) => {
                    if (!price || price < 10) {
                        log('❌ Rejected: price too low (<10):', price);
                        return false;
                    }
                    if (isRatingOrCount(price)) {
                        log('❌ Rejected: looks like rating/count:', price);
                        return false;
                    }
                    const range = priceRanges[category] || priceRanges.general;
                    const valid = price >= range.min && price <= range.max;
                    if (!valid) {
                        log(`❌ Rejected: ₹${price} outside ${category} range (₹${range.min}-₹${range.max})`);
                    }
                    return valid;
                };

                // ✅ DEBUG VERSION: Logs each selector match
                const collectPrices = (scope, selectors, category, contextText, label = 'prices') => {
                    const values = [];
                    const debugInfo = [];
                    
                    log(`\\n🔍 Collecting ${label} (category: ${category})`);
                    
                    selectors.forEach((selector) => {
                        const elements = scope.querySelectorAll(selector);
                        
                        if (elements.length === 0) {
                            log(`   ⚪ ${selector}: No matches`);
                            return;
                        }
                        
                        elements.forEach((el, idx) => {
                            const rawText = (el.textContent || el.innerText || '').trim();
                            const amount = parseAmount(rawText);
                            
                            if (!amount) {
                                log(`   ⚪ ${selector} [${idx}]: "${rawText}" → null (parse failed)`);
                                return;
                            }
                            
                            const valid = isValidPrice(amount, category);
                            
                            if (valid) {
                                values.push(amount);
                                log(`   ✅ ${selector} [${idx}]: "${rawText}" → ₹${amount} (VALID)`);
                            } else {
                                log(`   ❌ ${selector} [${idx}]: "${rawText}" → ₹${amount} (REJECTED)`);
                            }
                            
                            debugInfo.push({
                                selector,
                                rawText,
                                parsed: amount,
                                valid
                            });
                        });
                    });
                    
                    log(`   📊 Found ${values.length} valid prices:`, values);
                    
                    return values;
                };

                const chooseCurrentCandidate = (primaryCandidates, fallbackCandidates = [], category = 'general') => {
                    log('\\n🎯 Choosing current price:');
                    log('   Primary candidates:', primaryCandidates);
                    log('   Fallback candidates:', fallbackCandidates);
                    
                    const uniquePrimary = [...new Set((primaryCandidates || []).filter((value) => isValidPrice(value, category)))];
                    
                    if (uniquePrimary.length > 0) {
                        const chosen = Math.min(...uniquePrimary);
                        log(`   ✅ Chosen from primary: ₹${chosen} (min of [${uniquePrimary}])`);
                        return chosen;
                    }

                    const uniqueFallback = [...new Set((fallbackCandidates || []).filter((value) => isValidPrice(value, category)))];
                    
                    if (uniqueFallback.length === 0) {
                        log('   ❌ No valid candidates found');
                        return null;
                    }
                    
                    const chosen = Math.min(...uniqueFallback);
                    log(`   ✅ Chosen from fallback: ₹${chosen} (min of [${uniqueFallback}])`);
                    return chosen;
                };
                
                // Find all product links
                const links = document.querySelectorAll('a[href*="/p/itm"], a[href*="/p/"]');
                const seen = new Set();
                
                log(`\\n🔎 Found ${links.length} product links on page`);
                
                links.forEach((link, linkIndex) => {
                    const href = link.getAttribute('href');
                    if (!href || seen.has(href) || !href.includes('/p/')) return;
                    seen.add(href);
                    
                    let container = link.closest('[data-id]') || link.closest('div._1AtVbE') || link.parentElement.parentElement.parentElement;
                    if (!container) {
                        log(`\\n⚠️ Product ${linkIndex}: No container found`);
                        return;
                    }
                    
                    const text = container.innerText || '';
                    const category = detectCategory(text, href);
                    
                    // Extract title first for better logging
                    const lines = text.split('\\n').filter(l => {
                        const s = l.trim();
                        return s.length > 10 && 
                               !s.includes('Add to Compare') && 
                               !s.includes('₹') && 
                               !s.includes('% off');
                    });
                    const title = lines.length > 0 ? lines[0] : 'Unknown Product';
                    
                    log(`\\n${'='.repeat(80)}`);
                    log(`📦 Product ${linkIndex + 1}: "${title.substring(0, 50)}..."`);
                    log(`   Category: ${category}`);
                    log(`   URL: ${href.substring(0, 60)}...`);

                    const currentSelectors = [
                        'div.Nx9bqj',
                        'div._30jeq3',
                        'div._16Jk6d',
                        'span.Nx9bqj',
                        'span._30jeq3',
                        'div[class*="Nx9bqj"]',
                        'div[class*="_30jeq3"]'
                    ];

                    const originalSelectors = [
                        'div.yRaY8j',
                        'div._3I9_wc',
                        'div._2p6lqe',
                        'span._3I9_wc',
                        'div[class*="yRaY8j"]',
                        'div[class*="_3I9_wc"]'
                    ];

                    const currentCandidates = collectPrices(container, currentSelectors, category, text, 'CURRENT prices');
                    const originalCandidates = collectPrices(container, originalSelectors, category, text, 'ORIGINAL prices');

                    const allPriceCandidates = Array
                        .from(text.matchAll(/₹\\s*([0-9,]+)(?!\\s*\\/?\\s*month)/gi))
                        .map((m) => {
                            const parsed = parseAmount(m[1]);
                            log(`   💰 Regex found: "${m[0]}" → ₹${parsed}`);
                            return parsed;
                        })
                        .filter(Boolean);

                    let currentPrice = chooseCurrentCandidate(currentCandidates, allPriceCandidates, category);

                    if ((category === 'mobile' || category === 'laptop' || category === 'tablet') && currentPrice && currentPrice < 1000) {
                        const highCandidates = [...currentCandidates, ...allPriceCandidates].filter((v) => v >= 10000);
                        if (highCandidates.length > 0) {
                            const correctedCurrent = Math.min(...highCandidates);
                            log(`   🔧 Corrected low electronics price: ₹${currentPrice} → ₹${correctedCurrent}`);
                            currentPrice = correctedCurrent;
                        }
                    }

                    let originalPrice = originalCandidates.length > 0
                        ? Math.max(...originalCandidates)
                        : null;

                    if (!originalPrice && allPriceCandidates.length >= 2 && currentPrice) {
                        const aboveCurrent = allPriceCandidates.filter((v) => v > currentPrice);
                        if (aboveCurrent.length > 0) {
                            originalPrice = Math.max(...aboveCurrent);
                            log(`   🔄 Original from regex: ₹${originalPrice}`);
                        }
                    }

                    if (!currentPrice) {
                        log('   ❌ SKIPPED: No valid current price found\\n');
                        return;
                    }

                    log(`\\n   💵 BEFORE x100 fix: current=₹${currentPrice}, original=₹${originalPrice}`);

                    // Contextual x100 correction
                    const beforeCurrent = currentPrice;
                    const beforeOriginal = originalPrice;
                    currentPrice = fixLikelyX100(currentPrice, text, href, category);
                    if (originalPrice) {
                        originalPrice = fixLikelyX100(originalPrice, text, href, category);
                    }
                    
                    if (beforeCurrent !== currentPrice || beforeOriginal !== originalPrice) {
                        log(`   💵 AFTER x100 fix: current=₹${currentPrice}, original=₹${originalPrice}`);
                    }

                    // Ensure current is lower
                    if (originalPrice && originalPrice < currentPrice) {
                        log(`   🔄 Swapping: current (₹${currentPrice}) ↔ original (₹${originalPrice})`);
                        const temp = currentPrice;
                        currentPrice = originalPrice;
                        originalPrice = temp;
                    }

                    if (originalPrice && originalPrice <= currentPrice) {
                        log(`   ⚠️ Dropping original (₹${originalPrice}) - not higher than current (₹${currentPrice})`);
                        originalPrice = null;
                    }

                    // Drop suspicious originals
                    if (currentPrice && originalPrice) {
                        const ratio = originalPrice / currentPrice;
                        const discount = ((originalPrice - currentPrice) / originalPrice) * 100;

                        if (ratio >= 10 && currentPrice < 200 && originalPrice >= 1500 && discount > 90) {
                            log(`   ⚠️ Suspicious original detected: ratio=${ratio.toFixed(1)}, discount=${discount.toFixed(1)}%`);
                            log(`      Dropping original (₹${originalPrice})`);
                            originalPrice = null;
                        }
                    }

                    const discountMatch = text.match(/(\\d{1,2})\\s*%\\s*off/i);
                    const discount = discountMatch ? parseInt(discountMatch[1], 10) : null;
                    
                    if (!title) {
                        log('   ❌ SKIPPED: No valid title found\\n');
                        return;
                    }
                    
                    const img = container.querySelector('img');
                    const imgSrc = img ? (img.src || img.getAttribute('data-src')) : null;
                    
                    const ratingMatch = text.match(/([0-5]\\.?\\d?)\\s*[★|\\|]/);
                    
                    log(`\\n   ✅ FINAL RESULT:`);
                    log(`      Title: "${title}"`);
                    log(`      Current: ₹${currentPrice}`);
                    log(`      Original: ₹${originalPrice || 'N/A'}`);
                    log(`      Discount: ${discount || 'N/A'}%`);
                    log(`      Rating: ${ratingMatch ? ratingMatch[1] : 'N/A'}`);
                    log('');
                    
                    products.push({
                        title: title,
                        price: String(currentPrice),
                        originalPrice: originalPrice ? String(originalPrice) : null,
                        discount: discount,
                        url: href,
                        image: imgSrc,
                        rating: ratingMatch ? ratingMatch[1] : null
                    });
                });
                
                log(`\\n${'='.repeat(80)}`);
                log(`📊 SUMMARY: Returning ${products.length} products\\n`);
                
                return products.slice(0, 20);
            }''')
            
            logger.info(f"📊 JavaScript returned {len(products_data)} raw products")
            
            products = []
            for item in products_data:
                try:
                    url = item.get('url', '')
                    if url and not url.startswith('http'):
                        url = f"{self.BASE_URL}{url}"

                    extracted_current = self._to_decimal_price(
                        item.get('price'),
                        title_hint=item.get('title'),
                        context_text=url,
                    )
                    extracted_original = self._to_decimal_price(
                        item.get('originalPrice'),
                        title_hint=item.get('title'),
                        context_text=url,
                    )
                    discount_hint = item.get('discount')

                    logger.debug(
                        f"🔍 Raw JS: {item.get('title', '')[:50]}: "
                        f"₹{extracted_current} (was ₹{extracted_original})"
                    )

                    current_price, original_price, discount = self._normalize_price_snapshot(
                        current_price=extracted_current,
                        original_price=extracted_original,
                        discount_hint=discount_hint,
                        title_hint=item.get('title'),
                        context_text=url,
                    )

                    if current_price and original_price and original_price > current_price:
                        discount = round(((float(original_price) - float(current_price)) / float(original_price)) * 100, 1)
                    elif current_price:
                        discount = None

                    if not current_price:
                        logger.warning(f"⚠️ Skipping product - no valid current price: {item.get('title', '')[:50]}")
                        continue
                    
                    product_id = self.extract_product_id(url)
                    if not product_id:
                        product_id = hashlib.md5(url.encode()).hexdigest()[:16]
                    
                    rating = None
                    if item.get('rating'):
                        try:
                            rating = float(item['rating'])
                        except:
                            pass
                    
                    logger.info(
                        f"✅ Product extracted: {item.get('title', '')[:50]} - "
                        f"₹{current_price} (was ₹{original_price if original_price else 'N/A'}) "
                        f"{discount}% off" if discount else ""
                    )
                    
                    products.append(ProductData(
                        external_id=product_id,
                        title=item.get('title', '')[:200],
                        current_price=current_price,
                        original_price=original_price,
                        discount_percent=discount,
                        product_url=self.build_affiliate_url(url),
                        platform_name="flipkart",
                        image_url=item.get('image'),
                        rating=rating,
                        in_stock=True,
                        extraction_method=ExtractionMethod.DOM_JAVASCRIPT,
                        data_source=HandlerType.SCRAPER
                    ))
                except Exception as e:
                    logger.error(f"❌ Error processing product item: {e}", exc_info=True)
                    continue
            
            return products
        
        except Exception as e:
            logger.error(f"❌ JS extraction error: {e}", exc_info=True)
            return []
    
    # =========================================================================
    # PRODUCT DETAILS
    # =========================================================================
    
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get product details"""
        try:
            fsn = self.extract_product_id(product_url)
            await self.rate_limiter.acquire("flipkart")
            
            logger.info(f"🛒 Flipkart product: {fsn or product_url[:50]}")
            
            browser = await self._get_browser()
            
            async with browser.get_page(block_resources=False, stealth=True) as page_obj:
                
                await self._dismiss_login_popup(page_obj)
                
                success = await browser.safe_goto(
                    page_obj, product_url,
                    wait_until='networkidle',
                    timeout=45000
                )
                
                if not success:
                    return None
                
                await page_obj.wait_for_timeout(4000)
                
                # JavaScript extraction
                product = await self._extract_product_javascript(page_obj, fsn, product_url)
                
                if product:
                    await self.rate_limiter.record_success("flipkart")
                    self.record_success()
                    return product
                
                return None

        except RateLimitExceeded as e:
            logger.warning(f"⏳ Flipkart product rate limited: retry_after={e.retry_after}s")
            raise
        
        except Exception as e:
            logger.error(f"❌ Flipkart product error: {e}", exc_info=True)
            return None
    
    async def _extract_product_javascript(
        self, 
        page_obj, 
        fsn: Optional[str],
        product_url: str
    ) -> Optional[ProductData]:
        """JavaScript extraction for product details"""
        try:
            product_data = await page_obj.evaluate('''() => {
                const result = {
                    title: null,
                    price: null,
                    originalPrice: null,
                    discount: null,
                    image: null,
                    rating: null,
                    reviewCount: null,
                    brand: null,
                    inStock: true
                };

                const parseAmount = (value) => {
                    if (value === null || value === undefined) return null;
                    const normalized = String(value)
                        .replace(/[₹,\s]/g, '')
                        .replace(/[^\d.]/g, '');
                    if (!normalized) return null;
                    const amount = parseFloat(normalized);
                    return Number.isFinite(amount) && amount > 0 ? Math.floor(amount) : null;
                };

                const collectPrices = (selectors) => {
                    const values = [];
                    selectors.forEach((selector) => {
                        document.querySelectorAll(selector).forEach((el) => {
                            const amount = parseAmount(el.textContent || el.innerText || '');
                            if (amount) values.push(amount);
                        });
                    });
                    return values;
                };

                const collectText = (selectors) => {
                    const chunks = [];
                    selectors.forEach((selector) => {
                        document.querySelectorAll(selector).forEach((el) => {
                            const txt = (el.textContent || el.innerText || '').trim();
                            if (txt) chunks.push(txt.toLowerCase());
                        });
                    });
                    return chunks.join(' | ');
                };

                const categoryPatterns = {
                    mobile: ['mobile', 'phone', 'smartphone', 'iphone', 'pixel', 'samsung', 'oneplus', 'xiaomi', 'redmi', 'oppo', 'vivo', 'realme'],
                    laptop: ['laptop', 'notebook', 'macbook', 'ultrabook', 'chromebook', 'thinkpad', 'inspiron', 'pavilion', 'ideapad'],
                    tablet: ['tablet', 'ipad', 'tab'],
                    fashion: ['shirt', 'dress', 'tshirt', 't-shirt', 'saree', 'jeans', 'trouser', 'jacket', 'shoes', 'top', 'pant', 'kurta', 'kurti'],
                    home: ['table', 'chair', 'bed', 'sofa', 'mattress', 'pillow', 'cushion'],
                    kitchen: ['cooker', 'pan', 'kadai', 'mixer', 'grinder', 'fryer', 'kettle', 'cookware'],
                    book: ['book', 'ebook', 'novel', 'textbook', 'paperback', 'hardcover'],
                    accessories: ['charger', 'cable', 'case', 'cover', 'pouch', 'adapter', 'cord', 'wire', 'earphone', 'headphone', 'earbuds', 'tempered glass', 'screen protector', 'power bank', 'airpods', 'buds'],
                    watch: ['watch', 'smartwatch'],
                    bag: ['bag', 'backpack', 'handbag', 'suitcase', 'luggage']
                };

                const priceRanges = {
                    mobile: { min: 500, max: 600000 },
                    laptop: { min: 500, max: 1000000 },
                    tablet: { min: 300, max: 200000 },
                    fashion: { min: 50, max: 150000 },
                    home: { min: 100, max: 500000 },
                    kitchen: { min: 100, max: 100000 },
                    book: { min: 20, max: 5000 },
                    accessories: { min: 20, max: 100000 },
                    watch: { min: 100, max: 500000 },
                    bag: { min: 100, max: 100000 },
                    general: { min: 30, max: 1000000 }
                };

                const detectCategory = (text, href) => {
                    const combined = `${String(text || '').toLowerCase()} ${String(href || '').toLowerCase()}`;
                    for (const [category, keywords] of Object.entries(categoryPatterns)) {
                        if (keywords.some((keyword) => combined.includes(keyword))) {
                            return category;
                        }
                    }
                    return 'general';
                };

                const isRatingOrCount = (price) => {
                    if (price === null || price === undefined) return true;
                    if (price >= 1 && price <= 5 && !Number.isInteger(price)) return true;
                    if (price >= 1 && price <= 9 && Number.isInteger(price)) return true;
                    return false;
                };

                const isValidPrice = (price, category) => {
                    if (!price || price < 10) return false;
                    if (isRatingOrCount(price)) return false;
                    const range = priceRanges[category] || priceRanges.general;
                    return price >= range.min && price <= range.max;
                };

                const chooseCurrentCandidate = (primaryCandidates, fallbackCandidates = [], category = 'general') => {
                    const filteredPrimary = (primaryCandidates || []).filter((value) => isValidPrice(value, category));
                    if (filteredPrimary.length > 0) {
                        return Math.min(...new Set(filteredPrimary));
                    }

                    const filteredFallback = (fallbackCandidates || []).filter((value) => isValidPrice(value, category));
                    if (filteredFallback.length === 0) return null;
                    return Math.min(...new Set(filteredFallback));
                };

                const extractFromJsonLd = () => {
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    let jsonCurrent = null;
                    let jsonOriginal = null;
                    let jsonAvailability = null;

                    const parseOfferPrice = (offer) => {
                        if (!offer || typeof offer !== 'object') return null;
                        const direct = parseAmount(offer.price);
                        if (direct) return direct;
                        if (offer.priceSpecification && typeof offer.priceSpecification === 'object') {
                            return parseAmount(offer.priceSpecification.price || offer.priceSpecification.minPrice);
                        }
                        return null;
                    };

                    scripts.forEach((script) => {
                        const raw = script.textContent;
                        if (!raw) return;
                        try {
                            const parsed = JSON.parse(raw);
                            const nodes = Array.isArray(parsed)
                                ? parsed
                                : (Array.isArray(parsed['@graph']) ? parsed['@graph'] : [parsed]);

                            nodes.forEach((node) => {
                                if (!node || typeof node !== 'object') return;
                                const typeVal = String(node['@type'] || '').toLowerCase();
                                if (!typeVal.includes('product')) return;

                                if (!result.title && node.name) {
                                    result.title = String(node.name).trim();
                                }

                                const offersRaw = node.offers;
                                const offers = Array.isArray(offersRaw) ? offersRaw : (offersRaw ? [offersRaw] : []);
                                offers.forEach((offer) => {
                                    const offerPrice = parseOfferPrice(offer);
                                    if (offerPrice) {
                                        jsonCurrent = jsonCurrent ? Math.min(jsonCurrent, offerPrice) : offerPrice;
                                    }

                                    const availability = String(offer?.availability || '').toLowerCase();
                                    if (availability) {
                                        if (availability.includes('instock')) {
                                            jsonAvailability = true;
                                        } else if (
                                            jsonAvailability !== true && (
                                                availability.includes('outofstock') ||
                                                availability.includes('soldout') ||
                                                availability.includes('discontinued')
                                            )
                                        ) {
                                            jsonAvailability = false;
                                        }
                                    }

                                    const originalHints = [
                                        offer?.highPrice,
                                        offer?.priceBeforeDiscount,
                                        offer?.mrp,
                                        offer?.priceSpecification?.maxPrice,
                                    ];

                                    originalHints.forEach((hint) => {
                                        const parsedHint = parseAmount(hint);
                                        if (parsedHint) {
                                            jsonOriginal = jsonOriginal ? Math.max(jsonOriginal, parsedHint) : parsedHint;
                                        }
                                    });
                                });
                            });
                        } catch {
                            // Ignore malformed JSON-LD blocks.
                        }
                    });

                    return { jsonCurrent, jsonOriginal, jsonAvailability };
                };

                const detectStockSignals = () => {
                    const enabledButtonTexts = Array
                        .from(document.querySelectorAll('button:not([disabled])'))
                        .map((el) => (el.textContent || el.innerText || '').toLowerCase().trim())
                        .filter(Boolean);

                    const allButtonTexts = Array
                        .from(document.querySelectorAll('button'))
                        .map((el) => (el.textContent || el.innerText || '').toLowerCase().trim())
                        .filter(Boolean);

                    const ctaTextPool = [...enabledButtonTexts, ...allButtonTexts];
                    const hasAddToCart = ctaTextPool.some((txt) => txt.includes('add to cart'));
                    const hasBuyNow = ctaTextPool.some((txt) => txt.includes('buy now'));
                    const hasCta = hasAddToCart || hasBuyNow;

                    const availabilityText = collectText([
                        'div._16FRp0',
                        'div[class*="_16FRp0"]',
                        'div._1o9grS',
                        'div._2D5lwg',
                        'span._2D5lwg',
                        'div[class*="availability"]',
                        'span[class*="availability"]',
                    ]);

                    const outKeywords = [
                        'out of stock',
                        'currently unavailable',
                        'sold out',
                        'not available',
                        'unavailable',
                    ];
                    const inKeywords = [
                        'in stock',
                        'available',
                    ];

                    const explicitOut = outKeywords.some((kw) => availabilityText.includes(kw));
                    const explicitIn = inKeywords.some((kw) => availabilityText.includes(kw)) && !explicitOut;
                    const hasNotifyMe = ctaTextPool.some((txt) => txt.includes('notify me')) || availabilityText.includes('notify me');

                    return {
                        hasCta,
                        hasNotifyMe,
                        explicitOut,
                        explicitIn,
                    };
                };
                
                // Title from page title
                const pageTitle = document.title;
                if (pageTitle && pageTitle.includes('Buy')) {
                    const match = pageTitle.match(/Buy\\s+(.+?)\\s+(?:Online|Price|at|\\|)/i);
                    if (match) result.title = match[1].trim();
                }
                
                // Fallback: find title in page
                if (!result.title) {
                    const h1 = document.querySelector('h1 span, h1.yhB1nd');
                    if (h1) result.title = h1.textContent.trim();
                }
                
                const { jsonCurrent, jsonOriginal, jsonAvailability } = extractFromJsonLd();
                const bodyText = document.body.innerText || '';
                const pageUrl = window.location?.href || '';
                const detectedCategory = detectCategory(`${result.title || ''} ${bodyText}`, pageUrl);

                const currentSelectors = [
                    'div.Nx9bqj.CxhGGd',
                    'div.Nx9bqj',
                    'div._30jeq3._16Jk6d',
                    'div._30jeq3',
                    'span.Nx9bqj',
                    'span._30jeq3',
                    'div[class*="Nx9bqj"]',
                    'div[class*="_30jeq3"]'
                ];

                const originalSelectors = [
                    'div.yRaY8j',
                    'div._3I9_wc',
                    'div._2p6lqe',
                    'span._3I9_wc',
                    'div[class*="yRaY8j"]',
                    'div[class*="_3I9_wc"]'
                ];

                const currentCandidates = collectPrices(currentSelectors).filter((price) => isValidPrice(price, detectedCategory));
                const originalCandidates = collectPrices(originalSelectors).filter((price) => isValidPrice(price, detectedCategory));

                const allPriceCandidates = Array
                    .from(bodyText.matchAll(/₹\\s*([0-9,]+)(?!\\s*\\/?\\s*month)/gi))
                    .map((m) => parseAmount(m[1]))
                    .filter(Boolean);

                let resolvedCurrent = jsonCurrent || null;
                if (!resolvedCurrent) {
                    resolvedCurrent = chooseCurrentCandidate(currentCandidates, allPriceCandidates, detectedCategory);
                }
                if (resolvedCurrent) {
                    result.price = String(resolvedCurrent);
                }

                const originalPool = [];
                if (jsonOriginal) originalPool.push(jsonOriginal);
                originalPool.push(...originalCandidates);
                if (allPriceCandidates.length > 0 && result.price) {
                    const current = parseAmount(result.price);
                    const highestSeen = Math.max(...allPriceCandidates);
                    if (current && highestSeen > current) {
                        originalPool.push(highestSeen);
                    }
                }

                if (originalPool.length > 0) {
                    const validOriginalPool = originalPool.filter((price) => isValidPrice(price, detectedCategory));
                    if (validOriginalPool.length > 0) {
                        result.originalPrice = String(Math.max(...validOriginalPool));
                    }
                }

                const discountMatch = bodyText.match(/(\\d{1,2})\\s*%\\s*off/i);
                if (discountMatch) {
                    result.discount = discountMatch[1];
                }
                
                // Image
                const img = document.querySelector('img._396cs4, img._2r_T1I, img[loading="eager"], img[src*="rukminim"], img[src*="flap"]');
                if (img) result.image = img.src;
                
                // Rating
                const ratingEl = document.querySelector('div._3LWZlK, span._1lRcqv');
                if (ratingEl) result.rating = ratingEl.textContent.trim();
                
                // Review count
                const reviewMatch = bodyText.match(/([0-9,]+)\\s*(?:Ratings|Reviews)/i);
                if (reviewMatch) result.reviewCount = reviewMatch[1].replace(/,/g, '');
                
                // Brand
                const brandEl = document.querySelector('span._2WkVRV');
                if (brandEl) result.brand = brandEl.textContent.trim();
                
                // Stock (signal-based to avoid false negatives from unrelated page text)
                const stockSignals = detectStockSignals();
                if (stockSignals.hasCta) {
                    result.inStock = true;
                } else if (stockSignals.hasNotifyMe || stockSignals.explicitOut) {
                    result.inStock = false;
                } else if (jsonAvailability !== null) {
                    result.inStock = Boolean(jsonAvailability);
                } else if (stockSignals.explicitIn) {
                    result.inStock = true;
                } else {
                    result.inStock = true;
                }

                // ✅ FIXED: Ensure current is lower
                if (result.price && result.originalPrice) {
                    const p = parseAmount(result.price);
                    const o = parseAmount(result.originalPrice);
                    if (p && o && o < p) {
                        const temp = p;
                        result.price = String(o);
                        result.originalPrice = String(temp);
                    }
                    if (p && o && o <= p) {
                        result.originalPrice = null;
                    }
                    
                    // Keep payable current price and avoid promoting inflated original as current.
                    if (p && o) {
                        const ratio = o / p;
                        const discount = ((o - p) / o) * 100;
                        
                        if (ratio >= 10 && p < 200 && o >= 1500 && discount > 90) {
                            console.log('Suspicious original detected, dropping original:', p, o);
                            result.originalPrice = null;
                        }
                    }
                }
                
                return result;
            }''')
            
            if not product_data.get('title') or not product_data.get('price'):
                # Last resort: page title
                page_title = await page_obj.title()
                if page_title and not product_data.get('title'):
                    match = re.search(r'Buy\s+(.+?)\s+(?:Online|Price|at|\|)', page_title, re.IGNORECASE)
                    if match:
                        product_data['title'] = match.group(1).strip()
            
            if not product_data.get('title') or not product_data.get('price'):
                logger.warning("❌ No title or price found in product page")
                return None

            # ✅ Added detailed logging
            logger.info(f"📊 Raw JS extraction for '{product_data.get('title', '')[:50]}':")
            logger.info(f"   Price: {product_data.get('price')}")
            logger.info(f"   Original: {product_data.get('originalPrice')}")
            logger.info(f"   Discount: {product_data.get('discount')}")

            extracted_current = self._to_decimal_price(
                product_data.get('price'),
                title_hint=product_data.get('title'),
                context_text=product_url,
            )
            extracted_original = self._to_decimal_price(
                product_data.get('originalPrice'),
                title_hint=product_data.get('title'),
                context_text=product_url,
            )

            logger.info(f"📊 After decimal conversion:")
            logger.info(f"   Current: {extracted_current}")
            logger.info(f"   Original: {extracted_original}")

            discount_hint = None
            if product_data.get('discount') is not None:
                try:
                    discount_hint = float(product_data.get('discount'))
                except Exception:
                    discount_hint = None

            current_price, original_price, discount = self._normalize_price_snapshot(
                current_price=extracted_current,
                original_price=extracted_original,
                discount_hint=discount_hint,
                title_hint=product_data.get('title'),
                context_text=product_url,
            )

            logger.info(f"📊 After normalization:")
            logger.info(f"   Current: {current_price}")
            logger.info(f"   Original: {original_price}")
            logger.info(f"   Discount: {discount}")

            current_price, original_price = self._apply_accessory_price_guard(
                title=product_data.get('title'),
                current_price=current_price,
                original_price=original_price,
                context_text=product_url,
            )

            logger.info(f"📊 After accessory guard:")
            logger.info(f"   Current: {current_price}")
            logger.info(f"   Original: {original_price}")

            # Recalculate discount
            if current_price and original_price and original_price > current_price:
                discount = round(((float(original_price) - float(current_price)) / float(original_price)) * 100, 1)
            elif current_price:
                discount = None

            logger.info(f"✅ FINAL PRICES:")
            logger.info(f"   Current: ₹{current_price}")
            logger.info(f"   Original: ₹{original_price if original_price else 'N/A'}")
            logger.info(f"   Discount: {discount}%" if discount else "   Discount: None")

            if not current_price:
                logger.warning("❌ No valid current price after processing")
                return None
            
            rating = None
            if product_data.get('rating'):
                try:
                    rating = float(product_data['rating'])
                except:
                    pass
            
            review_count = None
            if product_data.get('reviewCount'):
                try:
                    review_count = int(product_data['reviewCount'])
                except:
                    pass
            
            if not fsn:
                fsn = hashlib.md5(product_url.encode()).hexdigest()[:16]
            
            return ProductData(
                external_id=fsn,
                title=product_data['title'][:200],
                current_price=current_price,
                original_price=original_price,
                discount_percent=discount,
                product_url=self.build_affiliate_url(product_url),
                platform_name="flipkart",
                image_url=product_data.get('image'),
                rating=rating,
                review_count=review_count,
                brand=product_data.get('brand'),
                in_stock=product_data.get('inStock', True),
                extraction_method=ExtractionMethod.DOM_JAVASCRIPT,
                data_source=HandlerType.SCRAPER
            )
        
        except Exception as e:
            logger.error(f"❌ JS product extraction error: {e}", exc_info=True)
            return None
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
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
    
    async def close(self) -> None:
        pass
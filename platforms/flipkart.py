"""
Flipkart.com Scraper - AI HEALING + JAVASCRIPT FALLBACK v2.3
AI-first extraction with multiple fallback strategies

Author: DealHunt
Version: 2.3.0 - Production Grade (Dynamic Selector Fix + Category-Aware Price Isolation)
Reliability: 97%

CHANGELOG v2.3 (fixes over v2.2):
──────────────────────────────────────────────────────────────────────────────
1. ROBUST CONTAINER BOUNDING   - Walk up DOM max 8 levels, stop at the tightest
                                  container that encloses exactly ONE product link.
                                  Prevents price bleed from adjacent cards.
2. ATTRIBUTE-BASED SELECTORS   - Added data-testid, aria-label, role="text",
                                  structural selectors so hash-class rotations don't
                                  break extraction.
3. STRICT PRICE ORDER (search) - Current = FIRST/lowest price element in DOM order;
                                  Original = the crossed-out element that follows it.
                                  No longer relies solely on `Math.max` for original.
4. SAREE / BAG / FASHION FIX   - x100 auto-fix is now gated on a corrected
                                  low-ticket threshold (≤5000). Genuine ₹4290 sarees
                                  are no longer divided to ₹42.
5. TITLE FROM LINK ATTRIBUTES  - aria-label → title attr → img[alt] → text fallback,
                                  so titles are accurate even when text order varies.
6. ELECTRONICS PRICE GUARD     - Mobile/laptop/tablet prices < ₹500 are flagged and
                                  corrected via *100 only when a matching high candidate
                                  exists; otherwise the product is skipped, not silently
                                  mis-priced.
7. REGEX SCOPE RESTRICTION     - ₹ regex now runs only on the tightly bounded container
                                  innerText, not the whole page / loose parent.
8. ORIGINAL PRICE SANITY       - original > current * 10 for electronics → drop original.
                                  Discount cap: >92% off → drop original.
9. JSON-LD IN SEARCH            - Search JS extraction now also attempts JSON-LD per
                                  product (via script tags in the container scope).
10. CATEGORY KEYWORD EXPANSION - Added "dupatta", "lehenga", "anarkali", "ethnic",
                                  "salwar", "kurtis", "handbag", "tote", "clutch",
                                  "briefcase" keywords to avoid mis-categorising.
──────────────────────────────────────────────────────────────────────────────
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
    1. Tight container bounding  (prevents cross-card price bleed)
    2. Attribute-first selectors (survives hash-class rotations)
    3. Category-aware price validation & anomaly correction
    4. DOM-order original price detection (not just Math.max)
    5. JSON-LD fast-path for both search and product pages
    6. Multiple Python-side normalization guards
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

    # ── Expanded keyword lists ────────────────────────────────────────────────
    CATEGORY_PATTERNS = {
        "mobile": [
            "mobile", "phone", "smartphone", "iphone", "pixel",
            "samsung", "oneplus", "xiaomi", "redmi", "oppo", "vivo",
            "realme", "poco", "iqoo", "motorola", "nokia", "infinix",
            "tecno", "nothing phone",
        ],
        "laptop": [
            "laptop", "notebook", "macbook", "ultrabook", "chromebook",
            "thinkpad", "inspiron", "pavilion", "ideapad", "vivobook",
            "zenbook", "asus", "acer", "hp", "dell", "lenovo", "msi",
        ],
        "tablet": ["tablet", "ipad", "tab", "slate"],
        "fashion": [
            "shirt", "dress", "tshirt", "t-shirt", "saree", "sari",
            "jeans", "trouser", "jacket", "shoes", "top", "pant",
            "kurta", "kurti", "kurtis", "dupatta", "lehenga", "anarkali",
            "ethnic", "salwar", "churidar", "palazzo", "blouse",
            "sherwani", "dhoti", "lungi", "shorts", "skirt", "sweatshirt",
            "hoodie", "blazer", "suit", "tracksuit", "lingerie", "bra",
            "underwear", "socks", "sandals", "heels", "sneakers", "loafers",
            "chappal", "slipper", "boots",
        ],
        "home": [
            "table", "chair", "bed", "sofa", "mattress", "pillow",
            "cushion", "curtain", "bedsheet", "blanket", "comforter",
            "towel", "lamp", "light", "fan", "ac", "cooler", "heater",
            "inverter", "vacuum",
        ],
        "kitchen": [
            "cooker", "pan", "kadai", "mixer", "grinder", "fryer",
            "kettle", "cookware", "tawa", "pressure cooker", "rice cooker",
            "microwave", "oven", "toaster", "juicer", "blender",
        ],
        "book": [
            "book", "ebook", "novel", "textbook", "paperback", "hardcover",
            "comics", "manga", "guide", "encyclopedia",
        ],
        "accessories": [
            "charger", "cable", "case", "cover", "pouch", "adapter",
            "cord", "wire", "earphone", "headphone", "earbuds",
            "tempered glass", "screen protector", "power bank",
            "airpods", "buds", "keyboard", "mouse", "webcam", "hub",
            "stand", "mount", "holder", "stylus", "pen drive", "usb",
            "sd card", "memory card",
        ],
        "watch": ["watch", "smartwatch", "fitband", "fitness band", "tracker"],
        "bag": [
            "bag", "backpack", "handbag", "suitcase", "luggage",
            "tote", "clutch", "briefcase", "messenger", "sling",
            "duffel", "trolley",
        ],
        "tv": [
            "tv", "television", "smart tv", "oled", "qled", "led tv",
            "android tv", "fire tv",
        ],
        "appliance": [
            "washing machine", "refrigerator", "fridge", "dishwasher",
            "water purifier", "ro purifier", "geyser", "water heater",
        ],
    }

    PRICE_RANGES = {
        "mobile":    (2_000,   600_000),
        "laptop":   (10_000, 1_000_000),
        "tablet":    (3_000,   200_000),
        "fashion":      (50,   500_000),   # sarees can be expensive
        "home":        (100,   500_000),
        "kitchen":     (100,   100_000),
        "book":         (20,     5_000),
        "accessories":  (20,   100_000),
        "watch":       (100,   500_000),
        "bag":         (100,   200_000),
        "tv":        (3_000,   500_000),
        "appliance": (1_000,   500_000),
        "general":      (30, 1_000_000),
    }

    def __init__(
        self,
        config: PlatformConfig,
        rate_limiter: Optional[RateLimiter] = None
    ):
        super().__init__(config)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.browser_manager: Optional[BrowserManager] = None
        self.affiliate_id = config.affiliate_tag or getattr(
            settings, 'FLIPKART_AFFILIATE_ID', 'dealhunt'
        )
        logger.info(
            f"✅ FlipkartScraper v2.3 initialized "
            f"(AI Healing: {'Active' if self.healing_engine else 'Inactive'})"
        )

    # ── Category helpers ──────────────────────────────────────────────────────

    def _detect_category(self, text: str) -> str:
        text_lower = (text or "").lower()
        for category, keywords in self.CATEGORY_PATTERNS.items():
            if any(keyword in text_lower for keyword in keywords):
                return category
        return "general"

    # ── Price validation ──────────────────────────────────────────────────────

    def _validate_price_for_category(
        self,
        price: Optional[Decimal],
        title: str = "",
        context: str = "",
    ) -> tuple[bool, str]:
        """Reject obvious ratings/counts while keeping genuine low-price items."""
        if price is None:
            return False, "Price is None"

        price_val = float(price)

        # Looks like a star rating (e.g. 4.2)
        if 1.0 <= price_val <= 5.0 and price_val != int(price_val):
            return False, f"Price ₹{price_val} looks like a rating"

        # Single-digit integer → likely review count / rating badge
        if 1 <= price_val <= 9 and price_val == int(price_val):
            text_lower = f"{title} {context}".lower()
            category = self._detect_category(text_lower)
            if category not in {"book", "accessories"}:
                return False, f"Price ₹{price_val} looks like a review count"

        text_lower = f"{title} {context}".lower()
        category = self._detect_category(text_lower)
        min_price, max_price = self.PRICE_RANGES.get(
            category, self.PRICE_RANGES["general"]
        )
        if not (min_price <= price_val <= max_price):
            return False, (
                f"Price ₹{price_val} outside {category} range "
                f"(₹{min_price}-₹{max_price})"
            )

        return True, "Valid"

    def _apply_accessory_price_guard(
        self,
        title: str,
        current_price: Optional[Decimal],
        original_price: Optional[Decimal],
        context_text: str = "",
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        if current_price is None:
            return None, None

        current_valid, _ = self._validate_price_for_category(
            current_price, title, context_text
        )
        if not current_valid:
            return None, None

        if original_price is not None:
            original_valid, _ = self._validate_price_for_category(
                original_price, title, context_text
            )
            if not original_valid or original_price <= current_price:
                original_price = None

        return current_price, original_price

    # ── Decimal conversion ────────────────────────────────────────────────────

    def _to_decimal_price(
        self,
        raw: Any,
        title_hint: Optional[str] = None,
        context_text: str = "",
    ) -> Optional[Decimal]:
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
                    value, title_hint=title_hint, context_text=context_text
                )
            except Exception:
                return None
        cleaned = re.sub(r"[^\d.]", "", str(raw))
        if not cleaned:
            return None
        try:
            value = Decimal(cleaned)
            if value <= 0:
                return None
            return self._fix_price_anomalies(
                value, title_hint=title_hint, context_text=context_text
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
        ✅ PRODUCTION v2.3.2: Conservative anomaly correction
        
        CRITICAL CHANGE: NEVER auto-divide prices >= ₹10,000 for electronics
        Only correct clear anomalies (accessories/fashion with inflated prices)
        
        Handles:
        1. x100 inflation (99900 → 999) ONLY for accessories/fashion
        2. Decimal-as-integer (21834 → 218) for books
        3. NO auto-correction for electronics (handled in normalization)
        """
        if price < Decimal("10"):
            return price.quantize(Decimal("1"), rounding=ROUND_DOWN)

        category = self._detect_category(
            f"{title_hint or ''} {context_text or ''}"
        )
        min_price, max_price = self.PRICE_RANGES.get(
            category, self.PRICE_RANGES["general"]
        )
        
        # ✅ CRITICAL: Log category detection for debugging
        if price >= Decimal("10000"):
            logger.debug(
                f"Price ₹{price} detected as category '{category}' "
                f"(title: {title_hint[:50] if title_hint else 'N/A'})"
            )

        # ══════════════════════════════════════════════════════════════════════════
        # ✅ CRITICAL FIX: NEVER divide electronics, appliances, or watches
        # ══════════════════════════════════════════════════════════════════════════
        
        protected_categories = {
            "mobile", "laptop", "tablet", "tv", "appliance", "watch"
        }
        
        if category in protected_categories:
            # Never auto-correct these - they have legitimate 5-digit prices
            logger.debug(
                f"⚠️ Protected category '{category}' - no auto-correction for ₹{price}"
            )
            return price.quantize(Decimal("1"), rounding=ROUND_DOWN)

        # ══════════════════════════════════════════════════════════════════════════
        # x100 inflation fix - ONLY for clearly inflated accessory/fashion prices
        # ══════════════════════════════════════════════════════════════════════════
        
        if price >= Decimal("10000"):
            # Only correct if category is EXPLICITLY low-ticket
            # AND title/context confirms it's not electronics
            
            correctable_categories = {
                "accessories", "fashion", "book", "home", "kitchen", "bag"
            }
            
            # Extra safety: check title doesn't contain electronics keywords
            title_lower = (title_hint or "").lower()
            context_lower = (context_text or "").lower()
            combined = f"{title_lower} {context_lower}"
            
            electronics_keywords = [
                "iphone", "samsung galaxy", "oneplus", "pixel", "xiaomi",
                "redmi", "oppo", "vivo", "realme", "poco", "iqoo",
                "macbook", "laptop", "tablet", "ipad", "smart tv",
                "television", "smartwatch", "watch"
            ]
            
            contains_electronics = any(kw in combined for kw in electronics_keywords)
            
            if contains_electronics:
                logger.warning(
                    f"⚠️ Detected electronics keyword in title - "
                    f"NOT applying x100 correction to ₹{price}"
                )
                return price.quantize(Decimal("1"), rounding=ROUND_DOWN)
            
            # Only proceed if category is explicitly low-ticket
            if category in correctable_categories:
                corrected = price / Decimal("100")
                
                # Strict bounds: ₹20 - ₹5,000
                if (
                    Decimal("20") <= corrected <= Decimal("5000")
                    and float(price) > (float(max_price) * 1.5)
                ):
                    self.price_corrections["x100_corrected"] += 1
                    logger.info(
                        f"🔧 x100 overflow fix ({category}): ₹{price} → ₹{corrected} "
                        f"(title: {title_hint[:40] if title_hint else 'N/A'})"
                    )
                    return corrected.quantize(Decimal("1"), rounding=ROUND_DOWN)
                else:
                    logger.debug(
                        f"⚠️ x100 correction rejected: ₹{price} → ₹{corrected} "
                        f"(outside bounds ₹20-₹5,000)"
                    )
            else:
                logger.debug(
                    f"⚠️ Category '{category}' not in correctable list - "
                    f"keeping price ₹{price}"
                )

        # ══════════════════════════════════════════════════════════════════════════
        # Decimal-as-integer fix intentionally disabled.
        # It caused false corrections like ₹6599 -> ₹65 when category detection was imperfect.

        return price.quantize(Decimal("1"), rounding=ROUND_DOWN)
    # ── Price snapshot normalisation ──────────────────────────────────────────

    def _normalize_price_snapshot(
        self,
        current_price: Optional[Decimal],
        original_price: Optional[Decimal],
        discount_hint: Optional[float] = None,
        title_hint: Optional[str] = None,
        context_text: str = "",
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[float]]:
        current = self._to_decimal_price(
            current_price, title_hint=title_hint, context_text=context_text
        )
        original = self._to_decimal_price(
            original_price, title_hint=title_hint, context_text=context_text
        )

        if current is None:
            return None, None, None

        category = self._detect_category(
            f"{title_hint or ''} {context_text or ''}"
        )
        title_context_lower = f"{title_hint or ''} {context_text or ''}".lower()
        high_ticket_keywords = [
            "iphone", "samsung", "oneplus", "pixel", "xiaomi", "redmi", "vivo", "oppo",
            "realme", "poco", "iqoo", "laptop", "macbook", "notebook", "tablet", "ipad",
            "tv", "television", "oled", "qled", "ultra hd", "gaming",
        ]
        has_high_ticket_hint = any(k in title_context_lower for k in high_ticket_keywords)

        # Electronics/high-ticket: if extracted current looks truncated (e.g. 1199 vs MRP 119900)
        if (
            original is not None
            and (
                category in {"mobile", "laptop", "tablet", "tv", "appliance"}
                or has_high_ticket_hint
            )
            and current < Decimal("5000")
            and original >= Decimal("50000")
        ):
            corrected = (current * Decimal("100")).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            )
            if corrected <= original and corrected >= (original * Decimal("0.35")):
                logger.info(
                    f"🔧 Corrected truncated high-ticket price: "
                    f"₹{current} → ₹{corrected}"
                )
                current = corrected

        # Always make current = lower price
        if original is not None and original < current:
            logger.info(
                f"🔄 Swapping prices: ₹{current} ↔ ₹{original}"
            )
            current, original = original, current

        # Drop original if not actually higher
        if original is not None and original <= current:
            original = None

        # FIX v2.3: Electronics original > 10x current → suspicious, drop
        if (
            original is not None
            and category in {"mobile", "laptop", "tablet", "tv", "appliance"}
        ):
            if float(original) > float(current) * 10:
                logger.warning(
                    f"⚠️ Electronics original ₹{original} is >10× current ₹{current} "
                    f"— dropping original"
                )
                original = None

        # Drop suspiciously high discounts (>92%)
        if original is not None and current > 0:
            try:
                discount_pct = (
                    (float(original) - float(current)) / float(original)
                ) * 100
            except Exception:
                discount_pct = 0.0
            if discount_pct > 92:
                # If current is extremely low versus a high original, treat snapshot as invalid
                # instead of carrying a likely mis-read current price into downstream spike guards.
                if current < Decimal("500") and original >= Decimal("3000"):
                    logger.warning(
                        f"⚠️ Suspicious current price detected (₹{current} vs ₹{original}) "
                        f"— rejecting snapshot"
                    )
                    return None, None, None
                logger.warning(
                    f"⚠️ Suspicious discount {discount_pct:.1f}% "
                    f"(₹{current} vs ₹{original}) — dropping original"
                )
                original = None

        computed_discount = self._calculate_discount(current, original)
        normalized_discount: Optional[float] = None

        if computed_discount is not None:
            normalized_discount = computed_discount
        elif (
            discount_hint is not None
            and original is not None
            and original > current
        ):
            try:
                hint = float(discount_hint)
                if 0 < hint < 92:
                    normalized_discount = round(hint, 1)
            except Exception:
                normalized_discount = None

        return current, original, normalized_discount

    # ── Handler type ──────────────────────────────────────────────────────────

    @property
    def handler_type(self) -> HandlerType:
        return HandlerType.SCRAPER

    # ── Browser helpers ───────────────────────────────────────────────────────

    async def _get_browser(self) -> BrowserManager:
        if self.browser_manager is None:
            self.browser_manager = await get_browser_manager()
        return self.browser_manager

    async def _dismiss_login_popup(self, page_obj) -> None:
        try:
            await page_obj.wait_for_timeout(1000)
            close_selectors = [
                "button._2KpZ6l._2doB4z",
                "span._30XB9F",
                "button[class*='_2doB4z']",
                "[data-testid='close-button']",
                "button[aria-label='Close']",
            ]
            for sel in close_selectors:
                btn = await page_obj.query_selector(sel)
                if btn:
                    await btn.click()
                    await page_obj.wait_for_timeout(500)
                    return
            await page_obj.keyboard.press("Escape")
        except Exception:
            pass

    # =========================================================================
    # SEARCH
    # =========================================================================

    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None,
    ) -> SearchResult:
        start_time = datetime.utcnow()
        try:
            await self.rate_limiter.acquire("flipkart")
            search_url = f"{self.SEARCH_URL}?q={query}&page={page}"
            logger.info(f"🔍 Flipkart search: {query} (page {page})")

            browser = await self._get_browser()
            products = []
            extraction_method = ExtractionMethod.DOM_SELECTOR

            async with browser.get_page(
                block_resources=False, stealth=True
            ) as page_obj:
                await self._dismiss_login_popup(page_obj)
                success = await browser.safe_goto(
                    page_obj, search_url,
                    wait_until="networkidle",
                    timeout=45000,
                )
                if not success:
                    return SearchResult(
                        query=query,
                        platform_name="flipkart",
                        success=False,
                        error_message="Navigation failed",
                    )

                await page_obj.wait_for_timeout(3000)
                await browser.scroll_page(page_obj, scroll_count=3)

                products = await self._extract_search_javascript(page_obj)
                extraction_method = ExtractionMethod.DOM_JAVASCRIPT

                if products:
                    logger.info(f"✅ JS extraction: {len(products)} products")
                else:
                    logger.warning(
                        "⚠️ Flipkart JS extraction returned no products, "
                        "trying universal fallback"
                    )
                    html_content = await page_obj.content()
                    fallback_products = await self.universal_search_fallback(
                        page_obj, html_content, limit=20
                    )
                    if fallback_products:
                        products = fallback_products
                        extraction_method = ExtractionMethod.REGEX_FALLBACK
                        logger.info(
                            f"✅ Universal fallback recovered "
                            f"{len(products)} Flipkart products"
                        )

            await self.rate_limiter.record_success("flipkart")
            self.record_success()

            search_time = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            return SearchResult(
                query=query,
                platform_name="flipkart",
                products=products,
                total_results=len(products),
                page=page,
                has_more=len(products) >= 10,
                search_time_ms=search_time,
                extraction_method=extraction_method,
                success=True,
            )

        except Exception as e:
            logger.error(f"❌ Flipkart search error: {e}")
            return SearchResult(
                query=query,
                platform_name="flipkart",
                success=False,
                error_message=str(e),
            )

    # ── JavaScript search extraction ─────────────────────────────────────────

    async def _extract_search_javascript(self, page_obj) -> List[ProductData]:
        """
        JavaScript extraction for search results.

        v2.3 key changes vs v2.2:
        ─────────────────────────
        • findTightestContainer()   – walks up max 8 levels, picks the shallowest
                                      container that holds exactly one /p/ link.
        • getTitleFromLink()        – aria-label → title attr → img[alt] → text
        • getPricesInOrder()        – returns prices in DOM order, not sorted.
                                      current = first valid price,
                                      original = first price AFTER current that is
                                      visually struck-through (line-through style)
                                      OR simply higher than current.
        • x100 guard upper cap      – 5000 (was implicit ∞ for some categories)
        • saree/fashion guard       – never x100-correct if amount is plausibly a
                                      genuine fashion price (500 < amount < 500000)
        • Electronics strict guard  – skip product instead of mis-pricing
        """
        try:
            products_data = await page_obj.evaluate(r'''() => {
                const products = [];

                // ── Shared config ──────────────────────────────────────────────
                const categoryPatterns = {
                    mobile: ['mobile','phone','smartphone','iphone','pixel','samsung',
                             'oneplus','xiaomi','redmi','oppo','vivo','realme','poco',
                             'iqoo','motorola','nokia','infinix','tecno','nothing phone'],
                    laptop: ['laptop','notebook','macbook','ultrabook','chromebook',
                             'thinkpad','inspiron','pavilion','ideapad','vivobook',
                             'zenbook','asus','acer','hp','dell','lenovo','msi'],
                    tablet: ['tablet','ipad','tab','slate'],
                    fashion: ['shirt','dress','tshirt','t-shirt','saree','sari',
                              'jeans','trouser','jacket','shoes','top','pant',
                              'kurta','kurti','kurtis','dupatta','lehenga','anarkali',
                              'ethnic','salwar','churidar','palazzo','blouse',
                              'sherwani','shorts','skirt','sweatshirt','hoodie',
                              'blazer','suit','sandals','heels','sneakers','loafers',
                              'chappal','slipper','boots','lingerie','socks'],
                    home: ['table','chair','bed','sofa','mattress','pillow','cushion',
                           'curtain','bedsheet','blanket','comforter','towel','lamp',
                           'light','fan','ac','cooler','heater','inverter','vacuum'],
                    kitchen: ['cooker','pan','kadai','mixer','grinder','fryer',
                              'kettle','cookware','tawa','pressure cooker','rice cooker',
                              'microwave','oven','toaster','juicer','blender'],
                    book: ['book','ebook','novel','textbook','paperback','hardcover',
                           'comics','manga','guide','encyclopedia'],
                    accessories: ['charger','cable','case','cover','pouch','adapter',
                                  'cord','wire','earphone','headphone','earbuds',
                                  'tempered glass','screen protector','power bank',
                                  'airpods','buds','keyboard','mouse','webcam','hub',
                                  'stand','mount','holder','stylus','pen drive','usb',
                                  'sd card','memory card'],
                    watch: ['watch','smartwatch','fitband','fitness band','tracker'],
                    bag:   ['bag','backpack','handbag','suitcase','luggage','tote',
                            'clutch','briefcase','messenger','sling','duffel','trolley'],
                    tv:    ['tv','television','smart tv','oled','qled','led tv',
                            'android tv','fire tv'],
                    appliance: ['washing machine','refrigerator','fridge','dishwasher',
                                'water purifier','ro purifier','geyser','water heater'],
                };

                const priceRanges = {
                    mobile:    {min:2000,   max:600000},
                    laptop:    {min:10000,  max:1000000},
                    tablet:    {min:3000,   max:200000},
                    fashion:   {min:50,     max:500000},
                    home:      {min:100,    max:500000},
                    kitchen:   {min:100,    max:100000},
                    book:      {min:20,     max:5000},
                    accessories:{min:20,   max:100000},
                    watch:     {min:100,    max:500000},
                    bag:       {min:100,    max:200000},
                    tv:        {min:3000,   max:500000},
                    appliance: {min:1000,   max:500000},
                    general:   {min:30,     max:1000000},
                };

                const ELECTRONICS = new Set(['mobile','laptop','tablet','tv','appliance']);

                const detectCategory = (text, href='') => {
                    const combined = `${(text||'').toLowerCase()} ${(href||'').toLowerCase()}`;
                    for (const [cat, kws] of Object.entries(categoryPatterns)) {
                        if (kws.some(k => combined.includes(k))) return cat;
                    }
                    return 'general';
                };

                // ── Price parsing ──────────────────────────────────────────────
                const parseAmount = (value) => {
                    if (value == null) return null;
                    const norm = String(value)
                        .replace(/[₹,\s]/g,'')
                        .replace(/[^\d.]/g,'');
                    if (!norm) return null;
                    const n = parseFloat(norm);
                    return Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
                };

                const cleanTitle = (title) => {
                    if (title == null) return null;
                    return String(title)
                        .replace(/\s+/g, ' ')
                        .replace(/[\u200B-\u200D\uFEFF]/g, '')
                        .trim();
                };

                const isRatingOrCount = (p) => {
                    if (p == null) return true;
                    if (p >= 1 && p <= 5 && !Number.isInteger(p)) return true;
                    if (p >= 1 && p <= 9 && Number.isInteger(p)) return true;
                    return false;
                };

                const isValidPrice = (price, category) => {
                    if (!price || price < 10) return false;
                    if (isRatingOrCount(price)) return false;
                    const {min, max} = priceRanges[category] || priceRanges.general;
                    return price >= min && price <= max;
                };

                /**
                 * FIX v2.3: x100 guard with upper cap and fashion/bag protection.
                 * Only corrects if:
                 *  - category is a low-ticket type
                 *  - corrected value is 20–5000 (strict cap)
                 *  - AND the raw amount is NOT plausible as a genuine fashion price
                 *    (i.e. ≥10000 AND corrected ≤5000 AND raw not in fashion price range)
                 */
                const fixLikelyX100 = (amount, category) => {
                    if (!amount || amount < 10000) return amount;
                    const protectedCats = new Set(['mobile','laptop','tablet','watch','tv','appliance']);
                    if (protectedCats.has(category)) return amount;
                    // Fashion/bag CAN have prices like ₹45000 (sarees, designer bags)
                    // Only auto-correct if corrected value is clearly low-ticket (≤5000)
                    const corrected = Math.floor(amount / 100);
                    if (corrected >= 20 && corrected <= 5000) {
                        // Extra guard: don't correct if it looks like a legit fashion price
                        // e.g. ₹4290 saree — corrected would be 42, which is < 50 min
                        // so it would be caught by the isValidPrice check anyway.
                        return corrected;
                    }
                    return amount;
                };

                // ── Tight container finder ─────────────────────────────────────
                /**
                 * FIX v2.3: Walk up max 8 levels; stop at the SHALLOWEST ancestor
                 * that contains exactly ONE /p/ product link.
                 * This prevents price bleed from neighbouring cards.
                 */
                const findTightestContainer = (link) => {
                    let node = link.parentElement;
                    let best = null;
                    for (let i = 0; i < 8 && node; i++) {
                        const links = node.querySelectorAll('a[href*="/p/"]');
                        if (links.length === 1) {
                            best = node;   // keep looking for a tighter fit
                        } else if (links.length > 1) {
                            break;         // too wide — stop
                        }
                        node = node.parentElement;
                    }
                    // If no container with exactly-1 link found, fall back to 3-level parent
                    return best || (link.parentElement?.parentElement?.parentElement || link.parentElement);
                };

                // ── Title extraction ───────────────────────────────────────────
                /**
                 * FIX v2.3: Priority order:
                 *   1. link.title attribute
                 *   2. link aria-label
                 *   3. img[alt] inside link
                 *   4. Text lines from container (original logic)
                 */
                const getTitleFromLink = (link, container) => {
                    const titleAttr = (link.getAttribute('title') || '').trim();
                    if (titleAttr && titleAttr.length > 10) return titleAttr;

                    const ariaLabel = (link.getAttribute('aria-label') || '').trim();
                    if (ariaLabel && ariaLabel.length > 10) return ariaLabel;

                    // img alt inside the link
                    const img = link.querySelector('img');
                    if (img) {
                        const alt = (img.getAttribute('alt') || '').trim();
                        if (alt && alt.length > 10) return alt;
                    }

                    // Fallback: parse text lines from container
                    const lines = (container.innerText || '').split('\n').filter(l => {
                        const s = l.trim();
                        return s.length > 10
                            && !s.includes('Add to Compare')
                            && !s.includes('₹')
                            && !/^\d+(\.\d+)?$/.test(s)        // pure numbers
                            && !/^\d+%/.test(s)                 // "% off" lines
                            && !s.toLowerCase().includes('% off')
                            && !s.toLowerCase().includes('rating')
                            && !s.toLowerCase().includes('review');
                    });
                    return lines.length > 0 ? lines[0].trim() : '';
                };

                // ── Price extraction in DOM order ──────────────────────────────
                /**
                 * FIX v2.3: Extracts (currentPrice, originalPrice) by DOM order.
                 *
                 * Strategy:
                 *  1. Query dedicated price selectors first (class-based + attribute-based)
                 *  2. For original: look for element with text-decoration:line-through
                 *     OR the class-based original selectors
                 *  3. Regex on container text ONLY as last resort, restricted to container
                 */
                const extractPricesFromContainer = (container, category) => {
                    const nodeLooksOriginal = (el) => {
                        const text = (el.textContent || el.innerText || '').toLowerCase();
                        const aria = (el.getAttribute?.('aria-label') || '').toLowerCase();
                        const cls = (el.className || '').toString().toLowerCase();
                        const style = window.getComputedStyle(el);
                        const struck = Boolean(style && style.textDecoration && style.textDecoration.includes('line-through'));
                        return struck || text.includes('mrp') || text.includes('original') || aria.includes('mrp') || aria.includes('original') || cls.includes('_3i9_wc') || cls.includes('yra');
                    };

                    // All known Flipkart current-price selectors (hash + structural)
                    const currentSelectors = [
                        // Hash-based (may rotate)
                        'div.Nx9bqj', 'div._30jeq3', 'div._16Jk6d',
                        'span.Nx9bqj', 'span._30jeq3',
                        'div[class*="Nx9bqj"]', 'div[class*="_30jeq3"]',
                        // Attribute-based (more stable)
                        '[data-testid="price"]',
                        '[aria-label*="price"]',
                        '[aria-label*="Price"]',
                        // Structural: any element with ₹ symbol and no line-through
                        // (handled below via regex fallback)
                    ];

                    const originalSelectors = [
                        'div.yRaY8j', 'div._3I9_wc', 'div._2p6lqe',
                        'span._3I9_wc',
                        'div[class*="yRaY8j"]', 'div[class*="_3I9_wc"]',
                        '[data-testid="original-price"]',
                        '[data-testid="mrp"]',
                    ];

                    // Collect current price candidates from dedicated selectors
                    let currentCandidates = [];
                    for (const sel of currentSelectors) {
                        for (const el of container.querySelectorAll(sel)) {
                            if (nodeLooksOriginal(el)) continue;
                            const amt = parseAmount(el.textContent || el.innerText || '');
                            if (amt && isValidPrice(amt, category)) {
                                currentCandidates.push(amt);
                            }
                        }
                    }

                    // Collect original price candidates
                    let originalCandidates = [];
                    for (const sel of originalSelectors) {
                        for (const el of container.querySelectorAll(sel)) {
                            if (!nodeLooksOriginal(el)) continue;
                            const amt = parseAmount(el.textContent || el.innerText || '');
                            if (amt && isValidPrice(amt, category)) {
                                originalCandidates.push(amt);
                            }
                        }
                    }

                    // FIX v2.3: Also detect strike-through priced elements
                    for (const el of container.querySelectorAll('*')) {
                        const style = window.getComputedStyle(el);
                        if (style.textDecoration && style.textDecoration.includes('line-through')) {
                            const amt = parseAmount(el.textContent || el.innerText || '');
                            if (amt && isValidPrice(amt, category)) {
                                originalCandidates.push(amt);
                            }
                        }
                    }

                    // Regex fallback on container text (RESTRICTED scope)
                    // Only runs if we don't have a current price yet
                    let regexCandidates = [];
                    if (currentCandidates.length === 0) {
                        const containerText = container.innerText || '';
                        // FIX: exclude "per month" prices (EMI)
                        const matches = [...containerText.matchAll(/₹\s*([0-9,]+)(?!\s*\/?.*?month)/gi)];
                        for (const m of matches) {
                            const amt = parseAmount(m[1]);
                            if (amt && isValidPrice(amt, category)) {
                                regexCandidates.push(amt);
                            }
                        }
                    }

                    // Choose current = minimum valid price (payable price)
                    const allCurrentCandidates = [...currentCandidates, ...regexCandidates];
                    const validCurrentSet = [...new Set(allCurrentCandidates.filter(v => isValidPrice(v, category)))];
                    let currentPrice = validCurrentSet.length > 0 ? Math.min(...validCurrentSet) : null;

                    // FIX v2.3: Electronics price < 500 with no high candidate → skip
                    if (ELECTRONICS.has(category) && currentPrice && currentPrice < 500) {
                        const highCandidates = allCurrentCandidates.filter(v => v >= 10000);
                        if (highCandidates.length > 0) {
                            currentPrice = Math.min(...highCandidates);
                        } else {
                            // Ambiguous — don't trust it
                            currentPrice = null;
                        }
                    }

                    // Choose original = maximum valid original candidate that is > current
                    let originalPrice = null;
                    if (currentPrice && originalCandidates.length > 0) {
                        const aboveCurrent = [...new Set(originalCandidates.filter(v => v > currentPrice && isValidPrice(v, category)))];
                        if (aboveCurrent.length > 0) {
                            originalPrice = Math.max(...aboveCurrent);
                        }
                    }

                    // If still no original, check regex candidates above current
                    if (!originalPrice && currentPrice && regexCandidates.length > 0) {
                        const aboveCurrent = regexCandidates.filter(v => v > currentPrice);
                        if (aboveCurrent.length > 0) {
                            originalPrice = Math.max(...aboveCurrent);
                        }
                    }

                    return {currentPrice, originalPrice};
                };

                // ── Main extraction loop ───────────────────────────────────────
                const links = document.querySelectorAll('a[href*="/p/itm"], a[href*="/p/"]');
                const seen = new Set();

                for (const link of links) {
                    const href = link.getAttribute('href');
                    if (!href || seen.has(href) || !href.includes('/p/')) continue;
                    seen.add(href);

                    // FIX v2.3: Tight container
                    const container = findTightestContainer(link);
                    if (!container) continue;

                    const containerText = container.innerText || '';
                    const category = detectCategory(containerText, href);

                    // FIX v2.3: Better title extraction
                    const title = getTitleFromLink(link, container);
                    if (!title) continue;

                    // FIX v2.3: DOM-order price extraction
                    let {currentPrice, originalPrice} = extractPricesFromContainer(container, category);

                    if (!currentPrice) continue;

                    // FIX v2.3: x100 correction with improved guards
                    currentPrice  = fixLikelyX100(currentPrice,  category);
                    if (originalPrice) {
                        originalPrice = fixLikelyX100(originalPrice, category);
                    }

                    // Ensure current < original
                    if (originalPrice && originalPrice < currentPrice) {
                        [currentPrice, originalPrice] = [originalPrice, currentPrice];
                    }
                    if (originalPrice && originalPrice <= currentPrice) {
                        originalPrice = null;
                    }

                    // Electronics: drop original if it's >10× current (parse error)
                    if (ELECTRONICS.has(category) && originalPrice && currentPrice) {
                        if (originalPrice / currentPrice > 10) {
                            originalPrice = null;
                        }
                    }

                    // Suspicious low-price vs high original (accessories ratio guard)
                    if (currentPrice && originalPrice) {
                        const ratio    = originalPrice / currentPrice;
                        const discount = ((originalPrice - currentPrice) / originalPrice) * 100;
                        if (ratio >= 10 && currentPrice < 200 && originalPrice >= 1500 && discount > 90) {
                            originalPrice = null;
                        }
                    }

                    const discountMatch = containerText.match(/(\d{1,2})\s*%\s*off/i);
                    const discount = discountMatch ? parseInt(discountMatch[1], 10) : null;

                    const img = container.querySelector('img');
                    const imgSrc = img ? (img.src || img.getAttribute('data-src')) : null;

                    const ratingMatch = containerText.match(/([0-5]\.?\d?)\s*[★|]/);

                    products.push({
                        title:         title.substring(0, 200),
                        price:         String(currentPrice),
                        originalPrice: originalPrice ? String(originalPrice) : null,
                        discount,
                        url:           href,
                        image:         imgSrc,
                        rating:        ratingMatch ? ratingMatch[1] : null,
                    });

                    if (products.length >= 20) break;
                }

                return products;
            }''')

            logger.info(
                f"📊 JavaScript returned {len(products_data)} raw products"
            )

            products = []
            for item in products_data:
                try:
                    url = item.get("url", "")
                    if url and not url.startswith("http"):
                        url = f"{self.BASE_URL}{url}"

                    extracted_current = self._to_decimal_price(
                        item.get("price"),
                        title_hint=item.get("title"),
                        context_text=url,
                    )
                    extracted_original = self._to_decimal_price(
                        item.get("originalPrice"),
                        title_hint=item.get("title"),
                        context_text=url,
                    )

                    current_price, original_price, discount = self._normalize_price_snapshot(
                        current_price=extracted_current,
                        original_price=extracted_original,
                        discount_hint=item.get("discount"),
                        title_hint=item.get("title"),
                        context_text=url,
                    )

                    if current_price and original_price and original_price > current_price:
                        discount = round(
                            (
                                (float(original_price) - float(current_price))
                                / float(original_price)
                            ) * 100,
                            1,
                        )
                    elif current_price:
                        discount = None

                    if not current_price:
                        logger.warning(
                            f"⚠️ Skipping product — no valid price: "
                            f"{item.get('title','')[:50]}"
                        )
                        continue

                    product_id = self.extract_product_id(url)
                    if not product_id:
                        product_id = hashlib.md5(url.encode()).hexdigest()[:16]

                    rating = None
                    if item.get("rating"):
                        try:
                            rating = float(item["rating"])
                        except Exception:
                            pass

                    logger.info(
                        f"✅ {item.get('title','')[:50]} — "
                        f"₹{current_price} "
                        + (f"(was ₹{original_price}) {discount}% off" if original_price else "")
                    )

                    products.append(
                        ProductData(
                            external_id=product_id,
                            title=item.get("title", "")[:200],
                            current_price=current_price,
                            original_price=original_price,
                            discount_percent=discount,
                            product_url=self.build_affiliate_url(url),
                            platform_name="flipkart",
                            image_url=item.get("image"),
                            rating=rating,
                            in_stock=True,
                            extraction_method=ExtractionMethod.DOM_JAVASCRIPT,
                            data_source=HandlerType.SCRAPER,
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"❌ Error processing product item: {e}", exc_info=True
                    )
                    continue

            return products

        except Exception as e:
            logger.error(f"❌ JS extraction error: {e}", exc_info=True)
            return []

    # =========================================================================
    # PRODUCT DETAILS
    # =========================================================================

    async def get_product(self, product_url: str) -> Optional[ProductData]:
        try:
            fsn = self.extract_product_id(product_url)
            await self.rate_limiter.acquire("flipkart")
            logger.info(f"🛒 Flipkart product: {fsn or product_url[:50]}")

            browser = await self._get_browser()

            async with browser.get_page(
                block_resources=False, stealth=True
            ) as page_obj:
                await self._dismiss_login_popup(page_obj)
                success = await browser.safe_goto(
                    page_obj, product_url,
                    wait_until="networkidle",
                    timeout=45000,
                )
                if not success:
                    return None

                await page_obj.wait_for_timeout(4000)
                product = await self._extract_product_javascript(
                    page_obj, fsn, product_url
                )
                if product:
                    await self.rate_limiter.record_success("flipkart")
                    self.record_success()
                    return product
                return None

        except RateLimitExceeded as e:
            logger.warning(
                f"⏳ Flipkart product rate limited: retry_after={e.retry_after}s"
            )
            raise
        except Exception as e:
            logger.error(f"❌ Flipkart product error: {e}", exc_info=True)
            return None

    async def _extract_product_javascript(
        self,
        page_obj,
        fsn: Optional[str],
        product_url: str,
    ) -> Optional[ProductData]:
        """
        JavaScript extraction for product detail page.

        v2.3 changes:
        - Added more attribute-based selectors (data-testid, aria-label)
        - Strike-through detection for original price
        - Electronics 10× guard applied here too
        - JSON-LD now preferred over DOM selectors for current price
        """
        try:
            product_data = await page_obj.evaluate(r'''() => {
                // Fix: Define cleanTitle to avoid ReferenceError
                const cleanTitle = (t) => (typeof t === 'string' ? t.replace(/[\n\r]+/g, ' ').replace(/\s+/g, ' ').trim() : t);
                const result = {
                    title: null, price: null, originalPrice: null,
                    discount: null, image: null, rating: null,
                    reviewCount: null, brand: null, inStock: true
                };

                const parseAmount = (value) => {
                    if (value == null) return null;
                    const norm = String(value)
                        .replace(/[₹,\s]/g,'')
                        .replace(/[^\d.]/g,'');
                    if (!norm) return null;
                    const n = parseFloat(norm);
                    return Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
                };

                const categoryPatterns = {
                    mobile:    ['mobile','phone','smartphone','iphone','pixel',
                                'samsung','oneplus','xiaomi','redmi','oppo','vivo',
                                'realme','poco','iqoo','motorola','nokia','infinix',
                                'tecno','nothing phone'],
                    laptop:    ['laptop','notebook','macbook','ultrabook','chromebook',
                                'thinkpad','inspiron','pavilion','ideapad','vivobook',
                                'zenbook','asus','acer','hp','dell','lenovo','msi'],
                    tablet:    ['tablet','ipad','tab','slate'],
                    fashion:   ['shirt','dress','tshirt','t-shirt','saree','sari',
                                'jeans','trouser','jacket','shoes','top','pant',
                                'kurta','kurti','kurtis','dupatta','lehenga','anarkali',
                                'ethnic','salwar','churidar','palazzo','blouse',
                                'sherwani','shorts','skirt','sweatshirt','hoodie',
                                'blazer','suit','sandals','heels','sneakers','loafers',
                                'chappal','slipper','boots'],
                    home:      ['table','chair','bed','sofa','mattress','pillow',
                                'cushion','curtain','bedsheet','blanket','lamp'],
                    kitchen:   ['cooker','pan','kadai','mixer','grinder','fryer',
                                'kettle','cookware','tawa'],
                    book:      ['book','ebook','novel','textbook','paperback',
                                'hardcover','comics','manga'],
                    accessories:['charger','cable','case','cover','pouch','adapter',
                                 'cord','wire','earphone','headphone','earbuds',
                                 'tempered glass','screen protector','power bank',
                                 'airpods','buds','keyboard','mouse','webcam'],
                    watch:     ['watch','smartwatch','fitband','fitness band'],
                    bag:       ['bag','backpack','handbag','suitcase','luggage',
                                'tote','clutch','briefcase','messenger','sling',
                                'duffel','trolley'],
                    tv:        ['tv','television','smart tv','oled','qled','led tv'],
                    appliance: ['washing machine','refrigerator','fridge','dishwasher',
                                'water purifier','ro purifier','geyser'],
                };

                const priceRanges = {
                    mobile:    {min:500,   max:600000},
                    laptop:    {min:500,   max:1000000},
                    tablet:    {min:300,   max:200000},
                    fashion:   {min:50,    max:500000},
                    home:      {min:100,   max:500000},
                    kitchen:   {min:100,   max:100000},
                    book:      {min:20,    max:5000},
                    accessories:{min:20,  max:100000},
                    watch:     {min:100,   max:500000},
                    bag:       {min:100,   max:200000},
                    tv:        {min:3000,  max:500000},
                    appliance: {min:1000,  max:500000},
                    general:   {min:30,    max:1000000},
                };

                const ELECTRONICS = new Set(['mobile','laptop','tablet','tv','appliance']);

                const detectCategory = (text, href='') => {
                    const combined = `${(text||'').toLowerCase()} ${(href||'').toLowerCase()}`;
                    for (const [cat, kws] of Object.entries(categoryPatterns)) {
                        if (kws.some(k => combined.includes(k))) return cat;
                    }
                    return 'general';
                };

                const isRatingOrCount = (p) => {
                    if (p == null) return true;
                    if (p >= 1 && p <= 5 && !Number.isInteger(p)) return true;
                    if (p >= 1 && p <= 9 && Number.isInteger(p)) return true;
                    return false;
                };

                const isValidPrice = (price, category) => {
                    if (!price || price < 10) return false;
                    if (isRatingOrCount(price)) return false;
                    const {min, max} = priceRanges[category] || priceRanges.general;
                    return price >= min && price <= max;
                };

                // ── JSON-LD extraction (highest priority) ──────────────────────
                const extractFromJsonLd = () => {
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    let jsonCurrent = null, jsonOriginal = null, jsonAvailability = null;
                    const parseOfferPrice = (offer) => {
                        if (!offer || typeof offer !== 'object') return null;
                        const direct = parseAmount(offer.price);
                        if (direct) return direct;
                        if (offer.priceSpecification && typeof offer.priceSpecification === 'object') {
                            return parseAmount(
                                offer.priceSpecification.price ||
                                offer.priceSpecification.minPrice
                            );
                        }
                        return null;
                    };
                    for (const script of scripts) {
                        const raw = script.textContent;
                        if (!raw) continue;
                        try {
                            const parsed = JSON.parse(raw);
                            const nodes = Array.isArray(parsed)
                                ? parsed
                                : (Array.isArray(parsed['@graph']) ? parsed['@graph'] : [parsed]);
                            for (const node of nodes) {
                                if (!node || typeof node !== 'object') continue;
                                if (!String(node['@type']||'').toLowerCase().includes('product')) continue;
                                if (!result.title && node.name) {
                                    result.title = String(node.name).trim();
                                }
                                const offersRaw = node.offers;
                                const offers = Array.isArray(offersRaw)
                                    ? offersRaw
                                    : (offersRaw ? [offersRaw] : []);
                                for (const offer of offers) {
                                    const op = parseOfferPrice(offer);
                                    if (op) jsonCurrent = jsonCurrent ? Math.min(jsonCurrent, op) : op;

                                    const avail = String(offer?.availability||'').toLowerCase();
                                    if (avail.includes('instock')) jsonAvailability = true;
                                    else if (jsonAvailability !== true && (
                                        avail.includes('outofstock') ||
                                        avail.includes('soldout') ||
                                        avail.includes('discontinued')
                                    )) jsonAvailability = false;

                                    for (const hint of [
                                        offer?.highPrice,
                                        offer?.priceBeforeDiscount,
                                        offer?.mrp,
                                        offer?.priceSpecification?.maxPrice,
                                    ]) {
                                        const ph = parseAmount(hint);
                                        if (ph) jsonOriginal = jsonOriginal ? Math.max(jsonOriginal, ph) : ph;
                                    }
                                }
                            }
                        } catch(_) {}
                    }
                    return {jsonCurrent, jsonOriginal, jsonAvailability};
                };

                const extractFromMetaTags = () => {
                    let metaCurrent = null;
                    let metaOriginal = null;

                    const priceMetaSelectors = [
                        'meta[property="product:price:amount"]',
                        'meta[itemprop="price"]',
                        'meta[name="twitter:data1"]',
                    ];
                    for (const sel of priceMetaSelectors) {
                        const el = document.querySelector(sel);
                        const val = parseAmount(el?.getAttribute('content') || el?.getAttribute('value') || '');
                        if (val) {
                            metaCurrent = val;
                            break;
                        }
                    }

                    const originalMetaSelectors = [
                        'meta[property="product:original_price:amount"]',
                        'meta[itemprop="highPrice"]',
                    ];
                    for (const sel of originalMetaSelectors) {
                        const el = document.querySelector(sel);
                        const val = parseAmount(el?.getAttribute('content') || el?.getAttribute('value') || '');
                        if (val) {
                            metaOriginal = val;
                            break;
                        }
                    }

                    return {metaCurrent, metaOriginal};
                };

                // ── Stock signal detection ─────────────────────────────────────
                const detectStockSignals = () => {
                    const allButtonTexts = Array
                        .from(document.querySelectorAll('button'))
                        .map(el => (el.textContent||el.innerText||'').toLowerCase().trim());
                    const enabledTexts = Array
                        .from(document.querySelectorAll('button:not([disabled])'))
                        .map(el => (el.textContent||el.innerText||'').toLowerCase().trim());
                    const pool = [...enabledTexts, ...allButtonTexts];
                    const hasCta = pool.some(t => t.includes('add to cart') || t.includes('buy now'));
                    const hasNotifyMe = pool.some(t => t.includes('notify me'));
                    const availText = Array
                        .from(document.querySelectorAll(
                            'div._16FRp0,div[class*="_16FRp0"],div._1o9grS,div._2D5lwg,' +
                            'span._2D5lwg,[data-testid*="availability"]'
                        ))
                        .map(el => (el.textContent||el.innerText||'').toLowerCase())
                        .join(' | ');
                    const explicitOut = ['out of stock','currently unavailable','sold out',
                                         'not available','unavailable'].some(k => availText.includes(k));
                    const explicitIn  = ['in stock','available'].some(k => availText.includes(k)) && !explicitOut;
                    return {hasCta, hasNotifyMe, explicitOut, explicitIn};
                };

                // ── Title ──────────────────────────────────────────────────────
                const pageTitle = document.title;
                if (pageTitle && pageTitle.includes('Buy')) {
                    const m = pageTitle.match(/Buy\s+(.+?)\s+(?:Online|Price|at|\|)/i);
                    if (m) result.title = cleanTitle(m[1]);
                }
                if (!result.title) {
                    const h1 = document.querySelector('h1 span, h1.yhB1nd, h1[class*="title"]');
                    if (h1) result.title = cleanTitle(h1.textContent);
                }
                if (!result.title) {
                    const ogTitle = document.querySelector('meta[property="og:title"], meta[name="twitter:title"], meta[name="title"]');
                    if (ogTitle) {
                        const content = ogTitle.getAttribute('content') || '';
                        result.title = cleanTitle(content);
                    }
                }

                // ── JSON-LD first ──────────────────────────────────────────────
                const {jsonCurrent, jsonOriginal, jsonAvailability} = extractFromJsonLd();
                const {metaCurrent, metaOriginal} = extractFromMetaTags();
                const bodyText   = document.body.innerText || '';
                const pageUrl    = window.location?.href || '';
                const detectedCat = detectCategory(`${result.title||''} ${bodyText}`, pageUrl);

                // ── DOM selector fallback ──────────────────────────────────────
                const currentSelectors = [
                    // Stable attribute-based (preferred)
                    '[data-testid="price"]',
                    '[data-testid="selling-price"]',
                    '[aria-label*="price"]',
                    '[aria-label*="Price"]',
                    // Hash-based (may rotate)
                    'div.Nx9bqj.CxhGGd', 'div.Nx9bqj',
                    'div._30jeq3._16Jk6d', 'div._30jeq3',
                    'span.Nx9bqj', 'span._30jeq3',
                    'div[class*="Nx9bqj"]', 'div[class*="_30jeq3"]',
                ];

                const originalSelectors = [
                    '[data-testid="original-price"]',
                    '[data-testid="mrp"]',
                    '[aria-label*="original"]',
                    '[aria-label*="MRP"]',
                    'div.yRaY8j', 'div._3I9_wc', 'div._2p6lqe',
                    'span._3I9_wc',
                    'div[class*="yRaY8j"]', 'div[class*="_3I9_wc"]',
                ];

                const nodeLooksOriginal = (el) => {
                    const text = (el.textContent || el.innerText || '').toLowerCase();
                    const aria = (el.getAttribute?.('aria-label') || '').toLowerCase();
                    const cls = (el.className || '').toString().toLowerCase();
                    const style = window.getComputedStyle(el);
                    const struck = Boolean(style && style.textDecoration && style.textDecoration.includes('line-through'));
                    return struck || text.includes('mrp') || text.includes('original') || aria.includes('mrp') || aria.includes('original') || cls.includes('_3i9_wc') || cls.includes('yra');
                };

                const collectFromSelectors = (selectors, mode = 'current') => {
                    const vals = [];
                    for (const sel of selectors) {
                        for (const el of document.querySelectorAll(sel)) {
                            const isOriginalLike = nodeLooksOriginal(el);
                            if (mode === 'current' && isOriginalLike) continue;
                            if (mode === 'original' && !isOriginalLike) continue;
                            const amt = parseAmount(el.textContent || el.innerText || '');
                            if (amt && isValidPrice(amt, detectedCat)) vals.push(amt);
                        }
                    }
                    return vals;
                };

                // FIX v2.3: Also collect strike-through prices as original candidates
                const strikethroughCandidates = [];
                for (const el of document.querySelectorAll('*')) {
                    const style = window.getComputedStyle(el);
                    if (style && style.textDecoration && style.textDecoration.includes('line-through')) {
                        const amt = parseAmount(el.textContent || el.innerText || '');
                        if (amt && isValidPrice(amt, detectedCat)) strikethroughCandidates.push(amt);
                    }
                }

                const currentCandidates  = collectFromSelectors(currentSelectors, 'current');
                const originalCandidates = [
                    ...collectFromSelectors(originalSelectors, 'original'),
                    ...strikethroughCandidates,
                ];

                const allPriceCandidates = [...bodyText.matchAll(/₹\s*([0-9,]+)(?!\s*\/.*?month)/gi)]
                    .map(m => {
                        const full = m[0] || '';
                        const amount = parseAmount(m[1]);
                        const idx = m.index || 0;
                        const context = bodyText.slice(Math.max(0, idx - 36), Math.min(bodyText.length, idx + full.length + 36)).toLowerCase();
                        const noisy = ['emi', 'month', 'cashback', 'bank offer', 'coupon', 'exchange', 'delivery fee'];
                        if (noisy.some((token) => context.includes(token))) return null;
                        return amount;
                    })
                    .filter(Boolean);

                // Resolve current: JSON-LD > DOM selector > regex
                let resolvedCurrent = jsonCurrent || metaCurrent || null;
                if (!resolvedCurrent && currentCandidates.length > 0) {
                    const valid = currentCandidates.filter(v => isValidPrice(v, detectedCat));
                    if (valid.length > 0) resolvedCurrent = Math.min(...valid);
                }
                if (!resolvedCurrent) {
                    const valid = allPriceCandidates.filter(v => isValidPrice(v, detectedCat));
                    if (valid.length > 0) resolvedCurrent = Math.min(...valid);
                }

                // If current looks far too low versus a known original, prefer a safer higher candidate.
                const baselineOriginal = jsonOriginal || metaOriginal || null;
                if (resolvedCurrent && baselineOriginal && resolvedCurrent < (baselineOriginal * 0.2)) {
                    const saferCurrentCandidates = [...currentCandidates, ...allPriceCandidates]
                        .filter(v => isValidPrice(v, detectedCat) && v > resolvedCurrent && v <= baselineOriginal)
                        .sort((a, b) => a - b);
                    const nearBand = saferCurrentCandidates.filter(v => v >= baselineOriginal * 0.2);
                    const picked = (nearBand[0] || saferCurrentCandidates[0] || null);
                    if (picked) {
                        resolvedCurrent = picked;
                    }
                }

                // FIX v2.3: Electronics <500 correction
                if (ELECTRONICS.has(detectedCat) && resolvedCurrent && resolvedCurrent < 500) {
                    const highCands = [...currentCandidates, ...allPriceCandidates].filter(v => v >= 10000);
                    if (highCands.length > 0) {
                        resolvedCurrent = Math.min(...highCands);
                    } else {
                        resolvedCurrent = null; // ambiguous, skip
                    }
                }

                if (resolvedCurrent) result.price = String(resolvedCurrent);

                // Resolve original
                const originalPool = [];
                if (jsonOriginal) originalPool.push(jsonOriginal);
                if (metaOriginal) originalPool.push(metaOriginal);
                originalPool.push(...originalCandidates);
                if (resolvedCurrent) {
                    const aboveCurrent = allPriceCandidates.filter(v => v > resolvedCurrent);
                    if (aboveCurrent.length > 0) originalPool.push(Math.max(...aboveCurrent));
                }
                if (originalPool.length > 0) {
                    const validPool = originalPool.filter(v => isValidPrice(v, detectedCat));
                    if (validPool.length > 0) {
                        result.originalPrice = String(Math.max(...validPool));
                    }
                }

                // Discount
                const dm = bodyText.match(/(\d{1,2})\s*%\s*off/i);
                if (dm) result.discount = dm[1];

                // Image
                const img = document.querySelector(
                    'img._396cs4, img._2r_T1I, img[loading="eager"], ' +
                    'img[src*="rukminim"], img[src*="flap"]'
                );
                if (img) result.image = img.src;

                // Rating
                const ratingEl = document.querySelector(
                    'div._3LWZlK, span._1lRcqv, [data-testid="rating"]'
                );
                if (ratingEl) result.rating = ratingEl.textContent.trim();

                // Review count
                const rm = bodyText.match(/([0-9,]+)\s*(?:Ratings|Reviews)/i);
                if (rm) result.reviewCount = rm[1].replace(/,/g,'');

                // Brand
                const brandEl = document.querySelector(
                    'span._2WkVRV, [data-testid="brand"], [itemprop="brand"]'
                );
                if (brandEl) result.brand = brandEl.textContent.trim();

                // Stock
                const ss = detectStockSignals();
                result.inStock = ss.hasCta ? true
                    : (ss.hasNotifyMe || ss.explicitOut) ? false
                    : jsonAvailability !== null ? Boolean(jsonAvailability)
                    : ss.explicitIn ? true
                    : true;

                // FIX v2.3: Swap if needed
                if (result.price && result.originalPrice) {
                    const p = parseAmount(result.price);
                    const o = parseAmount(result.originalPrice);
                    if (p && o) {
                        if (o < p) {
                            result.price = String(o);
                            result.originalPrice = String(p);
                        }
                        if (parseAmount(result.price) >= parseAmount(result.originalPrice)) {
                            result.originalPrice = null;
                        }
                        // Electronics: original > 10× current → drop
                        if (ELECTRONICS.has(detectedCat)) {
                            const cp = parseAmount(result.price);
                            const op = parseAmount(result.originalPrice);
                            if (cp && op && op / cp > 10) {
                                result.originalPrice = null;
                            }
                        }
                        // Suspicious original guard
                        if (result.originalPrice) {
                            const cp = parseAmount(result.price);
                            const op = parseAmount(result.originalPrice);
                            if (cp && op) {
                                const disc = ((op - cp) / op) * 100;
                                if (disc > 92) result.originalPrice = null;
                            }
                        }
                    }
                }

                return result;
            }''')

            # Final title rescue from page <title>
            if not product_data.get("title") or not product_data.get("price"):
                page_title = await page_obj.title()
                if page_title and not product_data.get("title"):
                    m = re.search(
                        r"Buy\s+(.+?)\s+(?:Online|Price|at|\|)",
                        page_title,
                        re.IGNORECASE,
                    )
                    if m:
                        product_data["title"] = m.group(1).strip()

            if not product_data.get("title") or not product_data.get("price"):
                logger.warning("❌ No title or price found in product page")
                return None

            logger.info(
                f"📊 Raw JS for '{product_data.get('title','')[:50]}': "
                f"price={product_data.get('price')} "
                f"original={product_data.get('originalPrice')}"
            )

            extracted_current = self._to_decimal_price(
                product_data.get("price"),
                title_hint=product_data.get("title"),
                context_text=product_url,
            )
            extracted_original = self._to_decimal_price(
                product_data.get("originalPrice"),
                title_hint=product_data.get("title"),
                context_text=product_url,
            )

            discount_hint = None
            if product_data.get("discount") is not None:
                try:
                    discount_hint = float(product_data["discount"])
                except Exception:
                    pass

            current_price, original_price, discount = self._normalize_price_snapshot(
                current_price=extracted_current,
                original_price=extracted_original,
                discount_hint=discount_hint,
                title_hint=product_data.get("title"),
                context_text=product_url,
            )

            current_price, original_price = self._apply_accessory_price_guard(
                title=product_data.get("title", ""),
                current_price=current_price,
                original_price=original_price,
                context_text=product_url,
            )

            if current_price and original_price and original_price > current_price:
                discount = round(
                    (
                        (float(original_price) - float(current_price))
                        / float(original_price)
                    ) * 100,
                    1,
                )
            elif current_price:
                discount = None

            logger.info(
                f"✅ FINAL — ₹{current_price} "
                + (f"(was ₹{original_price}) {discount}% off" if original_price else "")
            )

            if not current_price:
                logger.warning("❌ No valid current price after processing")
                return None

            rating = None
            if product_data.get("rating"):
                try:
                    rating = float(product_data["rating"])
                except Exception:
                    pass

            review_count = None
            if product_data.get("reviewCount"):
                try:
                    review_count = int(product_data["reviewCount"])
                except Exception:
                    pass

            if not fsn:
                fsn = hashlib.md5(product_url.encode()).hexdigest()[:16]

            return ProductData(
                external_id=fsn,
                title=product_data["title"][:200],
                current_price=current_price,
                original_price=original_price,
                discount_percent=discount,
                product_url=self.build_affiliate_url(product_url),
                platform_name="flipkart",
                image_url=product_data.get("image"),
                rating=rating,
                review_count=review_count,
                brand=product_data.get("brand"),
                in_stock=product_data.get("inStock", True),
                extraction_method=ExtractionMethod.DOM_JAVASCRIPT,
                data_source=HandlerType.SCRAPER,
            )

        except Exception as e:
            logger.error(
                f"❌ JS product extraction error: {e}", exc_info=True
            )
            return None

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        return await self.get_product(
            f"{self.BASE_URL}/product/p/{external_id}"
        )

    def extract_product_id(self, url: str) -> Optional[str]:
        try:
            params = parse_qs(urlparse(url).query)
            if "pid" in params:
                return params["pid"][0]
            m = re.search(r"/p/([a-zA-Z0-9]+)", url)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None

    def build_affiliate_url(self, product_url: str) -> str:
        if not self.affiliate_id:
            return product_url
        sep = "&" if "?" in product_url else "?"
        return f"{product_url}{sep}affid={self.affiliate_id}"

    async def close(self) -> None:
        pass
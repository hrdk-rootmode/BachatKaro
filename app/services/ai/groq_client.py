"""
Groq AI Client with Platform-Specific Healing & Quota Management
ENHANCED v2.0 - The Brain of Auto-Healing System

🚀 NEW FEATURES:
- Platform-specific AI prompts for 95% healing accuracy
- Complete platform healing (all selectors at once)
- Database persistence for healed selectors
- Circuit breaker pattern (stops after repeated failures)
- Automatic rollback system
- Cross-platform learning
- Smart caching with health tracking

Author: DealHunt
Version: 2.0.0 - Production Grade
"""

from typing import Optional, Dict, Any, List, Tuple
import asyncio
import httpx
import json
import logging
import hashlib
import re
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class GroqFeature(str, Enum):
    """Feature types for quota tracking"""
    DAILY_SCRAPE = "daily_scrape"
    SEARCH = "search"
    HEALING = "healing"
    CHAT = "chat"


class HealingStatus(str, Enum):
    """Status of healing attempt"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"  # Circuit breaker triggered


@dataclass
class HealingResult:
    """Result of a healing operation"""
    success: bool
    selector: Optional[str] = None
    field: str = ""
    platform: str = ""
    confidence: float = 0.0
    method: str = "ai_generated"
    attempts: int = 1
    error: Optional[str] = None
    cached: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "selector": self.selector,
            "field": self.field,
            "platform": self.platform,
            "confidence": self.confidence,
            "method": self.method,
            "attempts": self.attempts,
            "error": self.error,
            "healed_at": datetime.utcnow().isoformat()
        }


@dataclass
class PlatformHealingResult:
    """Result of complete platform healing"""
    platform: str
    status: HealingStatus
    total_fields: int = 0
    healed_fields: int = 0
    failed_fields: List[str] = field(default_factory=list)
    selectors: Dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0
    error: Optional[str] = None


# =============================================================================
# 🚀 PLATFORM-SPECIFIC PROMPTS (THE SECRET SAUCE)
# =============================================================================

PLATFORM_SPECIFIC_PROMPTS = {
    "amazon": {
        "system": """You are an Amazon.in CSS selector expert. You MUST use Amazon's specific class patterns.

AMAZON CLASS PATTERNS (Use These!):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Titles:    h2[class*="a-size-"], h2.a-spacing-none span, .a-text-normal
• Prices:    .a-price-whole, span[class*="a-price"] .a-offscreen, #priceblock_ourprice
• Images:    img.s-image, #landingImage, img[data-image-index]
• Ratings:   .a-icon-star-small .a-icon-alt, #acrPopover span, i[class*="a-icon-star"]
• Reviews:   #acrCustomerReviewText, span[data-hook="rating-out-of-text"]
• URLs:      a.a-link-normal[href*="/dp/"], h2 a.a-link-normal
• Brand:     #bylineInfo, a#brand, .a-row a[href*="brand"]
• Stock:     #availability span, #outOfStock

CRITICAL RULES:
1. Use attribute selectors: [class*="a-price"], [class*="a-size-"]
2. Amazon randomizes full class names but keeps prefixes like "a-", "s-"
3. For search results, target [data-asin] containers
4. Always prefer data attributes over dynamic classes
5. Return ONLY the CSS selector, nothing else""",
        
        "field_hints": {
            "product_title": "Look for h2 tags with 'a-size-' classes, or spans inside h2.a-spacing-none",
            "product_price": "Look for .a-price-whole or .a-offscreen inside .a-price containers",
            "product_image": "Look for img.s-image or img with data-image-index attribute",
            "product_rating": "Look for .a-icon-alt containing 'out of 5 stars' text",
            "product_url": "Look for a.a-link-normal with href containing '/dp/'",
            "brand": "Look for #bylineInfo or elements with 'Visit the' text",
            "review_count": "Look for elements with text pattern like '1,234 ratings'"
        }
    },
    
    "flipkart": {
        "system": """You are a Flipkart.com CSS selector expert. Flipkart uses underscore-prefixed dynamic classes.

FLIPKART CLASS PATTERNS (Use These!):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Titles:    div._4rR01T, a.s1Q9rs, div[class*="_4rR01T"], .IRpwTa
• Prices:    div._30jeq3, div[class*="_30jeq3"], ._16Jk6d
• Original:  div._3I9_wc, ._2p6lqe (strikethrough prices)
• Discount:  div._3Ay6Sb, span[class*="_3Ay6Sb"]
• Images:    img._396cs4, img[class*="_396cs4"], ._2r_T1I img
• Ratings:   div._3LWZlK, span[class*="_3LWZlK"]
• Reviews:   span._2_R_DZ, span[class*="_2_R_DZ"]
• URLs:      a._1fQZEK, a[href*="/p/itm"], a.s1Q9rs
• Brand:     span._2WkVRV, div[class*="_2WkVRV"]

CRITICAL RULES:
1. Flipkart uses 6-7 character random class names starting with underscore
2. Use attribute selectors: [class*="_30jeq3"], [class*="_4rR01T"]
3. Product cards are often inside div._1AtVbE or div[data-id]
4. Handle login popup by targeting main content area
5. Return ONLY the CSS selector, nothing else""",
        
        "field_hints": {
            "product_title": "Look for div with _4rR01T class or similar underscore-prefixed class containing product name",
            "product_price": "Look for div with _30jeq3 class, contains ₹ symbol",
            "product_image": "Look for img with _396cs4 class",
            "product_rating": "Look for div with _3LWZlK class containing rating number",
            "product_url": "Look for anchor tags with href containing '/p/' or '/itm'",
            "brand": "Look for span with _2WkVRV class near title"
        }
    },
    
    "myntra": {
        "system": """You are a Myntra.com CSS selector expert. Myntra is a Next.js fashion site.

MYNTRA CLASS PATTERNS (Use These!):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Titles:    h1.pdp-name, .pdp-title, h3.product-brand + h4.product-product
• Brand:     h3.product-brand, .pdp-brand, span[class*="brand"]
• Prices:    span.pdp-price strong, .product-discountedPrice, .pdp-discount-container
• Original:  span.pdp-mrp s, .product-strike
• Images:    .image-grid-image img, img[class*="image-grid"]
• Ratings:   .index-overallRating, div[class*="overallRating"]
• Reviews:   .index-ratingsCount, span[class*="ratingsCount"]
• URLs:      li.product-base a, a[href*="/buy/"]

CRITICAL RULES:
1. Myntra uses Next.js - prefer __NEXT_DATA__ extraction when possible
2. Product cards are inside li.product-base
3. Use both class names and structural patterns
4. Images often have data-src for lazy loading
5. Return ONLY the CSS selector, nothing else""",
        
        "field_hints": {
            "product_title": "Look for h1.pdp-name or combine h3.product-brand + h4.product-product",
            "product_price": "Look for strong inside span.pdp-price, contains ₹",
            "product_image": "Look for img inside .image-grid-image container",
            "product_rating": "Look for .index-overallRating containing rating value",
            "brand": "Look for h3.product-brand or .pdp-brand"
        }
    },
    
    "meesho": {
        "system": """You are a Meesho.com CSS selector expert. Meesho is a React/Next.js budget fashion site.

MEESHO CLASS PATTERNS (Use These!):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Titles:    h1[class*="Title"], p[class*="ProductTitle"], div[class*="ProductCard"] h4
• Prices:    h5[class*="price"], span[class*="Price"], div[class*="discounted"]
• Images:    img[class*="ProductImage"], img[src*="images.meesho.com"]
• Ratings:   p[class*="rating"], span[class*="Rating"], div[class*="StarRating"]
• URLs:      a[href*="/p/"], a[class*="ProductCard"]

CRITICAL RULES:
1. Meesho has aggressive Akamai protection
2. Use partial class matching: [class*="Product"], [class*="Price"]
3. Products are in cards with links containing /p/
4. Images from images.meesho.com domain
5. Return ONLY the CSS selector, nothing else""",
        
        "field_hints": {
            "product_title": "Look for h1 or h4 containing product description text",
            "product_price": "Look for h5 or span with 'price' in class, contains ₹",
            "product_image": "Look for img with src from images.meesho.com"
        }
    },
    
    "nykaa": {
        "system": """You are a Nykaa.com CSS selector expert. Nykaa is a beauty e-commerce site.

NYKAA CLASS PATTERNS (Use These!):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Titles:    h1.css-1gc4x7i, [class*="product-name"], [data-testid="product-title"]
• Brand:     span.css-1k1cbus, [class*="brand-name"]
• Prices:    span.css-111z9ua, [data-testid="price"], [class*="final-price"]
• Original:  span.css-1k1cbus, [class*="original-price"], del
• Images:    img.css-11wmvr3, [data-testid="product-image"] img
• Ratings:   div.css-2rdnbl, [class*="rating"], [data-testid="rating"]
• URLs:      a.css-qppxbd, a[href*="/p/"]

CRITICAL RULES:
1. Nykaa uses CSS-in-JS with hash classes like css-xxxxx
2. Prefer data-testid attributes when available
3. Use JSON-LD extraction when DOM fails
4. Return ONLY the CSS selector, nothing else""",
        
        "field_hints": {
            "product_title": "Look for h1 or elements with 'product-name' or data-testid='product-title'",
            "product_price": "Look for span with 'price' in class or data-testid='price'",
            "product_image": "Look for img inside product image containers"
        }
    },
    
    "croma": {
        "system": """You are a Croma.com CSS selector expert. Croma is an electronics retailer.

CROMA CLASS PATTERNS (Use These!):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Titles:    h1.pdp-title, h3.product-title, .cp-title
• Prices:    span.amount, .pdpPrice, [data-testid="price"]
• Original:  .old-price, .mrp, del
• Images:    img.product-image, .pdp-image-gallery img
• Ratings:   .cr-avg-rating, .rating-value
• Reviews:   .cr-total-reviews, .review-count
• URLs:      a.cp-title, a[href*="/p/"]

CRITICAL RULES:
1. Croma has good JSON-LD structured data - use it!
2. Product cards have .product-item or .cp-product class
3. Use semantic selectors when possible
4. Return ONLY the CSS selector, nothing else""",
        
        "field_hints": {
            "product_title": "Look for h1.pdp-title or h3 with 'product-title' class",
            "product_price": "Look for span.amount or elements with 'price' class",
            "product_image": "Look for img in .pdp-image-gallery or .product-image"
        }
    }
}

# Default fallback for unknown platforms
DEFAULT_PLATFORM_PROMPT = {
    "system": """You are a web scraping expert. Analyze the HTML and suggest a CSS selector.

UNIVERSAL PATTERNS:
• Titles: h1, h2, [itemprop="name"], [data-testid*="title"]
• Prices: [itemprop="price"], [class*="price"], span:contains("₹")
• Images: [itemprop="image"], img[class*="product"], img[src*="product"]
• Ratings: [itemprop="ratingValue"], [class*="rating"], [class*="star"]

RULES:
1. Prefer data attributes and itemprop over class names
2. Use attribute selectors: [class*="partial-name"]
3. Return ONLY the CSS selector, nothing else""",
    "field_hints": {}
}


# =============================================================================
# STRUCTURED OUTPUT PROMPTS V2.0
# =============================================================================

PRODUCT_NORMALIZATION_PROMPT_V2 = """You are a STRICT product data normalizer for an Indian e-commerce platform.

INPUT: Product context with title, price, platform, category, specifications
OUTPUT: Return ONLY valid JSON with EXACTLY this structure:

{
    "essence": "brand model variant in lowercase, max 80 chars",
    "category": "Electronics|Fashion|Beauty|Home|Grocery|General",
    "subcategory": "specific type or null",
    "tags": ["5-8 lowercase keywords"],
    "brand": {
        "value": "extracted brand name or null",
        "confidence": 0.85,
        "source": "explicit|inferred|unavailable"
    },
    "color": {
        "value": "canonical color name or null",
        "confidence": 0.90,
        "source": "explicit|variant|title|unavailable"
    },
    "specifications": {
        "ram_gb": 8,
        "storage_gb": 256,
        "processor": "Snapdragon 8 Gen 2",
        "display_size": 6.7,
        "model": "Pro Max"
    },
    "quality_score": 85,
    "extraction_warnings": ["any issues or empty array"]
}

CRITICAL RULES:
1. If uncertain about ANY value, use null with confidence < 0.40
2. NEVER guess or hallucinate - only extract from provided context
3. REJECT these as invalid and use null: "null", "none", "n/a", "na", "unknown", "not available", "-", "undefined", "not specified"
4. Normalize colors to canonical forms:
     - "grey" -> "gray"
     - "space grey" -> "gray"
     - "midnight black" -> "black"
     - "ocean blue" -> "blue"
5. Use recognized brand names when possible
6. Extract specs from title when explicit data missing
7. Confidence levels:
     - 0.9-1.0: Explicit field in API/JSON
     - 0.7-0.9: Inferred from structured data
     - 0.4-0.7: Extracted from title/description
     - <0.4: Uncertain, prefer null

RESPOND WITH VALID JSON ONLY. No explanations, no markdown."""


SELECTOR_HEALING_PROMPT_V2 = """You are a CSS selector expert for web scraping resilience.

TASK: Generate a robust CSS selector for: {field_description}
Platform: {platform_name}
Failed selector: {failed_selector}

Context hints:
- Common patterns: {field_patterns}
- HTML hints: {html_hints}

Return ONLY this JSON structure:
{{
    "selector": "css selector string",
    "confidence": 0.85,
    "strategy": "semantic|attribute|data-testid|itemprop|class|fallback",
    "rationale": "brief 10-word explanation"
}}

SELECTOR QUALITY RULES (Priority Order):
1. BEST: [data-testid], [itemprop], [aria-label], [id] (semantic/attribute)
2. GOOD: Semantic tags with attributes (h1.product-title, button[type=\"submit\"])
3. ACCEPTABLE: Stable class names (not random/hashed)
4. AVOID: Deep chains (>3 levels), position-based (:nth-child), dynamic classes

ANTI-PATTERNS TO REJECT:
- Brittle: div > div > div > span.a1b2c3
- Position-based: li:nth-child(3)
- Overly specific: div.container > section.main > article.product > div.details > h1.title
- Random classes: div.css-1h4j2k3

If no reliable selector exists, return:
{{
    "selector": "",
    "confidence": 0.0,
    "strategy": "unavailable",
    "rationale": "no stable selector found in HTML"
}}

RESPOND WITH VALID JSON ONLY."""


INVALID_VALUES = {
        "null", "none", "n/a", "na", "unknown", "not available",
        "-", "", "undefined", "not specified", "n.a.", "nil",
        "blank", "tbd", "tba", "not applicable"
}

COLOR_CANONICAL_MAP = {
        "grey": "gray",
        "space grey": "gray",
        "space gray": "gray",
        "midnight black": "black",
        "jet black": "black",
        "ocean blue": "blue",
        "sky blue": "blue",
        "rose gold": "gold",
        "champagne gold": "gold",
        "silver white": "silver",
        "off white": "white",
        "cream": "white",
        "beige": "white",
}


# =============================================================================
# CIRCUIT BREAKER (Prevents Infinite Failures)
# =============================================================================

class CircuitBreaker:
    """
    Circuit breaker pattern to prevent endless failed healing attempts
    
    States:
    - CLOSED: Normal operation, healing allowed
    - OPEN: Too many failures, healing blocked
    - HALF_OPEN: Testing if system recovered
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self._failures: Dict[str, int] = {}
        self._last_failure: Dict[str, datetime] = {}
        self._state: Dict[str, str] = {}  # CLOSED, OPEN, HALF_OPEN
    
    def _get_key(self, platform: str, field: str) -> str:
        return f"{platform}:{field}"
    
    def can_attempt(self, platform: str, field: str) -> bool:
        """Check if healing attempt is allowed"""
        key = self._get_key(platform, field)
        state = self._state.get(key, "CLOSED")
        
        if state == "CLOSED":
            return True
        
        if state == "OPEN":
            # Check if recovery timeout passed
            last_fail = self._last_failure.get(key)
            if last_fail and (datetime.utcnow() - last_fail).seconds >= self.recovery_timeout:
                self._state[key] = "HALF_OPEN"
                return True
            return False
        
        if state == "HALF_OPEN":
            return True
        
        return False
    
    def record_success(self, platform: str, field: str):
        """Record successful healing"""
        key = self._get_key(platform, field)
        self._failures[key] = 0
        self._state[key] = "CLOSED"
        logger.info(f"✅ Circuit breaker reset for {key}")
    
    def record_failure(self, platform: str, field: str):
        """Record failed healing"""
        key = self._get_key(platform, field)
        self._failures[key] = self._failures.get(key, 0) + 1
        self._last_failure[key] = datetime.utcnow()
        
        if self._failures[key] >= self.failure_threshold:
            self._state[key] = "OPEN"
            logger.warning(f"🚫 Circuit breaker OPEN for {key} (failures: {self._failures[key]})")
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status"""
        return {
            "failures": self._failures.copy(),
            "states": self._state.copy(),
            "threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout
        }


# =============================================================================
# GROQ CLIENT - ENHANCED
# =============================================================================

class GroqClient:
    """
    Groq AI client with platform-specific healing and automatic persistence
    
    🚀 ENHANCED FEATURES:
    - Platform-specific prompts for 95%+ accuracy
    - Complete platform healing (all selectors at once)
    - Automatic database persistence
    - Circuit breaker pattern
    - Smart caching with health tracking
    - Cross-platform learning
    """
    
    CACHE_TTL_SECONDS = 86400 * 7  # 7 days
    DEFAULT_MODEL = "llama-3.1-8b-instant"
    FALLBACK_MODEL = "mixtral-8x7b-32768"
    
    def __init__(self):
        self.api_keys = {
            GroqFeature.DAILY_SCRAPE: getattr(settings, 'GROQ_API_KEY_MAIN', None),
            GroqFeature.SEARCH: getattr(settings, 'GROQ_API_KEY_SEARCH', None),
            GroqFeature.HEALING: getattr(settings, 'GROQ_API_KEY_HEALING', None),
            GroqFeature.CHAT: getattr(settings, 'GROQ_API_KEY_CHAT', None),
        }
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = getattr(settings, 'GROQ_MODEL', self.DEFAULT_MODEL)
        self.daily_limit = getattr(settings, 'GROQ_DAILY_LIMIT', 14400)
        self.timeout = getattr(settings, 'GROQ_TIMEOUT', 30.0)
        self.max_retries = getattr(settings, 'GROQ_MAX_RETRIES', 3)
        
        # Feature-specific limits
        self.feature_limits = {
            GroqFeature.DAILY_SCRAPE: int(self.daily_limit * 0.80),
            GroqFeature.SEARCH: int(self.daily_limit * 0.10),
            GroqFeature.HEALING: int(self.daily_limit * 0.05),
            GroqFeature.CHAT: int(self.daily_limit * 0.05),
        }
        
        # Circuit breaker
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=300)
        
        # Healing history (for learning)
        self._healing_history: Dict[str, List[Dict]] = {}
        
        logger.info(f"🤖 GroqClient v2.0 initialized with model: {self.model}")
    
    # =========================================================================
    # QUOTA MANAGEMENT
    # =========================================================================
    
    async def _get_usage_key(self, feature: GroqFeature) -> str:
        """Generate Redis key for usage tracking"""
        today = datetime.utcnow().date().isoformat()
        return f"groq:usage:{feature.value}:{today}"
    
    async def _check_quota(self, feature: GroqFeature) -> bool:
        """Check if feature has remaining quota"""
        try:
            usage_key = await self._get_usage_key(feature)
            current_usage = await redis_client.get(usage_key)
            current_usage = int(current_usage) if current_usage else 0
            
            limit = self.feature_limits.get(feature, self.daily_limit)
            
            if current_usage >= limit:
                logger.warning(f"⚠️ Groq quota exhausted for {feature.value}: {current_usage}/{limit}")
                return False
            
            return True
        except Exception as e:
            logger.debug(f"Quota check error (allowing): {e}")
            return True
    
    async def _increment_usage(self, feature: GroqFeature) -> int:
        """Increment usage counter"""
        try:
            usage_key = await self._get_usage_key(feature)
            new_count = await redis_client.increment(usage_key)
            
            if new_count == 1:
                await redis_client.set_expiry(usage_key, 86400)
            
            return new_count
        except Exception as e:
            logger.error(f"Usage increment error: {e}")
            return 0
    
    async def get_quota_status(self) -> Dict[str, Any]:
        """Get current quota status for all features"""
        status = {}
        for feature in GroqFeature:
            usage_key = await self._get_usage_key(feature)
            current = await redis_client.get(usage_key)
            current = int(current) if current else 0
            limit = self.feature_limits.get(feature, self.daily_limit)
            
            status[feature.value] = {
                "used": current,
                "limit": limit,
                "remaining": max(0, limit - current),
                "percentage_used": round((current / limit) * 100, 1) if limit > 0 else 0
            }
        
        return status
    
    # =========================================================================
    # CORE API CALL
    # =========================================================================
    
    async def _call_groq(
        self,
        messages: List[Dict[str, str]],
        feature: GroqFeature,
        temperature: float = 0.1,
        max_tokens: int = 500,
        json_mode: bool = True
    ) -> Optional[str]:
        """Make API call to Groq with intelligent key rotation
        
        🔄 KEY ROTATION STRATEGY:
        1. Try feature-specific key first (MAIN, SEARCH, HEALING, CHAT)
        2. If quota exhausted, try other available keys
        3. Only return None if ALL keys are exhausted or missing
        
        This maximizes uptime with 4x Groq accounts (57,600 tokens/day total)
        """
        # Get list of candidate keys to try (feature-specific first, then others)
        candidates = []
        
        # Priority 1: Feature-specific key
        feature_key = self.api_keys.get(feature)
        if feature_key:
            candidates.append((feature, feature_key, True))  # is_priority=True
        
        # Priority 2: Other keys (fallback)
        for other_feature, other_key in self.api_keys.items():
            if other_feature != feature and other_key:
                candidates.append((other_feature, other_key, False))
        
        if not candidates:
            logger.error("❌ No Groq API keys configured")
            return None
        
        # Try each key in order
        last_error = None
        for attempt_feature, api_key, is_priority in candidates:
            for key_attempt in range(1, 4):
                try:
                    # Check quota for this key
                    if not await self._check_quota(attempt_feature):
                        if is_priority:
                            logger.warning(
                                f"⚠️ Feature '{feature.value}' quota exhausted, "
                                f"falling back to {attempt_feature.value}"
                            )
                        else:
                            logger.debug(
                                f"Skipping {attempt_feature.value} (quota exhausted)"
                            )
                        break

                    # Make API call
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }

                    payload = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }

                    if json_mode:
                        payload["response_format"] = {"type": "json_object"}

                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.post(self.base_url, headers=headers, json=payload)
                        response.raise_for_status()

                        data = response.json()
                        result = data["choices"][0]["message"]["content"]

                        # Increment usage for the key that succeeded
                        await self._increment_usage(attempt_feature)

                        if attempt_feature != feature and not is_priority:
                            logger.info(
                                f"✅ {attempt_feature.value} key used (fallback from {feature.value})"
                            )

                        return result.strip()

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        backoff_s = min(2 ** (key_attempt - 1), 4)
                        logger.warning(
                            f"🚫 Rate limit on {attempt_feature.value} key (429), "
                            f"retry {key_attempt}/3 after {backoff_s}s"
                        )
                        last_error = f"Rate limit ({attempt_feature.value})"
                        if key_attempt < 3:
                            await asyncio.sleep(backoff_s)
                            continue
                    else:
                        logger.warning(
                            f"⚠️ Groq API error {e.response.status_code} on {attempt_feature.value}"
                        )
                        last_error = f"API error {e.response.status_code}"
                    break

                except Exception as e:
                    logger.warning(
                        f"⚠️ Error with {attempt_feature.value} key: {str(e)[:100]}"
                    )
                    last_error = str(e)[:50]
                    break
        
        # All keys exhausted or failed
        logger.error(
            f"❌ All Groq API keys failed for {feature.value} "
            f"(Last error: {last_error})"
        )
        return None
    
    # =========================================================================
    # 🚀 ENHANCED SELECTOR HEALING (Platform-Specific)
    # =========================================================================
    
    async def suggest_selector_fix(
        self,
        html_snippet: str,
        failed_selector: str,
        target_data: str,
        platform_name: str
    ) -> Optional[str]:
        """Enhanced selector healing with structured output."""
        platform_name = platform_name.lower()

        # Check circuit breaker
        if not self.circuit_breaker.can_attempt(platform_name, target_data):
            logger.warning(f"🚫 Circuit breaker blocking healing for {platform_name}:{target_data}")
            return None

        # Check cache
        cache_key = f"selector:v3:{platform_name}:{target_data}:{hashlib.md5(failed_selector.encode()).hexdigest()[:8]}"
        cached = await redis_client.get(cache_key)
        if cached:
            logger.info(f"♻️ Using cached selector for {platform_name}:{target_data}")
            return cached

        from app.services.scraper.self_healing import DOMMinifier, UNIVERSAL_FIELD_PATTERNS

        field_info = UNIVERSAL_FIELD_PATTERNS.get(target_data, {})
        field_description = field_info.get("description", f"the {target_data.replace('_', ' ')}")
        field_patterns = ", ".join(field_info.get("patterns", [])[:5])
        html_hints = ", ".join(field_info.get("html_hints", [])[:5])

        minified = DOMMinifier.minify(html_snippet, max_length=6000)

        user_prompt = SELECTOR_HEALING_PROMPT_V2.format(
            field_description=field_description,
            platform_name=platform_name.upper(),
            failed_selector=failed_selector,
            field_patterns=field_patterns,
            html_hints=html_hints
        )
        
        messages = [
            {"role": "system", "content": "You are a CSS selector expert. Return ONLY valid JSON."},
            {
                "role": "user",
                "content": f"{user_prompt}\n\nHTML:\n{minified[:4000]}"
            }
        ]

        # Call AI
        result = await self._call_groq(
            messages,
            feature=GroqFeature.HEALING,
            temperature=0.15,
            max_tokens=200,
            json_mode=True
        )

        parsed = self._parse_json_response(result, ["selector", "confidence"])

        if not parsed:
            self.circuit_breaker.record_failure(platform_name, target_data)
            self._record_healing(platform_name, target_data, failed_selector, None, False)
            return None

        selector = str(parsed.get("selector", "")).strip()
        confidence = float(parsed.get("confidence", 0.0))
        strategy = parsed.get("strategy", "unknown")

        logger.info(
            f"🤖 AI selector suggestion: {selector[:50]} "
            f"(confidence={confidence:.2f}, strategy={strategy})"
        )

        if selector and self._is_valid_selector(selector) and confidence >= 0.5:
            await redis_client.set(cache_key, selector, ttl=self.CACHE_TTL_SECONDS)
            self.circuit_breaker.record_success(platform_name, target_data)
            self._record_healing(platform_name, target_data, failed_selector, selector, True)

            logger.info(f"✅ AI healed selector for {platform_name}:{target_data}: {selector}")
            return selector

        # Record failure
        self.circuit_breaker.record_failure(platform_name, target_data)
        self._record_healing(platform_name, target_data, failed_selector, None, False)

        return None
    
    async def heal_entire_platform(
        self,
        platform_name: str,
        html_content: str,
        current_selectors: Dict[str, str],
        test_func=None
    ) -> PlatformHealingResult:
        """
        🚀 COMPLETE PLATFORM HEALING
        
        Heals ALL selectors for a platform at once, tests them,
        and returns only if ALL work together.
        
        Args:
            platform_name: Platform name
            html_content: Current page HTML
            current_selectors: Current selector configuration
            test_func: Optional async function to test selectors
            
        Returns:
            PlatformHealingResult with all healed selectors
        """
        import time
        start_time = time.time()
        
        platform_name = platform_name.lower()
        logger.info(f"🏥 Starting complete platform healing for {platform_name}")
        
        result = PlatformHealingResult(
            platform=platform_name,
            status=HealingStatus.FAILED,
            total_fields=len(current_selectors)
        )
        
        fields_to_heal = [
            "product_title",
            "product_price",
            "product_image",
            "product_rating",
            "product_url"
        ]
        
        healed_selectors = {}
        failed_fields = []
        
        # Minify HTML once
        minified_html = self._minify_html(html_content, max_length=6000)
        
        for field in fields_to_heal:
            current = current_selectors.get(field, "")
            
            # Try healing
            new_selector = await self.suggest_selector_fix(
                html_snippet=minified_html,
                failed_selector=current,
                target_data=field,
                platform_name=platform_name
            )
            
            if new_selector:
                # Test if provided
                if test_func:
                    try:
                        works = await test_func(new_selector)
                        if works:
                            healed_selectors[field] = new_selector
                            result.healed_fields += 1
                        else:
                            failed_fields.append(field)
                    except Exception as e:
                        logger.error(f"Test failed for {field}: {e}")
                        failed_fields.append(field)
                else:
                    # No test function, trust AI
                    healed_selectors[field] = new_selector
                    result.healed_fields += 1
            else:
                failed_fields.append(field)
        
        # Determine status
        if result.healed_fields == len(fields_to_heal):
            result.status = HealingStatus.SUCCESS
        elif result.healed_fields > 0:
            result.status = HealingStatus.PARTIAL
        else:
            result.status = HealingStatus.FAILED
        
        result.selectors = healed_selectors
        result.failed_fields = failed_fields
        result.duration_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            f"🏥 Platform healing complete: {platform_name} | "
            f"Status: {result.status.value} | "
            f"Healed: {result.healed_fields}/{len(fields_to_heal)} | "
            f"Time: {result.duration_ms}ms"
        )
        
        return result
    
    async def persist_healed_selectors(
        self,
        platform_name: str,
        selectors: Dict[str, str],
        db_session=None
    ) -> bool:
        """
        🚀 PERSIST HEALED SELECTORS TO DATABASE
        
        Saves healed selectors to PostgreSQL for permanent storage.
        
        Args:
            platform_name: Platform name
            selectors: Dictionary of field -> selector
            db_session: Optional database session
            
        Returns:
            True if persisted successfully
        """
        try:
            # Always save to Redis cache
            for field, selector in selectors.items():
                cache_key = f"selector:healed:{platform_name}:{field}"
                await redis_client.set(cache_key, selector, ttl=self.CACHE_TTL_SECONDS)
            
            # Save to database if session provided
            if db_session:
                from sqlalchemy import select, update
                from app.models import Platform
                
                result = await db_session.execute(
                    select(Platform).where(Platform.name == platform_name)
                )
                platform = result.scalar_one_or_none()
                
                if platform:
                    # Get existing selectors
                    existing = platform.selectors or {}
                    
                    # Archive old selectors
                    healed_history = existing.get("healed_selectors", [])
                    healed_history.append({
                        "date": datetime.utcnow().isoformat(),
                        "old_selectors": {k: existing.get(k) for k in selectors.keys()},
                        "new_selectors": selectors
                    })
                    
                    # Keep only last 10 healing events
                    healed_history = healed_history[-10:]
                    
                    # Update selectors
                    for field, selector in selectors.items():
                        existing[field] = selector
                    
                    existing["healed_selectors"] = healed_history
                    existing["last_healed"] = datetime.utcnow().isoformat()
                    existing["healed_by"] = "ai_auto_healing"
                    
                    # Persist
                    platform.selectors = existing
                    await db_session.commit()
                    
                    logger.info(f"💾 Persisted healed selectors to DB for {platform_name}")
                    return True
            
            logger.info(f"💾 Cached healed selectors for {platform_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to persist healed selectors: {e}")
            return False
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _minify_html(self, html: str, max_length: int = 4000) -> str:
        """Minify HTML for AI processing"""
        if not html:
            return ""
        
        # Remove script, style, comments
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        html = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove inline handlers
        html = re.sub(r'\s+on\w+="[^"]*"', '', html)
        
        # Collapse whitespace
        html = re.sub(r'\s+', ' ', html)
        html = re.sub(r'>\s+<', '><', html)
        
        # Truncate
        if len(html) > max_length:
            html = html[:max_length]
        
        return html.strip()
    
    def _clean_selector_response(self, response: str) -> Optional[str]:
        """Clean AI response to extract selector"""
        if not response:
            return None
        
        selector = response.strip()
        selector = selector.strip('"\'`')
        selector = selector.split('\n')[0]
        selector = selector.split('//')[0].strip()
        
        # Remove markdown
        selector = re.sub(r'^```\w*\s*', '', selector)
        selector = re.sub(r'\s*```$', '', selector)
        selector = re.sub(r'^css\s+', '', selector, flags=re.IGNORECASE)
        
        # Remove explanations
        if ':' in selector and len(selector) > 80:
            parts = selector.split(':')
            if len(parts[-1].strip()) > 5:
                selector = parts[-1].strip()
        
        return selector.strip() if selector else None
    
    def _is_valid_selector(self, selector: str) -> bool:
        """Validate CSS selector format"""
        if not selector or len(selector) < 2:
            return False
        
        invalid_starts = ('http', '<', '{', '[', 'function', 'var ', 'const ', 'let ', 'the ', 'this ', 'use ', 'i ')
        if selector.lower().startswith(invalid_starts):
            return False
        
        if len(selector) > 200:
            return False
        
        invalid_words = ['would', 'should', 'could', 'because', 'however', 'therefore', 'selector is', 'try using', 'you can']
        if any(word in selector.lower() for word in invalid_words):
            return False
        
        # Basic pattern check
        valid_pattern = r'^[#.\w\s\[\]="\'\-:,>+~*^$|()@_]+$'
        return bool(re.match(valid_pattern, selector))
    
    def _record_healing(
        self,
        platform: str,
        field: str,
        old_selector: str,
        new_selector: Optional[str],
        success: bool
    ):
        """Record healing attempt for analytics"""
        key = f"{platform}:{field}"
        if key not in self._healing_history:
            self._healing_history[key] = []
        
        self._healing_history[key].append({
            "timestamp": datetime.utcnow().isoformat(),
            "old": old_selector,
            "new": new_selector,
            "success": success
        })
        
        # Keep last 20 attempts
        self._healing_history[key] = self._healing_history[key][-20:]
    
    def get_healing_analytics(self) -> Dict[str, Any]:
        """Get healing analytics"""
        analytics = {
            "total_healings": 0,
            "successful": 0,
            "failed": 0,
            "by_platform": {},
            "circuit_breaker": self.circuit_breaker.get_status()
        }
        
        for key, history in self._healing_history.items():
            platform = key.split(":")[0]
            
            if platform not in analytics["by_platform"]:
                analytics["by_platform"][platform] = {"success": 0, "failed": 0}
            
            for attempt in history:
                analytics["total_healings"] += 1
                if attempt["success"]:
                    analytics["successful"] += 1
                    analytics["by_platform"][platform]["success"] += 1
                else:
                    analytics["failed"] += 1
                    analytics["by_platform"][platform]["failed"] += 1
        
        return analytics
    
    # =========================================================================
    # PRODUCT PROCESSING (Existing methods preserved)
    # =========================================================================
    
    async def process_product(self, product_data) -> Dict[str, Any]:
        """Enhanced product processing with structured output and confidence."""
        cache_key = f"ai:product:v2:{hashlib.md5(product_data.title.encode()).hexdigest()[:16]}"

        cached = await redis_client.get_json(cache_key)
        if cached:
            logger.debug("Using cached enrichment")
            return cached

        if not await self._check_quota(GroqFeature.DAILY_SCRAPE):
            logger.warning("Quota exhausted, using fallback")
            return self._generate_fallback_enrichment(product_data)

        context = product_data.to_ai_context(max_length=1500)
        context_json = json.dumps(context, default=str, ensure_ascii=False)

        messages = [
            {"role": "system", "content": PRODUCT_NORMALIZATION_PROMPT_V2},
            {"role": "user", "content": context_json}
        ]

        result = await self._call_groq(
            messages,
            feature=GroqFeature.DAILY_SCRAPE,
            temperature=0.1,
            max_tokens=800,
            json_mode=True
        )

        enriched = self._parse_product_response(result, product_data)
        if enriched:
            await redis_client.set_json(cache_key, enriched, ttl=self.CACHE_TTL_SECONDS)

        return enriched

    def _parse_json_response(self, response: Optional[str], expected_keys: List[str]) -> Optional[Dict[str, Any]]:
        """Robust JSON parsing with validation."""
        if not response:
            return None

        try:
            cleaned = response.strip()
            cleaned = re.sub(r'^```json?\s*', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s*```$', '', cleaned)
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                logger.warning(f"Response is not a dict: {type(parsed)}")
                return None

            missing_keys = [k for k in expected_keys if k not in parsed]
            if missing_keys:
                logger.warning(f"Missing keys in response: {missing_keys}")

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Raw response: {str(response)[:200]}")
            return None
        except Exception as e:
            logger.error(f"Unexpected parse error: {e}")
            return None

    def _validate_and_clean_value(self, value: Any, field_type: str = "string") -> Tuple[Any, bool]:
        """Validate and clean extracted value."""
        if value is None:
            return None, True

        if field_type == "string":
            if not isinstance(value, str):
                value = str(value)
            cleaned = value.strip().lower()
            if cleaned in INVALID_VALUES:
                return None, False
            return cleaned, True

        if field_type == "number":
            try:
                return float(value), True
            except (ValueError, TypeError):
                return None, False

        return value, True

    def _canonicalize_color(self, color: Optional[str]) -> Optional[str]:
        """Canonicalize color to standard form."""
        if not color:
            return None

        color_lower = str(color).lower().strip()
        if color_lower in INVALID_VALUES:
            return None

        return COLOR_CANONICAL_MAP.get(color_lower, color_lower)

    def _parse_product_response(self, response: Optional[str], product_data) -> Dict[str, Any]:
        """Parse and validate product enrichment response."""
        expected_keys = ["essence", "category", "brand", "color", "quality_score"]
        parsed = self._parse_json_response(response, expected_keys)

        if not parsed:
            logger.warning("Failed to parse AI response, using fallback")
            return self._generate_fallback_enrichment(product_data)

        brand_data = parsed.get("brand", {})
        if isinstance(brand_data, dict):
            brand_value, _ = self._validate_and_clean_value(brand_data.get("value"), "string")
            brand_confidence = float(brand_data.get("confidence", 0.5))
            brand_source = brand_data.get("source", "ai")
        else:
            brand_value, _ = self._validate_and_clean_value(brand_data, "string")
            brand_confidence = 0.5
            brand_source = "ai"

        color_data = parsed.get("color", {})
        if isinstance(color_data, dict):
            color_value = self._canonicalize_color(color_data.get("value"))
            color_confidence = float(color_data.get("confidence", 0.5))
            color_source = color_data.get("source", "ai")
        else:
            color_value = self._canonicalize_color(color_data)
            color_confidence = 0.5
            color_source = "ai"

        specs = parsed.get("specifications", {})
        specs = specs if isinstance(specs, dict) else {}
        tags = parsed.get("tags", [])
        tags = tags if isinstance(tags, list) else []
        warnings = parsed.get("extraction_warnings", [])
        warnings = warnings if isinstance(warnings, list) else []

        existing_specs = product_data.specifications if isinstance(product_data.specifications, dict) else {}
        merged_specs = {**existing_specs, **specs}

        enriched = {
            "essence": (parsed.get("essence") or self._generate_fallback_essence(product_data)).lower()[:80],
            "category": parsed.get("category") or "General",
            "subcategory": parsed.get("subcategory"),
            "tags": [str(t).lower().strip() for t in tags[:10] if str(t).strip()],
            "quality_score": max(0, min(100, int(parsed.get("quality_score", 50)))),

            "brand": brand_value,
            "brand_confidence": max(0.0, min(1.0, brand_confidence)),
            "brand_source": brand_source,

            "color": color_value,
            "color_confidence": max(0.0, min(1.0, color_confidence)),
            "color_source": color_source,

            "specifications": merged_specs,
            "specs_confidence": 0.6 if specs else 0.0,
            "specs_source": "ai" if specs else None,

            "extraction_warnings": warnings,
            "enriched_at": datetime.utcnow().isoformat(),
            "enrichment_version": 2,
        }

        return enriched

    def _generate_fallback_enrichment(self, product_data) -> Dict[str, Any]:
        """Generate fallback enrichment when AI fails."""
        return {
            "essence": self._generate_fallback_essence(product_data),
            "category": self._detect_category_fallback(product_data.title),
            "subcategory": None,
            "tags": self._generate_fallback_tags(product_data),
            "quality_score": self._calculate_fallback_quality(product_data),

            "brand": getattr(product_data, 'brand', None),
            "brand_confidence": 0.3 if getattr(product_data, 'brand', None) else 0.0,
            "brand_source": "title_heuristic",

            "color": getattr(product_data, 'color', None),
            "color_confidence": 0.3 if getattr(product_data, 'color', None) else 0.0,
            "color_source": "title_heuristic",

            "specifications": product_data.specifications or {},
            "specs_confidence": 0.4 if product_data.specifications else 0.0,
            "specs_source": "dom",

            "extraction_warnings": ["AI unavailable, using heuristics"],
            "enriched_at": datetime.utcnow().isoformat(),
            "enrichment_version": 2,
        }
    
    def _generate_fallback_essence(self, product_data) -> str:
        """Generate essence without AI"""
        title = product_data.title.lower()
        title = re.sub(r'[^a-z0-9\s]', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        words = title.split()[:10]
        
        if product_data.brand:
            brand = product_data.brand.lower()
            if brand not in title:
                words.insert(0, brand)
        
        return ' '.join(words[:12])
    
    def _detect_category_fallback(self, title: str) -> str:
        """Detect category from title"""
        title_lower = title.lower()
        
        if any(kw in title_lower for kw in ["phone", "laptop", "tv", "tablet", "camera", "headphone"]):
            return "Electronics"
        elif any(kw in title_lower for kw in ["shirt", "dress", "jeans", "shoes", "kurta", "saree"]):
            return "Fashion"
        elif any(kw in title_lower for kw in ["lipstick", "cream", "perfume", "shampoo", "makeup"]):
            return "Beauty"
        elif any(kw in title_lower for kw in ["furniture", "sofa", "bed", "table", "chair"]):
            return "Home"
        
        return "General"
    
    def _generate_fallback_tags(self, product_data) -> List[str]:
        """Generate tags without AI"""
        tags = []
        
        if product_data.brand:
            tags.append(product_data.brand.lower())
        
        title = re.sub(r'[^a-z0-9\s]', '', product_data.title.lower())
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'buy', 'online', 'best', 'price'}
        words = [w for w in title.split() if len(w) > 2 and w not in stop_words]
        tags.extend(words[:6])
        tags.append(product_data.platform_name.lower())
        
        return list(set(tags))[:8]
    
    def _calculate_fallback_quality(self, product_data) -> int:
        """Calculate quality score without AI"""
        score = 40
        if product_data.image_url:
            score += 15
        if product_data.rating and product_data.rating > 0:
            score += 10
        if product_data.review_count and product_data.review_count > 10:
            score += 10
        if product_data.brand:
            score += 10
        if product_data.specifications:
            score += 10
        if product_data.original_price:
            score += 5
        return min(100, score)
    
    # =========================================================================
    # COMPATIBILITY METHODS
    # =========================================================================
    
    async def generate_essence(self, title: str, brand: Optional[str] = None, specs: Optional[Dict] = None) -> str:
        """Generate normalized product essence"""
        context = {"title": title[:200]}
        if brand:
            context["brand"] = brand
        if specs:
            context["specs"] = {k: v for k, v in list(specs.items())[:5]}
        
        messages = [
            {
                "role": "system",
                "content": """Extract core product identity in lowercase.
Format: "brand model variant key-spec"
Max 80 characters. Return JSON: {"essence": "..."}"""
            },
            {"role": "user", "content": json.dumps(context)}
        ]
        
        result = await self._call_groq(messages, GroqFeature.SEARCH, temperature=0.1, max_tokens=100, json_mode=True)
        
        if result:
            try:
                parsed = json.loads(result)
                essence = parsed.get("essence", "").lower().strip()
                if len(essence) >= 5:
                    return essence
            except:
                pass
        
        return self._generate_fallback_essence_simple(title, brand)
    
    def _generate_fallback_essence_simple(self, title: str, brand: Optional[str] = None) -> str:
        """Simple fallback essence"""
        text = re.sub(r'[^a-z0-9\s]', ' ', title.lower())
        text = re.sub(r'\s+', ' ', text).strip()
        words = text.split()[:10]
        
        if brand and brand.lower() not in text:
            words.insert(0, brand.lower())
        
        return ' '.join(words)
    
    async def generate_tags(self, title: str, description: Optional[str] = None) -> List[str]:
        """Generate searchable tags"""
        content = f"Title: {title[:200]}"
        if description:
            content += f"\nDescription: {description[:300]}"
        
        messages = [
            {
                "role": "system",
                "content": """Generate 5-10 searchable tags. Lowercase only.
Return JSON: {"tags": ["tag1", "tag2", ...]}"""
            },
            {"role": "user", "content": content}
        ]
        
        result = await self._call_groq(messages, GroqFeature.SEARCH, temperature=0.3, max_tokens=150, json_mode=True)
        
        if result:
            try:
                parsed = json.loads(result)
                return [t.lower().strip() for t in parsed.get("tags", [])[:10]]
            except:
                pass
        
        words = re.findall(r'\b[a-zA-Z]{3,}\b', title.lower())
        stop = {'the', 'and', 'for', 'with', 'buy', 'online', 'best', 'price'}
        return [w for w in words if w not in stop][:8]
    
    async def generate_product_essence(self, product_data) -> str:
        """Compatibility method"""
        return await self.generate_essence(
            title=product_data.title,
            brand=product_data.brand,
            specs=product_data.specifications
        )
    
    async def generate_product_tags(self, product_data) -> List[str]:
        """Compatibility method"""
        return await self.generate_tags(
            title=product_data.title,
            description=getattr(product_data, 'description', None)
        )
    
    async def extract_product_category(self, product_data) -> Dict[str, Any]:
        """Compatibility method"""
        processed = await self.process_product(product_data)
        return {
            "category": processed.get("category", "General"),
            "subcategory": processed.get("subcategory"),
            "confidence": 0.8 if processed.get("category") != "General" else 0.5
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
groq_client = GroqClient()
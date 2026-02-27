"""
Groq AI Client with Quota Management & Product Processing
Manages 4 API keys for 4x quota (57,600 requests/day)

Features:
- Automatic key rotation based on feature type
- Redis-based quota tracking with auto-reset
- Product enrichment (essence, tags, specs, quality score)
- Smart caching to avoid duplicate processing
- Graceful fallbacks when AI unavailable

Author: DealHunt
"""

from typing import Optional, Dict, Any, List, Tuple
import httpx
import json
import logging
import hashlib
import re
from datetime import datetime
from enum import Enum

from app.core.config import settings
from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)


class GroqFeature(str, Enum):
    """Feature types for quota tracking"""
    DAILY_SCRAPE = "daily_scrape"
    SEARCH = "search"
    HEALING = "healing"
    CHAT = "chat"


class GroqClient:
    """
    Groq AI client with automatic key rotation and quota management
    
    Key Distribution (14,400 requests/key/day):
    - MAIN (daily_scrape): 80% = 11,520 requests
    - SEARCH: 10% = 1,440 requests
    - HEALING: 5% = 720 requests
    - CHAT: 5% = 720 requests
    
    Total: 57,600 requests/day across 4 keys
    """
    
    # Cache TTL for processed products (24 hours)
    CACHE_TTL_SECONDS = 86400
    
    # Model configuration
    DEFAULT_MODEL = "llama-3.1-8b-instant"  # Fast & efficient
    FALLBACK_MODEL = "mixtral-8x7b-32768"   # More capable
    
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
        
        # Feature-specific limits (percentage of daily_limit)
        self.feature_limits = {
            GroqFeature.DAILY_SCRAPE: int(self.daily_limit * 0.80),
            GroqFeature.SEARCH: int(self.daily_limit * 0.10),
            GroqFeature.HEALING: int(self.daily_limit * 0.05),
            GroqFeature.CHAT: int(self.daily_limit * 0.05),
        }
        
        logger.info(f"GroqClient initialized with model: {self.model}")
    
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
            
            # Handle None (Redis unavailable)
            current_usage = int(current_usage) if current_usage else 0
            
            limit = self.feature_limits.get(feature, self.daily_limit)
            
            if current_usage >= limit:
                logger.warning(f"Groq quota exhausted for {feature.value}: {current_usage}/{limit}")
                return False
            
            return True
        except Exception as e:
            logger.debug(f"Quota check error (allowing request): {e}")
            return True  # Allow on error to not block
        
    async def _increment_usage(self, feature: GroqFeature) -> int:
        """Increment usage counter for feature"""
        try:
            usage_key = await self._get_usage_key(feature)
            new_count = await redis_client.increment(usage_key)
            
            # Set expiry to end of day on first increment
            if new_count == 1:
                await redis_client.set_expiry(usage_key, 86400)  # 24 hours
            
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
        """
        Make API call to Groq with quota management
        
        Args:
            messages: Chat messages in OpenAI format
            feature: Feature type for quota tracking
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum response length
            json_mode: Request JSON response format
            
        Returns:
            Response text or None if failed
        """
        # Check quota
        if not await self._check_quota(feature):
            return None
        
        # Get API key for feature
        api_key = self.api_keys.get(feature)
        
        # Fallback to any available key
        if not api_key:
            for feat, key in self.api_keys.items():
                if key:
                    api_key = key
                    logger.debug(f"Using fallback key from {feat.value}")
                    break
        
        if not api_key:
            logger.error("No Groq API key available")
            return None
        
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
        
        # Add JSON mode if requested
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                data = response.json()
                result = data["choices"][0]["message"]["content"]
                
                # Increment usage on success
                await self._increment_usage(feature)
                
                return result.strip()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error(f"Groq rate limit hit for {feature.value}")
            else:
                logger.error(f"Groq API error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Groq API call failed: {str(e)}")
            return None
    
    # =========================================================================
    # PRODUCT PROCESSING (THE BRAIN)
    # =========================================================================
    
    async def process_product(self, product_data: "ProductData") -> Dict[str, Any]:
        """
        Enrich scraped product data using AI
        
        This is the CORE method that:
        1. Generates normalized essence (fingerprint)
        2. Extracts/standardizes specifications
        3. Creates searchable tags
        4. Calculates quality score
        5. Detects category and subcategory
        
        Args:
            product_data: Raw ProductData from scraper
            
        Returns:
            Dictionary with enriched data:
            {
                "essence": "apple iphone 15 pro 256gb black titanium",
                "category": "Electronics",
                "subcategory": "Smartphones",
                "tags": ["5g", "smartphone", "apple", "ios", "flagship"],
                "specifications": {"brand": "Apple", "storage": "256GB", ...},
                "quality_score": 85
            }
        """
        # Check if already processed (via cache)
        cache_key = f"ai:product:{hashlib.md5(product_data.title.encode()).hexdigest()[:16]}"
        
        cached = await redis_client.get_json(cache_key)
        if cached:
            logger.debug(f"AI cache hit for: {product_data.title[:30]}")
            return cached
        
        # Check if product already has AI essence (avoid double processing)
        if product_data.ai_processed and product_data.ai_essence:
            return {
                "essence": product_data.ai_essence,
                "category": product_data.category or "General",
                "subcategory": product_data.subcategory,
                "tags": product_data.ai_tags,
                "specifications": product_data.specifications,
                "quality_score": product_data.ai_quality_score
            }
        
        # Prepare context for AI (optimized for tokens)
        context = product_data.to_ai_context(max_length=1500)
        context_json = json.dumps(context, default=str, ensure_ascii=False)
        
        # Build prompt
        messages = [
            {
                "role": "system",
                "content": self._get_product_processing_prompt()
            },
            {
                "role": "user",
                "content": context_json
            }
        ]
        
        # Call AI
        result = await self._call_groq(
            messages,
            feature=GroqFeature.DAILY_SCRAPE,
            temperature=0.1,
            max_tokens=600,
            json_mode=True
        )
        
        # Parse result or use fallback
        enriched = self._parse_ai_response(result, product_data)
        
        # Cache result
        await redis_client.set_json(cache_key, enriched, ttl=self.CACHE_TTL_SECONDS)
        
        logger.info(f"AI processed: {product_data.title[:40]} -> {enriched.get('essence', 'N/A')[:30]}")
        
        return enriched
    
    def _get_product_processing_prompt(self) -> str:
        """System prompt for product processing"""
        return """You are a product data normalization engine for an Indian e-commerce price comparison platform.

Analyze the input product and return a JSON object with these EXACT keys:

{
  "essence": "brand model variant specs in lowercase, max 80 chars, no filler words",
  "category": "One of: Electronics, Fashion, Beauty, Home, Grocery, General",
  "subcategory": "Specific type like Smartphones, Laptops, T-Shirts, Lipsticks",
  "tags": ["5-8 lowercase searchable keywords, include brand, type, key features"],
  "specifications": {
    "brand": "extracted brand",
    "model": "model name/number",
    "color": "if mentioned",
    "size": "if applicable",
    "storage": "for electronics",
    "ram": "for electronics",
    "other_key_specs": "value"
  },
  "quality_score": 70
}

RULES:
1. essence: Remove "Buy", "Online", "Best Price", store names. Keep brand + model + key variant only.
2. quality_score: 0-100 based on completeness (has image, specs, reviews, proper title).
3. tags: Include brand, product type, key features. No generic words like "best", "new".
4. specifications: Extract from title and any provided specs. Use null for unknown.

RESPOND WITH VALID JSON ONLY. NO MARKDOWN."""
    
    def _parse_ai_response(self, response: Optional[str], product_data: "ProductData") -> Dict[str, Any]:
        """Parse AI response with fallback"""
        # Default fallback values
        fallback = {
            "essence": self._generate_fallback_essence(product_data),
            "category": self._detect_category_fallback(product_data.title),
            "subcategory": None,
            "tags": self._generate_fallback_tags(product_data),
            "specifications": product_data.specifications or {},
            "quality_score": self._calculate_fallback_quality(product_data)
        }
        
        if not response:
            logger.debug("Using fallback: No AI response")
            return fallback
        
        try:
            # Clean response (remove markdown if present)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```json?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)
            
            parsed = json.loads(cleaned)
            
            # Validate and merge with fallback
            result = {
                "essence": parsed.get("essence") or fallback["essence"],
                "category": parsed.get("category") or fallback["category"],
                "subcategory": parsed.get("subcategory"),
                "tags": parsed.get("tags") if isinstance(parsed.get("tags"), list) else fallback["tags"],
                "specifications": parsed.get("specifications") if isinstance(parsed.get("specifications"), dict) else fallback["specifications"],
                "quality_score": int(parsed.get("quality_score", 50))
            }
            
            # Validate essence
            if len(result["essence"]) < 5:
                result["essence"] = fallback["essence"]
            
            # Ensure essence is lowercase
            result["essence"] = result["essence"].lower().strip()
            
            # Limit tags
            result["tags"] = [t.lower().strip() for t in result["tags"][:10]]
            
            # Clamp quality score
            result["quality_score"] = max(0, min(100, result["quality_score"]))
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"AI response parse error: {e}")
            return fallback
        except Exception as e:
            logger.error(f"AI response processing error: {e}")
            return fallback
    
    def _generate_fallback_essence(self, product_data: "ProductData") -> str:
        """Generate essence without AI (regex-based)"""
        title = product_data.title.lower()
        
        # Remove common noise
        noise_patterns = [
            r'\(.*?\)',           # (anything in brackets)
            r'\[.*?\]',           # [anything in brackets]
            r'buy\s+',            # Buy
            r'online\s+',         # Online
            r'at\s+best\s+price', # at best price
            r'with\s+\d+%\s+off', # with X% off
            r'free\s+delivery',   # free delivery
            r'sale\s*[-:]?\s*',   # sale: or sale -
            r'limited\s+time',    # limited time
            r'offer\s+',          # offer
        ]
        
        for pattern in noise_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        # Clean up
        title = re.sub(r'[^a-z0-9\s]', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Add brand if available
        if product_data.brand:
            brand = product_data.brand.lower()
            if brand not in title:
                title = f"{brand} {title}"
        
        # Limit length
        words = title.split()[:12]
        return ' '.join(words)
    
    def _detect_category_fallback(self, title: str) -> str:
        """Detect category from title (fallback)"""
        title_lower = title.lower()
        
        electronics = ["phone", "laptop", "tv", "tablet", "camera", "headphone", "speaker", "watch"]
        fashion = ["shirt", "dress", "jeans", "shoes", "kurta", "saree", "jacket", "top"]
        beauty = ["lipstick", "cream", "lotion", "perfume", "shampoo", "makeup", "serum"]
        home = ["furniture", "sofa", "bed", "table", "chair", "curtain", "mattress"]
        
        if any(kw in title_lower for kw in electronics):
            return "Electronics"
        elif any(kw in title_lower for kw in fashion):
            return "Fashion"
        elif any(kw in title_lower for kw in beauty):
            return "Beauty"
        elif any(kw in title_lower for kw in home):
            return "Home"
        
        return "General"
    
    def _generate_fallback_tags(self, product_data: "ProductData") -> List[str]:
        """Generate tags without AI"""
        tags = []
        
        # Add brand
        if product_data.brand:
            tags.append(product_data.brand.lower())
        
        # Extract keywords from title
        title = product_data.title.lower()
        title = re.sub(r'[^a-z0-9\s]', '', title)
        
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'buy', 'online', 'best', 'price'}
        
        words = [w for w in title.split() if len(w) > 2 and w not in stop_words]
        tags.extend(words[:6])
        
        # Add platform
        tags.append(product_data.platform_name.lower())
        
        return list(set(tags))[:8]
    
    def _calculate_fallback_quality(self, product_data: "ProductData") -> int:
        """Calculate quality score without AI"""
        score = 40  # Base score
        
        if product_data.image_url:
            score += 15
        if product_data.rating and product_data.rating > 0:
            score += 10
        if product_data.review_count and product_data.review_count > 10:
            score += 10
        if product_data.brand:
            score += 10
        if product_data.specifications and len(product_data.specifications) > 0:
            score += 10
        if product_data.original_price:
            score += 5
        
        return min(100, score)
    
    # =========================================================================
    # SELECTOR HEALING (SELF-HEALING)
    # =========================================================================
    
    async def suggest_selector_fix(
        self,
        html_snippet: str,
        failed_selector: str,
        target_data: str,
        platform_name: str
    ) -> Optional[str]:
        """
        Suggest new CSS selector when scraping fails (self-healing)
        
        Args:
            html_snippet: HTML where selector failed (truncated)
            failed_selector: The selector that stopped working
            target_data: What we're trying to extract (e.g., "price", "title")
            platform_name: Platform name for context
            
        Returns:
            New CSS selector suggestion or None
        """
        # Check cache first
        cache_key = f"selector:{platform_name}:{target_data}:{hashlib.md5(failed_selector.encode()).hexdigest()[:8]}"
        cached = await redis_client.get(cache_key)
        if cached:
            return cached
        
        # Truncate HTML to save tokens
        html_truncated = html_snippet[:2000]
        
        messages = [
            {
                "role": "system",
                "content": """You are a web scraping expert. Analyze the HTML and suggest a CSS selector to extract the target data.

RULES:
1. Return ONLY the CSS selector string, nothing else
2. Prefer stable selectors: IDs > data attributes > classes
3. Avoid dynamic classes (random strings)
4. Test multiple approaches mentally
5. Max 100 characters

Examples:
- #productTitle
- [data-testid="price"]
- .a-price .a-offscreen
- span[class*="price"]"""
            },
            {
                "role": "user",
                "content": f"Platform: {platform_name}\nTarget: {target_data}\nFailed: {failed_selector}\n\nHTML:\n{html_truncated}"
            }
        ]
        
        result = await self._call_groq(
            messages,
            feature=GroqFeature.HEALING,
            temperature=0.2,
            max_tokens=100,
            json_mode=False  # Plain text response
        )
        
        if result:
            # Clean selector
            selector = result.strip().strip('"\'`').split('\n')[0]
            
            # Validate
            if len(selector) > 5 and len(selector) < 150:
                if not selector.startswith(('http', '<', '{', '[')):
                    # Cache for 7 days
                    await redis_client.set(cache_key, selector, ttl=604800)
                    return selector
        
        return None
    
    # =========================================================================
    # ESSENCE GENERATION (Direct method)
    # =========================================================================
    
    async def generate_essence(
        self,
        title: str,
        brand: Optional[str] = None,
        specs: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate normalized product essence for fingerprinting
        
        This is a lightweight method for quick essence generation
        without full product processing.
        
        Args:
            title: Product title
            brand: Optional brand name
            specs: Optional specifications
            
        Returns:
            Normalized essence string (50-100 chars)
        """
        # Build context
        context = {"title": title[:200]}
        if brand:
            context["brand"] = brand
        if specs:
            context["specs"] = {k: v for k, v in list(specs.items())[:5]}
        
        messages = [
            {
                "role": "system",
                "content": """Extract the core product identity in lowercase.
Format: "brand model variant key-spec"
Remove: "Buy", "Online", "Best Price", promotional text
Max 80 characters.
Return JSON: {"essence": "the normalized string"}"""
            },
            {
                "role": "user",
                "content": json.dumps(context)
            }
        ]
        
        result = await self._call_groq(
            messages,
            feature=GroqFeature.SEARCH,
            temperature=0.1,
            max_tokens=100,
            json_mode=True
        )
        
        if result:
            try:
                parsed = json.loads(result)
                essence = parsed.get("essence", "").lower().strip()
                if len(essence) >= 5:
                    return essence
            except:
                pass
        
        # Fallback
        return self._generate_fallback_essence_simple(title, brand)
    
    def _generate_fallback_essence_simple(self, title: str, brand: Optional[str] = None) -> str:
        """Simple fallback essence generation"""
        text = title.lower()
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        words = text.split()[:10]
        
        if brand and brand.lower() not in text:
            words.insert(0, brand.lower())
        
        return ' '.join(words)
    
    # =========================================================================
    # SPECIFICATION EXTRACTION
    # =========================================================================
    
    async def extract_specs_from_html(self, html_snippet: str) -> Dict[str, Any]:
        """
        Extract product specifications from HTML
        
        Args:
            html_snippet: HTML containing product specs (max 2000 chars)
            
        Returns:
            Dictionary of extracted specs
        """
        html_truncated = html_snippet[:2000]
        
        messages = [
            {
                "role": "system",
                "content": """Extract product specifications from HTML.
Return JSON with key-value pairs.
Common keys: brand, model, color, storage, ram, screen_size, battery, camera, processor, material, dimensions, weight.
Use null for unknown values.
Return empty {} if nothing found."""
            },
            {
                "role": "user",
                "content": html_truncated
            }
        ]
        
        result = await self._call_groq(
            messages,
            feature=GroqFeature.SEARCH,
            temperature=0.1,
            max_tokens=400,
            json_mode=True
        )
        
        if result:
            try:
                specs = json.loads(result)
                return specs if isinstance(specs, dict) else {}
            except json.JSONDecodeError:
                pass
        
        return {}
    
    # =========================================================================
    # TAG GENERATION
    # =========================================================================
    
    async def generate_tags(
        self,
        title: str,
        description: Optional[str] = None
    ) -> List[str]:
        """
        Generate searchable tags for product
        
        Args:
            title: Product title
            description: Optional product description
            
        Returns:
            List of 5-10 tags
        """
        content = f"Title: {title[:200]}"
        if description:
            content += f"\nDescription: {description[:300]}"
        
        messages = [
            {
                "role": "system",
                "content": """Generate 5-10 searchable tags for this product.
Rules:
- Lowercase only
- Single words or hyphenated
- Include brand, type, key features
- No generic words like "best", "new", "buy"
Return JSON: {"tags": ["tag1", "tag2", ...]}"""
            },
            {
                "role": "user",
                "content": content
            }
        ]
        
        result = await self._call_groq(
            messages,
            feature=GroqFeature.SEARCH,
            temperature=0.3,
            max_tokens=150,
            json_mode=True
        )
        
        if result:
            try:
                parsed = json.loads(result)
                tags = parsed.get("tags", [])
                return [t.lower().strip() for t in tags[:10] if isinstance(t, str)]
            except:
                pass
        
        # Fallback
        words = re.findall(r'\b[a-zA-Z]{3,}\b', title.lower())
        stop = {'the', 'and', 'for', 'with', 'buy', 'online', 'best', 'price'}
        return [w for w in words if w not in stop][:8]


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
groq_client = GroqClient()
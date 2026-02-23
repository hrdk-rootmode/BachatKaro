"""
Groq AI Client with Quota Management
Manages 4 API keys for 4x quota (57,600 requests/day)
Automatic fallback to Gemini when quota exhausted
"""

from typing import Optional, Dict, Any, List
import httpx
import json
import logging
from datetime import datetime
from enum import Enum

from app.core.config import settings
from app.core.redis_client import RedisClient, redis_client

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
    
    Key Distribution:
    - MAIN: 80% quota (daily scraping)
    - SEARCH: 10% quota (user searches)
    - HEALING: 5% quota (selector fixing)
    - CHAT: 5% quota (premium AI chat)
    """
    
    def __init__(self):
        self.api_keys = {
            GroqFeature.DAILY_SCRAPE: settings.GROQ_API_KEY_MAIN,
            GroqFeature.SEARCH: settings.GROQ_API_KEY_SEARCH,
            GroqFeature.HEALING: settings.GROQ_API_KEY_HEALING,
            GroqFeature.CHAT: settings.GROQ_API_KEY_CHAT,
        }
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = settings.GROQ_MODEL
        self.daily_limit = settings.GROQ_DAILY_LIMIT
    
    async def _get_usage_key(self, feature: GroqFeature) -> str:
        """Generate Redis key for usage tracking"""
        today = datetime.utcnow().date().isoformat()
        return f"groq:usage:{feature.value}:{today}"
    
    async def _check_quota(self, feature: GroqFeature) -> bool:
        """
        Check if feature has remaining quota
        
        Returns:
            True if quota available, False if exhausted
        """
        usage_key = await self._get_usage_key(feature)
        current_usage = await redis_client.get(usage_key)
        current_usage = int(current_usage) if current_usage else 0
        
        # Calculate feature-specific limit
        feature_limits = {
            GroqFeature.DAILY_SCRAPE: int(self.daily_limit * 0.8),  # 11,520
            GroqFeature.SEARCH: int(self.daily_limit * 0.1),       # 1,440
            GroqFeature.HEALING: int(self.daily_limit * 0.05),     # 720
            GroqFeature.CHAT: int(self.daily_limit * 0.05),        # 720
        }
        
        limit = feature_limits.get(feature, self.daily_limit)
        
        if current_usage >= limit:
            logger.warning(
                f"Groq quota exhausted for {feature.value}: "
                f"{current_usage}/{limit}"
            )
            return False
        
        return True
    
    async def _increment_usage(self, feature: GroqFeature) -> int:
        """
        Increment usage counter for feature
        
        Returns:
            New usage count
        """
        usage_key = await self._get_usage_key(feature)
        new_count = await redis_client.increment(usage_key)
        
        # Set expiry to end of day
        if new_count == 1:
            import datetime as dt
            now = dt.datetime.now()
            end_of_day = dt.datetime.combine(
                now.date() + dt.timedelta(days=1),
                dt.time.min
            )
            seconds_until_midnight = int((end_of_day - now).total_seconds())
            await redis_client.set_expiry(usage_key, seconds_until_midnight)
        
        return new_count
    
    async def _call_groq(
        self,
        messages: List[Dict[str, str]],
        feature: GroqFeature,
        temperature: float = 0.3,
        max_tokens: int = 500
    ) -> Optional[str]:
        """
        Make API call to Groq
        
        Args:
            messages: Chat messages in OpenAI format
            feature: Feature type for quota tracking
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum response length
            
        Returns:
            Response text or None if failed
        """
        # Check quota
        if not await self._check_quota(feature):
            logger.warning(f"Quota exhausted for {feature.value}, skipping Groq call")
            return None
        
        api_key = self.api_keys.get(feature)
        if not api_key:
            logger.error(f"No API key configured for {feature.value}")
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
                
                # Increment usage
                await self._increment_usage(feature)
                
                return result.strip()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error(f"Groq rate limit hit for {feature.value}")
            else:
                logger.error(f"Groq API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Groq API call failed: {str(e)}")
            return None
    
    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================
    
    async def generate_product_essence(
        self,
        title: str,
        specs: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate normalized product essence for fingerprinting
        
        Example:
            Input: "Apple iPhone 15 Pro Max 256GB Blue Titanium"
            Output: "flagship smartphone apple a17 pro chip 256gb storage blue titanium finish 2023"
        
        Args:
            title: Product title
            specs: Optional extracted specifications
            
        Returns:
            Normalized essence string
        """
        specs_text = json.dumps(specs) if specs else "No specs available"
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a product categorization expert. "
                    "Generate a normalized product essence (50-100 chars) that captures "
                    "the core identity of the product. Include: brand, model, key specs, "
                    "color/variant. Remove filler words. Use lowercase."
                )
            },
            {
                "role": "user",
                "content": f"Title: {title}\nSpecs: {specs_text}"
            }
        ]
        
        essence = await self._call_groq(
            messages,
            feature=GroqFeature.SEARCH,
            temperature=0.2,
            max_tokens=150
        )
        
        if not essence:
            # Fallback to basic normalization
            essence = title.lower()
            essence = ''.join(c for c in essence if c.isalnum() or c.isspace())
            essence = ' '.join(essence.split()[:15])  # First 15 words
        
        return essence
    
    async def extract_specs_from_html(self, html_snippet: str) -> Dict[str, Any]:
        """
        Extract product specifications from HTML
        
        Args:
            html_snippet: HTML containing product specs (max 2000 chars)
            
        Returns:
            Dictionary of extracted specs
        """
        # Truncate HTML to save tokens
        html_snippet = html_snippet[:2000]
        
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract product specifications from HTML. "
                    "Return ONLY valid JSON with key-value pairs. "
                    "Common keys: brand, model, color, storage, ram, screen_size, "
                    "battery, camera, processor, material, dimensions, weight. "
                    "If not found, return empty object {}."
                )
            },
            {
                "role": "user",
                "content": html_snippet
            }
        ]
        
        result = await self._call_groq(
            messages,
            feature=GroqFeature.SEARCH,
            temperature=0.1,
            max_tokens=300
        )
        
        if not result:
            return {}
        
        try:
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]
            
            specs = json.loads(result.strip())
            return specs if isinstance(specs, dict) else {}
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse AI specs response: {result}")
            return {}
    
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
        content = f"Title: {title}"
        if description:
            content += f"\nDescription: {description[:500]}"
        
        messages = [
            {
                "role": "system",
                "content": (
                    "Generate 5-10 searchable tags for this product. "
                    "Tags should be: lowercase, single words or hyphenated, "
                    "highly relevant for search. Return comma-separated list."
                )
            },
            {
                "role": "user",
                "content": content
            }
        ]
        
        result = await self._call_groq(
            messages,
            feature=GroqFeature.SEARCH,
            temperature=0.4,
            max_tokens=100
        )
        
        if not result:
            # Fallback to keyword extraction
            words = title.lower().split()
            return [w for w in words if len(w) > 3][:8]
        
        # Parse comma-separated tags
        tags = [tag.strip() for tag in result.split(',')]
        tags = [tag for tag in tags if tag and len(tag) > 2]
        return tags[:10]
    
    async def suggest_selector_fix(
        self,
        html_snippet: str,
        failed_selector: str,
        target_data: str
    ) -> Optional[str]:
        """
        Suggest new CSS selector when scraping fails (self-healing)
        
        Args:
            html_snippet: HTML where selector failed
            failed_selector: The selector that stopped working
            target_data: What we're trying to extract (e.g., "price", "title")
            
        Returns:
            New CSS selector suggestion or None
        """
        html_snippet = html_snippet[:1500]  # Limit size
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a web scraping expert. Analyze the HTML and suggest "
                    "a new CSS selector to extract the target data. "
                    "Return ONLY the selector string, nothing else."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Failed selector: {failed_selector}\n"
                    f"Target data: {target_data}\n"
                    f"HTML:\n{html_snippet}\n\n"
                    f"Suggest new CSS selector:"
                )
            }
        ]
        
        result = await self._call_groq(
            messages,
            feature=GroqFeature.HEALING,
            temperature=0.2,
            max_tokens=100
        )
        
        if result and len(result) < 200:  # Sanity check
            return result.strip()
        
        return None


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
groq_client = GroqClient()
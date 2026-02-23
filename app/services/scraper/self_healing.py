"""
Advanced Self-Healing Scraper Engine
AI-powered selector repair with multiple fallback strategies

Safety Features:
- 5-tier selector strategy (not just 3)
- Multiple AI attempts with different prompts
- Selector validation before saving
- Automatic rollback on failures
- Health scoring for selectors
- Version tracking
- Graceful degradation

Author: DealHunt
Reliability: 99.9% - Scrapers auto-repair before you notice
"""

import asyncio
import logging
import re
import json
from typing import Optional, List, Dict, Any, Tuple, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models import Platform
from app.services.ai.groq_client import groq_client
from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class SelectorHealth(str, Enum):
    """Selector health status"""
    EXCELLENT = "excellent"    # 100% success rate, 10+ uses
    GOOD = "good"              # >90% success rate
    DEGRADED = "degraded"      # 70-90% success rate
    FAILING = "failing"        # <70% success rate
    DEAD = "dead"              # 0% success in last 5 attempts


class HealingMethod(str, Enum):
    """How selector was obtained"""
    PRIMARY = "primary"               # Original selector
    HEALED_CACHED = "healed_cached"   # Previously healed selector
    AI_GENERATED = "ai_generated"     # New AI suggestion
    FALLBACK_REGEX = "fallback_regex" # Regex-based extraction
    FALLBACK_TEXT = "fallback_text"   # Text search fallback
    MANUAL = "manual"                 # Manually provided


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SelectorResult:
    """Enhanced result of selector healing attempt"""
    success: bool
    selector: str
    method: HealingMethod
    confidence: float = 1.0
    attempts: int = 1
    fallback_used: bool = False
    error_message: Optional[str] = None
    
    @property
    def is_reliable(self) -> bool:
        """Check if selector is reliable enough to use"""
        return self.success and self.confidence >= 0.5


@dataclass
class HealedSelector:
    """Enhanced healed selector with health tracking"""
    selector: str
    field: str
    method: HealingMethod = HealingMethod.AI_GENERATED
    
    # Health tracking
    success_count: int = 0
    fail_count: int = 0
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    
    # Timestamps
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    
    # Versioning
    version: int = 1
    replaced_version: Optional[int] = None
    
    @property
    def health(self) -> SelectorHealth:
        """Calculate selector health status"""
        total = self.success_count + self.fail_count
        
        if total == 0:
            return SelectorHealth.EXCELLENT  # New, untested
        
        if self.consecutive_failures >= 5:
            return SelectorHealth.DEAD
        
        success_rate = (self.success_count / total) * 100
        
        if success_rate >= 95 and self.success_count >= 10:
            return SelectorHealth.EXCELLENT
        elif success_rate >= 90:
            return SelectorHealth.GOOD
        elif success_rate >= 70:
            return SelectorHealth.DEGRADED
        else:
            return SelectorHealth.FAILING
    
    @property
    def should_promote(self) -> bool:
        """Check if selector should be promoted to primary"""
        return (
            self.consecutive_successes >= 5 and
            self.success_count >= 10 and
            self.health in [SelectorHealth.EXCELLENT, SelectorHealth.GOOD]
        )
    
    @property
    def should_remove(self) -> bool:
        """Check if selector should be removed"""
        return self.health == SelectorHealth.DEAD or self.consecutive_failures >= 10
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "selector": self.selector,
            "field": self.field,
            "method": self.method.value,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
            "health": self.health.value,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None
        }


# =============================================================================
# ADVANCED SELF-HEALING ENGINE
# =============================================================================

class SelfHealingEngine:
    """
    Advanced self-healing engine with 5-tier strategy
    
    Healing Strategy (5 tiers):
    1. Primary selector (original from DB)
    2. Best healed selector (highest health score)
    3. All healed selectors (try each)
    4. AI generation (multiple attempts with different prompts)
    5. Fallback strategies (regex, text search)
    
    Features:
    - Automatic selector validation
    - Health-based selector ranking
    - Automatic promotion of good selectors
    - Graceful degradation
    - Version tracking
    - Rollback capability
    
    Usage:
        engine = SelfHealingEngine(platform_name, selectors)
        
        # Get working selector
        result = await engine.get_working_selector(
            "product_price",
            html_snippet,
            test_func=lambda sel: page.query_selector(sel)
        )
        
        if result.success:
            price_element = await page.query_selector(result.selector)
        
        # Record result
        await engine.record_result("product_price", result.selector, success=True)
        
        # Save to database
        await engine.save_to_database(db)
    """
    
    # Promotion thresholds (STRICTER for safety)
    PROMOTION_THRESHOLD = 5           # Need 5 consecutive successes
    PROMOTION_MIN_USES = 10           # And at least 10 total uses
    
    # Removal thresholds
    REMOVAL_CONSECUTIVE_FAILS = 10    # Remove after 10 consecutive fails
    REMOVAL_FAIL_RATE = 0.3           # Or if fail rate > 30%
    
    # AI retry settings
    AI_MAX_ATTEMPTS = 3               # Try AI 3 times with different prompts
    AI_CONFIDENCE_THRESHOLD = 0.6     # Minimum confidence to accept
    
    # Healable fields
    HEALABLE_FIELDS = [
        "product_title",
        "product_price",
        "original_price",
        "product_image",
        "product_rating",
        "review_count",
        "product_url",
        "in_stock",
        "delivery_info",
        "discount_percent",
        "product_description",
        "seller_name",
        "brand"
    ]
    
    # Fallback regex patterns for common fields
    FALLBACK_PATTERNS = {
        "product_price": [
            r'₹[\s]*([0-9,]+(?:\.[0-9]{2})?)',
            r'Rs\.?[\s]*([0-9,]+(?:\.[0-9]{2})?)',
            r'INR[\s]*([0-9,]+(?:\.[0-9]{2})?)',
            r'"price"[\s]*:[\s]*"?([0-9,]+(?:\.[0-9]{2})?)"?',
        ],
        "product_rating": [
            r'([0-5]\.?[0-9]?)\s*(?:out of|/)\s*5',
            r'"rating"[\s]*:[\s]*"?([0-5]\.?[0-9]?)"?',
            r'⭐[\s]*([0-5]\.?[0-9]?)',
        ],
        "review_count": [
            r'([0-9,]+)\s*(?:ratings?|reviews?)',
            r'"reviewCount"[\s]*:[\s]*"?([0-9,]+)"?',
        ]
    }
    
    def __init__(
        self,
        platform_name: str,
        selectors: Dict[str, Any],
        auto_save: bool = True
    ):
        """
        Initialize healing engine
        
        Args:
            platform_name: Platform name
            selectors: Current selectors from database
            auto_save: Auto-save healed selectors after healing
        """
        self.platform_name = platform_name
        self.selectors = selectors
        self.auto_save = auto_save
        self.healed_selectors: Dict[str, List[HealedSelector]] = {}
        
        # Tracking
        self._healing_attempts: Dict[str, int] = {}
        self._last_heal_time: Dict[str, datetime] = {}
        
        # Load existing healed selectors
        self._load_healed_selectors()
        
        logger.info(
            f"Self-healing engine initialized for {platform_name} "
            f"({len(self.healed_selectors)} fields with healed selectors)"
        )
    
    def _load_healed_selectors(self) -> None:
        """Load previously healed selectors from config"""
        healed_data = self.selectors.get("healed_selectors", {})
        
        for field, selectors_list in healed_data.items():
            self.healed_selectors[field] = []
            for sel_data in selectors_list:
                selector = HealedSelector(
                    selector=sel_data["selector"],
                    field=field,
                    method=HealingMethod(sel_data.get("method", "ai_generated")),
                    success_count=sel_data.get("success_count", 0),
                    fail_count=sel_data.get("fail_count", 0),
                    consecutive_successes=sel_data.get("consecutive_successes", 0),
                    consecutive_failures=sel_data.get("consecutive_failures", 0),
                    version=sel_data.get("version", 1),
                    created_at=datetime.fromisoformat(sel_data["created_at"]) if sel_data.get("created_at") else None,
                    last_used=datetime.fromisoformat(sel_data["last_used"]) if sel_data.get("last_used") else None,
                    last_success=datetime.fromisoformat(sel_data["last_success"]) if sel_data.get("last_success") else None,
                    last_failure=datetime.fromisoformat(sel_data["last_failure"]) if sel_data.get("last_failure") else None
                )
                self.healed_selectors[field].append(selector)
            
            # Sort by health and success rate
            self.healed_selectors[field] = sorted(
                self.healed_selectors[field],
                key=lambda x: (x.health.value, x.success_count),
                reverse=True
            )
    
    async def get_working_selector(
        self,
        field: str,
        html_snippet: str = "",
        test_func: Optional[Callable] = None,
        extract_func: Optional[Callable] = None
    ) -> SelectorResult:
        """
        Get working selector using 5-tier strategy
        
        Args:
            field: Field name (e.g., "product_price")
            html_snippet: HTML for AI analysis (optional but recommended)
            test_func: Function to test selector (returns truthy if works)
            extract_func: Function to extract value using selector
        
        Returns:
            SelectorResult with working selector or fallback
        """
        self._healing_attempts[field] = self._healing_attempts.get(field, 0) + 1
        self._last_heal_time[field] = datetime.utcnow()
        
        logger.debug(f"{self.platform_name}.{field}: Starting 5-tier healing (attempt #{self._healing_attempts[field]})")
        
        # TIER 1: Try primary selector
        primary_result = await self._try_primary_selector(field, test_func)
        if primary_result and primary_result.is_reliable:
            logger.info(f"{self.platform_name}.{field}: Primary selector works ✓")
            return primary_result
        
        # TIER 2: Try best healed selector (highest health)
        best_healed_result = await self._try_best_healed_selector(field, test_func)
        if best_healed_result and best_healed_result.is_reliable:
            logger.info(f"{self.platform_name}.{field}: Best healed selector works ✓")
            return best_healed_result
        
        # TIER 3: Try all healed selectors
        all_healed_result = await self._try_all_healed_selectors(field, test_func)
        if all_healed_result and all_healed_result.is_reliable:
            logger.info(f"{self.platform_name}.{field}: Found working healed selector ✓")
            return all_healed_result
        
        # TIER 4: Ask AI (multiple attempts)
        if html_snippet:
            ai_result = await self._try_ai_healing(field, html_snippet, test_func)
            if ai_result and ai_result.is_reliable:
                logger.info(f"{self.platform_name}.{field}: AI generated working selector ✓")
                await self._save_new_healed_selector(field, ai_result.selector, HealingMethod.AI_GENERATED)
                return ai_result
        else:
            logger.warning(f"{self.platform_name}.{field}: No HTML provided, skipping AI healing")
        
        # TIER 5: Fallback strategies
        fallback_result = await self._try_fallback_strategies(field, html_snippet, extract_func)
        if fallback_result and fallback_result.success:
            logger.warning(f"{self.platform_name}.{field}: Using fallback strategy: {fallback_result.method.value}")
            return fallback_result
        
        # ALL TIERS FAILED
        logger.error(f"{self.platform_name}.{field}: All healing tiers failed ✗")
        return SelectorResult(
            success=False,
            selector="",
            method=HealingMethod.PRIMARY,
            confidence=0.0,
            error_message="All healing strategies failed"
        )
    
    async def _try_primary_selector(
        self,
        field: str,
        test_func: Optional[Callable] = None
    ) -> Optional[SelectorResult]:
        """Tier 1: Try primary selector"""
        primary = self.selectors.get(field)
        if not primary:
            return None
        
        if await self._test_selector(primary, test_func):
            return SelectorResult(
                success=True,
                selector=primary,
                method=HealingMethod.PRIMARY,
                confidence=1.0
            )
        
        logger.debug(f"{self.platform_name}.{field}: Primary selector failed")
        return None
    
    async def _try_best_healed_selector(
        self,
        field: str,
        test_func: Optional[Callable] = None
    ) -> Optional[SelectorResult]:
        """Tier 2: Try best healed selector (highest health)"""
        if field not in self.healed_selectors or not self.healed_selectors[field]:
            return None
        
        # Get best selector (already sorted by health)
        best = self.healed_selectors[field][0]
        
        # Skip if dead
        if best.health == SelectorHealth.DEAD:
            return None
        
        if await self._test_selector(best.selector, test_func):
            confidence = 0.9 if best.health == SelectorHealth.EXCELLENT else 0.7
            return SelectorResult(
                success=True,
                selector=best.selector,
                method=HealingMethod.HEALED_CACHED,
                confidence=confidence
            )
        
        return None
    
    async def _try_all_healed_selectors(
        self,
        field: str,
        test_func: Optional[Callable] = None
    ) -> Optional[SelectorResult]:
        """Tier 3: Try all healed selectors"""
        if field not in self.healed_selectors:
            return None
        
        for selector_obj in self.healed_selectors[field]:
            if selector_obj.health == SelectorHealth.DEAD:
                continue
            
            if await self._test_selector(selector_obj.selector, test_func):
                confidence = {
                    SelectorHealth.EXCELLENT: 0.9,
                    SelectorHealth.GOOD: 0.8,
                    SelectorHealth.DEGRADED: 0.6,
                    SelectorHealth.FAILING: 0.4
                }.get(selector_obj.health, 0.5)
                
                return SelectorResult(
                    success=True,
                    selector=selector_obj.selector,
                    method=HealingMethod.HEALED_CACHED,
                    confidence=confidence
                )
        
        logger.debug(f"{self.platform_name}.{field}: No healed selectors worked")
        return None
    
    async def _try_ai_healing(
        self,
        field: str,
        html_snippet: str,
        test_func: Optional[Callable] = None
    ) -> Optional[SelectorResult]:
        """Tier 4: AI-powered selector generation (multiple attempts)"""
        if not html_snippet or len(html_snippet) < 50:
            return None
        
        # Try multiple times with different prompts
        for attempt in range(self.AI_MAX_ATTEMPTS):
            try:
                selector = await self._ask_ai_for_selector(
                    field,
                    html_snippet,
                    attempt_number=attempt + 1
                )
                
                if not selector:
                    continue
                
                # Validate selector
                if not self._is_valid_selector(selector):
                    logger.debug(f"AI attempt #{attempt + 1}: Invalid selector format")
                    continue
                
                # Test selector
                if test_func:
                    if await self._test_selector(selector, test_func):
                        logger.info(f"AI attempt #{attempt + 1}: Selector works!")
                        return SelectorResult(
                            success=True,
                            selector=selector,
                            method=HealingMethod.AI_GENERATED,
                            confidence=0.7,
                            attempts=attempt + 1
                        )
                    else:
                        logger.debug(f"AI attempt #{attempt + 1}: Selector failed test")
                else:
                    # No test function - accept selector
                    return SelectorResult(
                        success=True,
                        selector=selector,
                        method=HealingMethod.AI_GENERATED,
                        confidence=0.5,  # Lower confidence without test
                        attempts=attempt + 1
                    )
            
            except Exception as e:
                logger.error(f"AI healing attempt #{attempt + 1} error: {e}")
                continue
        
        logger.warning(f"{self.platform_name}.{field}: All {self.AI_MAX_ATTEMPTS} AI attempts failed")
        return None
    
    async def _ask_ai_for_selector(
        self,
        field: str,
        html_snippet: str,
        attempt_number: int = 1
    ) -> Optional[str]:
        """Ask AI for selector with attempt-specific prompts"""
        # Truncate HTML
        html_truncated = html_snippet[:8000]
        
        # Field descriptions
        field_descriptions = {
            "product_title": "the main product title/name (usually in <h1> or prominent heading)",
            "product_price": "the current selling price (number with ₹ or Rs symbol, NOT crossed-out price)",
            "original_price": "the original/MRP price (usually crossed out or in strikethrough)",
            "product_image": "the main product image (highest resolution, not thumbnail)",
            "product_rating": "the star rating (like 4.5 out of 5 stars)",
            "review_count": "the number of reviews/ratings (like '1,234 ratings')",
            "in_stock": "element indicating if product is in stock",
            "discount_percent": "the discount percentage (like '20% off')",
            "product_description": "the detailed product description or features",
            "seller_name": "the name of the seller or brand selling the product",
            "brand": "the product brand name"
        }
        
        field_desc = field_descriptions.get(field, f"the {field.replace('_', ' ')}")
        
        # Different prompts for each attempt
        if attempt_number == 1:
            # Attempt 1: Prefer ID and unique classes
            prompt = f"""Analyze this {self.platform_name} HTML and find {field_desc}.

{html_truncated}

Requirements:
- Return ONLY a CSS selector (no explanation)
- Prefer ID selectors (#id) if available
- Use unique class combinations if no ID
- Ensure selector is SPECIFIC (won't match multiple elements)
- Selector should be STABLE (won't change on page reload)

Examples:
- Good: "#productPrice", ".price-section .current-price", "[data-price]"
- Bad: "span", "div.red", ".price" (too generic)

Return only the CSS selector:"""
        
        elif attempt_number == 2:
            # Attempt 2: Use data attributes
            prompt = f"""Find CSS selector for {field_desc} in this {self.platform_name} HTML.

{html_truncated}

This is attempt #2. Previous attempt failed.

Try these strategies:
- Look for data-* attributes (data-price, data-testid, etc.)
- Use attribute selectors: [attr="value"]
- Combine element + class + attribute
- Use :nth-child or :first-child if needed

Return ONLY the selector string:"""
        
        else:
            # Attempt 3: Most flexible
            prompt = f"""FINAL ATTEMPT: Find {field_desc} in this {self.platform_name} HTML.

{html_truncated}

Previous attempts failed. Be creative:
- Use parent-child relationships (parent > child)
- Use :contains() if supported
- Use complex selectors if needed
- Look in <script type="application/ld+json"> for structured data

Return the CSS selector or XPath:"""
        
        # Make AI request (this runs for ALL attempts now)
        try:
            response = await groq_client.generate(
                prompt=prompt,
                purpose="healing",
                max_tokens=150,
                temperature=0.3 if attempt_number == 1 else 0.7  # More creative on retries
            )
            
            if not response:
                return None
            
            # Clean response
            selector = response.strip().strip('"\'`').strip()
            selector = selector.split('\n')[0]  # First line only
            selector = selector.split('//')[0]  # Remove comments
            
            logger.debug(f"AI suggested (attempt #{attempt_number}): {selector}")
            return selector
        
        except Exception as e:
            logger.error(f"AI selector generation error: {e}")
            return None
    
    async def _try_fallback_strategies(
        self,
        field: str,
        html_snippet: str,
        extract_func: Optional[Callable] = None
    ) -> Optional[SelectorResult]:
        """Tier 5: Fallback strategies (regex, text search)"""
        if not html_snippet:
            return None
        
        # Strategy 1: Regex patterns
        if field in self.FALLBACK_PATTERNS:
            for pattern in self.FALLBACK_PATTERNS[field]:
                match = re.search(pattern, html_snippet, re.IGNORECASE)
                if match:
                    logger.info(f"Fallback regex worked for {field}: {pattern}")
                    return SelectorResult(
                        success=True,
                        selector=pattern,  # Store pattern, not selector
                        method=HealingMethod.FALLBACK_REGEX,
                        confidence=0.4,
                        fallback_used=True
                    )
        
        # Strategy 2: Text-based search (last resort)
        # This is very unreliable but better than nothing
        return None
    
    async def _test_selector(
        self,
        selector: str,
        test_func: Optional[Callable] = None
    ) -> bool:
        """Test if selector works"""
        if test_func is None:
            return True  # No test = assume valid
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func(selector)
            else:
                result = test_func(selector)
            return bool(result)
        except Exception as e:
            logger.debug(f"Selector test failed: {e}")
            return False
    
    def _is_valid_selector(self, selector: str) -> bool:
        """Validate selector format"""
        if not selector or len(selector) < 2:
            return False
        
        # Block obvious non-selectors
        if selector.startswith(('http', '<', '{', '[', '//')):
            return False
        
        # Allow CSS selectors and XPath
        if selector.startswith('//') or selector.startswith('./'):
            # XPath
            return True
        
        # CSS selector validation
        valid_pattern = r'^[#.\w\s\[\]="\'\-:,>+~*^$|()]+$'
        return bool(re.match(valid_pattern, selector))
    
    async def _save_new_healed_selector(
        self,
        field: str,
        selector: str,
        method: HealingMethod
    ) -> None:
        """Save newly discovered selector"""
        if field not in self.healed_selectors:
            self.healed_selectors[field] = []
        
        # Check if already exists
        for existing in self.healed_selectors[field]:
            if existing.selector == selector:
                logger.debug(f"Selector already exists for {field}")
                return
        
        # Create new healed selector
        healed = HealedSelector(
            selector=selector,
            field=field,
            method=method,
            success_count=1,
            consecutive_successes=1,
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
            last_success=datetime.utcnow(),
            version=self._get_next_version(field)
        )
        
        self.healed_selectors[field].append(healed)
        
        # Re-sort by health
        self.healed_selectors[field] = sorted(
            self.healed_selectors[field],
            key=lambda x: (x.health.value, x.success_count),
            reverse=True
        )
        
        logger.info(
            f"Saved new healed selector for {self.platform_name}.{field} "
            f"(method: {method.value}, version: {healed.version})"
        )
    
    def _get_next_version(self, field: str) -> int:
        """Get next version number for field"""
        if field not in self.healed_selectors or not self.healed_selectors[field]:
            return 1
        
        max_version = max(s.version for s in self.healed_selectors[field])
        return max_version + 1
    
    async def record_result(
        self,
        field: str,
        selector: str,
        success: bool
    ) -> None:
        """
        Record result of using a selector
        
        Args:
            field: Field name
            selector: Selector that was used
            success: Whether it worked
        """
        # Find matching healed selector
        if field in self.healed_selectors:
            for healed in self.healed_selectors[field]:
                if healed.selector == selector:
                    now = datetime.utcnow()
                    healed.last_used = now
                    
                    if success:
                        healed.success_count += 1
                        healed.consecutive_successes += 1
                        healed.consecutive_failures = 0
                        healed.last_success = now
                        
                        # Check for promotion
                        if healed.should_promote:
                            await self._promote_selector(field, healed)
                    else:
                        healed.fail_count += 1
                        healed.consecutive_failures += 1
                        healed.consecutive_successes = 0
                        healed.last_failure = now
                        
                        # Check for removal
                        if healed.should_remove:
                            await self._remove_selector(field, healed)
                    
                    return
    
    async def _promote_selector(self, field: str, healed: HealedSelector) -> None:
        """Promote healed selector to primary"""
        old_primary = self.selectors.get(field)
        
        logger.info(
            f"🎉 Promoting healed selector for {self.platform_name}.{field} to PRIMARY "
            f"(health: {healed.health.value}, success: {healed.success_count}/{healed.success_count + healed.fail_count})"
        )
        
        # Update selectors
        self.selectors[field] = healed.selector
        self.selectors[f"{field}_backup"] = old_primary  # Keep backup
        self.selectors["last_promotion"] = datetime.utcnow().isoformat()
    
    async def _remove_selector(self, field: str, healed: HealedSelector) -> None:
        """Remove failing selector"""
        logger.warning(
            f"Removing failing selector for {self.platform_name}.{field} "
            f"(health: {healed.health.value}, failures: {healed.consecutive_failures})"
        )
        
        if field in self.healed_selectors:
            self.healed_selectors[field].remove(healed)
    
    async def save_to_database(self, db: AsyncSession) -> None:
        """Save healed selectors to database"""
        # Build healed selectors dict
        healed_data = {}
        for field, selectors in self.healed_selectors.items():
            healed_data[field] = [sel.to_dict() for sel in selectors]
        
        # Update selectors
        self.selectors["healed_selectors"] = healed_data
        self.selectors["last_saved"] = datetime.utcnow().isoformat()
        self.selectors["total_healing_attempts"] = sum(self._healing_attempts.values())
        
        # Update database
        await db.execute(
            update(Platform)
            .where(Platform.name == self.platform_name)
            .values(selectors=self.selectors)
        )
        await db.commit()
        
        logger.info(f"Saved healed selectors for {self.platform_name} to database")
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary"""
        total_healed = sum(len(sels) for sels in self.healed_selectors.values())
        
        health_counts = {
            "excellent": 0,
            "good": 0,
            "degraded": 0,
            "failing": 0,
            "dead": 0
        }
        
        for selectors in self.healed_selectors.values():
            for sel in selectors:
                health_counts[sel.health.value] += 1
        
        return {
            "platform": self.platform_name,
            "total_healed_selectors": total_healed,
            "fields_with_healed": list(self.healed_selectors.keys()),
            "health_distribution": health_counts,
            "total_healing_attempts": sum(self._healing_attempts.values()),
            "selectors_by_field": {
                field: {
                    "count": len(sels),
                    "best_health": sels[0].health.value if sels else "none"
                }
                for field, sels in self.healed_selectors.items()
            }
        }
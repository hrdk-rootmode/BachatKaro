"""
Base Platform Handler
Abstract class that ALL platform implementations must follow
Designed for seamless switching between Scraping ↔ API

Author: DealHunt
Updated: AI-Ready ProductData with Essence Support
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal
import hashlib
import re

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class HandlerType(str, Enum):
    """Type of data source"""
    SCRAPER = "scraper"
    API = "api"
    HYBRID = "hybrid"


class ProductCondition(str, Enum):
    """Product condition"""
    NEW = "new"
    REFURBISHED = "refurbished"
    USED = "used"
    UNKNOWN = "unknown"


class StockStatus(str, Enum):
    """Stock availability"""
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LIMITED = "limited"
    UNKNOWN = "unknown"


# =============================================================================
# PRODUCT CATEGORY (For smart platform routing)
# =============================================================================

class ProductCategory(str, Enum):
    """Product categories for smart platform routing"""
    ELECTRONICS = "electronics"
    FASHION = "fashion"
    HOME = "home"
    BEAUTY = "beauty"
    GROCERY = "grocery"
    GENERAL = "general"
    
    @classmethod
    def detect_from_query(cls, query: str) -> "ProductCategory":
        """Auto-detect category from search query"""
        query_lower = query.lower()
        
        electronics_keywords = [
            "phone", "laptop", "tv", "tablet", "watch", "camera", "speaker",
            "headphone", "earphone", "computer", "iphone", "samsung", "xbox",
            "playstation", "console", "keyboard", "mouse", "monitor", "mobile",
            "smartphone", "macbook", "ipad", "airpods", "pixel", "oneplus",
            "realme", "redmi", "poco", "asus", "dell", "hp", "lenovo", "acer"
        ]
        
        fashion_keywords = [
            "shirt", "dress", "kurta", "saree", "jeans", "shoes", "sneakers",
            "jacket", "t-shirt", "tshirt", "top", "bottom", "ethnic", "western",
            "kurti", "lehenga", "pant", "trouser", "watch", "bag", "wallet"
        ]
        
        beauty_keywords = [
            "lipstick", "makeup", "cream", "lotion", "perfume", "shampoo",
            "skincare", "foundation", "mascara", "serum", "moisturizer",
            "sunscreen", "face wash", "body lotion", "hair oil"
        ]
        
        home_keywords = [
            "furniture", "sofa", "bed", "table", "chair", "curtain", "mattress",
            "pillow", "kitchen", "cookware", "decor", "lamp", "fan", "ac"
        ]
        
        if any(kw in query_lower for kw in electronics_keywords):
            return cls.ELECTRONICS
        elif any(kw in query_lower for kw in fashion_keywords):
            return cls.FASHION
        elif any(kw in query_lower for kw in beauty_keywords):
            return cls.BEAUTY
        elif any(kw in query_lower for kw in home_keywords):
            return cls.HOME
        
        return cls.GENERAL
    
    @classmethod
    def get_platforms_for_category(cls, category: "ProductCategory") -> List[str]:
        """Get relevant platforms for a category"""
        platform_map = {
            cls.ELECTRONICS: ["amazon", "flipkart", "croma", "reliancedigital"],
            cls.FASHION: ["myntra", "ajio", "amazon", "flipkart", "meesho"],
            cls.BEAUTY: ["nykaa", "myntra", "amazon", "flipkart"],
            cls.HOME: ["amazon", "flipkart", "meesho"],
            cls.GROCERY: ["amazon", "flipkart"],
            cls.GENERAL: ["amazon", "flipkart"],
        }
        return platform_map.get(category, ["amazon", "flipkart"])


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PlatformConfig:
    """Platform configuration loaded from database"""
    id: int
    name: str
    base_url: str
    affiliate_tag: Optional[str] = None
    
    # Scraper-specific
    selectors: Dict[str, Any] = field(default_factory=dict)
    scrape_delay_seconds: int = 2
    
    # API-specific
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    api_endpoint: Optional[str] = None
    
    # Common
    is_active: bool = True
    rate_limit_per_minute: int = 30
    handler_type: HandlerType = HandlerType.SCRAPER
    
    # Health tracking
    last_success: Optional[datetime] = None
    consecutive_failures: int = 0
    success_rate: float = 100.0


@dataclass
class ProductData:
    """
    Unified product data structure
    Same format whether from scraping or API
    
    NEW FIELDS:
    - raw_html: Carries page content for AI processing
    - ai_essence: AI-generated normalized fingerprint
    - ai_processed: Flag to check if AI has enriched this data
    """
    # Required fields
    external_id: str
    title: str
    current_price: Decimal
    product_url: str
    platform_name: str
    
    # Optional fields
    original_price: Optional[Decimal] = None
    discount_percent: Optional[float] = None
    image_url: Optional[str] = None
    
    # Ratings & Reviews
    rating: Optional[float] = None
    review_count: Optional[int] = None
    
    # Stock
    in_stock: bool = True
    stock_status: StockStatus = StockStatus.UNKNOWN
    stock_count: Optional[int] = None
    
    # Delivery
    delivery_days: Optional[int] = None
    delivery_info: Optional[str] = None
    
    # Product details
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    condition: ProductCondition = ProductCondition.NEW
    
    # Additional data
    specifications: Dict[str, Any] = field(default_factory=dict)
    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None
    
    # Metadata
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    data_source: HandlerType = HandlerType.SCRAPER
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # =========================================================================
    # NEW: AI Processing Fields
    # =========================================================================
    raw_html: Optional[str] = field(default=None, repr=False)  # For AI to analyze
    ai_essence: Optional[str] = None  # AI-generated clean fingerprint
    ai_tags: List[str] = field(default_factory=list)
    ai_quality_score: int = 0  # 0-100
    ai_processed: bool = False  # Flag to avoid double-processing
    
    # Internal fingerprint cache
    _fingerprint: Optional[str] = field(default=None, repr=False)
    
    @property
    def fingerprint(self) -> str:
        """
        Generate unique fingerprint for product deduplication
        
        Priority:
        1. AI-generated essence (most accurate)
        2. Cached fingerprint
        3. Regex-based fallback (least accurate)
        """
        # Priority 1: AI Essence
        if self.ai_essence:
            return hashlib.sha256(self.ai_essence.encode()).hexdigest()[:32]
        
        # Priority 2: Cached
        if self._fingerprint:
            return self._fingerprint
        
        # Priority 3: Fallback (regex-based)
        normalized = self.title.lower()
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        words = sorted(normalized.split())
        
        fp_string = f"{(self.brand or 'unknown').lower()}_{' '.join(words[:10])}"
        self._fingerprint = hashlib.sha256(fp_string.encode()).hexdigest()[:32]
        
        return self._fingerprint
    
    @fingerprint.setter
    def fingerprint(self, value: str):
        """Allow setting fingerprint from AI"""
        self._fingerprint = value
    
    @property
    def affiliate_url(self) -> str:
        """Generate affiliate URL (to be set by handler)"""
        return self.product_url
    
    @property
    def has_discount(self) -> bool:
        """Check if product has discount"""
        return self.discount_percent is not None and self.discount_percent > 0
    
    def to_ai_context(self, max_length: int = 2000) -> Dict[str, Any]:
        """
        Prepare minimal context for AI processing
        Optimized to save tokens while providing enough data
        
        Args:
            max_length: Max length for raw_html truncation
        
        Returns:
            Dictionary optimized for AI prompt
        """
        context = {
            "title": self.title[:200],  # Truncate long titles
            "brand": self.brand,
            "price": float(self.current_price) if self.current_price else 0,
            "platform": self.platform_name,
            "category": self.category,
        }
        
        # Add specs if available (limit size)
        if self.specifications:
            specs_str = str(self.specifications)
            if len(specs_str) < 500:
                context["specs"] = self.specifications
        
        # Add raw_data hints (useful metadata from scraper)
        if self.raw_data:
            useful_keys = ["is_prime", "seller", "color", "size", "variant"]
            context["hints"] = {
                k: v for k, v in self.raw_data.items()
                if k in useful_keys
            }
        
        # Add truncated HTML only if no specs available
        if self.raw_html and not self.specifications:
            context["html_snippet"] = self.raw_html[:max_length]
        
        return context
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            "external_id": self.external_id,
            "title": self.title,
            "current_price": float(self.current_price),
            "original_price": float(self.original_price) if self.original_price else None,
            "discount_percent": self.discount_percent,
            "product_url": self.product_url,
            "affiliate_url": self.affiliate_url,
            "image_url": self.image_url,
            "rating": self.rating,
            "review_count": self.review_count,
            "in_stock": self.in_stock,
            "stock_count": self.stock_count,
            "delivery_days": self.delivery_days,
            "brand": self.brand,
            "category": self.category,
            "subcategory": self.subcategory,
            "specifications": self.specifications,
            "platform_name": self.platform_name,
            "fingerprint": self.fingerprint,
            "ai_essence": self.ai_essence,
            "ai_tags": self.ai_tags,
            "ai_quality_score": self.ai_quality_score,
            "scraped_at": self.scraped_at.isoformat(),
            "data_source": self.data_source.value
        }


@dataclass
class SearchResult:
    """Search operation result"""
    query: str
    platform_name: str
    products: List[ProductData] = field(default_factory=list)
    
    # Pagination
    total_results: int = 0
    page: int = 1
    has_more: bool = False
    
    # Performance
    search_time_ms: int = 0
    data_source: HandlerType = HandlerType.SCRAPER
    
    # Errors
    success: bool = True
    error_message: Optional[str] = None
    
    # Cache info
    from_cache: bool = False
    cache_key: Optional[str] = None
    
    @property
    def product_count(self) -> int:
        return len(self.products)


@dataclass
class HealthStatus:
    """Platform handler health status"""
    platform_name: str
    handler_type: HandlerType
    is_healthy: bool
    
    success_rate: float = 100.0
    avg_response_time_ms: int = 0
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    
    # Selector health
    selector_status: str = "healthy"
    healed_selectors_count: int = 0


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class BasePlatformHandler(ABC):
    """
    Abstract base class for ALL platform handlers
    
    Implement this for:
    - Web scrapers (AmazonScraper, FlipkartScraper)
    - API clients (AmazonAPI, FlipkartAPI)
    - Hybrid handlers (scrape + API fallback)
    """
    
    def __init__(self, config: PlatformConfig):
        """Initialize handler with platform configuration"""
        self.config = config
        self.platform_name = config.name
        self.base_url = config.base_url
        self.affiliate_tag = config.affiliate_tag
        
        # Health tracking
        self._request_count = 0
        self._success_count = 0
        self._last_error: Optional[str] = None
        self._consecutive_failures = 0
        
        logger.info(f"Initialized {self.__class__.__name__} for {self.platform_name}")
    
    # =========================================================================
    # ABSTRACT METHODS
    # =========================================================================
    
    @abstractmethod
    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """Search for products on the platform"""
        pass
    
    @abstractmethod
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """Get single product details from URL"""
        pass
    
    @abstractmethod
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        """Get product by platform's product ID"""
        pass
    
    @property
    @abstractmethod
    def handler_type(self) -> HandlerType:
        """Return the type of this handler"""
        pass
    
    # =========================================================================
    # COMMON METHODS
    # =========================================================================
    
    def build_affiliate_url(self, product_url: str) -> str:
        """Add affiliate tag to product URL"""
        if not self.affiliate_tag:
            return product_url
        
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}tag={self.affiliate_tag}"
    
    def extract_product_id(self, url: str) -> Optional[str]:
        """Extract product ID from URL"""
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path
            segments = [s for s in path.split("/") if s]
            return segments[-1] if segments else None
        except Exception:
            return None
    
    async def health_check(self) -> HealthStatus:
        """Check handler health"""
        success_rate = 0.0
        if self._request_count > 0:
            success_rate = (self._success_count / self._request_count) * 100
        
        return HealthStatus(
            platform_name=self.platform_name,
            handler_type=self.handler_type,
            is_healthy=self._consecutive_failures < 5,
            success_rate=round(success_rate, 1),
            last_error=self._last_error,
            consecutive_failures=self._consecutive_failures
        )
    
    def record_success(self) -> None:
        """Record successful request"""
        self._request_count += 1
        self._success_count += 1
        self._consecutive_failures = 0
        self.config.last_success = datetime.utcnow()
    
    def record_failure(self, error: str) -> None:
        """Record failed request"""
        self._request_count += 1
        self._consecutive_failures += 1
        self._last_error = error
        logger.warning(f"{self.platform_name} failure #{self._consecutive_failures}: {error}")
    
    @property
    def is_healthy(self) -> bool:
        """Check if handler is healthy"""
        return self._consecutive_failures < 5
    
    async def close(self) -> None:
        """Cleanup resources"""
        pass
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _clean_price(self, price_str: str) -> Optional[Decimal]:
        """Clean price string and convert to Decimal"""
        if not price_str:
            return None
        
        try:
            cleaned = re.sub(r'[₹$€£,\s]', '', price_str)
            match = re.search(r'[\d.]+', cleaned)
            if match:
                return Decimal(match.group())
        except Exception as e:
            logger.debug(f"Price parsing failed for '{price_str}': {e}")
        
        return None
    
    def _clean_rating(self, rating_str: str) -> Optional[float]:
        """Clean rating string and convert to float"""
        if not rating_str:
            return None
        
        try:
            match = re.search(r'([\d.]+)', rating_str)
            if match:
                rating = float(match.group(1))
                if 0 <= rating <= 5:
                    return round(rating, 1)
        except Exception:
            pass
        
        return None
    
    def _clean_review_count(self, count_str: str) -> Optional[int]:
        """Clean review count string"""
        if not count_str:
            return None
        
        try:
            count_str = count_str.upper()
            multiplier = 1
            
            if 'K' in count_str:
                multiplier = 1000
                count_str = count_str.replace('K', '')
            elif 'M' in count_str:
                multiplier = 1000000
                count_str = count_str.replace('M', '')
            
            cleaned = re.sub(r'[,\s]', '', count_str)
            match = re.search(r'[\d.]+', cleaned)
            if match:
                return int(float(match.group()) * multiplier)
        except Exception:
            pass
        
        return None
    
    def _calculate_discount(
        self,
        current: Decimal,
        original: Optional[Decimal]
    ) -> Optional[float]:
        """Calculate discount percentage"""
        if not original or original <= 0 or current >= original:
            return None
        
        discount = ((original - current) / original) * 100
        return round(float(discount), 1)
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(platform={self.platform_name}, type={self.handler_type.value})>"
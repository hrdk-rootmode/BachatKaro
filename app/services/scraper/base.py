"""
Base Platform Handler
Abstract class that ALL platform implementations must follow
Designed for seamless switching between Scraping ↔ API

Author: DealHunt
Future-Proof: YES - Add API support without changing interface
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
    SCRAPER = "scraper"      # Web scraping (Playwright)
    API = "api"              # Official API (future)
    HYBRID = "hybrid"        # Mix of both


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
# DATA CLASSES
# =============================================================================

@dataclass
class PlatformConfig:
    """
    Platform configuration loaded from database
    Used by both scrapers and API handlers
    """
    id: int
    name: str
    base_url: str
    affiliate_tag: Optional[str] = None
    
    # Scraper-specific (ignored by API handlers)
    selectors: Dict[str, Any] = field(default_factory=dict)
    scrape_delay_seconds: int = 2
    
    # API-specific (ignored by scrapers)
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
    """
    # Required fields
    external_id: str                    # Platform's product ID
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
    condition: ProductCondition = ProductCondition.NEW
    
    # Additional data
    specifications: Dict[str, Any] = field(default_factory=dict)
    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None
    
    # Metadata
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    data_source: HandlerType = HandlerType.SCRAPER
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # Fingerprint for deduplication
    _fingerprint: Optional[str] = field(default=None, repr=False)
    
    @property
    def fingerprint(self) -> str:
        """Generate unique fingerprint for product deduplication"""
        if self._fingerprint:
            return self._fingerprint
        
        # Normalize title
        normalized = self.title.lower()
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        words = sorted(normalized.split())
        
        # Create fingerprint
        fp_string = f"{self.brand or 'unknown'}_{' '.join(words[:10])}"
        self._fingerprint = hashlib.sha256(fp_string.encode()).hexdigest()[:32]
        
        return self._fingerprint
    
    @property
    def affiliate_url(self) -> str:
        """Generate affiliate URL (to be set by handler)"""
        return self.product_url
    
    @property
    def has_discount(self) -> bool:
        """Check if product has discount"""
        return self.discount_percent is not None and self.discount_percent > 0
    
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
            "specifications": self.specifications,
            "platform_name": self.platform_name,
            "fingerprint": self.fingerprint,
            "scraped_at": self.scraped_at.isoformat(),
            "data_source": self.data_source.value
        }


@dataclass
class SearchResult:
    """
    Search operation result
    Contains products + metadata about the search
    """
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
    
    # Selector health (scraper only)
    selector_status: str = "healthy"  # healthy, healed, degraded, failing
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
    
    Benefits:
    - Swap implementations without changing calling code
    - Same interface for scraper and API
    - Easy testing with mock handlers
    - Future-proof architecture
    
    Example:
        class AmazonScraper(BasePlatformHandler):
            async def search(self, query: str) -> SearchResult:
                # Scraping implementation
                pass
        
        class AmazonAPI(BasePlatformHandler):
            async def search(self, query: str) -> SearchResult:
                # API implementation
                pass
        
        # Both work the same way:
        handler = get_handler("amazon")  # Returns scraper or API based on config
        results = await handler.search("iphone")
    """
    
    def __init__(self, config: PlatformConfig):
        """
        Initialize handler with platform configuration
        
        Args:
            config: Platform configuration from database
        """
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
    # ABSTRACT METHODS - Must implement in child classes
    # =========================================================================
    
    @abstractmethod
    async def search(
        self,
        query: str,
        page: int = 1,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """
        Search for products on the platform
        
        Args:
            query: Search query string
            page: Page number (1-indexed)
            filters: Optional filters (min_price, max_price, category, etc.)
        
        Returns:
            SearchResult with list of products
        """
        pass
    
    @abstractmethod
    async def get_product(self, product_url: str) -> Optional[ProductData]:
        """
        Get single product details from URL
        
        Args:
            product_url: Full product URL
        
        Returns:
            ProductData or None if not found
        """
        pass
    
    @abstractmethod
    async def get_product_by_id(self, external_id: str) -> Optional[ProductData]:
        """
        Get product by platform's product ID
        
        Args:
            external_id: Platform's product ID (ASIN for Amazon, etc.)
        
        Returns:
            ProductData or None if not found
        """
        pass
    
    @property
    @abstractmethod
    def handler_type(self) -> HandlerType:
        """Return the type of this handler (SCRAPER, API, HYBRID)"""
        pass
    
    # =========================================================================
    # COMMON METHODS - Shared by all handlers
    # =========================================================================
    
    def build_affiliate_url(self, product_url: str) -> str:
        """
        Add affiliate tag to product URL
        
        Override in child class for platform-specific logic
        
        Args:
            product_url: Original product URL
        
        Returns:
            URL with affiliate tag appended
        """
        if not self.affiliate_tag:
            return product_url
        
        # Default implementation - append as query param
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}tag={self.affiliate_tag}"
    
    def extract_product_id(self, url: str) -> Optional[str]:
        """
        Extract product ID from URL
        
        Override in child class for platform-specific patterns
        
        Args:
            url: Product URL
        
        Returns:
            Product ID or None
        """
        # Default: return last path segment
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path
            segments = [s for s in path.split("/") if s]
            return segments[-1] if segments else None
        except Exception:
            return None
    
    async def health_check(self) -> HealthStatus:
        """
        Check handler health
        
        Returns:
            HealthStatus with current metrics
        """
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
        """Check if handler is healthy (less than 5 consecutive failures)"""
        return self._consecutive_failures < 5
    
    async def close(self) -> None:
        """
        Cleanup resources
        
        Override in child class to close browser, connections, etc.
        """
        pass
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _clean_price(self, price_str: str) -> Optional[Decimal]:
        """
        Clean price string and convert to Decimal
        
        Args:
            price_str: Price string like "₹29,999.00" or "$299.99"
        
        Returns:
            Decimal price or None
        """
        if not price_str:
            return None
        
        try:
            # Remove currency symbols and commas
            cleaned = re.sub(r'[₹$€£,\s]', '', price_str)
            # Extract number
            match = re.search(r'[\d.]+', cleaned)
            if match:
                return Decimal(match.group())
        except Exception as e:
            logger.debug(f"Price parsing failed for '{price_str}': {e}")
        
        return None
    
    def _clean_rating(self, rating_str: str) -> Optional[float]:
        """
        Clean rating string and convert to float
        
        Args:
            rating_str: Rating string like "4.5 out of 5" or "4.5"
        
        Returns:
            Float rating or None
        """
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
        """
        Clean review count string
        
        Args:
            count_str: String like "1,234 ratings" or "1.2K reviews"
        
        Returns:
            Integer count or None
        """
        if not count_str:
            return None
        
        try:
            # Handle K/M suffixes
            count_str = count_str.upper()
            multiplier = 1
            
            if 'K' in count_str:
                multiplier = 1000
                count_str = count_str.replace('K', '')
            elif 'M' in count_str:
                multiplier = 1000000
                count_str = count_str.replace('M', '')
            
            # Extract number
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
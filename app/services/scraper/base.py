"""
Base Platform Handler - Universal AI Healing Edition (FIXED)
Abstract class that ALL platform implementations must follow

🔧 FIXES APPLIED:
- Removed @property vs dataclass field conflicts (discount_percentage, fingerprint)
- Added __post_init__ for calculated fields
- Added API/JSON extraction helpers
- Added DOM minification for AI healing
- Cloud-deployment ready

Author: DealHunt
Version: 2.0.0 - Production Grade
"""

import logging
import asyncio
import time
import re
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Union, Callable
from decimal import Decimal, InvalidOperation

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


class ExtractionMethod(str, Enum):
    """How data was extracted"""
    API_NATIVE = "api_native"           # Official API
    API_INTERCEPTED = "api_intercepted" # XHR/Fetch interception
    JSON_LD = "json_ld"                 # Schema.org structured data
    NEXT_DATA = "next_data"             # Next.js __NEXT_DATA__
    DOM_SELECTOR = "dom_selector"       # CSS selector extraction
    DOM_JAVASCRIPT = "dom_javascript"   # JavaScript evaluation
    AI_HEALED = "ai_healed"             # AI-generated selector
    REGEX_FALLBACK = "regex_fallback"   # Regex from raw text


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
    
    🔧 FIXED: Removed @property conflicts with dataclass fields
    - discount_percentage is now an alias handled in __post_init__
    - fingerprint is calculated on-demand, not stored as conflicting property
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
    extraction_method: ExtractionMethod = ExtractionMethod.DOM_SELECTOR
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # =========================================================================
    # AI Processing Fields
    # =========================================================================
    raw_html: Optional[str] = field(default=None, repr=False)
    ai_essence: Optional[str] = None
    ai_tags: List[str] = field(default_factory=list)
    ai_quality_score: int = 0
    ai_processed: bool = False
    
    # Internal fingerprint cache (use underscore prefix to avoid conflicts)
    _cached_fingerprint: Optional[str] = field(default=None, repr=False)
    
    def __post_init__(self):
        """
        Post-initialization processing
        🔧 FIX: Handle type conversions and calculated fields here
        """
        # Ensure current_price is Decimal
        if self.current_price is not None and not isinstance(self.current_price, Decimal):
            try:
                self.current_price = Decimal(str(self.current_price))
            except (InvalidOperation, ValueError):
                self.current_price = Decimal('0')
        
        # Ensure original_price is Decimal
        if self.original_price is not None and not isinstance(self.original_price, Decimal):
            try:
                self.original_price = Decimal(str(self.original_price))
            except (InvalidOperation, ValueError):
                self.original_price = None
        
        # Auto-calculate discount if not provided
        if self.discount_percent is None and self.original_price and self.current_price:
            if self.original_price > 0 and self.current_price < self.original_price:
                discount = ((self.original_price - self.current_price) / self.original_price) * 100
                self.discount_percent = round(float(discount), 1)
        
        # Ensure discount_percent is float
        if self.discount_percent is not None:
            try:
                self.discount_percent = float(self.discount_percent)
            except (TypeError, ValueError):
                self.discount_percent = None
        
        # Ensure rating is valid
        if self.rating is not None:
            try:
                self.rating = float(self.rating)
                if not (0 <= self.rating <= 5):
                    self.rating = None
            except (TypeError, ValueError):
                self.rating = None
        
        # Ensure review_count is int
        if self.review_count is not None:
            try:
                self.review_count = int(self.review_count)
            except (TypeError, ValueError):
                self.review_count = None
    
    def get_fingerprint(self) -> str:
        """
        Generate unique fingerprint for product deduplication
        🔧 FIX: This is now a method, not a conflicting property
        """
        if self.ai_essence:
            return hashlib.sha256(self.ai_essence.encode()).hexdigest()[:32]
        
        if self._cached_fingerprint:
            return self._cached_fingerprint
        
        # Generate from title
        normalized = self.title.lower()
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        words = sorted(normalized.split())
        
        fp_string = f"{(self.brand or 'unknown').lower()}_{' '.join(words[:10])}"
        self._cached_fingerprint = hashlib.sha256(fp_string.encode()).hexdigest()[:32]
        
        return self._cached_fingerprint
    
    # Alias property for backward compatibility (read-only, no conflict)
    @property
    def fingerprint(self) -> str:
        """Backward compatible fingerprint property"""
        return self.get_fingerprint()
    
    @property
    def discount_percentage(self) -> Optional[float]:
        """Alias for discount_percent (backward compatibility)"""
        return self.discount_percent
    
    @property
    def affiliate_url(self) -> str:
        """Generate affiliate URL (to be set by handler)"""
        return self.product_url
    
    @property
    def has_discount(self) -> bool:
        """Check if product has discount"""
        return self.discount_percent is not None and self.discount_percent > 0
    
    def to_ai_context(self, max_length: int = 2000) -> Dict[str, Any]:
        """Prepare minimal context for AI processing"""
        context = {
            "title": self.title[:200],
            "brand": self.brand,
            "price": float(self.current_price) if self.current_price else 0,
            "platform": self.platform_name,
            "category": self.category,
        }
        
        if self.specifications:
            specs_str = str(self.specifications)
            if len(specs_str) < 500:
                context["specs"] = self.specifications
        
        if self.raw_data:
            useful_keys = ["is_prime", "seller", "color", "size", "variant"]
            context["hints"] = {
                k: v for k, v in self.raw_data.items()
                if k in useful_keys
            }
        
        if self.raw_html and not self.specifications:
            context["html_snippet"] = self.raw_html[:max_length]
        
        return context
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            "external_id": self.external_id,
            "title": self.title,
            "current_price": float(self.current_price) if self.current_price else None,
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
            "fingerprint": self.get_fingerprint(),
            "ai_essence": self.ai_essence,
            "ai_tags": self.ai_tags,
            "ai_quality_score": self.ai_quality_score,
            "extraction_method": self.extraction_method.value if self.extraction_method else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "data_source": self.data_source.value if self.data_source else None
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
    extraction_method: ExtractionMethod = ExtractionMethod.DOM_SELECTOR
    
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
# UNIVERSAL FIELD MAPPING (For Auto-Adoption)
# =============================================================================

UNIVERSAL_FIELD_CONFIG = {
    # Field name -> (attribute_type, clean_function_name)
    "product_title": ("text", "_clean_text"),
    "title": ("text", "_clean_text"),
    "product_price": ("text", "_clean_price"),
    "price": ("text", "_clean_price"),
    "current_price": ("text", "_clean_price"),
    "original_price": ("text", "_clean_price"),
    "product_image": ("attribute", "src"),
    "image": ("attribute", "src"),
    "image_url": ("attribute", "src"),
    "product_rating": ("text", "_clean_rating"),
    "rating": ("text", "_clean_rating"),
    "review_count": ("text", "_clean_review_count"),
    "brand": ("text", "_clean_text"),
    "product_url": ("attribute", "href"),
    "url": ("attribute", "href"),
    "in_stock": ("text", "_clean_stock_status"),
    "delivery_info": ("text", "_clean_text"),
    "seller_name": ("text", "_clean_text"),
    "discount_percent": ("text", "_clean_discount"),
}


# =============================================================================
# DOM MINIFICATION UTILITIES (For AI Healing)
# =============================================================================

class DOMMinifier:
    """
    Minify HTML DOM for AI processing
    Strips scripts, styles, comments to reduce token usage
    """
    
    # Tags to completely remove
    REMOVE_TAGS = ['script', 'style', 'noscript', 'iframe', 'svg', 'path', 'meta', 'link']
    
    # Attributes to keep (remove all others to reduce size)
    KEEP_ATTRIBUTES = [
        'id', 'class', 'href', 'src', 'data-testid', 'data-id', 'data-pid',
        'data-asin', 'itemprop', 'itemtype', 'aria-label', 'title', 'alt',
        'data-price', 'data-name', 'data-brand', 'data-category'
    ]
    
    @classmethod
    def minify_for_ai(cls, html: str, max_length: int = 15000) -> str:
        """
        Minify HTML for AI selector generation
        
        Args:
            html: Raw HTML content
            max_length: Maximum output length
        
        Returns:
            Minified HTML suitable for AI processing
        """
        if not html:
            return ""
        
        # Remove script and style tags completely
        for tag in cls.REMOVE_TAGS:
            html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(rf'<{tag}[^>]*/>', '', html, flags=re.IGNORECASE)
        
        # Remove HTML comments
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        
        # Remove inline event handlers
        html = re.sub(r'\s+on\w+="[^"]*"', '', html)
        html = re.sub(r"\s+on\w+='[^']*'", '', html)
        
        # Remove data-* attributes except important ones
        def clean_attributes(match):
            tag = match.group(0)
            # Keep only essential attributes
            for attr in re.findall(r'([\w-]+)=["\'][^"\']*["\']', tag):
                if attr.lower() not in cls.KEEP_ATTRIBUTES and not attr.startswith('data-'):
                    tag = re.sub(rf'\s*{attr}=["\'][^"\']*["\']', '', tag)
            return tag
        
        html = re.sub(r'<[^>]+>', clean_attributes, html)
        
        # Collapse whitespace
        html = re.sub(r'\s+', ' ', html)
        html = re.sub(r'>\s+<', '><', html)
        
        # Truncate if too long
        if len(html) > max_length:
            # Try to cut at a tag boundary
            html = html[:max_length]
            last_tag = html.rfind('<')
            if last_tag > max_length - 500:
                html = html[:last_tag]
        
        return html.strip()
    
    @classmethod
    def extract_product_region(cls, html: str, hints: List[str] = None) -> str:
        """
        Extract the likely product region from full page HTML
        
        Args:
            html: Full page HTML
            hints: List of CSS selectors or keywords to look for
        
        Returns:
            Extracted product region HTML
        """
        hints = hints or ['product', 'pdp', 'item-detail', 'product-detail']
        
        # Try to find main product container
        for hint in hints:
            # Look for id or class containing hint
            pattern = rf'<(?:div|section|article)[^>]*(?:id|class)=["\'][^"\']*{hint}[^"\']*["\'][^>]*>.*?</(?:div|section|article)>'
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match and len(match.group(0)) > 500:
                return match.group(0)
        
        # Fallback: return body content
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if body_match:
            return body_match.group(1)
        
        return html


# =============================================================================
# JSON EXTRACTION UTILITIES
# =============================================================================

class JSONExtractor:
    """
    Extract product data from various JSON sources in pages
    Works for Next.js, JSON-LD, and custom API responses
    """
    
    @staticmethod
    def extract_json_ld(html: str) -> List[Dict[str, Any]]:
        """Extract all JSON-LD structured data from HTML"""
        results = []
        pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        
        for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(match.group(1).strip())
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)
            except json.JSONDecodeError:
                continue
        
        return results
    
    @staticmethod
    def extract_next_data(html: str) -> Optional[Dict[str, Any]]:
        """Extract __NEXT_DATA__ from Next.js pages"""
        pattern = r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        
        return None
    
    @staticmethod
    def extract_product_from_json_ld(json_ld_list: List[Dict]) -> Optional[Dict[str, Any]]:
        """Extract product data from JSON-LD"""
        for item in json_ld_list:
            item_type = item.get('@type', '')
            
            if item_type == 'Product' or item_type == 'ProductModel':
                product = {
                    'title': item.get('name'),
                    'brand': item.get('brand', {}).get('name') if isinstance(item.get('brand'), dict) else item.get('brand'),
                    'image': item.get('image'),
                    'description': item.get('description'),
                    'sku': item.get('sku'),
                    'rating': None,
                    'review_count': None,
                    'price': None,
                    'currency': 'INR'
                }
                
                # Extract price from offers
                offers = item.get('offers')
                if offers:
                    if isinstance(offers, list):
                        offers = offers[0]
                    product['price'] = offers.get('price')
                    product['currency'] = offers.get('priceCurrency', 'INR')
                    product['in_stock'] = offers.get('availability', '').lower() != 'outofstock'
                
                # Extract rating
                rating = item.get('aggregateRating')
                if rating:
                    product['rating'] = rating.get('ratingValue')
                    product['review_count'] = rating.get('reviewCount') or rating.get('ratingCount')
                
                # Handle image array
                if isinstance(product['image'], list):
                    product['image'] = product['image'][0] if product['image'] else None
                
                return product
            
            # Check for nested product in @graph
            if '@graph' in item:
                result = JSONExtractor.extract_product_from_json_ld(item['@graph'])
                if result:
                    return result
        
        return None
    
    @staticmethod
    def find_product_in_next_data(next_data: Dict, platform: str = "") -> Optional[Dict[str, Any]]:
        """
        Navigate Next.js data structure to find product info
        Different platforms have different structures
        """
        if not next_data:
            return None
        
        props = next_data.get('props', {})
        page_props = props.get('pageProps', {})
        
        # Try common patterns
        product_keys = ['product', 'productData', 'pdpData', 'item', 'productDetails']
        
        def search_dict(d, depth=0):
            if depth > 5:
                return None
            if not isinstance(d, dict):
                return None
            
            for key in product_keys:
                if key in d:
                    candidate = d[key]
                    if isinstance(candidate, dict) and ('name' in candidate or 'title' in candidate):
                        return candidate
            
            for key, value in d.items():
                if isinstance(value, dict):
                    result = search_dict(value, depth + 1)
                    if result:
                        return result
            
            return None
        
        return search_dict(page_props) or search_dict(props)


# =============================================================================
# ABSTRACT BASE CLASS - UNIVERSAL AI HEALING
# =============================================================================

class BasePlatformHandler(ABC):
    """
    Abstract base class for ALL platform handlers
    
    🚀 Universal AI Healing Auto-Adoption
    - Automatically initializes healing engine for ANY platform
    - Provides universal extraction methods
    - Tracks performance automatically
    - Works with any e-commerce site structure
    
    🔧 NEW in v2.0:
    - API/JSON interception support
    - DOM minification for AI
    - Fixed dataclass property conflicts
    - Cloud-deployment ready
    """
    
    # Override in subclass for platform-specific metadata
    PLATFORM_METADATA: Dict[str, Any] = {
        "name": "unknown",
        "display_name": "Unknown Platform",
        "base_url": "",
        "domains": [],
        "categories": ["general"],
        "product_id_patterns": [],
        "affiliate_param": "tag",
        "rate_limit_per_minute": 30,
        "scrape_delay_seconds": 2,
        "reliability": "medium",
        "support_level": "basic",
        "supports_api_interception": False
    }
    
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
        
        # Debug logging
        self._debug_enabled = True
        self._operation_start_time: Optional[datetime] = None
        
        # Intercepted API responses storage
        self._intercepted_responses: Dict[str, Any] = {}
        
        # JSON extraction utilities
        self.json_extractor = JSONExtractor()
        self.dom_minifier = DOMMinifier()
        
        # 🚀 AUTO-INITIALIZE HEALING ENGINE
        self._initialize_healing_engine()
        
        logger.info(f"✅ Initialized {self.__class__.__name__} for {self.platform_name}")
        if self._debug_enabled:
            logger.debug(f"🔧 Config: {config.name} | {config.base_url}")
    
    # =========================================================================
    # 🚀 UNIVERSAL HEALING ENGINE AUTO-INITIALIZATION
    # =========================================================================
    
    def _initialize_healing_engine(self):
        """
        Auto-initialize healing engine for ANY platform
        Called automatically in __init__ - no manual setup needed!
        """
        if hasattr(self, 'healing_engine') and self.healing_engine is not None:
            logger.debug(f"🔧 Healing engine already exists for {self.platform_name}")
            return
        
        try:
            from app.services.scraper.self_healing import UniversalSelfHealingEngine
            
            platform_name = self.platform_name
            if hasattr(self, 'PLATFORM_METADATA') and self.PLATFORM_METADATA.get("name"):
                platform_name = self.PLATFORM_METADATA["name"]
            
            self.healing_engine = UniversalSelfHealingEngine(
                platform_name=platform_name,
                selectors=self.config.selectors or {}
            )
            
            logger.info(f"🤖 Auto-initialized Universal Healing Engine for {platform_name}")
            
        except ImportError as e:
            logger.warning(f"⚠️ Could not import UniversalSelfHealingEngine: {e}")
            self.healing_engine = None
        except Exception as e:
            logger.error(f"❌ Failed to initialize healing engine for {self.platform_name}: {e}")
            self.healing_engine = None
    
    # =========================================================================
    # 🚀 JSON/API EXTRACTION METHODS (NEW!)
    # =========================================================================
    
    async def extract_from_json_ld(self, html: str) -> Optional[Dict[str, Any]]:
        """
        Extract product data from JSON-LD structured data
        Works for Croma, Nykaa, and other sites with Schema.org markup
        """
        json_ld_list = self.json_extractor.extract_json_ld(html)
        if json_ld_list:
            product = self.json_extractor.extract_product_from_json_ld(json_ld_list)
            if product:
                logger.info(f"✅ Extracted product from JSON-LD: {product.get('title', '')[:50]}")
                return product
        return None
    
    async def extract_from_next_data(self, html: str) -> Optional[Dict[str, Any]]:
        """
        Extract product data from Next.js __NEXT_DATA__
        Works for Myntra, Meesho, and other Next.js sites
        """
        next_data = self.json_extractor.extract_next_data(html)
        if next_data:
            product = self.json_extractor.find_product_in_next_data(next_data, self.platform_name)
            if product:
                logger.info(f"✅ Extracted product from __NEXT_DATA__: {product.get('name', product.get('title', ''))[:50]}")
                return product
        return None
    
    def store_intercepted_response(self, url: str, data: Any):
        """Store intercepted API response for later use"""
        self._intercepted_responses[url] = {
            "data": data,
            "timestamp": datetime.utcnow()
        }
    
    def get_intercepted_response(self, pattern: str) -> Optional[Any]:
        """Get intercepted response matching URL pattern"""
        for url, response in self._intercepted_responses.items():
            if pattern in url:
                return response["data"]
        return None
    
    def clear_intercepted_responses(self):
        """Clear stored intercepted responses"""
        self._intercepted_responses.clear()
    
    # =========================================================================
    # 🚀 UNIVERSAL AUTO-HEALING EXTRACTION
    # =========================================================================
    
    async def auto_healing_extraction(
        self,
        page,
        html_content: str,
        fields: List[str] = None,
        test_timeout: float = 5.0
    ) -> Dict[str, Any]:
        """
        Universal field extraction using AI healing
        
        🔧 IMPROVED: Now minifies DOM before AI processing
        """
        if fields is None:
            fields = [
                "product_title", "product_price", "product_image",
                "product_rating", "brand", "in_stock"
            ]
        
        extracted = {}
        extraction_stats = {
            "total_fields": len(fields),
            "successful": 0,
            "failed": 0,
            "ai_generated": 0,
            "cached": 0,
            "total_time_ms": 0
        }
        
        start_time = time.time()
        
        # 🔧 MINIFY HTML FOR AI (reduces tokens, improves accuracy)
        minified_html = self.dom_minifier.minify_for_ai(html_content)
        
        for field_name in fields:
            field_start = time.time()
            
            try:
                if self.healing_engine is None:
                    logger.warning(f"⚠️ No healing engine for {field_name}, skipping")
                    continue
                
                async def test_selector(selector: str) -> bool:
                    try:
                        element = await asyncio.wait_for(
                            page.query_selector(selector),
                            timeout=test_timeout
                        )
                        return element is not None
                    except asyncio.TimeoutError:
                        return False
                    except Exception:
                        return False
                
                # Use minified HTML for AI healing
                selector_result = await self.healing_engine.get_working_selector(
                    field_name,
                    minified_html,
                    test_func=test_selector
                )
                
                field_duration = time.time() - field_start
                
                if selector_result.success:
                    element = await page.query_selector(selector_result.selector)
                    
                    if element:
                        field_config = UNIVERSAL_FIELD_CONFIG.get(field_name)
                        
                        if field_config:
                            extract_type, clean_method = field_config
                            
                            if extract_type == "attribute":
                                raw_value = await element.get_attribute(clean_method)
                            else:
                                raw_value = await element.text_content()
                            
                            cleaned_value = self._clean_field_value(field_name, raw_value)
                            extracted[field_name] = cleaned_value
                        else:
                            raw_value = await element.text_content()
                            extracted[field_name] = self._clean_text(raw_value)
                        
                        extraction_stats["successful"] += 1
                        
                        if selector_result.method.value == "ai_generated":
                            extraction_stats["ai_generated"] += 1
                        elif selector_result.method.value == "healed_cached":
                            extraction_stats["cached"] += 1
                        
                        await self._record_extraction_performance(
                            field_name, selector_result.selector, True, field_duration
                        )
                    else:
                        extraction_stats["failed"] += 1
                else:
                    extraction_stats["failed"] += 1
                    
            except asyncio.TimeoutError:
                extraction_stats["failed"] += 1
            except Exception as e:
                extraction_stats["failed"] += 1
                logger.debug(f"❌ Error extracting {field_name}: {e}")
        
        extraction_stats["total_time_ms"] = int((time.time() - start_time) * 1000)
        
        logger.info(
            f"📊 Extraction: {extraction_stats['successful']}/{extraction_stats['total_fields']} | "
            f"AI: {extraction_stats['ai_generated']} | Time: {extraction_stats['total_time_ms']}ms"
        )
        
        extracted["_extraction_stats"] = extraction_stats
        return extracted
    
    async def _record_extraction_performance(
        self,
        field_name: str,
        selector: str,
        success: bool,
        duration: float
    ):
        """Record extraction performance for analytics"""
        if self.healing_engine is None:
            return
        
        try:
            if hasattr(self.healing_engine, 'record_selector_performance'):
                await self.healing_engine.record_selector_performance(
                    field_name, selector, success, duration
                )
            else:
                await self.healing_engine.record_result(field_name, selector, success)
        except Exception as e:
            logger.debug(f"Performance recording error: {e}")
    
    # =========================================================================
    # 🚀 UNIVERSAL FIELD CLEANING METHODS
    # =========================================================================
    
    def _clean_field_value(self, field_name: str, value: Any) -> Any:
        """Universal field cleaning based on field type"""
        if value is None:
            return None
        
        if isinstance(value, str):
            value = value.strip()
        
        if "price" in field_name.lower():
            return self._clean_price(value)
        elif "rating" in field_name.lower():
            return self._clean_rating(value)
        elif "review" in field_name.lower() or "count" in field_name.lower():
            return self._clean_review_count(value)
        elif "stock" in field_name.lower():
            return self._clean_stock_status(value)
        elif "discount" in field_name.lower():
            return self._clean_discount(value)
        elif "image" in field_name.lower() or "url" in field_name.lower():
            return self._clean_url(value)
        else:
            return self._clean_text(value)
    
    def _clean_text(self, text: Any) -> Optional[str]:
        """Clean text content"""
        if text is None:
            return None
        
        if not isinstance(text, str):
            text = str(text)
        
        text = re.sub(r'\s+', ' ', text).strip()
        
        noise_patterns = [
            r'^\s*Buy\s+',
            r'\s+Online$',
            r'\s+at\s+Best\s+Price.*$',
            r'^\s*-\s*',
        ]
        
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        return text.strip() if text else None
    
    def _clean_price(self, price_str: Any) -> Optional[Decimal]:
        """Clean price string and convert to Decimal"""
        if not price_str:
            return None
        
        if isinstance(price_str, (int, float, Decimal)):
            return Decimal(str(price_str))
        
        try:
            cleaned = re.sub(r'[₹$€£,\s]', '', str(price_str))
            match = re.search(r'[\d.]+', cleaned)
            if match:
                return Decimal(match.group())
        except Exception as e:
            logger.debug(f"Price parsing failed for '{price_str}': {e}")
        
        return None
    
    def _clean_rating(self, rating_str: Any) -> Optional[float]:
        """Clean rating string and convert to float"""
        if not rating_str:
            return None
        
        if isinstance(rating_str, (int, float)):
            rating = float(rating_str)
            return round(rating, 1) if 0 <= rating <= 5 else None
        
        try:
            match = re.search(r'([\d.]+)', str(rating_str))
            if match:
                rating = float(match.group(1))
                if 0 <= rating <= 5:
                    return round(rating, 1)
        except Exception:
            pass
        
        return None
    
    def _clean_review_count(self, count_str: Any) -> Optional[int]:
        """Clean review count string"""
        if not count_str:
            return None
        
        if isinstance(count_str, int):
            return count_str
        
        try:
            count_str = str(count_str).upper()
            multiplier = 1
            
            if 'K' in count_str:
                multiplier = 1000
                count_str = count_str.replace('K', '')
            elif 'M' in count_str:
                multiplier = 1000000
                count_str = count_str.replace('M', '')
            elif 'L' in count_str or 'LAKH' in count_str:
                multiplier = 100000
                count_str = re.sub(r'L(?:AKH)?', '', count_str)
            
            cleaned = re.sub(r'[,\s]', '', count_str)
            match = re.search(r'[\d.]+', cleaned)
            if match:
                return int(float(match.group()) * multiplier)
        except Exception:
            pass
        
        return None
    
    def _clean_stock_status(self, stock_str: Any) -> bool:
        """Clean stock status and return boolean"""
        if stock_str is None:
            return True
        
        if isinstance(stock_str, bool):
            return stock_str
        
        stock_lower = str(stock_str).lower()
        
        out_of_stock_keywords = [
            "out of stock", "unavailable", "not available",
            "sold out", "currently unavailable", "no stock"
        ]
        
        return not any(kw in stock_lower for kw in out_of_stock_keywords)
    
    def _clean_discount(self, discount_str: Any) -> Optional[float]:
        """Clean discount percentage"""
        if not discount_str:
            return None
        
        if isinstance(discount_str, (int, float)):
            return float(discount_str)
        
        try:
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', str(discount_str))
            if match:
                return float(match.group(1))
        except Exception:
            pass
        
        return None
    
    def _clean_url(self, url: Any) -> Optional[str]:
        """Clean and validate URL"""
        if not url:
            return None
        
        url = str(url).strip()
        
        if url.startswith('/'):
            url = f"{self.base_url}{url}"
        
        if url.startswith(('http://', 'https://')):
            return url
        
        return None
    
    # =========================================================================
    # LOGGING HELPERS
    # =========================================================================
    
    def _log_operation_start(self, operation: str, **kwargs):
        """Log the start of an operation"""
        if self._debug_enabled:
            self._operation_start_time = datetime.utcnow()
            details = " | ".join(f"{k}={v}" for k, v in kwargs.items())
            logger.debug(f"🚀 [{self.platform_name}] Starting {operation}: {details}")
    
    def _log_operation_end(self, operation: str, result_count: int = 0, success: bool = True, error: str = None):
        """Log the end of an operation"""
        if self._debug_enabled and self._operation_start_time:
            duration = (datetime.utcnow() - self._operation_start_time).total_seconds()
            status = "✅ SUCCESS" if success else "❌ FAILED"
            error_info = f" | Error: {error}" if error else ""
            logger.debug(f"🏁 [{self.platform_name}] {operation} {status} | Duration: {duration:.2f}s | Results: {result_count}{error_info}")
            self._operation_start_time = None
    
    def _log_debug(self, message: str):
        """Log debug message with platform context"""
        if self._debug_enabled:
            logger.debug(f"🔍 [{self.platform_name}] {message}")
    
    def _log_warning(self, message: str):
        """Log warning message with platform context"""
        logger.warning(f"⚠️  [{self.platform_name}] {message}")
    
    def _log_error(self, message: str, exception: Exception = None):
        """Log error message with platform context"""
        if exception:
            logger.error(f"💥 [{self.platform_name}] {message}: {str(exception)}")
        else:
            logger.error(f"💥 [{self.platform_name}] {message}")
    
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
        
        healed_count = 0
        if self.healing_engine is not None:
            health_summary = self.healing_engine.get_health_summary()
            healed_count = health_summary.get("total_healed_selectors", 0)
        
        return HealthStatus(
            platform_name=self.platform_name,
            handler_type=self.handler_type,
            is_healthy=self._consecutive_failures < 5,
            success_rate=round(success_rate, 1),
            last_error=self._last_error,
            consecutive_failures=self._consecutive_failures,
            healed_selectors_count=healed_count
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
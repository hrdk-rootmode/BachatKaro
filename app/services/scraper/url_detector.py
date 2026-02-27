"""
URL Platform Detector - Auto-Discovery Edition
Identifies platform from product URL with high accuracy

Features:
- Pattern matching for all supported platforms
- AUTO-DISCOVERY: Loads patterns from PlatformFactory dynamically
- Product ID extraction
- Category-aware platform suggestions
- Unsupported platform detection
- URL validation and normalization
- Runtime pattern refresh

Author: DealHunt
Updated: Auto-Discovery Integration
"""

import re
import logging
from typing import Optional, Dict, Any, List, Set
from urllib.parse import urlparse, parse_qs, unquote
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PlatformSupport(str, Enum):
    """Platform support level"""
    FULL = "full"                # Full scraper support (dedicated .py file)
    PARTIAL = "partial"          # Generic AI scraper
    UNSUPPORTED = "unsupported"  # Cannot scrape


@dataclass
class URLAnalysis:
    """Result of URL analysis"""
    platform_name: str
    is_supported: bool
    support_level: PlatformSupport
    product_id: Optional[str] = None
    normalized_url: Optional[str] = None
    domain: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # NEW: Category information for smart routing
    platform_categories: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class PlatformPattern:
    """Platform detection pattern configuration"""
    name: str
    domains: List[str]
    product_patterns: List[str]
    support_level: PlatformSupport
    categories: List[str] = field(default_factory=list)
    affiliate_param: Optional[str] = None
    affiliate_value: Optional[str] = None
    
    # Compiled patterns (for performance)
    _compiled_domains: List[re.Pattern] = field(default_factory=list, repr=False)
    _compiled_products: List[re.Pattern] = field(default_factory=list, repr=False)
    
    def compile(self) -> "PlatformPattern":
        """Compile regex patterns for performance"""
        self._compiled_domains = [
            re.compile(p, re.IGNORECASE) for p in self.domains
        ]
        self._compiled_products = [
            re.compile(p, re.IGNORECASE) for p in self.product_patterns
        ]
        return self


class URLDetector:
    """
    Detect platform and extract product info from URLs
    
    AUTO-DISCOVERY FEATURE:
    - On startup, loads patterns from PlatformFactory
    - Reads PLATFORM_METADATA from each scraper file
    - Merges with static patterns (static takes priority)
    - Can refresh patterns at runtime
    
    Supported Platforms (Full):
    - Amazon.in / Amazon.com
    - Flipkart.com
    - Meesho.com
    - Myntra.com
    - Croma.com
    - Nykaa.com
    + Any platform with a .py file in platforms/
    
    Usage:
        detector = URLDetector()
        analysis = detector.analyze("https://amazon.in/dp/B09G9FPHY6")
        
        print(analysis.platform_name)  # "amazon"
        print(analysis.product_id)     # "B09G9FPHY6"
        print(analysis.is_supported)   # True
    """
    
    # =========================================================================
    # STATIC PATTERNS (Fallback + Priority Override)
    # These are guaranteed to exist even if auto-discovery fails
    # =========================================================================
    
    STATIC_PATTERNS: Dict[str, Dict[str, Any]] = {
        "amazon": {
            "domains": [
                r"amazon\.in",
                r"amazon\.com",
                r"amzn\.to",
                r"amzn\.in"
            ],
            "product_patterns": [
                r"/dp/([A-Z0-9]{10})",
                r"/gp/product/([A-Z0-9]{10})",
                r"/gp/aw/d/([A-Z0-9]{10})",
                r"asin=([A-Z0-9]{10})",
            ],
            "support": PlatformSupport.FULL,
            "categories": ["electronics", "fashion", "home", "beauty", "general"],
            "affiliate_param": "tag",
            "affiliate_value": "dealhunt-21"
        },
        "flipkart": {
            "domains": [
                r"flipkart\.com",
                r"fkrt\.it",
                r"dl\.flipkart\.com"
            ],
            "product_patterns": [
                r"/p/([a-zA-Z0-9]+)\?",
                r"pid=([a-zA-Z0-9]+)",
                r"/([a-zA-Z0-9-]+)/p/itm([a-zA-Z0-9]+)",
            ],
            "support": PlatformSupport.FULL,
            "categories": ["electronics", "fashion", "home", "beauty", "general"],
            "affiliate_param": "affid",
            "affiliate_value": "dealhunt"
        },
        "meesho": {
            "domains": [r"meesho\.com"],
            "product_patterns": [
                r"/s/p/([0-9a-z]+)",
                r"product/([0-9]+)",
                r"/([0-9]+)$"
            ],
            "support": PlatformSupport.FULL,
            "categories": ["fashion", "home", "budget"],
            "affiliate_param": "utm_source",
            "affiliate_value": "dealhunt"
        },
        "myntra": {
            "domains": [r"myntra\.com"],
            "product_patterns": [
                r"/(\d{6,10})(?:/|$)",
                r"/buy/(\d+)",
                r"p=(\d+)"
            ],
            "support": PlatformSupport.FULL,
            "categories": ["fashion", "beauty"],
            "affiliate_param": "utm_source",
            "affiliate_value": "dealhunt"
        },
        "croma": {
            "domains": [r"croma\.com"],
            "product_patterns": [r"/p/(\d+)", r"productId=(\d+)"],
            "support": PlatformSupport.FULL,
            "categories": ["electronics"],
            "affiliate_param": "utm_source",
            "affiliate_value": "dealhunt"
        },
        "nykaa": {
            "domains": [r"nykaa\.com", r"nykaafashion\.com"],
            "product_patterns": [r"/p/(\d+)", r"skuId=(\d+)"],
            "support": PlatformSupport.FULL,
            "categories": ["beauty"],
            "affiliate_param": "utm_source",
            "affiliate_value": "dealhunt"
        },
        # Partial support platforms (AI scraping)
        "snapdeal": {
            "domains": [r"snapdeal\.com"],
            "product_patterns": [r"/product/([0-9]+)"],
            "support": PlatformSupport.PARTIAL,
            "categories": ["general"]
        },
        "reliancedigital": {
            "domains": [r"reliancedigital\.in"],
            "product_patterns": [r"/([0-9]+)$"],
            "support": PlatformSupport.PARTIAL,
            "categories": ["electronics"]
        },
        "tatacliq": {
            "domains": [r"tatacliq\.com"],
            "product_patterns": [r"/p-([a-z0-9]+)"],
            "support": PlatformSupport.PARTIAL,
            "categories": ["fashion", "electronics"]
        },
        "ajio": {
            "domains": [r"ajio\.com"],
            "product_patterns": [r"/p/([a-zA-Z0-9_]+)"],
            "support": PlatformSupport.PARTIAL,
            "categories": ["fashion"]
        },
    }
    
    def __init__(self, auto_discover: bool = True):
        """
        Initialize URL Detector
        
        Args:
            auto_discover: If True, loads patterns from PlatformFactory
        """
        # All registered patterns (static + dynamic)
        self._patterns: Dict[str, PlatformPattern] = {}
        
        # Track discovered platforms
        self._discovered_platforms: Set[str] = set()
        
        # Load static patterns first
        self._load_static_patterns()
        
        # Auto-discover from Factory
        if auto_discover:
            self._load_dynamic_patterns()
        
        logger.info(
            f"URLDetector initialized: {len(self._patterns)} platforms "
            f"({len(self._discovered_platforms)} auto-discovered)"
        )
    
    def _load_static_patterns(self) -> None:
        """Load hardcoded static patterns"""
        for name, config in self.STATIC_PATTERNS.items():
            pattern = PlatformPattern(
                name=name,
                domains=config["domains"],
                product_patterns=config["product_patterns"],
                support_level=config["support"],
                categories=config.get("categories", ["general"]),
                affiliate_param=config.get("affiliate_param"),
                affiliate_value=config.get("affiliate_value")
            ).compile()
            
            self._patterns[name] = pattern
    
    def _load_dynamic_patterns(self) -> None:
        """
        Auto-discover patterns from PlatformFactory
        
        Reads PLATFORM_METADATA from each scraper file and
        registers any new platforms not in static patterns.
        """
        try:
            # Lazy import to avoid circular dependency
            from app.services.scraper.factory import get_factory
            
            factory = get_factory()
            
            # Get all platform names from factory
            platform_names = factory.get_all_platform_names()
            
            for name in platform_names:
                # Skip if already in static patterns (static takes priority)
                if name in self._patterns:
                    continue
                
                # Get metadata from factory
                metadata = factory.get_platform_metadata(name)
                
                if not metadata:
                    continue
                
                # Extract pattern info from metadata
                domains = metadata.get("domains", [])
                
                # If no domains, try to generate from name
                if not domains:
                    domains = [rf"{name}\.com", rf"{name}\.in"]
                
                product_patterns = metadata.get("product_id_patterns", [])
                
                # Default product pattern if none specified
                if not product_patterns:
                    product_patterns = [r"/p/([a-zA-Z0-9]+)", r"/product/([a-zA-Z0-9]+)"]
                
                # Determine support level
                support_str = metadata.get("support_level", "partial")
                if support_str == "full":
                    support_level = PlatformSupport.FULL
                elif support_str == "partial":
                    support_level = PlatformSupport.PARTIAL
                else:
                    support_level = PlatformSupport.PARTIAL
                
                # Create and register pattern
                pattern = PlatformPattern(
                    name=name,
                    domains=domains,
                    product_patterns=product_patterns,
                    support_level=support_level,
                    categories=metadata.get("categories", ["general"]),
                    affiliate_param=metadata.get("affiliate_param"),
                    affiliate_value=metadata.get("affiliate_value_setting")
                ).compile()
                
                self._patterns[name] = pattern
                self._discovered_platforms.add(name)
                
                logger.debug(f"Auto-discovered platform: {name}")
            
            logger.info(f"Auto-discovered {len(self._discovered_platforms)} platforms from Factory")
            
        except ImportError as e:
            logger.warning(f"Factory import failed (using static patterns only): {e}")
        except Exception as e:
            logger.error(f"Dynamic pattern loading failed: {e}")
    
    def refresh_patterns(self) -> int:
        """
        Refresh patterns from PlatformFactory
        
        Call this after adding new platform files at runtime.
        
        Returns:
            Number of newly discovered platforms
        """
        before_count = len(self._discovered_platforms)
        self._load_dynamic_patterns()
        after_count = len(self._discovered_platforms)
        
        new_count = after_count - before_count
        
        if new_count > 0:
            logger.info(f"Refreshed patterns: {new_count} new platforms discovered")
        
        return new_count
    
    def register_platform(
        self,
        name: str,
        domains: List[str],
        product_patterns: List[str],
        support_level: PlatformSupport = PlatformSupport.PARTIAL,
        categories: List[str] = None,
        affiliate_param: str = None,
        affiliate_value: str = None
    ) -> bool:
        """
        Manually register a new platform
        
        Use this to add platforms without creating a scraper file.
        
        Args:
            name: Platform name (lowercase)
            domains: List of domain regex patterns
            product_patterns: List of product ID regex patterns
            support_level: Support level
            categories: Product categories
            affiliate_param: Affiliate URL parameter
            affiliate_value: Affiliate ID value
            
        Returns:
            True if registered successfully
        """
        try:
            name = name.lower().strip()
            
            pattern = PlatformPattern(
                name=name,
                domains=domains,
                product_patterns=product_patterns,
                support_level=support_level,
                categories=categories or ["general"],
                affiliate_param=affiliate_param,
                affiliate_value=affiliate_value
            ).compile()
            
            self._patterns[name] = pattern
            
            logger.info(f"Manually registered platform: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register platform {name}: {e}")
            return False
    
    def analyze(self, url: str) -> URLAnalysis:
        """
        Analyze URL and extract platform info
        
        Args:
            url: Product URL to analyze
        
        Returns:
            URLAnalysis with platform info and product ID
        """
        if not url:
            return URLAnalysis(
                platform_name="unknown",
                is_supported=False,
                support_level=PlatformSupport.UNSUPPORTED,
                confidence=0
            )
        
        # Normalize URL
        url = self._normalize_url(url)
        
        # Parse URL
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
        except Exception as e:
            logger.error(f"URL parse error: {e}")
            return URLAnalysis(
                platform_name="unknown",
                is_supported=False,
                support_level=PlatformSupport.UNSUPPORTED,
                confidence=0
            )
        
        # Try to match platform
        for platform_name, pattern in self._patterns.items():
            # Check domain
            domain_match = any(p.search(domain) for p in pattern._compiled_domains)
            
            if domain_match:
                # Extract product ID
                product_id = None
                for regex in pattern._compiled_products:
                    match = regex.search(url)
                    if match:
                        product_id = match.group(1)
                        break
                
                return URLAnalysis(
                    platform_name=platform_name,
                    is_supported=pattern.support_level in [PlatformSupport.FULL, PlatformSupport.PARTIAL],
                    support_level=pattern.support_level,
                    product_id=product_id,
                    normalized_url=url,
                    domain=domain,
                    confidence=1.0 if product_id else 0.8,
                    metadata={
                        "affiliate_param": pattern.affiliate_param,
                        "affiliate_value": pattern.affiliate_value
                    },
                    platform_categories=pattern.categories
                )
        
        # Unknown platform
        logger.debug(f"Unknown platform for URL: {url[:50]}...")
        
        return URLAnalysis(
            platform_name=self._extract_domain_name(domain),
            is_supported=False,
            support_level=PlatformSupport.UNSUPPORTED,
            domain=domain,
            normalized_url=url,
            confidence=0.3
        )
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent handling"""
        url = url.strip()
        
        # Add https if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Decode URL-encoded characters
        url = unquote(url)
        
        # Remove tracking parameters
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'ref', 'ref_', 'gclid', 'fbclid', 'dclid', 'msclkid',
            '_ga', '_gl', 'mc_cid', 'mc_eid'
        }
        
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query, keep_blank_values=False)
            
            # Remove tracking params but keep important ones
            filtered_params = {
                k: v for k, v in query_params.items()
                if k.lower() not in tracking_params
            }
            
            if filtered_params:
                query_string = '&'.join(
                    f"{k}={v[0]}" for k, v in filtered_params.items()
                )
                url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_string}"
            else:
                url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        except Exception:
            pass
        
        return url
    
    def _extract_domain_name(self, domain: str) -> str:
        """Extract readable platform name from domain"""
        domain = re.sub(r'^www\.', '', domain)
        domain = re.sub(r'\.(com|in|co\.in|org|net)$', '', domain)
        return domain.replace('.', '_')
    
    def get_affiliate_url(self, url: str) -> str:
        """
        Add affiliate tag to URL
        
        Args:
            url: Original product URL
        
        Returns:
            URL with affiliate tag added
        """
        analysis = self.analyze(url)
        
        if not analysis.metadata:
            return url
        
        affiliate_param = analysis.metadata.get("affiliate_param")
        affiliate_value = analysis.metadata.get("affiliate_value")
        
        if not affiliate_param or not affiliate_value:
            return url
        
        # Check if already has affiliate param
        if f"{affiliate_param}=" in url:
            return url
        
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{affiliate_param}={affiliate_value}"
    
    def is_product_url(self, url: str) -> bool:
        """Check if URL is a product page (not search/category)"""
        analysis = self.analyze(url)
        return analysis.product_id is not None
    
    def get_supported_platforms(self) -> Dict[str, str]:
        """Get list of supported platforms with support level"""
        return {
            name: pattern.support_level.value
            for name, pattern in self._patterns.items()
        }
    
    def get_platforms_for_category(self, category: str) -> List[str]:
        """
        Get platforms that support a specific category
        
        Args:
            category: Category name (electronics, fashion, etc.)
        
        Returns:
            List of platform names
        """
        category = category.lower()
        matching = []
        
        for name, pattern in self._patterns.items():
            if category in [c.lower() for c in pattern.categories]:
                matching.append(name)
            elif "general" in [c.lower() for c in pattern.categories]:
                matching.append(name)
        
        return matching
    
    def get_platform_info(self, platform_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed info about a platform
        
        Args:
            platform_name: Platform name
        
        Returns:
            Dictionary with platform details or None
        """
        platform_name = platform_name.lower()
        
        if platform_name not in self._patterns:
            return None
        
        pattern = self._patterns[platform_name]
        
        return {
            "name": pattern.name,
            "support_level": pattern.support_level.value,
            "categories": pattern.categories,
            "domains": [p.pattern for p in pattern._compiled_domains],
            "affiliate_param": pattern.affiliate_param,
            "is_auto_discovered": platform_name in self._discovered_platforms
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics"""
        full_support = sum(
            1 for p in self._patterns.values()
            if p.support_level == PlatformSupport.FULL
        )
        partial_support = sum(
            1 for p in self._patterns.values()
            if p.support_level == PlatformSupport.PARTIAL
        )
        
        return {
            "total_platforms": len(self._patterns),
            "full_support": full_support,
            "partial_support": partial_support,
            "auto_discovered": len(self._discovered_platforms),
            "static": len(self._patterns) - len(self._discovered_platforms),
            "platforms": list(self._patterns.keys())
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
url_detector = URLDetector()
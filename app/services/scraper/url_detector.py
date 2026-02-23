"""
URL Platform Detector
Identifies platform from product URL with high accuracy

Features:
- Pattern matching for all supported platforms
- Product ID extraction
- Unsupported platform detection
- URL validation and normalization
"""

import re
import logging
from typing import Tuple, Optional, Dict, Any
from urllib.parse import urlparse, parse_qs, unquote
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PlatformSupport(str, Enum):
    """Platform support level"""
    FULL = "full"              # Full scraper support
    PARTIAL = "partial"        # Generic AI scraper
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
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class URLDetector:
    """
    Detect platform and extract product info from URLs
    
    Supported Platforms (Full):
    - Amazon.in / Amazon.com
    - Flipkart.com
    - Meesho.com
    - Myntra.com
    
    Partial Support (AI Scraping):
    - Snapdeal, Croma, Reliance Digital, etc.
    
    Usage:
        detector = URLDetector()
        analysis = detector.analyze("https://amazon.in/dp/B09G9FPHY6")
        
        print(analysis.platform_name)  # "amazon"
        print(analysis.product_id)     # "B09G9FPHY6"
        print(analysis.is_supported)   # True
    """
    
    # Platform detection patterns
    # Format: (domain_pattern, product_id_pattern, platform_name)
    PLATFORM_PATTERNS = {
        "amazon": {
            "domains": [
                r"amazon\.in",
                r"amazon\.com",
                r"amzn\.to",
                r"amzn\.in"
            ],
            "product_patterns": [
                r"/dp/([A-Z0-9]{10})",           # Standard product page
                r"/gp/product/([A-Z0-9]{10})",   # Alternative format
                r"/gp/aw/d/([A-Z0-9]{10})",      # Mobile format
                r"asin=([A-Z0-9]{10})",          # Query param
            ],
            "support": PlatformSupport.FULL,
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
                r"/p/([a-zA-Z0-9]+)\?",          # Product ID in path
                r"pid=([a-zA-Z0-9]+)",           # Product ID in query
                r"/([a-zA-Z0-9-]+)/p/itm([a-zA-Z0-9]+)",  # Full format
            ],
            "support": PlatformSupport.FULL,
            "affiliate_param": "affid",
            "affiliate_value": "dealhunt"
        },
        "meesho": {
            "domains": [
                r"meesho\.com"
            ],
            "product_patterns": [
                r"/s/p/([0-9a-z]+)",             # Product page
                r"product/([0-9]+)",             # Alternative
                r"/([0-9]+)$"                    # Numeric ID at end
            ],
            "support": PlatformSupport.FULL,
            "affiliate_param": "utm_source",
            "affiliate_value": "dealhunt"
        },
        "myntra": {
            "domains": [
                r"myntra\.com"
            ],
            "product_patterns": [
                r"/([0-9]+)/buy",                # Standard product page
                r"/([0-9]+)$",                   # Product ID at end
                r"p=([0-9]+)"                    # Query param
            ],
            "support": PlatformSupport.FULL,
            "affiliate_param": "utm_source",
            "affiliate_value": "dealhunt"
        },
        # Partial support platforms (AI scraping)
        "snapdeal": {
            "domains": [r"snapdeal\.com"],
            "product_patterns": [r"/product/([0-9]+)"],
            "support": PlatformSupport.PARTIAL
        },
        "croma": {
            "domains": [r"croma\.com"],
            "product_patterns": [r"/p/([0-9]+)"],
            "support": PlatformSupport.PARTIAL
        },
        "reliancedigital": {
            "domains": [r"reliancedigital\.in"],
            "product_patterns": [r"/([0-9]+)$"],
            "support": PlatformSupport.PARTIAL
        },
        "tatacliq": {
            "domains": [r"tatacliq\.com"],
            "product_patterns": [r"/p-([a-z0-9]+)"],
            "support": PlatformSupport.PARTIAL
        },
        "ajio": {
            "domains": [r"ajio\.com"],
            "product_patterns": [r"/p/([a-zA-Z0-9_]+)"],
            "support": PlatformSupport.PARTIAL
        },
        "nykaa": {
            "domains": [r"nykaa\.com"],
            "product_patterns": [r"/p/([0-9]+)"],
            "support": PlatformSupport.PARTIAL
        }
    }
    
    def __init__(self):
        self._compiled_patterns = {}
        self._compile_patterns()
    
    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance"""
        for platform, config in self.PLATFORM_PATTERNS.items():
            self._compiled_patterns[platform] = {
                "domains": [re.compile(p, re.IGNORECASE) for p in config["domains"]],
                "products": [re.compile(p, re.IGNORECASE) for p in config["product_patterns"]]
            }
    
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
        for platform_name, patterns in self._compiled_patterns.items():
            # Check domain
            domain_match = any(p.search(domain) for p in patterns["domains"])
            
            if domain_match:
                # Extract product ID
                product_id = None
                for pattern in patterns["products"]:
                    match = pattern.search(url)
                    if match:
                        product_id = match.group(1)
                        break
                
                config = self.PLATFORM_PATTERNS[platform_name]
                support_level = config["support"]
                
                return URLAnalysis(
                    platform_name=platform_name,
                    is_supported=support_level in [PlatformSupport.FULL, PlatformSupport.PARTIAL],
                    support_level=support_level,
                    product_id=product_id,
                    normalized_url=url,
                    domain=domain,
                    confidence=1.0 if product_id else 0.8,
                    metadata={
                        "affiliate_param": config.get("affiliate_param"),
                        "affiliate_value": config.get("affiliate_value")
                    }
                )
        
        # Unknown platform
        logger.info(f"Unknown platform for URL: {url}")
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
        
        # Remove tracking parameters (common ones)
        tracking_params = [
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'ref', 'ref_', 'gclid', 'fbclid', 'dclid', 'msclkid',
            '_ga', '_gl', 'mc_cid', 'mc_eid'
        ]
        
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query, keep_blank_values=False)
            
            # Remove tracking params
            filtered_params = {
                k: v for k, v in query_params.items()
                if k.lower() not in tracking_params
            }
            
            # Rebuild URL (simplified - keeps essential params)
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
        # Remove www. and common TLDs
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
        
        # Add affiliate parameter
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{affiliate_param}={affiliate_value}"
    
    def is_product_url(self, url: str) -> bool:
        """Check if URL is a product page (not search/category)"""
        analysis = self.analyze(url)
        return analysis.product_id is not None
    
    def get_supported_platforms(self) -> Dict[str, str]:
        """Get list of supported platforms with support level"""
        return {
            name: config["support"].value
            for name, config in self.PLATFORM_PATTERNS.items()
        }


# Singleton instance
url_detector = URLDetector()
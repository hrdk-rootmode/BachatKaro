"""
Platform Scrapers Package - API INTERCEPTION + AI HEALING EDITION v2.0
Production-ready scrapers for Indian e-commerce platforms

🚀 VERSION 2.0 - UNBREAKABLE EDITION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ NEW IN v2.0: ✨
- 🔥 API INTERCEPTION: Steal JSON directly from network requests
- 🔥 STEALTH MODE: Bypass Akamai, Cloudflare, Amazon Captcha
- 🔥 MULTI-FALLBACK: JSON → __NEXT_DATA__ → JSON-LD → DOM
- 🔥 MOBILE MODE: For sites with aggressive bot detection
- 🔥 DOM MINIFICATION: 80% fewer tokens for AI healing
- 🔥 FIXED: Property object bugs in ProductData
- 🔥 FIXED: Windows asyncio crash

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Supported Platforms (Auto-Discovered):
─────────────────────────────────────
✅ Amazon.in        - Stealth mode, captcha handling, ASIN extraction
✅ Flipkart.com     - JavaScript extraction, popup handling
✅ Myntra.com       - API interception, __NEXT_DATA__ extraction
✅ Meesho.com       - Mobile stealth, Akamai bypass, API interception
✅ Nykaa.com        - JSON-LD, __NEXT_DATA__, API interception
✅ Croma.com        - JSON-LD, API interception

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 EXTRACTION STRATEGY (v2.0):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Each scraper now uses a 5-tier extraction strategy:

┌─────────────────────────────────────────────────────────────────┐
│ TIER 1: API INTERCEPTION (Fastest, Most Reliable)              │
│         ├─ Intercepts XHR/Fetch JSON responses                 │
│         ├─ Zero DOM parsing needed                             │
│         └─ Immune to CSS class changes                         │
├─────────────────────────────────────────────────────────────────┤
│ TIER 2: __NEXT_DATA__ (For Next.js Sites)                      │
│         ├─ Extracts from <script id="__NEXT_DATA__">           │
│         ├─ Works for Myntra, Meesho, etc.                      │
│         └─ Pre-rendered JSON data                              │
├─────────────────────────────────────────────────────────────────┤
│ TIER 3: JSON-LD (Schema.org Structured Data)                   │
│         ├─ Extracts from <script type="application/ld+json">   │
│         ├─ Works for Croma, Nykaa, etc.                        │
│         └─ SEO-optimized data, very reliable                   │
├─────────────────────────────────────────────────────────────────┤
│ TIER 4: DOM + AI HEALING (Adaptive)                            │
│         ├─ Uses CSS selectors with AI healing                  │
│         ├─ Auto-repairs broken selectors                       │
│         └─ Learns and improves over time                       │
├─────────────────────────────────────────────────────────────────┤
│ TIER 5: JAVASCRIPT FALLBACK (Last Resort)                      │
│         ├─ Pure JavaScript DOM extraction                      │
│         ├─ Regex-based text extraction                         │
│         └─ Always works, may be less accurate                  │
└─────────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 USAGE EXAMPLES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Factory Pattern (Recommended):
   ────────────────────────────────
   from app.services.scraper import get_platform_handler
   
   # With database
   handler = await get_platform_handler("myntra", db)
   
   # Without database (file cache mode)
   handler = await get_platform_handler("myntra")
   
   # Search with API interception!
   results = await handler.search("kurti")
   print(results.extraction_method)  # "api_intercepted" 🎉


2. Direct Import:
   ─────────────────────────────
   from platforms import MyntraScraper
   from app.services.scraper.base import PlatformConfig
   
   config = PlatformConfig(id=0, name="myntra", base_url="https://www.myntra.com")
   scraper = MyntraScraper(config)
   
   results = await scraper.search("dress")


3. Check Extraction Method:
   ────────────────────────────
   results = await handler.search("phone")
   
   for product in results.products:
       print(f"{product.title}: {product.extraction_method.value}")
       # Output: "iPhone 15: api_intercepted"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Author: DealHunt
Version: 2.0.0 (API Interception + AI Healing Edition)
License: Proprietary
"""

import logging
import sys
from typing import Dict, Type, Optional, Any, List

logger = logging.getLogger(__name__)

# ============================================================================
# SAFE IMPORTS WITH ERROR HANDLING
# ============================================================================

_import_errors: Dict[str, str] = {}

# Amazon
try:
    from platforms.amazon import AmazonScraper
except ImportError as e:
    _import_errors["amazon"] = str(e)
    AmazonScraper = None

# Flipkart
try:
    from platforms.flipkart import FlipkartScraper
except ImportError as e:
    _import_errors["flipkart"] = str(e)
    FlipkartScraper = None

# Meesho
try:
    from platforms.meesho import MeeshoScraper
except ImportError as e:
    _import_errors["meesho"] = str(e)
    MeeshoScraper = None

# Myntra
try:
    from platforms.myntra import MyntraScraper
except ImportError as e:
    _import_errors["myntra"] = str(e)
    MyntraScraper = None

# Nykaa
try:
    from platforms.nykaa import NykaaScraper
except ImportError as e:
    _import_errors["nykaa"] = str(e)
    NykaaScraper = None

# Croma
try:
    from platforms.croma import CromaScraper
except ImportError as e:
    _import_errors["croma"] = str(e)
    CromaScraper = None

# Log import errors
if _import_errors:
    for platform, error in _import_errors.items():
        logger.warning(f"⚠️ Failed to import {platform}: {error}")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "AmazonScraper",
    "FlipkartScraper",
    "MeeshoScraper",
    "MyntraScraper",
    "NykaaScraper",
    "CromaScraper",
    "PLATFORM_REGISTRY",
    "get_scraper_class",
    "get_platform_stats",
    "get_all_platform_metadata",
    "check_platform_capabilities",
]


# ============================================================================
# PLATFORM REGISTRY
# ============================================================================

PLATFORM_REGISTRY: Dict[str, Optional[Type]] = {
    "amazon": AmazonScraper,
    "flipkart": FlipkartScraper,
    "meesho": MeeshoScraper,
    "myntra": MyntraScraper,
    "nykaa": NykaaScraper,
    "croma": CromaScraper,
}

# Filter out None values (failed imports)
PLATFORM_REGISTRY = {k: v for k, v in PLATFORM_REGISTRY.items() if v is not None}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_scraper_class(platform_name: str) -> Optional[Type]:
    """
    Get scraper class by platform name
    
    Args:
        platform_name: Platform name (case-insensitive)
    
    Returns:
        Scraper class or None
    
    Example:
        scraper_class = get_scraper_class("myntra")
        scraper = scraper_class(config)
    """
    return PLATFORM_REGISTRY.get(platform_name.lower())


def get_platform_stats() -> Dict[str, Any]:
    """
    Get statistics about available platforms
    
    Returns:
        Dictionary with platform statistics
    """
    # Check capabilities
    api_interception_platforms = []
    next_data_platforms = []
    json_ld_platforms = []
    
    for name, scraper_class in PLATFORM_REGISTRY.items():
        if scraper_class and hasattr(scraper_class, 'PLATFORM_METADATA'):
            metadata = scraper_class.PLATFORM_METADATA
            if metadata.get('supports_api_interception'):
                api_interception_platforms.append(name)
    
    return {
        "version": "2.0.0",
        "total_platforms": len(PLATFORM_REGISTRY),
        "platforms": list(PLATFORM_REGISTRY.keys()),
        "failed_imports": list(_import_errors.keys()),
        "api_interception_enabled": api_interception_platforms,
        "features": {
            "api_interception": True,
            "ai_healing": True,
            "stealth_mode": True,
            "mobile_mode": True,
            "json_ld_extraction": True,
            "next_data_extraction": True,
            "dom_minification": True
        }
    }


def get_all_platform_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Get metadata for all registered platforms
    
    Returns:
        Dictionary mapping platform name to metadata
    """
    metadata = {}
    
    for platform_name, scraper_class in PLATFORM_REGISTRY.items():
        if scraper_class and hasattr(scraper_class, 'PLATFORM_METADATA'):
            metadata[platform_name] = scraper_class.PLATFORM_METADATA.copy()
            metadata[platform_name]["available"] = True
        else:
            metadata[platform_name] = {
                "name": platform_name,
                "display_name": platform_name.title(),
                "available": scraper_class is not None
            }
    
    # Add failed imports
    for platform_name, error in _import_errors.items():
        if platform_name not in metadata:
            metadata[platform_name] = {
                "name": platform_name,
                "display_name": platform_name.title(),
                "available": False,
                "error": error
            }
    
    return metadata


def check_platform_capabilities() -> Dict[str, Dict[str, Any]]:
    """
    Check capabilities of all platforms
    
    Returns:
        Dictionary with capability status for each platform
    """
    capabilities = {}
    
    for platform_name, scraper_class in PLATFORM_REGISTRY.items():
        if not scraper_class:
            capabilities[platform_name] = {
                "status": "❌ Not Available",
                "error": _import_errors.get(platform_name, "Unknown error")
            }
            continue
        
        # Check for v2.0 features
        has_healing = hasattr(scraper_class, '_initialize_healing_engine')
        has_extraction = hasattr(scraper_class, 'auto_healing_extraction')
        has_json_ld = hasattr(scraper_class, 'extract_from_json_ld')
        has_next_data = hasattr(scraper_class, 'extract_from_next_data')
        
        # Check metadata
        metadata = getattr(scraper_class, 'PLATFORM_METADATA', {})
        supports_api_interception = metadata.get('supports_api_interception', False)
        anti_bot = metadata.get('anti_bot', 'none')
        reliability = metadata.get('reliability', 'unknown')
        
        capabilities[platform_name] = {
            "status": "✅ Ready" if has_healing else "⚠️ Limited",
            "ai_healing": has_healing,
            "universal_extraction": has_extraction,
            "json_ld_extraction": has_json_ld,
            "next_data_extraction": has_next_data,
            "api_interception": supports_api_interception,
            "anti_bot_handling": anti_bot,
            "reliability": reliability,
            "version": "2.0.0" if has_json_ld else "1.0.0"
        }
    
    return capabilities


def get_recommended_platforms(category: str = "general") -> List[str]:
    """
    Get recommended platforms for a category
    
    Args:
        category: Product category (electronics, fashion, beauty, etc.)
    
    Returns:
        List of recommended platform names
    """
    category_map = {
        "electronics": ["amazon", "flipkart", "croma"],
        "fashion": ["myntra", "meesho", "flipkart", "amazon"],
        "beauty": ["nykaa", "myntra", "amazon"],
        "home": ["amazon", "flipkart", "meesho"],
        "budget": ["meesho", "flipkart"],
        "general": ["amazon", "flipkart"]
    }
    
    recommended = category_map.get(category.lower(), category_map["general"])
    
    # Filter to only available platforms
    return [p for p in recommended if p in PLATFORM_REGISTRY]


# ============================================================================
# AUTO-ADOPTION VERIFICATION
# ============================================================================

def _verify_auto_adoption() -> Dict[str, Any]:
    """
    Verify that auto-adoption is working correctly for v2.0
    """
    results = {
        "total": len(PLATFORM_REGISTRY),
        "ready": 0,
        "limited": 0,
        "failed": len(_import_errors),
        "details": {}
    }
    
    required_v2_methods = [
        '_initialize_healing_engine',
        'auto_healing_extraction',
        'extract_from_json_ld',
        'extract_from_next_data',
    ]
    
    for platform_name, scraper_class in PLATFORM_REGISTRY.items():
        if not scraper_class:
            results["details"][platform_name] = {
                "status": "failed",
                "reason": "Import failed"
            }
            continue
        
        missing = []
        for method in required_v2_methods:
            if not hasattr(scraper_class, method):
                missing.append(method)
        
        if not missing:
            results["ready"] += 1
            results["details"][platform_name] = {
                "status": "ready",
                "version": "2.0.0"
            }
        else:
            results["limited"] += 1
            results["details"][platform_name] = {
                "status": "limited",
                "missing": missing
            }
    
    return results


# Run verification on import
_verification_result = _verify_auto_adoption()

if _verification_result["ready"] == _verification_result["total"]:
    logger.info(
        f"✅ All {_verification_result['total']} platforms ready (v2.0 API Interception + AI Healing)"
    )
elif _verification_result["failed"] > 0:
    logger.warning(
        f"⚠️ Platform status: {_verification_result['ready']} ready, "
        f"{_verification_result['limited']} limited, {_verification_result['failed']} failed"
    )
else:
    logger.info(
        f"📦 Platforms: {_verification_result['ready']} ready, "
        f"{_verification_result['limited']} limited"
    )


# ============================================================================
# PRINT SUMMARY (for debugging)
# ============================================================================

def print_platform_summary():
    """Print a summary of all platforms (for debugging)"""
    print("\n" + "=" * 60)
    print("🚀 DEALHUNT PLATFORM SCRAPERS v2.0")
    print("=" * 60)
    
    stats = get_platform_stats()
    print(f"\n📊 Total Platforms: {stats['total_platforms']}")
    print(f"🔌 API Interception: {len(stats['api_interception_enabled'])} platforms")
    
    print("\n📋 Platform Status:")
    print("-" * 60)
    
    capabilities = check_platform_capabilities()
    for name, caps in capabilities.items():
        status = caps.get('status', '❓ Unknown')
        version = caps.get('version', '?')
        reliability = caps.get('reliability', '?')
        api = "🔌" if caps.get('api_interception') else "  "
        
        print(f"  {api} {name:12} | {status:15} | v{version} | {reliability}")
    
    if _import_errors:
        print("\n⚠️ Import Errors:")
        for name, error in _import_errors.items():
            print(f"  ❌ {name}: {error}")
    
    print("\n" + "=" * 60 + "\n")


# Uncomment to debug:
# print_platform_summary()
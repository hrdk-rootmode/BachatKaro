"""
Scraper Service Package
Future-proof architecture supporting both scraping and API integration

Usage:
    from app.services.scraper import get_platform_handler, ScraperManager
    
    # Get handler for any platform
    handler = await get_platform_handler("amazon")
    results = await handler.search("iphone 15")
"""

from app.services.scraper.base import (
    BasePlatformHandler,
    PlatformConfig,
    ProductData,
    SearchResult,
    HandlerType
)
from app.services.scraper.factory import (
    PlatformFactory,
    get_platform_handler,
    get_all_handlers
)
from app.services.scraper.self_healing import SelfHealingEngine
from app.services.scraper.rate_limiter import RateLimiter, RateLimitExceeded
from app.services.scraper.browser import BrowserManager, get_browser_manager

__all__ = [
    # Base classes
    "BasePlatformHandler",
    "PlatformConfig",
    "ProductData",
    "SearchResult",
    "HandlerType",
    
    # Factory
    "PlatformFactory",
    "get_platform_handler",
    "get_all_handlers",
    
    # Self-healing
    "SelfHealingEngine",
    
    # Rate limiting
    "RateLimiter",
    "RateLimitExceeded",
    
    # Browser
    "BrowserManager",
    "get_browser_manager"
]
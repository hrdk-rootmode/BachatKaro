"""
Platform Scrapers Package
Production-ready scrapers for Indian e-commerce platforms

Supported Platforms:
- Amazon.in (Full support)
- Flipkart.com (Full support)
- Meesho.com (Full support)
- Myntra.com (Full support)

Usage:
    from platforms import AmazonScraper, FlipkartScraper
    
    # Or use factory pattern
    from app.services.scraper import get_platform_handler
    handler = await get_platform_handler("amazon", db)
"""

from platforms.amazon import AmazonScraper
from platforms.flipkart import FlipkartScraper
from platforms.meesho import MeeshoScraper
from platforms.myntra import MyntraScraper

__all__ = [
    "AmazonScraper",
    "FlipkartScraper",
    "MeeshoScraper",
    "MyntraScraper"
]

# Platform registry for factory pattern
PLATFORM_REGISTRY = {
    "amazon": AmazonScraper,
    "flipkart": FlipkartScraper,
    "meesho": MeeshoScraper,
    "myntra": MyntraScraper
}


def get_scraper_class(platform_name: str):
    """Get scraper class by platform name"""
    return PLATFORM_REGISTRY.get(platform_name.lower())
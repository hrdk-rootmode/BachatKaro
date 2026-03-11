#!/usr/bin/env python3
"""
Scraper Testing Script
======================

Debug scrapers without touching production database.

Modes:
- --offline:     Uses cached HTML, no network requests
- --standalone:  Scrapes live but doesn't save to DB
- --db:          Full pipeline (scrape + enrich + save)

Usage:
    python scripts/test_scrapers.py --platform amazon --query "iPhone 15"
    python scripts/test_scrapers.py --platform flipkart --url "https://..."
    python scripts/test_scrapers.py --platform all --query "laptop" --standalone
    python scripts/test_scrapers.py --list-platforms

Author: DealHunt
Version: 1.0
"""

import asyncio
import argparse
import sys
import os
import json
from datetime import datetime
from typing import Optional

# =============================================================================
# 🔧 WINDOWS FIX: Silence Proactor Event Loop Warning (Keep Default Loop)
# =============================================================================
if sys.platform == 'win32':
    # This allows Playwright to run (needs Proactor) while silencing the ugly 
    # "Event loop is closed" RuntimeError on exit
    from asyncio.proactor_events import _ProactorBasePipeTransport
    def silence_proactor_del(self): pass
    _ProactorBasePipeTransport.__del__ = silence_proactor_del

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import async_session_maker
from app.services.scraper.base import ProductData
from app.services.scraper.factory import get_platform_handler
from app.services.ai.enrichment_service import enrichment_service
from app.services.product_service import product_service


# =============================================================================
# CONFIGURATION
# =============================================================================

SUPPORTED_PLATFORMS = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]

DEFAULT_TIMEOUT = 45


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def print_product(product: ProductData, index: int = 1):
    """Pretty print a product"""
    print(f"\n{'─' * 50}")
    print(f"📦 Product #{index}")
    print(f"{'─' * 50}")
    print(f"   Title:    {product.title[:60]}...")
    print(f"   Brand:    {product.brand or 'N/A'}")
    print(f"   Price:    ₹{product.current_price}")
    
    if product.original_price:
        print(f"   Original: ₹{product.original_price}")
    if product.discount_percent:
        print(f"   Discount: {product.discount_percent}%")
    
    print(f"   Rating:   {product.rating or 'N/A'} ({product.review_count or 0} reviews)")
    print(f"   In Stock: {'✅' if product.in_stock else '❌'}")
    print(f"   Platform: {product.platform_name}")
    if product.extraction_method:
        print(f"   Method:   {product.extraction_method.value}")
    print(f"   URL:      {product.product_url[:60]}...")
    
    if product.ai_processed:
        print(f"\n   🤖 AI Enriched:")
        print(f"      Essence: {product.ai_essence[:50] if product.ai_essence else 'N/A'}...")
        print(f"      Tags:    {', '.join(product.ai_tags[:5]) if product.ai_tags else 'N/A'}")
        print(f"      Score:   {product.ai_quality_score}/100")


async def test_search(
    platform: str,
    query: str,
    mode: str,
    limit: int = 5
) -> list[ProductData]:
    """Test search functionality"""
    print(f"\n🔍 Searching '{query}' on {platform.upper()}...")
    
    products = []
    
    try:
        async with async_session_maker() as db:
            handler = await get_platform_handler(platform, db)
            
            if not handler:
                print(f"   ❌ No handler found for {platform}")
                return []
            
            # Execute search
            result = await asyncio.wait_for(
                handler.search(query=query, page=1),
                timeout=DEFAULT_TIMEOUT
            )
            
            if not result or not result.success:
                print(f"   ❌ Search failed: {result.error_message if result else 'Unknown error'}")
                return []
            
            products = result.products[:limit]
            print(f"   ✅ Found {len(products)} products (Method: {result.extraction_method.value if result.extraction_method else 'unknown'})")
            
            # Enrich if not offline mode
            if mode in ["standalone", "db"]:
                print(f"\n🤖 Enriching with AI...")
                for i, product in enumerate(products):
                    products[i] = await enrichment_service.enrich_product(product)
            
            # Save to DB if db mode
            if mode == "db":
                print(f"\n💾 Saving to database...")
                for product in products:
                    try:
                        saved = await product_service.save_product(
                            product_data=product,
                            db=db,
                            is_user_search=False
                        )
                        print(f"   ✅ Saved: {saved.id}")
                    except Exception as e:
                        print(f"   ❌ Save failed: {e}")
            
            # Print results
            for i, product in enumerate(products, 1):
                print_product(product, i)
            
    except asyncio.TimeoutError:
        print(f"   ❌ Search timed out after {DEFAULT_TIMEOUT}s")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    return products


async def test_url(
    platform: str,
    url: str,
    mode: str
) -> Optional[ProductData]:
    """Test URL scraping"""
    print(f"\n🔗 Scraping URL from {platform.upper()}...")
    print(f"   URL: {url[:60]}...")
    
    product = None
    
    try:
        async with async_session_maker() as db:
            handler = await get_platform_handler(platform, db)
            
            if not handler:
                print(f"   ❌ No handler found for {platform}")
                return None
            
            # Get product
            product = await asyncio.wait_for(
                handler.get_product(url),
                timeout=DEFAULT_TIMEOUT
            )
            
            if not product:
                print(f"   ❌ Failed to extract product")
                return None
            
            print(f"   ✅ Product extracted")
            
            # Enrich
            if mode in ["standalone", "db"]:
                print(f"\n🤖 Enriching with AI...")
                product = await enrichment_service.enrich_product(product)
            
            # Save
            if mode == "db":
                print(f"\n💾 Saving to database...")
                try:
                    saved = await product_service.save_product(
                        product_data=product,
                        db=db,
                        is_user_search=True
                    )
                    print(f"   ✅ Saved: {saved.id}")
                except Exception as e:
                    print(f"   ❌ Save failed: {e}")
            
            print_product(product)
            
    except asyncio.TimeoutError:
        print(f"   ❌ Scrape timed out after {DEFAULT_TIMEOUT}s")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    return product


async def test_all_platforms(query: str, mode: str):
    """Test search on all platforms"""
    print(f"\n🌐 Testing ALL platforms with query: '{query}'")
    
    results = {}
    
    for platform in SUPPORTED_PLATFORMS:
        try:
            products = await test_search(platform, query, mode, limit=2)
            results[platform] = len(products)
        except Exception as e:
            results[platform] = f"Error: {e}"
        
        # Small delay between platforms
        await asyncio.sleep(1)
        
        # Force cleanup
        from app.services.scraper.browser import close_browser_manager
        await close_browser_manager()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 RESULTS SUMMARY")
    print("=" * 60)
    
    for platform, result in results.items():
        status = "✅" if isinstance(result, int) and result > 0 else "❌"
        print(f"   {status} {platform.capitalize()}: {result}")


def list_platforms():
    """List all supported platforms"""
    print("\n📋 Supported Platforms:")
    print("=" * 40)
    
    for platform in SUPPORTED_PLATFORMS:
        print(f"   • {platform}")
    
    print("\nUsage examples:")
    print("   python scripts/test_scrapers.py --platform amazon --query 'iPhone'")
    print("   python scripts/test_scrapers.py --platform all --query 'laptop'")


# =============================================================================
# MAIN
# =============================================================================

async def main(args):
    """Main test function"""
    print("=" * 60)
    print("🧪 SCRAPER TEST")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Mode: {args.mode.upper()}")
    print("=" * 60)
    
    if args.list_platforms:
        list_platforms()
        return
    
    if not args.platform:
        print("❌ Please specify --platform or use --list-platforms")
        return
    
    if args.platform == "all":
        if not args.query:
            print("❌ Please specify --query for all-platform test")
            return
        await test_all_platforms(args.query, args.mode)
    elif args.url:
        await test_url(args.platform, args.url, args.mode)
    elif args.query:
        await test_search(args.platform, args.query, args.mode, args.limit)
        
        # Cleanup
        from app.services.scraper.browser import close_browser_manager
        await close_browser_manager()
    else:
        print("❌ Please specify --query or --url")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test DealHunt Scrapers")
    
    parser.add_argument("--platform", "-p", type=str, 
                        help="Platform to test (amazon, flipkart, all)")
    parser.add_argument("--query", "-q", type=str,
                        help="Search query")
    parser.add_argument("--url", "-u", type=str,
                        help="Product URL to scrape")
    parser.add_argument("--limit", "-l", type=int, default=5,
                        help="Max products to fetch (default: 5)")
    parser.add_argument("--list-platforms", action="store_true",
                        help="List all supported platforms")
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--offline", action="store_const", const="offline", dest="mode",
                            help="Use cached HTML, no network")
    mode_group.add_argument("--standalone", action="store_const", const="standalone", dest="mode",
                            help="Scrape live but don't save to DB")
    mode_group.add_argument("--db", action="store_const", const="db", dest="mode",
                            help="Full pipeline (scrape + enrich + save)")
    
    parser.set_defaults(mode="standalone")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
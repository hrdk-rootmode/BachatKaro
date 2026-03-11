#!/usr/bin/env python3
"""
Database Seeding Script
=======================

Populate database with products for demo/testing.
Includes AUTO CROSS-PLATFORM MATCHING.

Modes:
- --quick:        2 products per platform (fast demo)
- --smart-rotate: Category rotation system
- --full:         All categories, all platforms

Usage:
    python scripts/seed.py --quick
    python scripts/seed.py --smart-rotate --categories "Electronics,Fashion"
    python scripts/seed.py --full --limit 100

Author: DealHunt
Version: 2.0 (Cross-Platform Enabled)
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime
from typing import List, Dict, Any

# =============================================================================
# 🔧 WINDOWS FIX: Silence Proactor Event Loop Warning (Keep Default Loop)
# =============================================================================
if sys.platform == 'win32':
    from asyncio.proactor_events import _ProactorBasePipeTransport
    def silence_proactor_del(self): pass
    _ProactorBasePipeTransport.__del__ = silence_proactor_del

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import async_session_maker
from app.services.scraper.factory import get_platform_handler
from app.services.ai.enrichment_service import enrichment_service
from app.services.product_service import product_service
from app.services.scraper.cross_platform_matcher import cross_platform_matcher # ✅ NEW IMPORT

# =============================================================================
# CONFIGURATION
# =============================================================================

PLATFORMS = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]

CATEGORIES = [
    "Electronics",
    "Fashion",
    "Beauty",
    "Home & Kitchen",
    "Sports",
    "Books",
]

SEARCH_QUERIES = {
    "Electronics": ["smartphone", "laptop", "headphones", "smartwatch", "tablet"],
    "Fashion": ["men tshirt", "women dress", "sneakers", "watch", "handbag"],
    "Beauty": ["lipstick", "face cream", "perfume", "shampoo", "sunscreen"],
    "Home & Kitchen": ["mixer grinder", "air fryer", "bedsheet", "curtains", "cookware"],
    "Sports": ["running shoes", "yoga mat", "cricket bat", "football", "gym equipment"],
    "Books": ["fiction", "self help", "programming", "business", "biography"],
}

PLATFORM_CATEGORY_MAP = {
    "amazon": ["Electronics", "Fashion", "Home & Kitchen", "Books"],
    "flipkart": ["Electronics", "Fashion", "Home & Kitchen", "Sports"],
    "myntra": ["Fashion"],
    "nykaa": ["Beauty"],
    "croma": ["Electronics"],
    "meesho": ["Fashion", "Home & Kitchen"],
}


# =============================================================================
# 🔗 CROSS-PLATFORM HELPER (THE MAGIC SAUCE)
# =============================================================================

async def _find_and_save_cross_platform(source_product, db):
    """
    Finds matches for the seeded product on other platforms 
    and saves them with the same fingerprint.
    """
    try:
        print(f"      🔎 Looking for matches on other platforms...")
        
        # 1. Find alternatives (scrapes live if needed)
        alternatives = await cross_platform_matcher.find_alternatives(
            source_product=source_product,
            db=db,
            search_if_not_found=True, # ⚡ CRITICAL: Triggers live scraping on other sites
            skip_platforms=[source_product.platform_name],
            max_results=3 # Limit to 3 matches to keep seeding fast
        )
        
        saved_count = 0
        for alt in alternatives:
            # Skip if it's the same product we just saved
            if alt.platform_name.lower() == source_product.platform_name.lower():
                continue
                
            try:
                # 2. Enrich if needed (AI fixes missing brands/specs)
                if not alt.ai_processed:
                    alt = await enrichment_service.enrich_product(alt)
                
                # 3. Save to DB (Service handles fingerprint linking)
                saved_alt = await product_service.save_product(
                    product_data=alt,
                    db=db,
                    is_user_search=False
                )
                
                print(f"      🔗 Found Match: {alt.platform_name.upper()} - ₹{alt.current_price}")
                saved_count += 1
                
            except Exception as e:
                # Don't let one failed match stop the process
                pass
                
        if saved_count == 0:
            print("      ⚪ No cross-platform matches found.")
            
    except Exception as e:
        print(f"      ⚠️ Cross-platform check failed: {e}")


# =============================================================================
# SEEDING FUNCTIONS
# =============================================================================

async def seed_quick() -> Dict[str, int]:
    """Quick seed: 2 products per platform + matches"""
    print("\n⚡ Quick Seed Mode (2 products per platform + Cross-Platform Matches)")
    
    results = {p: 0 for p in PLATFORMS}
    
    async with async_session_maker() as db:
        for platform in PLATFORMS:
            print(f"\n📌 {platform.upper()}")
            
            try:
                handler = await get_platform_handler(platform, db)
                if not handler:
                    print(f"   ❌ No handler")
                    continue
                
                # Get first available category
                categories = PLATFORM_CATEGORY_MAP.get(platform, ["Electronics"])
                category = categories[0]
                queries = SEARCH_QUERIES.get(category, ["trending"])
                
                # Search
                result = await asyncio.wait_for(
                    handler.search(query=queries[0], page=1),
                    timeout=60 # Increased timeout for cross-platform
                )
                
                if not result or not result.products:
                    print(f"   ❌ No products found")
                    continue
                
                # Take first 2
                products = result.products[:2]
                
                for product in products:
                    try:
                        # Enrich
                        product = await enrichment_service.enrich_product(product)
                        
                        # Save Source Product
                        saved = await product_service.save_product(
                            product_data=product,
                            db=db,
                            is_user_search=False
                        )
                        
                        results[platform] += 1
                        print(f"   ✅ {saved.title[:40]}... (₹{product.current_price})")
                        
                        # ⚡ TRIGGER CROSS-PLATFORM MATCHING
                        await _find_and_save_cross_platform(product, db)
                        
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                
            except Exception as e:
                print(f"   ❌ Platform Error: {e}")
            
            await asyncio.sleep(1)
            from app.services.scraper.browser import close_browser_manager
            await close_browser_manager()
    
    return results


async def seed_smart_rotate(categories: List[str] = None, products_per_category: int = 5) -> Dict[str, int]:
    """Smart rotation: Distribute across categories"""
    categories = categories or CATEGORIES[:3]
    print(f"\n🔄 Smart Rotate Mode")
    
    results = {p: 0 for p in PLATFORMS}
    
    async with async_session_maker() as db:
        for category in categories:
            print(f"\n📁 Category: {category}")
            queries = SEARCH_QUERIES.get(category, ["trending"])
            
            for platform in PLATFORMS:
                if category not in PLATFORM_CATEGORY_MAP.get(platform, []):
                    continue
                
                print(f"\n   📌 {platform.upper()}")
                try:
                    handler = await get_platform_handler(platform, db)
                    if not handler: continue
                    
                    products_saved = 0
                    for query in queries:
                        if products_saved >= products_per_category: break
                        
                        result = await asyncio.wait_for(handler.search(query=f"{category} {query}", page=1), timeout=60)
                        
                        if not result or not result.products: continue
                        
                        for product in result.products:
                            if products_saved >= products_per_category: break
                            
                            try:
                                product.category = category
                                product = await enrichment_service.enrich_product(product)
                                
                                saved = await product_service.save_product(product_data=product, db=db, is_user_search=False)
                                
                                products_saved += 1
                                results[platform] += 1
                                print(f"      ✅ [{products_saved}] {saved.title[:35]}... (₹{product.current_price})")
                                
                                # ⚡ TRIGGER CROSS-PLATFORM MATCHING
                                await _find_and_save_cross_platform(product, db)
                                
                            except Exception as e:
                                print(f"      ❌ {e}")
                        await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"      ❌ {e}")
                
            await asyncio.sleep(1)
            from app.services.scraper.browser import close_browser_manager
            await close_browser_manager()
    
    return results


async def seed_full(limit: int = 100) -> Dict[str, int]:
    """Full seed: All categories, all platforms"""
    print(f"\n🌟 Full Seed Mode (limit: {limit})")
    results = {p: 0 for p in PLATFORMS}
    total_saved = 0
    
    async with async_session_maker() as db:
        for category in CATEGORIES:
            if total_saved >= limit: break
            print(f"\n📁 Category: {category}")
            queries = SEARCH_QUERIES.get(category, ["trending"])
            
            for platform in PLATFORMS:
                if total_saved >= limit: break
                if category not in PLATFORM_CATEGORY_MAP.get(platform, []): continue
                
                print(f"\n   📌 {platform.upper()}")
                try:
                    handler = await get_platform_handler(platform, db)
                    if not handler: continue
                    
                    for query in queries:
                        if total_saved >= limit: break
                        
                        result = await asyncio.wait_for(handler.search(query=query, page=1), timeout=60)
                        if not result or not result.products: continue
                        
                        for product in result.products[:5]:
                            if total_saved >= limit: break
                            try:
                                product.category = category
                                product = await enrichment_service.enrich_product(product)
                                
                                saved = await product_service.save_product(product_data=product, db=db, is_user_search=False)
                                results[platform] += 1
                                total_saved += 1
                                
                                print(f"   ✅ {saved.title[:40]}... (₹{product.current_price})")
                                # ⚡ TRIGGER CROSS-PLATFORM MATCHING
                                await _find_and_save_cross_platform(product, db)
                                
                            except Exception: pass
                        await asyncio.sleep(0.5)
                except Exception: pass
        
        from app.services.scraper.browser import close_browser_manager
        await close_browser_manager()
    
    return results


def print_summary(results: Dict[str, int], start_time: datetime):
    duration = (datetime.now() - start_time).total_seconds()
    total = sum(results.values())
    
    print("\n" + "=" * 60)
    print("📊 SEEDING SUMMARY")
    print("=" * 60)
    for platform, count in results.items():
        status = "✅" if count > 0 else "⚪"
        print(f"   {status} {platform.capitalize()}: {count} source products (excluding matches)")
    
    print(f"\n   Total Source Products: {total}")
    print(f"   Duration: {duration:.1f}s")
    print("=" * 60)


# =============================================================================
# MAIN
# =============================================================================

async def main(args):
    start_time = datetime.now()
    print("=" * 60)
    print("🌱 DEALHUNT SEEDER v2.0")
    print(f"   Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    if args.quick: results = await seed_quick()
    elif args.smart_rotate:
        categories = args.categories.split(",") if args.categories else None
        results = await seed_smart_rotate(categories=categories, products_per_category=args.products_per_category)
    elif args.full: results = await seed_full(limit=args.limit)
    else:
        print("❌ Please specify a mode: --quick, --smart-rotate, or --full")
        return
    print_summary(results, start_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed DealHunt Database")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--quick", action="store_true", help="Quick seed (2/platform + matches)")
    mode_group.add_argument("--smart-rotate", action="store_true", help="Smart rotation")
    mode_group.add_argument("--full", action="store_true", help="Full seed")
    parser.add_argument("--categories", type=str, help="Comma-separated categories")
    parser.add_argument("--products-per-category", type=int, default=5, help="Products per category")
    parser.add_argument("--limit", type=int, default=100, help="Max total products")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user.")
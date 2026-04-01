#!/usr/bin/env python3
"""
Database Seeding Script
=======================

Populate database with products for demo/testing.
Includes AUTO CROSS-PLATFORM MATCHING & GARBAGE PROTECTION.

Modes:
- --quick:        2 products per platform (fast demo)
- --smart-rotate: Category rotation system
- --full:         All categories, all platforms

Usage:
    python scripts/seed.py --quick
    python scripts/seed.py --smart-rotate --categories "Electronics,Fashion"
    python scripts/seed.py --full --limit 100

Author: DealHunt
Version: 3.0 (Zero False Positives Edition)
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
from app.core.config import settings
from app.services.scraper.factory import get_platform_handler
from app.services.ai.enrichment_service import enrichment_service
from app.services.product_service import product_service

# ✅ NEW IMPORTS: Added Quality Gate and Spec Extraction
from app.services.scraper.cross_platform_matcher import (
    cross_platform_matcher,
    extract_specs,
    check_quality_gate
)

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


def _is_seedable_product(product) -> bool:
    """Guard against saving broken or unavailable listings."""
    if not getattr(product, "product_url", None):
        return False
    if getattr(product, "in_stock", True) is False:
        return False
    return True


# =============================================================================
# SEEDING FUNCTIONS
# =============================================================================

async def seed_quick() -> Dict[str, int]:
    """
    Quick Seed (The Highlight Reel):
    Gets 2 high-profile products from a specific category per platform 
    to quickly prove the system works across all verticals.
    """
    print("\n⚡ QUICK SEED MODE (The Highlight Reel)")
    print("   Fetching 2 iconic products per platform + Cross-Platform Matches...")
    
    results = {p: 0 for p in PLATFORMS}
    
    # The "Highlight Reel" mapping: We force specific, highly-comparable queries.
    QUICK_QUERIES = {
        "amazon": ("Electronics", "iphone 15"),
        "flipkart": ("Electronics", "gaming laptop"),
        "myntra": ("Fashion", "men printed tshirt"),
        "nykaa": ("Beauty", "matte lipstick"),
        "croma": ("Electronics", "smart tv 43 inch"),
        "meesho": ("Fashion", "women kurti")
    }
    
    async with async_session_maker() as db:
        for platform in PLATFORMS:
            # Check if we have a highlight query for this platform
            if platform not in QUICK_QUERIES:
                continue
                
            category, query = QUICK_QUERIES[platform]
            print(f"\n{'='*60}\n📌 QUICK DEMO: {platform.upper()} (Searching: '{query}')\n{'='*60}")
            
            try:
                handler = await get_platform_handler(platform, db)
                if not handler:
                    print(f"   ❌ No handler configured.")
                    continue
                
                result = await asyncio.wait_for(
                    handler.search(query=query, page=1),
                    timeout=45
                )
                
                if not result or not result.products:
                    print(f"   ❌ No products found.")
                    continue
                
                products_saved = 0
                for p in result.products:
                    if products_saved >= 2: break  # Only grab 2 per platform
                    
                    try:
                        if not _is_seedable_product(p):
                            continue

                        # 🛡️ Quality Gate
                        specs = extract_specs(p.title, category=category)
                        passed, gate_reason = check_quality_gate(p.title, specs)
                        if not passed:
                            continue
                        
                        p.category = category
                        product = await enrichment_service.enrich_product(p)
                        
                        # Save Base Product
                        saved = await product_service.save_product(
                            product_data=product,
                            db=db,
                            is_user_search=False
                        )
                        
                        products_saved += 1
                        results[platform] += 1
                        print(f"   ✅ [Base] {saved.title[:45]}... (₹{product.current_price:,.0f})")
                        
                        # ⚡ Cross-Platform Compare
                        await _find_and_save_cross_platform(product, db)
                        print("") # spacing
                        
                    except Exception as e:
                        pass # Silently skip errors to keep demo fast
                
            except Exception as e:
                print(f"   ❌ Platform Error: {str(e)[:40]}")
            
            # Cleanup memory
            await asyncio.sleep(1)
            try:
                from app.services.scraper.browser import close_browser_manager
                await close_browser_manager()
            except: pass
    
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
                                if not _is_seedable_product(product):
                                    continue

                                product.category = category
                                product = await enrichment_service.enrich_product(product)
                                
                                # 🛡️ NEW: QUALITY GATE CHECK
                                specs = extract_specs(product.title)
                                passed, gate_reason = check_quality_gate(product.title, specs)
                                if not passed:
                                    print(f"      ⏭️ Rejected Garbage: {gate_reason} ({product.title[:20]}...)")
                                    continue
                                
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
            try:
                from app.services.scraper.browser import close_browser_manager
                await close_browser_manager()
            except: pass
    
    return results


async def seed_full(limit: int = 100) -> Dict[str, int]:
    """
    Advanced Platform-Centric Full Seed:
    - Loops by PLATFORM first.
    - Amazon/Flipkart: 7 per category, then 5 Trending.
    - Others: 5 per category, then 3 Trending.
    - Cross-platform matching triggers for every single valid product.
    """
    print(f"\n🌟 PLATFORM-CENTRIC FULL SEED MODE")
    results = {p: 0 for p in PLATFORMS}
    
    async with async_session_maker() as db:
        
        # OUTER LOOP: Platform by Platform
        for platform in PLATFORMS:
            print(f"\n{'='*65}\n🚀 STARTING PLATFORM BASE: {platform.upper()}\n{'='*65}")
            
            # 🎯 Determine the limits for this specific platform
            if platform in ["amazon", "flipkart"]:
                cat_limit = 7
                trend_limit = 5
            else:
                cat_limit = 5
                trend_limit = 3
                
            try:
                handler = await get_platform_handler(platform, db)
                if not handler:
                    print(f"   ❌ Platform handler not found.")
                    continue
                
                # ==========================================================
                # STAGE 1: EACH CATEGORY FOR THIS PLATFORM
                # ==========================================================
                platform_categories = PLATFORM_CATEGORY_MAP.get(platform, [])
                
                for category in platform_categories:
                    print(f"\n   📁 CATEGORY: {category.upper()} (Target: {cat_limit} products)")
                    queries = SEARCH_QUERIES.get(category, ["best sellers"])
                    
                    products_saved = 0
                    for query in queries:
                        if products_saved >= cat_limit: break
                        
                        result = await asyncio.wait_for(handler.search(query=query, page=1), timeout=45)
                        if not result or not result.products: continue
                        
                        for p in result.products:
                            if products_saved >= cat_limit: break
                            try:
                                if not _is_seedable_product(p):
                                    continue

                                # Quality Gate
                                specs = extract_specs(p.title, category=category)
                                passed, _ = check_quality_gate(p.title, specs)
                                if not passed: continue
                                
                                p.category = category
                                product = await enrichment_service.enrich_product(p)
                                
                                saved = await product_service.save_product(product_data=product, db=db, is_user_search=False)
                                products_saved += 1
                                results[platform] += 1
                                
                                print(f"      ✅ [{products_saved}/{cat_limit}] {saved.title[:45]}... (₹{product.current_price:,.0f})")
                                
                                # ⚡ Cross-Platform Match
                                await _find_and_save_cross_platform(product, db)
                                print("") # spacing
                                
                            except Exception: pass
                        await asyncio.sleep(0.5)
                
                # ==========================================================
                # STAGE 2: TRENDING DEALS FOR THIS PLATFORM
                # ==========================================================
                print(f"\n   🔥 {platform.upper()} TRENDING DEALS (Target: {trend_limit} products)")
                trend_query = "trending deals" if platform in ["amazon", "flipkart"] else "best sellers"
                
                result = await asyncio.wait_for(handler.search(query=trend_query, page=1), timeout=45)
                if result and result.products:
                    products_saved = 0
                    for p in result.products:
                        if products_saved >= trend_limit: break
                        try:
                            if not _is_seedable_product(p):
                                continue

                            # Quality Gate
                            specs = extract_specs(p.title, category="General")
                            passed, _ = check_quality_gate(p.title, specs)
                            if not passed: continue
                            
                            p.category = "Trending"
                            product = await enrichment_service.enrich_product(p)
                            
                            saved = await product_service.save_product(product_data=product, db=db, is_user_search=False)
                            products_saved += 1
                            results[platform] += 1
                            
                            print(f"      🔥 [{products_saved}/{trend_limit}] {saved.title[:45]}... (₹{product.current_price:,.0f})")
                            
                            # ⚡ Cross-Platform Match
                            await _find_and_save_cross_platform(product, db)
                            print("") # spacing
                            
                        except Exception: pass
                        
            except Exception as e:
                print(f"   ❌ {platform.upper()} Error: {str(e)[:40]}")
            
            # Clean up the browser memory before moving to the next base platform
            try:
                from app.services.scraper.browser import close_browser_manager
                await close_browser_manager()
            except: pass

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
    print("🌱 DEALHUNT SEEDER v3.0 (Zero False Positives Edition)")
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


async def run_seed_products() -> Dict[str, Any]:
    """Scheduler/manual entrypoint aligned with hardened scripts seeder."""
    try:
        from scripts.seed import seed_smart_rotate as hardened_seed_smart_rotate

        results = await hardened_seed_smart_rotate(
            categories=["Electronics", "Fashion", "Home & Kitchen"],
            products_per_category=4,
            enable_ai=not bool(getattr(settings, "SEED_NO_AI", False)),
            enable_cross_match=not bool(getattr(settings, "SEED_NO_CROSS_MATCH", False)),
            timeout_seconds=int(getattr(settings, "SEED_PLATFORM_TIMEOUT_SECONDS", 45)),
            query_interval_seconds=float(getattr(settings, "SEED_QUERY_INTERVAL_SECONDS", 4.0)),
            cooldown_buffer_seconds=int(getattr(settings, "SEED_COOLDOWN_BUFFER_SECONDS", 8)),
        )
        return {"success": True, "results": results, "mode": "smart_rotate_hardened"}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
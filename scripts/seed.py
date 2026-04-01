#!/usr/bin/env python3
"""
Database Seeding Script (Hardened)

Improvements:
- Per-platform DB sessions to avoid poisoned transactions
- Automatic rollback on failures
- Optional AI enrichment to reduce Groq quota pressure
- Optional cross-platform matching to reduce scraper load
- Respects rollout flags (e.g. paused Croma)

Usage:
  python scripts/seed.py --quick
  python scripts/seed.py --quick --no-ai
  python scripts/seed.py --smart-rotate --categories "Electronics,Fashion"
  python scripts/seed.py --full --no-cross-match
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    from asyncio.proactor_events import _ProactorBasePipeTransport

    def silence_proactor_del(self):
        pass

    _ProactorBasePipeTransport.__del__ = silence_proactor_del

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # Keep seeding resilient even on shells that do not support reconfigure.
    pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import Platform, ProductListing
from app.services.ai.enrichment_service import enrichment_service
from app.services.product_service import product_service
from app.services.scraper.cross_platform_matcher import (
    check_quality_gate,
    cross_platform_matcher,
    extract_specs,
)
from app.services.scraper.factory import get_platform_handler
from sqlalchemy import select

PLATFORMS = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]

CATEGORIES = [
    "Electronics",
    "Fashion",
    "Home & Kitchen",
    "Accessories",
    "Books",
]


def build_iphone_lineup_queries() -> List[str]:
    generations = ["17", "16", "15", "14", "13", "12", "11", "x"]
    queries: List[str] = []

    for generation in generations:
        if generation == "x":
            queries.extend(["iphone x", "iphone xr", "iphone xs", "iphone xs max"])
            continue
        queries.extend(
            [
                f"iphone {generation} pro max",
                f"iphone {generation} pro",
                f"iphone {generation} plus",
                f"iphone {generation}",
            ]
        )

    queries.extend(
        [
            "iphone se 2022",
            "iphone se 2020",
            "iphone 15 128gb",
            "iphone 15 256gb",
            "iphone 16 pro 256gb",
            "iphone 16 pro max 512gb",
            "iphone 17 pro 256gb",
            "iphone 17 pro max 512gb",
        ]
    )

    return queries


IPHONE_LINEUP_QUERIES = build_iphone_lineup_queries()

SEARCH_QUERIES = {
    "Electronics": IPHONE_LINEUP_QUERIES
    + [
        "samsung galaxy s24 ultra",
        "samsung galaxy s23",
        "oneplus 12",
        "google pixel 9",
        "gaming phone snapdragon 8 gen 3",
        "camera phone 200mp",
        "best processor mobile",
        "gaming laptop rtx 4060",
        "gaming laptop rtx 4070",
        "laptop intel i7 16gb ram",
        "laptop amd ryzen 7",
        "macbook air m3",
        "macbook pro m4",
        "dell xps laptop",
        "hp victus gaming laptop",
        "lenovo legion gaming laptop",
        "asus rog gaming laptop",
    ],
    "Fashion": [
        "men tshirt",
        "men jeans",
        "women kurti",
        "women dress",
        "girls top",
        "boys tshirt",
        "men sneakers",
        "women sneakers",
        "kids fashion set",
    ],
    "Home & Kitchen": [
        "mixer grinder",
        "air fryer",
        "pressure cooker",
        "cookware set",
        "water bottle steel",
        "kitchen storage container",
        "bedsheet cotton",
        "curtains set",
        "home organizer",
    ],
    "Accessories": [
        "iphone cover",
        "iphone 15 cover",
        "samsung cover",
        "tempered glass",
        "laptop sleeve",
        "mobile charger",
        "usb c cable",
        "earbuds case",
        "watch strap",
        "backpack",
    ],
    "Books": [
        "atomic habits",
        "rich dad poor dad",
        "psychology of money",
        "deep work",
        "self help books",
        "python programming book",
        "system design book",
        "fiction bestseller",
        "business biography",
    ],
}

PLATFORM_CATEGORY_MAP = {
    "amazon": ["Electronics", "Fashion", "Home & Kitchen", "Accessories", "Books"],
    "flipkart": ["Electronics", "Fashion", "Home & Kitchen", "Accessories", "Books"],
    "myntra": ["Fashion"],
    "nykaa": [],
    "croma": ["Electronics"],
    "meesho": ["Fashion", "Home & Kitchen", "Accessories"],
}

DEFAULT_MASTER_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "master_catalog.json")

QUICK_QUERIES = {
    "amazon": ("Electronics", "iphone 15"),
    "flipkart": ("Electronics", "gaming laptop"),
    "myntra": ("Fashion", "men printed tshirt"),
    "croma": ("Electronics", "smart tv 43 inch"),
    "meesho": ("Fashion", "women kurti"),
}


def enabled_seed_platforms() -> List[str]:
    platforms = list(PLATFORMS)
    if not getattr(settings, "CROMA_ENABLED", False) and "croma" in platforms:
        platforms.remove("croma")
    return [p for p in platforms if PLATFORM_CATEGORY_MAP.get(p)]


async def safe_rollback(db) -> None:
    try:
        await db.rollback()
    except Exception:
        pass


async def maybe_enrich(product, enable_ai: bool):
    if not enable_ai:
        return product
    try:
        return await enrichment_service.enrich_product(product)
    except Exception as e:
        print(f"      ⚠️ AI enrichment skipped: {str(e)[:100]}")
        return product


def extract_retry_after_seconds(message: str) -> Optional[int]:
    if not message:
        return None

    match = re.search(r"retry\s+after\s+(\d+)s", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"cool(?:ing)?\s*down\s*for\s*(\d+)s", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def build_query_fallbacks(query: str) -> List[str]:
    """Generate simpler fallback queries when extraction fails on verbose terms."""
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    if len(tokens) <= 3:
        return []

    candidates: List[str] = []

    # Keep first strong intent terms (brand/model usually appear first).
    candidates.append(" ".join(tokens[:4]))

    # Remove marketing words that often hurt selector precision.
    noise = {"latest", "new", "launch", "best", "top", "under", "with"}
    compact = [t for t in tokens if t not in noise]
    if len(compact) >= 3:
        candidates.append(" ".join(compact[:4]))

    deduped: List[str] = []
    for candidate in candidates:
        cleaned = candidate.strip()
        if cleaned and cleaned != query.lower() and cleaned not in deduped:
            deduped.append(cleaned)

    return deduped[:2]


async def execute_search_with_pacing(
    handler,
    query: str,
    timeout_seconds: int,
    query_interval_seconds: float,
    cooldown_buffer_seconds: int,
):
    if query_interval_seconds > 0:
        await asyncio.sleep(query_interval_seconds)

    try:
        result = await asyncio.wait_for(handler.search(query=query, page=1), timeout=timeout_seconds)

        if result and not result.success:
            retry_after = extract_retry_after_seconds(result.error_message or "")
            if retry_after:
                wait_for = retry_after + max(0, cooldown_buffer_seconds)
                print(f"      ⏳ Rate limit cooldown: waiting {wait_for}s before next query")
                await asyncio.sleep(wait_for)

        if result and result.success and result.products:
            return result

        should_retry = False
        if result is None:
            should_retry = True
        elif not result.success:
            err = (result.error_message or "").lower()
            should_retry = any(x in err for x in ["healing", "extraction", "no products", "timeout"])
        elif not result.products:
            should_retry = True

        if should_retry:
            for fallback_query in build_query_fallbacks(query):
                print(f"      🔁 Fallback query: '{fallback_query}'")
                retry_result = await asyncio.wait_for(
                    handler.search(query=fallback_query, page=1),
                    timeout=timeout_seconds,
                )
                if retry_result and retry_result.success and retry_result.products:
                    return retry_result

        return result
    except Exception as e:
        err = str(e)
        retry_after = extract_retry_after_seconds(err)
        if retry_after:
            wait_for = retry_after + max(0, cooldown_buffer_seconds)
            print(f"      ⏳ Rate limit exception cooldown: waiting {wait_for}s")
            await asyncio.sleep(wait_for)
        return None


async def find_and_save_cross_platform(source_product, db, enable_ai: bool) -> None:
    try:
        print("      🔎 Looking for cross-platform matches...")
        alternatives = await cross_platform_matcher.find_alternatives(
            source_product=source_product,
            db=db,
            search_if_not_found=True,
            skip_platforms=[source_product.platform_name],
            max_results=4,
        )

        saved_count = 0
        for alt in alternatives:
            if alt.platform_name.lower() == source_product.platform_name.lower():
                continue
            try:
                alt = await maybe_enrich(alt, enable_ai=enable_ai)
                saved_alt = await product_service.save_product(
                    product_data=alt,
                    db=db,
                    is_user_search=False,
                )
                if saved_alt:
                    saved_count += 1
                    print(f"      🔗 Match saved: {alt.platform_name.upper()} @ ₹{alt.current_price}")
            except Exception as e:
                await safe_rollback(db)
                print(f"      ⚠️ Match save failed: {str(e)[:90]}")

        if saved_count == 0:
            print("      ⚪ No eligible cross-platform matches")
    except Exception as e:
        print(f"      ⚠️ Cross-match failed: {str(e)[:90]}")


async def has_existing_listing(db, platform: str, external_id: Optional[str]) -> bool:
    """Return True when this platform/external_id is already in DB."""
    if not external_id:
        return False

    platform_result = await db.execute(select(Platform).where(Platform.name == platform))
    platform_obj = platform_result.scalar_one_or_none()
    if not platform_obj:
        return False

    listing_result = await db.execute(
        select(ProductListing.id).where(
            ProductListing.platform_id == platform_obj.id,
            ProductListing.external_id == external_id,
        )
    )
    return listing_result.scalar_one_or_none() is not None


async def save_products_from_result(
    db,
    platform: str,
    category: str,
    products,
    target_count: int,
    enable_ai: bool,
    enable_cross_match: bool,
    stats: Dict[str, int],
    seen_external_ids: Optional[set] = None,
) -> int:
    saved_count = 0
    seen_external_ids = seen_external_ids or set()

    for p in products:
        if saved_count >= target_count:
            break

        try:
            external_id = getattr(p, "external_id", None)
            if external_id and external_id in seen_external_ids:
                continue

            if not getattr(p, "product_url", None):
                print("      ⏭️ Skipped: missing product URL")
                continue

            if getattr(p, "in_stock", True) is False:
                print(f"      ⏭️ Skipped: out of stock ({p.title[:40]}...)")
                continue

            specs = extract_specs(p.title, category=category)
            passed, reason = check_quality_gate(p.title, specs)
            if not passed:
                bypass_reasons = (
                    reason.startswith("Title too short")
                    or reason.startswith("Too few words")
                )
                can_refresh_existing = False
                if bypass_reasons:
                    can_refresh_existing = await has_existing_listing(
                        db=db,
                        platform=platform,
                        external_id=getattr(p, "external_id", None),
                    )

                if not can_refresh_existing:
                    print(f"      ⏭️ Rejected by quality gate: {reason}")
                    continue

                print("      🔄 Existing listing detected; bypassing short-title gate for refresh")

            p.category = category
            p = await maybe_enrich(p, enable_ai=enable_ai)

            saved = await product_service.save_product(
                product_data=p,
                db=db,
                is_user_search=False,
            )
            if not saved:
                continue

            if external_id:
                seen_external_ids.add(external_id)

            saved_count += 1
            stats[platform] += 1

            brand_conf = getattr(p, "brand_confidence", 0.0) or 0.0
            color_conf = getattr(p, "color_confidence", 0.0) or 0.0

            confidence_indicator = ""
            if brand_conf >= 0.8 and color_conf >= 0.8:
                confidence_indicator = "🟢"
            elif brand_conf >= 0.6 or color_conf >= 0.6:
                confidence_indicator = "🟡"
            else:
                confidence_indicator = "🔴"

            print(
                f"      ✅ [{saved_count}/{target_count}] {confidence_indicator} "
                f"{saved.title[:45]}... "
                f"(B:{brand_conf:.2f}, C:{color_conf:.2f})"
            )

            if enable_cross_match:
                await find_and_save_cross_platform(p, db, enable_ai=enable_ai)
        except Exception as e:
            await safe_rollback(db)
            print(f"      ⚠️ Product skipped: {str(e)[:100]}")

    return saved_count


async def seed_quick(enable_ai: bool, enable_cross_match: bool, timeout_seconds: int) -> Dict[str, int]:
    print("\n⚡ QUICK SEED MODE")
    print("   2 source products per enabled platform")

    platforms = enabled_seed_platforms()
    stats = {p: 0 for p in platforms}

    for platform in platforms:
        if platform not in QUICK_QUERIES:
            continue

        category, query = QUICK_QUERIES[platform]
        print(f"\n{'=' * 60}\n📌 {platform.upper()} query='{query}'\n{'=' * 60}")

        async with async_session_maker() as db:
            try:
                handler = await get_platform_handler(platform, db)
                result = await execute_search_with_pacing(
                    handler=handler,
                    query=query,
                    timeout_seconds=timeout_seconds,
                    query_interval_seconds=0.0,
                    cooldown_buffer_seconds=0,
                )

                if not result or not result.products:
                    print("   ❌ No products found")
                    continue

                await save_products_from_result(
                    db=db,
                    platform=platform,
                    category=category,
                    products=result.products,
                    target_count=2,
                    enable_ai=enable_ai,
                    enable_cross_match=enable_cross_match,
                    stats=stats,
                )
            except Exception as e:
                await safe_rollback(db)
                print(f"   ❌ Platform failed: {str(e)[:120]}")

        await asyncio.sleep(1)

    return stats


async def seed_smart_rotate(
    categories: Optional[List[str]],
    products_per_category: int,
    enable_ai: bool,
    enable_cross_match: bool,
    timeout_seconds: int,
    query_interval_seconds: float,
    cooldown_buffer_seconds: int,
) -> Dict[str, int]:
    print("\n🔄 SMART ROTATE MODE")
    categories = categories or CATEGORIES[:3]

    platforms = enabled_seed_platforms()
    stats = {p: 0 for p in platforms}

    for category in categories:
        print(f"\n📁 Category: {category}")
        queries = SEARCH_QUERIES.get(category, ["trending"])

        for platform in platforms:
            if category not in PLATFORM_CATEGORY_MAP.get(platform, []):
                continue

            print(f"   📌 Platform: {platform.upper()}")
            async with async_session_maker() as db:
                try:
                    handler = await get_platform_handler(platform, db)

                    saved_for_pair = 0
                    for query in queries:
                        if saved_for_pair >= products_per_category:
                            break
                        result = await execute_search_with_pacing(
                            handler=handler,
                            query=f"{category} {query}",
                            timeout_seconds=timeout_seconds,
                            query_interval_seconds=query_interval_seconds,
                            cooldown_buffer_seconds=cooldown_buffer_seconds,
                        )
                        if not result or not result.products:
                            continue

                        remaining = products_per_category - saved_for_pair
                        saved = await save_products_from_result(
                            db=db,
                            platform=platform,
                            category=category,
                            products=result.products,
                            target_count=remaining,
                            enable_ai=enable_ai,
                            enable_cross_match=enable_cross_match,
                            stats=stats,
                        )
                        saved_for_pair += saved
                except Exception as e:
                    await safe_rollback(db)
                    print(f"      ❌ Failed: {str(e)[:100]}")

            await asyncio.sleep(0.5)

        await asyncio.sleep(1)

    return stats


async def seed_full(
    limit: int,
    enable_ai: bool,
    enable_cross_match: bool,
    timeout_seconds: int,
    query_interval_seconds: float,
    cooldown_buffer_seconds: int,
) -> Dict[str, int]:
    print("\n🌟 FULL MODE")

    platforms = enabled_seed_platforms()
    stats = {p: 0 for p in platforms}

    for platform in platforms:
        print(f"\n{'=' * 65}\n🚀 PLATFORM BASE: {platform.upper()}\n{'=' * 65}")

        cat_limit = 7 if platform in ["amazon", "flipkart"] else 5
        trend_limit = 5 if platform in ["amazon", "flipkart"] else 3

        async with async_session_maker() as db:
            try:
                handler = await get_platform_handler(platform, db)
                categories = PLATFORM_CATEGORY_MAP.get(platform, [])

                for category in categories:
                    if category == "Electronics":
                        category_target = 40 if platform in ["amazon", "flipkart"] else 20
                    elif category == "Accessories":
                        category_target = max(cat_limit, 10)
                    else:
                        category_target = cat_limit

                    print(f"   📁 {category} target={category_target}")
                    queries = SEARCH_QUERIES.get(category, ["best sellers"])
                    saved_for_category = 0

                    for query in queries:
                        if saved_for_category >= category_target:
                            break
                        result = await execute_search_with_pacing(
                            handler=handler,
                            query=query,
                            timeout_seconds=timeout_seconds,
                            query_interval_seconds=query_interval_seconds,
                            cooldown_buffer_seconds=cooldown_buffer_seconds,
                        )
                        if not result or not result.products:
                            continue

                        remaining = category_target - saved_for_category
                        per_query_target = min(2, remaining) if category == "Electronics" else remaining
                        saved = await save_products_from_result(
                            db=db,
                            platform=platform,
                            category=category,
                            products=result.products,
                            target_count=per_query_target,
                            enable_ai=enable_ai,
                            enable_cross_match=enable_cross_match,
                            stats=stats,
                        )
                        saved_for_category += saved

                print(f"   🔥 Trending target={trend_limit}")
                trend_query = "trending deals" if platform in ["amazon", "flipkart"] else "best sellers"
                result = await execute_search_with_pacing(
                    handler=handler,
                    query=trend_query,
                    timeout_seconds=timeout_seconds,
                    query_interval_seconds=query_interval_seconds,
                    cooldown_buffer_seconds=cooldown_buffer_seconds,
                )
                if result and result.products:
                    await save_products_from_result(
                        db=db,
                        platform=platform,
                        category="Trending",
                        products=result.products,
                        target_count=trend_limit,
                        enable_ai=enable_ai,
                        enable_cross_match=enable_cross_match,
                        stats=stats,
                    )
            except Exception as e:
                await safe_rollback(db)
                print(f"   ❌ Platform failed: {str(e)[:120]}")

        if sum(stats.values()) >= limit:
            print(f"\n🎯 Global limit reached: {limit}")
            break

        await asyncio.sleep(1)

    return stats


def load_master_catalog(path: str) -> Dict[str, Dict[str, List[str]]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Master catalog not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    groups = data.get("groups", {}) if isinstance(data, dict) else {}
    if not groups:
        raise ValueError("Master catalog has no groups")

    return groups


def flatten_catalog_group(
    groups: Dict[str, Dict[str, List[str]]],
    group_name: str,
) -> List[Tuple[str, str]]:
    group = groups.get(group_name)
    if not group or not isinstance(group, dict):
        raise ValueError(f"Catalog group not found: {group_name}")

    items: List[Tuple[str, str]] = []
    for category, queries in group.items():
        if not isinstance(queries, list):
            continue
        for query in queries:
            if isinstance(query, str) and query.strip():
                items.append((category, query.strip()))

    if not items:
        raise ValueError(f"Catalog group has no queries: {group_name}")

    return items


async def seed_catalog_group(
    group_name: str,
    catalog_path: str,
    per_query_target: int,
    limit: int,
    max_errors: int,
    max_rate_limit_strikes_per_platform: int,
    max_empty_queries_per_platform: int,
    enable_ai: bool,
    enable_cross_match: bool,
    timeout_seconds: int,
    query_interval_seconds: float,
    cooldown_buffer_seconds: int,
) -> Dict[str, int]:
    print("\n📚 MASTER CATALOG MODE")
    print(f"   Group: {group_name}")
    print(f"   Catalog: {catalog_path}")

    groups = load_master_catalog(catalog_path)
    items = flatten_catalog_group(groups, group_name)

    platforms = enabled_seed_platforms()
    stats = {p: 0 for p in platforms}
    error_count = 0

    for platform in platforms:
        print(f"\n{'=' * 65}\n🚀 PLATFORM: {platform.upper()} | GROUP: {group_name}\n{'=' * 65}")
        platform_rate_limit_strikes = 0
        platform_empty_queries = 0
        platform_seen_external_ids = set()

        async with async_session_maker() as db:
            try:
                handler = await get_platform_handler(platform, db)

                for category, query in items:
                    if category not in PLATFORM_CATEGORY_MAP.get(platform, []):
                        continue

                    if error_count >= max_errors:
                        print(
                            f"\n🛑 Stopping catalog run: error threshold reached "
                            f"({error_count}/{max_errors})."
                        )
                        return stats

                    if sum(stats.values()) >= limit:
                        print(f"\n🎯 Global limit reached: {limit}")
                        return stats

                    print(f"   📁 {category} | query='{query}' | target={per_query_target}")

                    result = await execute_search_with_pacing(
                        handler=handler,
                        query=query,
                        timeout_seconds=timeout_seconds,
                        query_interval_seconds=query_interval_seconds,
                        cooldown_buffer_seconds=cooldown_buffer_seconds,
                    )

                    if result is None:
                        error_count += 1
                        platform_empty_queries += 1
                        print(f"      ⚠️ Search failed ({error_count}/{max_errors})")

                        if platform_empty_queries >= max_empty_queries_per_platform:
                            print(
                                f"      🟠 Skipping {platform.upper()} after "
                                f"{platform_empty_queries} empty/failed queries"
                            )
                            break
                        continue

                    if not result.success and result.error_message:
                        error_count += 1
                        err_lower = result.error_message.lower()
                        if "rate limit" in err_lower or "cooldown" in err_lower:
                            platform_rate_limit_strikes += 1
                        if "healing" in err_lower or "extraction" in err_lower or "no products" in err_lower:
                            platform_empty_queries += 1
                        print(
                            f"      ⚠️ Search error ({error_count}/{max_errors}): "
                            f"{result.error_message[:120]}"
                        )

                        if platform_rate_limit_strikes >= max_rate_limit_strikes_per_platform:
                            print(
                                f"      🟠 Skipping {platform.upper()} after "
                                f"{platform_rate_limit_strikes} rate-limit strikes"
                            )
                            break

                        if error_count >= max_errors:
                            print(
                                f"\n🛑 Stopping catalog run: error threshold reached "
                                f"({error_count}/{max_errors})."
                            )
                            return stats

                        if platform_empty_queries >= max_empty_queries_per_platform:
                            print(
                                f"      🟠 Skipping {platform.upper()} after "
                                f"{platform_empty_queries} empty/failed queries"
                            )
                            break

                    if not result or not result.products:
                        platform_empty_queries += 1
                        print("      ⚪ No products found")

                        if platform_empty_queries >= max_empty_queries_per_platform:
                            print(
                                f"      🟠 Skipping {platform.upper()} after "
                                f"{platform_empty_queries} empty/failed queries"
                            )
                            break
                        continue

                    saved = await save_products_from_result(
                        db=db,
                        platform=platform,
                        category=category,
                        products=result.products,
                        target_count=per_query_target,
                        enable_ai=enable_ai,
                        enable_cross_match=enable_cross_match,
                        stats=stats,
                        seen_external_ids=platform_seen_external_ids,
                    )

                    if saved == 0:
                        platform_empty_queries += 1
                        print("      ⚪ No eligible products saved")
                        if platform_empty_queries >= max_empty_queries_per_platform:
                            print(
                                f"      🟠 Skipping {platform.upper()} after "
                                f"{platform_empty_queries} empty/failed queries"
                            )
                            break
                    else:
                        platform_empty_queries = 0

            except Exception as e:
                await safe_rollback(db)
                print(f"   ❌ Platform failed: {str(e)[:120]}")

        await asyncio.sleep(1)

    return stats


def print_summary(results: Dict[str, int], start_time: datetime) -> None:
    duration = (datetime.now() - start_time).total_seconds()
    total = sum(results.values())

    print("\n" + "=" * 60)
    print("📊 SEEDING SUMMARY")
    print("=" * 60)
    for platform, count in results.items():
        status = "✅" if count > 0 else "⚪"
        print(f"   {status} {platform.capitalize()}: {count} source products")

    print(f"\n   Total Source Products: {total}")
    print(f"   Duration: {duration:.1f}s")

    print("\n   💡 Tip: Run quality check with:")
    print("      python scripts/check_quality.py")

    print("=" * 60)


async def main(args) -> None:
    # Keep seed output focused on scraper/quality signals instead of SQL debug spam.
    engine_logger = logging.getLogger("sqlalchemy.engine")
    engine_logger.setLevel(logging.WARNING)
    engine_logger.propagate = False
    engine_logger.disabled = True

    engine_detail_logger = logging.getLogger("sqlalchemy.engine.Engine")
    engine_detail_logger.setLevel(logging.WARNING)
    engine_detail_logger.propagate = False
    engine_detail_logger.disabled = True

    start_time = datetime.now()
    print("=" * 60)
    print("🌱 DEALHUNT SEEDER (Hardened)")
    print(f"   Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if args.no_cross_match:
        print("   ⚠️ Cross-platform matching is disabled for this run (--no-cross-match).")
        print("   ⚠️ Run cross_platform_miner.py after seeding to recover platform links.")

    if args.quick:
        results = await seed_quick(
            enable_ai=not args.no_ai,
            enable_cross_match=not args.no_cross_match,
            timeout_seconds=args.platform_timeout,
        )
    elif args.catalog_group:
        results = await seed_catalog_group(
            group_name=args.catalog_group,
            catalog_path=args.catalog_path,
            per_query_target=args.catalog_per_query,
            limit=args.limit,
            max_errors=args.max_errors,
            max_rate_limit_strikes_per_platform=args.max_rate_limit_strikes,
            max_empty_queries_per_platform=args.max_empty_queries,
            enable_ai=not args.no_ai,
            enable_cross_match=not args.no_cross_match,
            timeout_seconds=args.platform_timeout,
            query_interval_seconds=args.query_interval,
            cooldown_buffer_seconds=args.cooldown_buffer,
        )
    elif args.smart_rotate:
        categories = args.categories.split(",") if args.categories else None
        results = await seed_smart_rotate(
            categories=categories,
            products_per_category=args.products_per_category,
            enable_ai=not args.no_ai,
            enable_cross_match=not args.no_cross_match,
            timeout_seconds=args.platform_timeout,
            query_interval_seconds=args.query_interval,
            cooldown_buffer_seconds=args.cooldown_buffer,
        )
    else:
        results = await seed_full(
            limit=args.limit,
            enable_ai=not args.no_ai,
            enable_cross_match=not args.no_cross_match,
            timeout_seconds=args.platform_timeout,
            query_interval_seconds=args.query_interval,
            cooldown_buffer_seconds=args.cooldown_buffer,
        )

    print_summary(results, start_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed DealHunt Database")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--quick", action="store_true", help="Quick seed (2 products/platform)")
    mode_group.add_argument("--catalog-group", type=str, help="Master catalog group (e.g. mobiles, laptops)")
    mode_group.add_argument("--smart-rotate", action="store_true", help="Category rotation seed")
    mode_group.add_argument("--full", action="store_true", help="Full platform-centric seed")

    parser.add_argument("--categories", type=str, help="Comma-separated categories")
    parser.add_argument("--products-per-category", type=int, default=5, help="Products per category")
    parser.add_argument("--limit", type=int, default=260, help="Maximum source products")
    parser.add_argument("--catalog-path", type=str, default=DEFAULT_MASTER_CATALOG_PATH, help="Path to master catalog JSON")
    parser.add_argument("--catalog-per-query", type=int, default=2, help="Products to save per master-catalog query")
    parser.add_argument("--max-errors", type=int, default=9, help="Stop catalog run after this many search errors")
    parser.add_argument("--max-rate-limit-strikes", type=int, default=3, help="Skip a platform after this many rate-limit errors")
    parser.add_argument("--max-empty-queries", type=int, default=8, help="Skip a platform after this many empty/unsaved catalog queries")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI enrichment to avoid Groq limits")
    parser.add_argument("--no-cross-match", action="store_true", help="Disable cross-platform matching")
    parser.add_argument("--platform-timeout", type=int, default=45, help="Per-search timeout seconds")
    parser.add_argument("--query-interval", type=float, default=4.0, help="Seconds to wait between queries (catalog/smart/full)")
    parser.add_argument("--cooldown-buffer", type=int, default=8, help="Extra seconds added after platform retry-after cooldown")

    cli_args = parser.parse_args()

    try:
        asyncio.run(main(cli_args))
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")

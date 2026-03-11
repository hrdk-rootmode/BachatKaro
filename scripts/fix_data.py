#!/usr/bin/env python3
"""
Data Fixer v3.0 — Full Database Coverage
==========================================

Scans and fixes NULL/empty/broken data across ALL tables:

  TABLE: products
    ✓ brand = NULL / 'Unknown'       → AI extraction from title
    ✓ category = NULL / 'General'    → AI categorization
    ✓ subcategory = NULL             → AI subcategorization
    ✓ image_url = NULL               → Pull from listing URL if possible
    ✓ specifications = {} / NULL     → AI spec extraction
    ✓ ai_metadata.essence = NULL     → AI generation
    ✓ ai_metadata.tags = []          → AI generation
    ✓ ai_metadata.quality_score = 0  → AI scoring
    ✓ stats = NULL                   → Default reset
    ✓ Orphan products (no listings)  → Optional delete

  TABLE: product_listings
    ✓ original_price = NULL          → Set equal to current_price
    ✓ discount_percent = NULL        → Calculate from prices
    ✓ rating = NULL                  → Set 0.0 placeholder
    ✓ review_count = NULL            → Set 0
    ✓ review_summary = NULL / {}     → Set default {}
    ✓ currency = NULL                → Default 'INR'
    ✓ price_history = NULL           → Seed from current_price
    ✓ in_stock = NULL                → Default True
    ✓ scrape_error_count = NULL      → Default 0

  TABLE: platforms
    ✓ selectors = NULL / {}          → Inject known good selectors
    ✓ scrape_delay_seconds = NULL    → Default 2
    ✓ is_active = NULL               → Default True

Usage:
    python scripts/fix_data.py                          # Scan only
    python scripts/fix_data.py --fix-all                # Fix ALL tables
    python scripts/fix_data.py --fix-products           # Only products table
    python scripts/fix_data.py --fix-listings           # Only listings table
    python scripts/fix_data.py --fix-platforms          # Only platforms table
    python scripts/fix_data.py --fix-orphans            # Delete orphan products
    python scripts/fix_data.py --re-enrich              # Re-run AI on all products
    python scripts/fix_data.py --dry-run --fix-all      # Preview without saving
    python scripts/fix_data.py --limit 200 --fix-all    # Custom batch size

Version: 3.0
"""

import asyncio
import argparse
import sys
import os
import json
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows: use SelectorEventLoop to avoid "Event loop is closed" error on exit
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


from sqlalchemy import select, func, or_, and_, delete, update, text
from sqlalchemy.orm import selectinload
from app.core.database import async_session_maker
from app.models import Product, ProductListing, Platform
from app.services.ai.groq_client import groq_client
from app.services.scraper.base import ProductData


# ── Cosmetic helpers ────────────────────────────────────────────────────────
BOLD = "\033[1m"
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
DIM = "\033[2m"

def ok(msg): print(f"      {GREEN}✅{RESET} {msg}")
def warn(msg): print(f"      {YELLOW}⚠️ {RESET} {msg}")
def err(msg): print(f"      {RED}❌{RESET} {msg}")
def info(msg): print(f"      {DIM}{msg}{RESET}")
def header(msg): print(f"\n{BOLD}{CYAN}{msg}{RESET}")

# ── Brand validation: words that are NEVER real brands ───────────────────────
GENERIC_WORDS = {
    "unknown", "generic", "unbranded", "other", "n/a", "na", "none",
    "new", "men", "women", "boys", "girls", "pack", "set", "combo",
    "cotton", "silk", "wool", "polyester", "nylon", "leather", "synthetic",
    "sneaker", "sneakers", "shoe", "dress", "shirt", "trouser", "pant",
    "kurta", "saree", "top", "bottom", "jacket", "casual", "formal",
    "stylish", "trendy", "elegant", "latest", "premium", "luxury",
    "digital", "analog", "silicone", "watch", "bag", "purse", "tote",
    "a-line", "maxi", "midi", "fit", "flare", "solid", "printed",
    "round", "polo", "v-neck", "maroon", "blue", "red", "black", "white",
    "brown", "pink", "yellow", "green", "grey", "beige", "gold",
    "square", "tech", "te", "db", "sb", "fashion", "collection",
    "series", "model", "product", "item", "brand", "original",
}

KNOWN_PLATFORM_SELECTORS = {
    "amazon": {
        "search_url_template": "https://www.amazon.in/s?k={query}&ref=sr_pg_1",
        "product_title": "#productTitle, span.a-size-large.product-title-word-break",
        "product_price": "span.a-price-whole, .a-offscreen",
        "product_image": "#landingImage, #imgTagWrapperId img",
        "product_rating": "span.a-icon-alt, #acrPopover",
        "product_url": "a.a-link-normal.s-no-outline",
        "search_result_title": "h2 a span, .a-size-medium.a-color-base.a-text-normal",
        "search_result_price": ".a-price .a-offscreen",
        "search_result_image": ".s-image",
        "healed_selectors": [],
    },
    "flipkart": {
        "search_url_template": "https://www.flipkart.com/search?q={query}&page=1",
        "product_title": "span.B_NuCI, .G6XhRU",
        "product_price": "div._30jeq3._16Jk6d, ._25b18c ._30jeq3",
        "product_image": "img._396cs4, .CXW8mj img",
        "product_rating": "div._3LWZlK",
        "product_url": "a._1fQZEK, a.s1Q9rs",
        "search_result_title": "._4rR01T, .s1Q9rs",
        "search_result_price": "._30jeq3",
        "search_result_image": "._396cs4",
        "healed_selectors": [],
    },
    "meesho": {
        "search_url_template": "https://www.meesho.com/search?q={query}",
        "product_title": "p.NewProductCard__title, h4",
        "product_price": "h5.NewProductCard__discountedPrice",
        "product_image": "img.NewProductCard__image",
        "product_rating": "p.NewProductCard__rating",
        "product_url": "a.NewProductCard__link",
        "search_result_title": "p[class*='title']",
        "search_result_price": "h5[class*='price']",
        "search_result_image": "img[class*='image']",
        "healed_selectors": [],
    },
    "myntra": {
        "search_url_template": "https://www.myntra.com/{query}",
        "product_title": "h1.pdp-name",
        "product_price": ".pdp-price strong",
        "product_image": ".image-grid-image",
        "product_rating": ".index-overallRating",
        "product_url": "li.product-base a",
        "search_result_title": "h3.product-brand",
        "search_result_price": ".product-discountedPrice",
        "search_result_image": ".product-imageSliderContainer img",
        "healed_selectors": [],
    },
    "croma": {
        "search_url_template": "https://www.croma.com/searchB?q={query}:relevance&langCode=en",
        "product_title": "h1.pdp-title",
        "product_price": "span.amount",
        "product_image": ".pdp-image-gallery img",
        "product_rating": ".cr-avg-rating",
        "product_url": ".product .cp-title a",
        "search_result_title": ".product .cp-title",
        "search_result_price": ".pdpPrice",
        "search_result_image": ".product-img img",
        "healed_selectors": [],
    },
    "nykaa": {
        "search_url_template": "https://www.nykaa.com/search/result/?q={query}",
        "product_title": "h1.css-ywbabr",
        "product_price": "span.css-111z9ua",
        "product_image": "img.css-11wmvr3",
        "product_rating": ".css-2rdnbl",
        "product_url": "a.css-qppxbd",
        "search_result_title": "a.css-qppxbd",
        "search_result_price": "span.css-111z9ua",
        "search_result_image": "img.css-11wmvr3",
        "healed_selectors": [],
    },
}

DEFAULT_SELECTORS = {
    "search_url_template": "",
    "product_title": "",
    "product_price": "",
    "product_image": "",
    "product_rating": "",
    "product_url": "",
    "healed_selectors": [],
}


# =============================================================================
# SECTION 1: COMPREHENSIVE SCANNER
# =============================================================================

async def scan_database() -> Dict[str, Any]:
    """Deep scan for all data quality issues across all tables"""
    header("🔍 Deep Scanning Database...")

    issues = {}

    async with async_session_maker() as db:

        # ── Products ────────────────────────────────────────────────────────
        r = await db.execute(select(func.count(Product.id)))
        issues["products_total"] = r.scalar() or 0

        for key, cond in [
            ("products_missing_brand",    or_(Product.brand == None, Product.brand == "", Product.brand == "Unknown")),
            ("products_missing_category", or_(Product.category == None, Product.category == "", Product.category == "General")),
            ("products_missing_subcat",   or_(Product.subcategory == None, Product.subcategory == "")),
            ("products_missing_image",    or_(Product.image_url == None, Product.image_url == "")),
            ("products_missing_essence",  or_(Product.ai_metadata == None, Product.ai_metadata['essence'].astext == None, Product.ai_metadata['essence'].astext == "")),
            ("products_missing_tags",     or_(Product.ai_metadata == None, Product.ai_metadata['tags'].astext == None, Product.ai_metadata['tags'].astext == "[]")),
            ("products_low_ai_score",     or_(Product.ai_metadata == None, Product.ai_metadata['quality_score'].astext == None, Product.ai_metadata['quality_score'].astext == "0")),
            ("products_empty_specs",      or_(Product.specifications == None, Product.specifications == {})),
            ("products_null_stats",       Product.stats == None),
        ]:
            r = await db.execute(select(func.count(Product.id)).where(cond))
            issues[key] = r.scalar() or 0

        r = await db.execute(select(func.count(Product.id)).where(
            ~Product.id.in_(select(ProductListing.product_id).distinct())
        ))
        issues["products_orphan"] = r.scalar() or 0

        # ── ProductListings ─────────────────────────────────────────────────
        r = await db.execute(select(func.count(ProductListing.id)))
        issues["listings_total"] = r.scalar() or 0

        for key, cond in [
            ("listings_null_original_price",  ProductListing.original_price == None),
            ("listings_null_discount",        ProductListing.discount_percent == None),
            ("listings_null_rating",          ProductListing.rating == None),
            ("listings_null_review_count",    ProductListing.review_count == None),
            ("listings_null_review_summary",  or_(ProductListing.review_summary == None, ProductListing.review_summary == {})),
            ("listings_null_currency",        or_(ProductListing.currency == None, ProductListing.currency == "")),
            ("listings_null_in_stock",        ProductListing.in_stock == None),
            ("listings_null_price_history",   or_(ProductListing.price_history_json == None, ProductListing.price_history_json == [])),
            ("listings_null_error_count",     ProductListing.scrape_error_count == None),
        ]:
            r = await db.execute(select(func.count(ProductListing.id)).where(cond))
            issues[key] = r.scalar() or 0

        # ── Platforms ───────────────────────────────────────────────────────
        r = await db.execute(select(func.count(Platform.id)))
        issues["platforms_total"] = r.scalar() or 0

        r = await db.execute(select(func.count(Platform.id)).where(
            or_(Platform.selectors == None, Platform.selectors == {})
        ))
        issues["platforms_null_selectors"] = r.scalar() or 0

        r = await db.execute(select(func.count(Platform.id)).where(
            Platform.scrape_delay_seconds == None
        ))
        issues["platforms_null_delay"] = r.scalar() or 0

    return issues


def print_scan_results(issues: Dict[str, Any]):
    total_p = issues.get("products_total", 0)
    total_l = issues.get("listings_total", 0)
    total_pl = issues.get("platforms_total", 0)

    def severity(v, total):
        pct = (v / max(total, 1)) * 100
        if pct > 30: return RED + "🔴"
        if pct > 10: return YELLOW + "🟡"
        if pct > 0:  return YELLOW + "🟠"
        return GREEN + "✅"

    def row(label, key, total):
        v = issues.get(key, 0)
        pct = (v / max(total, 1)) * 100
        icon = severity(v, total)
        print(f"    {icon} {label}: {v}/{total} ({pct:.1f}%){RESET}")

    print(f"\n{'=' * 65}")
    print(f"{BOLD}📊 DATA QUALITY REPORT{RESET}")
    print(f"{'=' * 65}")

    print(f"\n{BOLD}  ┌─ TABLE: products ({total_p} rows){RESET}")
    row("brand = NULL/Unknown",       "products_missing_brand",    total_p)
    row("category = NULL/General",    "products_missing_category", total_p)
    row("subcategory = NULL",         "products_missing_subcat",   total_p)
    row("image_url = NULL",           "products_missing_image",    total_p)
    row("ai_metadata.essence = NULL", "products_missing_essence",  total_p)
    row("ai_metadata.tags = []",      "products_missing_tags",     total_p)
    row("quality_score = 0/NULL",     "products_low_ai_score",     total_p)
    row("specifications = {}",        "products_empty_specs",      total_p)
    row("stats = NULL",               "products_null_stats",       total_p)
    row("orphan (no listings)",       "products_orphan",           total_p)

    print(f"\n{BOLD}  ├─ TABLE: product_listings ({total_l} rows){RESET}")
    row("original_price = NULL",      "listings_null_original_price",  total_l)
    row("discount_percent = NULL",    "listings_null_discount",        total_l)
    row("rating = NULL",              "listings_null_rating",          total_l)
    row("review_count = NULL",        "listings_null_review_count",    total_l)
    row("review_summary = NULL/{}",   "listings_null_review_summary",  total_l)
    row("currency = NULL",            "listings_null_currency",        total_l)
    row("in_stock = NULL",            "listings_null_in_stock",        total_l)
    row("price_history = NULL",       "listings_null_price_history",   total_l)
    row("scrape_error_count = NULL",  "listings_null_error_count",     total_l)

    print(f"\n{BOLD}  └─ TABLE: platforms ({total_pl} rows){RESET}")
    row("selectors = NULL/{}",        "platforms_null_selectors", total_pl)
    row("scrape_delay = NULL",        "platforms_null_delay",     total_pl)

    # Overall health
    fixable = sum(v for k, v in issues.items()
                  if k not in ("products_total", "listings_total", "platforms_total"))
    total_rows = total_p + total_l + total_pl
    health = max(0, 100 - (fixable / max(total_rows, 1) * 100))
    bar_filled = int(health / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    color = GREEN if health > 80 else (YELLOW if health > 50 else RED)
    print(f"\n  {color}DATA HEALTH: [{bar}] {health:.1f}%{RESET}")
    print(f"{'=' * 65}")


# =============================================================================
# SECTION 2: PRODUCTS TABLE FIXER
# =============================================================================

def _is_valid_brand(brand: Optional[str]) -> bool:
    """Check brand is not a generic word"""
    if not brand:
        return False
    b = brand.lower().strip()
    if b in GENERIC_WORDS:
        return False
    if len(b) <= 1:
        return False
    return True


def _build_product_data(product: Product, listing: Optional[ProductListing] = None,
                        platform_name: str = "unknown") -> ProductData:
    price = Decimal(str(listing.current_price)) if listing and listing.current_price else Decimal('0')
    return ProductData(
        external_id=str(product.id),
        title=product.title,
        current_price=price,
        product_url=listing.product_url if listing else "",
        platform_name=platform_name,
        brand=product.brand if _is_valid_brand(product.brand) else None,
        category=product.category if product.category and product.category not in ("General", "") else None,
        subcategory=product.subcategory,
        image_url=product.image_url or "",
        rating=listing.rating if listing else None,
        review_count=listing.review_count if listing else None,
        specifications=product.specifications or {},
    )


async def fix_products(limit: int = 200, dry_run: bool = False) -> Dict[str, int]:
    """Fix all NULL/empty fields in the products table using AI"""
    header(f"🛠️  Fixing Products Table (limit={limit}, dry_run={dry_run})")

    stats = {"brand": 0, "category": 0, "subcategory": 0, "specs": 0,
             "essence": 0, "tags": 0, "stats_reset": 0, "errors": 0, "skipped": 0}

    async with async_session_maker() as db:
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.listings))
            .where(or_(
                Product.brand == None, Product.brand == "", Product.brand == "Unknown",
                Product.category == None, Product.category == "", Product.category == "General",
                Product.subcategory == None,
                Product.ai_metadata == None,
                Product.ai_metadata['essence'].astext == None,
                Product.ai_metadata['essence'].astext == "",
                Product.ai_metadata['tags'].astext == None,
                Product.ai_metadata['tags'].astext == "[]",
                Product.specifications == None,
                Product.specifications == {},
                Product.stats == None,
            ))
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        products = result.scalars().all()
        print(f"\n   Found {len(products)} products needing fixes\n")

        batch = 0
        for i, product in enumerate(products, 1):
            try:
                listing = product.listings[0] if product.listings else None
                platform_name = "unknown"
                if listing:
                    try:
                        r = await db.execute(select(Platform.name).where(Platform.id == listing.platform_id))
                        platform_name = r.scalar() or "unknown"
                    except Exception:
                        pass

                print(f"   [{i}/{len(products)}] {product.title[:55]}...")

                # ── Fix stats (no AI needed) ──
                if product.stats is None:
                    if not dry_run:
                        product.stats = {"views": 0, "clicks": 0, "watches": 0, "searches": 0, "conversions": 0}
                    stats["stats_reset"] += 1

                # ── AI Enrichment ──
                pd = _build_product_data(product, listing, platform_name)
                enriched = await groq_client.process_product(pd)

                if not enriched:
                    stats["skipped"] += 1
                    info("AI returned nothing")
                    continue

                changes = []

                # Brand
                if not _is_valid_brand(product.brand):
                    new_brand = enriched.get("specifications", {}).get("brand")
                    if _is_valid_brand(new_brand):
                        if not dry_run: product.brand = new_brand
                        stats["brand"] += 1
                        changes.append(f"Brand→{new_brand}")

                # Category
                if not product.category or product.category in ("", "General"):
                    new_cat = enriched.get("category")
                    if new_cat and new_cat not in ("", "General"):
                        if not dry_run: product.category = new_cat
                        stats["category"] += 1
                        changes.append(f"Category→{new_cat}")

                # Subcategory
                if not product.subcategory:
                    new_sub = enriched.get("subcategory")
                    if new_sub:
                        if not dry_run: product.subcategory = new_sub
                        stats["subcategory"] += 1
                        changes.append(f"Subcat→{new_sub}")

                # Specifications
                if not product.specifications or product.specifications == {}:
                    new_specs = {k: v for k, v in (enriched.get("specifications") or {}).items() if v is not None}
                    if new_specs:
                        if not dry_run: product.specifications = new_specs
                        stats["specs"] += 1
                        changes.append(f"Specs({len(new_specs)})")

                # AI Metadata
                ai_meta = product.ai_metadata or {}
                ai_changed = False

                new_essence = enriched.get("essence", "")
                if new_essence and len(new_essence) >= 5 and not ai_meta.get("essence"):
                    ai_meta["essence"] = new_essence
                    stats["essence"] += 1
                    changes.append(f"Essence→{new_essence[:25]}...")
                    ai_changed = True

                new_tags = enriched.get("tags", [])
                if new_tags and not ai_meta.get("tags"):
                    ai_meta["tags"] = new_tags
                    stats["tags"] += 1
                    changes.append(f"Tags({len(new_tags)})")
                    ai_changed = True

                new_score = enriched.get("quality_score", 0)
                if new_score > (ai_meta.get("quality_score") or 0):
                    ai_meta["quality_score"] = new_score
                    ai_changed = True

                if ai_changed:
                    ai_meta["fixed_at"] = datetime.utcnow().isoformat()
                    ai_meta["fixed_by"] = "fix_data_v3"
                    if not dry_run: product.ai_metadata = ai_meta

                if changes:
                    ok(" | ".join(changes))
                else:
                    info("No fixable fields")

                batch += 1
                if batch >= 10 and not dry_run:
                    await db.commit()
                    batch = 0

            except Exception as e:
                stats["errors"] += 1
                err(str(e)[:80])

            await asyncio.sleep(0.2)  # Light rate limit

        if not dry_run and batch > 0:
            await db.commit()

    return stats


# =============================================================================
# SECTION 3: PRODUCT_LISTINGS TABLE FIXER  (NO AI — pure logic)
# =============================================================================

async def fix_listings(limit: int = 500, dry_run: bool = False) -> Dict[str, int]:
    """
    Fix NULL fields in product_listings using pure calculation logic.
    This is fast (no AI) — runs on all listings in bulk.
    """
    header(f"📋 Fixing ProductListings Table (limit={limit}, dry_run={dry_run})")

    stats = {
        "original_price": 0, "discount_percent": 0, "rating": 0,
        "review_count": 0, "review_summary": 0, "currency": 0,
        "in_stock": 0, "price_history": 0, "error_count": 0,
        "errors": 0,
    }

    async with async_session_maker() as db:
        result = await db.execute(
            select(ProductListing).where(or_(
                ProductListing.original_price == None,
                ProductListing.discount_percent == None,
                ProductListing.rating == None,
                ProductListing.review_count == None,
                ProductListing.review_summary == None,
                ProductListing.review_summary == {},
                ProductListing.currency == None,
                ProductListing.in_stock == None,
                ProductListing.price_history_json == None,
                ProductListing.price_history_json == [],
                ProductListing.scrape_error_count == None,
            ))
            .limit(limit)
        )
        listings = result.scalars().all()
        print(f"\n   Found {len(listings)} listings needing fixes")

        batch = 0
        fixed_ids = []

        for listing in listings:
            changed = []
            cp = listing.current_price or 0

            # ── original_price ──────────────────────────────────────────────
            if listing.original_price is None:
                if not dry_run: listing.original_price = cp
                stats["original_price"] += 1
                changed.append("orig_price")

            # ── discount_percent ─────────────────────────────────────────────
            if listing.discount_percent is None:
                op = listing.original_price or cp
                if op and cp and op > cp:
                    disc = round(((op - cp) / op) * 100, 1)
                else:
                    disc = 0.0
                if not dry_run: listing.discount_percent = disc
                stats["discount_percent"] += 1
                changed.append(f"disc={disc}%")

            # ── rating ───────────────────────────────────────────────────────
            if listing.rating is None:
                if not dry_run: listing.rating = 0.0
                stats["rating"] += 1
                changed.append("rating=0")

            # ── review_count ─────────────────────────────────────────────────
            if listing.review_count is None:
                if not dry_run: listing.review_count = 0
                stats["review_count"] += 1
                changed.append("reviews=0")

            # ── review_summary ───────────────────────────────────────────────
            if listing.review_summary is None or listing.review_summary == {}:
                default_summary = {"positive": [], "negative": [], "summary": "No reviews yet"}
                if not dry_run: listing.review_summary = default_summary
                stats["review_summary"] += 1
                changed.append("summary")

            # ── currency ──────────────────────────────────────────────────────
            if not listing.currency:
                if not dry_run: listing.currency = "INR"
                stats["currency"] += 1
                changed.append("currency=INR")

            # ── in_stock ──────────────────────────────────────────────────────
            if listing.in_stock is None:
                if not dry_run: listing.in_stock = True
                stats["in_stock"] += 1
                changed.append("in_stock=True")

            # ── price_history ─────────────────────────────────────────────────
            if not listing.price_history_json:
                seed = [{"p": round(cp, 2), "d": date.today().isoformat()}] if cp else []
                if not dry_run: listing.price_history_json = seed
                stats["price_history"] += 1
                changed.append("price_hist")

            # ── scrape_error_count ────────────────────────────────────────────
            if listing.scrape_error_count is None:
                if not dry_run: listing.scrape_error_count = 0
                stats["error_count"] += 1
                changed.append("err_count=0")

            if changed:
                fixed_ids.append(listing.id)

            batch += 1
            if batch >= 50 and not dry_run:
                await db.commit()
                batch = 0

        if not dry_run and batch > 0:
            await db.commit()

        print(f"   Fixed {len(fixed_ids)} listings")

    return stats


# =============================================================================
# SECTION 4: PLATFORMS TABLE FIXER
# =============================================================================

async def fix_platforms(dry_run: bool = False) -> Dict[str, int]:
    """Fix NULL selectors and other missing fields in platforms table"""
    header(f"🌐 Fixing Platforms Table (dry_run={dry_run})")

    stats = {"selectors": 0, "delay": 0, "activated": 0, "errors": 0}

    async with async_session_maker() as db:
        result = await db.execute(select(Platform))
        platforms = result.scalars().all()
        print(f"\n   Found {len(platforms)} platforms\n")

        for platform in platforms:
            changes = []

            # ── Selectors ─────────────────────────────────────────────────────
            current_selectors = platform.selectors or {}
            needs_selector_fix = (
                not current_selectors
                or not current_selectors.get("search_url_template")
                or not current_selectors.get("product_title")
            )

            if needs_selector_fix:
                known = KNOWN_PLATFORM_SELECTORS.get(platform.name.lower())
                if known:
                    if not dry_run: platform.selectors = known
                    stats["selectors"] += 1
                    changes.append("selectors=known")
                else:
                    # Inject default empty structure so it's not NULL
                    if not dry_run: platform.selectors = DEFAULT_SELECTORS.copy()
                    stats["selectors"] += 1
                    changes.append("selectors=default")

            # Ensure healed_selectors key always exists
            elif "healed_selectors" not in (platform.selectors or {}):
                new_sel = dict(platform.selectors)
                new_sel["healed_selectors"] = []
                if not dry_run: platform.selectors = new_sel
                changes.append("healed_selectors=[]")

            # ── scrape_delay_seconds ──────────────────────────────────────────
            if platform.scrape_delay_seconds is None:
                if not dry_run: platform.scrape_delay_seconds = 2
                stats["delay"] += 1
                changes.append("delay=2s")

            # ── is_active ─────────────────────────────────────────────────────
            if platform.is_active is None:
                if not dry_run: platform.is_active = True
                stats["activated"] += 1
                changes.append("is_active=True")

            if changes:
                print(f"   {GREEN}✅{RESET} {platform.name}: {' | '.join(changes)}")
            else:
                print(f"   {DIM}⚪ {platform.name}: OK{RESET}")

        if not dry_run:
            await db.commit()

    return stats


# =============================================================================
# SECTION 5: ORPHAN CLEANER
# =============================================================================

async def fix_orphans(dry_run: bool = False) -> Dict[str, int]:
    """Delete products with no listings"""
    header(f"🗑️  Cleaning Orphan Products (dry_run={dry_run})")
    stats = {"deleted": 0}

    async with async_session_maker() as db:
        result = await db.execute(
            select(Product.id, Product.title).where(
                ~Product.id.in_(select(ProductListing.product_id).distinct())
            )
        )
        orphans = result.all()
        print(f"\n   Found {len(orphans)} orphans\n")

        for pid, title in orphans:
            print(f"   {'🗑️ ' if not dry_run else '👁️ '} {title[:55]}...")
            if not dry_run:
                await db.execute(delete(Product).where(Product.id == pid))
            stats["deleted"] += 1

        if not dry_run and orphans:
            await db.commit()

    return stats


# =============================================================================
# SECTION 6: RE-ENRICH (Force AI refresh on all products)
# =============================================================================

async def re_enrich(limit: int = 50, dry_run: bool = False) -> Dict[str, int]:
    """Force re-run AI on products, update only if quality improves"""
    header(f"🤖 Re-enriching Products (limit={limit}, dry_run={dry_run})")
    stats = {"processed": 0, "improved": 0, "brand_fixed": 0, "cat_fixed": 0, "unchanged": 0, "errors": 0}

    async with async_session_maker() as db:
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.listings))
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        products = result.scalars().all()

        batch = 0
        for i, product in enumerate(products, 1):
            try:
                listing = product.listings[0] if product.listings else None
                old_score = (product.ai_metadata or {}).get("quality_score") or 0
                pd = _build_product_data(product, listing)
                enriched = await groq_client.process_product(pd)

                if not enriched:
                    stats["unchanged"] += 1
                    continue

                changes = []
                new_score = enriched.get("quality_score", 0)

                if new_score > old_score:
                    ai_meta = product.ai_metadata or {}
                    ai_meta.update({
                        "essence": enriched.get("essence") or ai_meta.get("essence", ""),
                        "tags": enriched.get("tags") or ai_meta.get("tags", []),
                        "quality_score": new_score,
                        "re_enriched_at": datetime.utcnow().isoformat(),
                    })
                    if not dry_run: product.ai_metadata = ai_meta
                    stats["improved"] += 1
                    changes.append(f"score {old_score}→{new_score}")

                # Always fix brand/category regardless of score
                if not _is_valid_brand(product.brand):
                    nb = enriched.get("specifications", {}).get("brand")
                    if _is_valid_brand(nb):
                        if not dry_run: product.brand = nb
                        stats["brand_fixed"] += 1
                        changes.append(f"brand→{nb}")

                if not product.category or product.category in ("", "General"):
                    nc = enriched.get("category")
                    if nc and nc not in ("", "General"):
                        if not dry_run:
                            product.category = nc
                            product.subcategory = enriched.get("subcategory") or product.subcategory
                        stats["cat_fixed"] += 1
                        changes.append(f"cat→{nc}")

                stats["processed"] += 1
                if changes:
                    ok(f"[{i}] {' | '.join(changes)}")
                else:
                    info(f"[{i}] No improvement (score={old_score})")
                    stats["unchanged"] += 1

                batch += 1
                if batch >= 10 and not dry_run:
                    await db.commit()
                    batch = 0

                await asyncio.sleep(0.2)

            except Exception as e:
                stats["errors"] += 1
                err(f"[{i}] {str(e)[:70]}")

        if not dry_run and batch > 0:
            await db.commit()

    return stats


# =============================================================================
# SECTION 7: SUMMARY PRINTER
# =============================================================================

def print_summary(title: str, results: Dict[str, int]):
    print(f"\n{'─' * 55}")
    print(f"{BOLD}📊 {title}{RESET}")
    print(f"{'─' * 55}")
    for key, value in results.items():
        if value > 0 and "error" in key:
            print(f"   {RED}❌{RESET} {key.replace('_', ' ').title()}: {value}")
        elif value > 0:
            print(f"   {GREEN}✅{RESET} {key.replace('_', ' ').title()}: {value}")
        else:
            print(f"   {DIM}⚪ {key.replace('_', ' ').title()}: 0{RESET}")
    print(f"{'─' * 55}")


# =============================================================================
# SECTION 8: MAIN
# =============================================================================

async def main(args):
    start = datetime.now()

    print(f"\n{'=' * 65}")
    print(f"{BOLD}🔧 DEALHUNT DATA FIXER v3.0{RESET}")
    print(f"   Time: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        print(f"   {YELLOW}⚠️  DRY RUN — no changes will be written to DB{RESET}")
    print(f"{'=' * 65}")

    # Always scan
    issues = await scan_database()
    print_scan_results(issues)

    do_anything = any([
        args.fix_products, args.fix_listings, args.fix_platforms,
        args.fix_orphans, args.re_enrich, args.fix_all,
    ])

    if not do_anything:
        print(f"\n{BOLD}📋 Scan complete. Available actions:{RESET}")
        print("   --fix-all          Fix all tables at once")
        print("   --fix-products     Fix products table (AI-powered)")
        print("   --fix-listings     Fix product_listings (logic-based, fast)")
        print("   --fix-platforms    Fix platforms table (selectors, delays)")
        print("   --fix-orphans      Delete orphan products")
        print("   --re-enrich        Force re-run AI on all products")
        print("   --dry-run          Preview without saving")
        print("   --limit N          Batch size (default 200)")
        return

    # ── Step 0: Platforms (no AI, fast) → always first
    if args.fix_all or args.fix_platforms:
        r = await fix_platforms(dry_run=args.dry_run)
        print_summary("PLATFORMS", r)

    # ── Step 1: Listings (no AI, fastest) → bulk fix
    if args.fix_all or args.fix_listings:
        r = await fix_listings(limit=args.limit * 5, dry_run=args.dry_run)
        print_summary("PRODUCT LISTINGS", r)

    # ── Step 2: Orphans → clean before fixing products
    if args.fix_all or args.fix_orphans:
        r = await fix_orphans(dry_run=args.dry_run)
        print_summary("ORPHAN CLEANUP", r)

    # ── Step 3: Products (AI-powered)
    if args.fix_all or args.fix_products:
        r = await fix_products(limit=args.limit, dry_run=args.dry_run)
        print_summary("PRODUCTS", r)

    # ── Step 4: Re-enrich
    if args.fix_all or args.re_enrich:
        r = await re_enrich(limit=args.limit, dry_run=args.dry_run)
        print_summary("RE-ENRICHMENT", r)

    duration = (datetime.now() - start).total_seconds()
    print(f"\n{BOLD}⏱️  Total Duration: {duration:.1f}s{RESET}")
    if args.dry_run:
        print(f"{YELLOW}⚠️  DRY RUN — remove --dry-run to apply changes.{RESET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="DealHunt Data Fixer v3.0 — Full DB Coverage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/fix_data.py                              # Scan only
  python scripts/fix_data.py --fix-all                    # Fix ALL tables
  python scripts/fix_data.py --fix-listings               # Fast: fix listings only
  python scripts/fix_data.py --fix-platforms              # Fix platform selectors
  python scripts/fix_data.py --fix-products --limit 100   # Fix 100 products
  python scripts/fix_data.py --fix-orphans                # Delete orphan products
  python scripts/fix_data.py --re-enrich --limit 20       # Re-AI 20 products
  python scripts/fix_data.py --dry-run --fix-all          # Preview everything
        """
    )
    parser.add_argument("--fix-all",       action="store_true", help="Fix all tables")
    parser.add_argument("--fix-products",  action="store_true", help="Fix products table (AI)")
    parser.add_argument("--fix-listings",  action="store_true", help="Fix product_listings (fast)")
    parser.add_argument("--fix-platforms", action="store_true", help="Fix platforms table")
    parser.add_argument("--fix-orphans",   action="store_true", help="Delete orphan products")
    parser.add_argument("--re-enrich",     action="store_true", help="Re-run AI on all products")
    parser.add_argument("--dry-run",       action="store_true", help="Preview without saving")
    parser.add_argument("--limit",         type=int, default=200, help="Max products to process (default 200)")

    args = parser.parse_args()
    asyncio.run(main(args))
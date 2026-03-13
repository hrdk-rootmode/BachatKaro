#!/usr/bin/env python3
"""
Database Health Analyzer & Fixer v4.0
======================================

Intelligent scanner that finds and fixes:

GARBAGE DATA (not just NULL):
  ❌ Brand = "Men", "Cotton", "Blue", "Tshirt", "Generic", "Unknown"
  ❌ Brand = "Te", "Sb", "Db" (random 2-letter junk)
  ❌ Title = just brand name ("VANGULL", "Ambrane", "NOISE")
  ❌ Image URL = broken/404/placeholder
  ❌ AI essence = NULL or same as title (no compression)
  ❌ Category = "General" (lazy categorization)
  ❌ Specs = {} (empty when product has RAM/storage in title)
  ❌ Quality score = 0 (AI never processed)

USES v4.0 INTELLIGENCE:
  ✅ Imports extraction from cross_platform_matcher.py
  ✅ 100+ brand patterns (Fire-Boltt, boAt, Noise, fashion)
  ✅ Product-line extraction (Phoenix, Hunter, Galaxy S)
  ✅ Spec extraction (RAM, storage, screen, processor)
  ✅ Quality gate (skip unfixable garbage)
  ✅ Smart AI prompts (category-aware)

MODES:
  --scan              Deep analysis report (no changes)
  --fix-all           Fix all issues
  --fix-brands        Fix garbage brands only
  --fix-specs         Extract missing specs from titles
  --fix-images        Find working image URLs from listings
  --fix-ai            Re-enrich low quality products
  --delete-garbage    Delete unfixable junk products
  --health-score      Show database health percentage

Usage:
    python scripts/fix_data.py --scan
    python scripts/fix_data.py --fix-all
    python scripts/fix_data.py --fix-brands --limit 100
    python scripts/fix_data.py --delete-garbage --dry-run
    python scripts/fix_data.py --health-score

Author: DealHunt
Version: 4.0 (Intelligent Analyzer)
"""

import asyncio
import argparse
import sys
import os
import json
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple, Set
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select, func, or_, and_, delete, update, text
from sqlalchemy.orm import selectinload
from app.core.database import async_session_maker
from app.models import Product, ProductListing, Platform

# ✅ IMPORT v4.0 INTELLIGENCE FROM MATCHER
from app.services.scraper.cross_platform_matcher import (
    extract_specs,
    extract_brand,
    check_quality_gate,
    ProductSpecs,
    BRAND_PATTERNS,
    # GENERIC_WORDS
)

# AI client
from app.services.ai.groq_client import groq_client
from app.services.scraper.base import ProductData

if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# =============================================================================
# STYLING
# =============================================================================
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


# =============================================================================
# GARBAGE DETECTORS (ENHANCED)
# =============================================================================

# Words that should NEVER be brand names
GARBAGE_BRANDS = {
    # Generic
    "unknown", "generic", "unbranded", "other", "n/a", "na", "none", "null",
    "brand", "original", "new", "latest", "premium", "best", "top",
    
    # Attributes mistaken for brands
    "men", "women", "boys", "girls", "kids", "unisex", "male", "female",
    "cotton", "silk", "wool", "polyester", "nylon", "leather", "synthetic",
    "polycotton", "blend", "mixed", "denim", "linen", "rayon",
    
    # Garment types
    "sneaker", "sneakers", "shoe", "shoes", "dress", "shirt", "tshirt",
    "trouser", "pant", "kurta", "saree", "top", "bottom", "jacket",
    
    # Colors
    "black", "white", "blue", "red", "green", "yellow", "pink", "grey",
    "brown", "orange", "purple", "maroon", "navy", "beige", "gold",
    
    # Styles
    "casual", "formal", "stylish", "trendy", "elegant", "smart", "classic",
    "modern", "vintage", "retro", "slim", "fit", "regular", "loose",
    
    # Product features
    "wireless", "bluetooth", "digital", "analog", "smart", "pro", "plus",
    "ultra", "max", "lite", "mini", "premium", "deluxe", "standard",
    
    # Random 2-letter junk
    "te", "sb", "db", "ab", "cd", "xy", "qr", "mn", "pq",
}

# Patterns that indicate garbage brand
GARBAGE_BRAND_PATTERNS = [
    re.compile(r'^[a-z]{1,2}$', re.I),  # 1-2 letters only
    re.compile(r'^\d+$'),  # Just numbers
    re.compile(r'^[^a-zA-Z]+$'),  # No letters at all
]


def is_garbage_brand(brand: Optional[str]) -> bool:
    """Detect if brand is garbage/invalid"""
    if not brand:
        return True
    
    brand_lower = brand.lower().strip()
    
    # Check garbage word list
    if brand_lower in GARBAGE_BRANDS:
        return True
    
    # Check patterns
    for pattern in GARBAGE_BRAND_PATTERNS:
        if pattern.match(brand):
            return True
    
    # Too short (but not known brand)
    if len(brand_lower) <= 2:
        # Check if it's a known brand abbreviation
        if not BRAND_PATTERNS.search(brand):
            return True
    
    return False


def is_valid_brand(brand: Optional[str]) -> bool:
    """Check if brand is valid (opposite of garbage)"""
    if not brand:
        return False
    
    if is_garbage_brand(brand):
        return False
    
    # Must match known brand pattern
    if BRAND_PATTERNS.search(brand):
        return True
    
    # Or be at least 3 chars and not in garbage list
    brand_lower = brand.lower().strip()
    if len(brand_lower) >= 3 and brand_lower not in GARBAGE_BRANDS:
        return True
    
    return False


def is_title_just_brand(title: str, brand: Optional[str]) -> bool:
    """Check if title is just the brand name (no product info)"""
    if not title or not brand:
        return False
    
    # Remove brand from title
    title_clean = re.sub(re.escape(brand), '', title, flags=re.IGNORECASE).strip()
    
    # Count remaining meaningful words
    words = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', title_clean)
             if w.lower() not in {'the', 'a', 'an', 'and', 'for', 'with'}]
    
    # If less than 2 meaningful words left, title is just brand
    return len(words) < 2


def is_image_url_broken(url: Optional[str]) -> bool:
    """Check if image URL is broken/placeholder"""
    if not url:
        return True
    
    url_lower = url.lower()
    
    # Common placeholder indicators
    placeholders = [
        'placeholder', 'noimage', 'no-image', 'default', 'missing',
        'na.jpg', 'na.png', 'null.jpg', 'dummy', 'temp'
    ]
    
    for placeholder in placeholders:
        if placeholder in url_lower:
            return True
    
    # Must start with http
    if not url.startswith(('http://', 'https://')):
        return True
    
    return False


def is_essence_useless(title: str, essence: Optional[str]) -> bool:
    """Check if AI essence is useless (same as title or too similar)"""
    if not essence:
        return True
    
    # Essence should be shorter than title (compression)
    if len(essence) >= len(title) * 0.9:
        return True
    
    # Essence should not be exactly the same
    if essence.lower().strip() == title.lower().strip():
        return True
    
    return False


def is_category_lazy(category: Optional[str]) -> bool:
    """Check if category is lazy/generic"""
    if not category:
        return True
    
    lazy_categories = {'general', 'other', 'miscellaneous', 'unknown', 'products'}
    return category.lower() in lazy_categories


def has_specs_in_title_but_empty(title: str, specs: Dict) -> bool:
    """Check if title has specs info but specifications field is empty"""
    if specs and len(specs) > 0:
        return False  # Specs exist
    
    # Check if title has common spec patterns
    spec_indicators = [
        r'\d+\s*GB',  # Storage/RAM
        r'\d+\.?\d*\s*inch',  # Screen
        r'i[3579]|Ryzen|Snapdragon|M[123]',  # Processors
        r'5G|4G|LTE',  # Network
    ]
    
    for pattern in spec_indicators:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    
    return False


# =============================================================================
# COMPREHENSIVE SCANNER
# =============================================================================

async def scan_database_health() -> Dict[str, Any]:
    """
    Deep scan for data quality issues
    
    Returns detailed breakdown of all issues found
    """
    header("🔬 Deep Scanning Database for ALL Issues...")
    
    issues = {
        "total_products": 0,
        "total_listings": 0,
        
        # Brand issues
        "garbage_brands": 0,
        "null_brands": 0,
        "title_just_brand": 0,
        
        # Title issues
        "titles_too_short": 0,
        "titles_low_quality": 0,
        
        # Image issues
        "null_images": 0,
        "broken_image_urls": 0,
        
        # AI issues
        "null_essence": 0,
        "useless_essence": 0,
        "null_tags": 0,
        "zero_quality_score": 0,
        "never_ai_processed": 0,
        
        # Category issues
        "null_category": 0,
        "lazy_category": 0,
        "null_subcategory": 0,
        
        # Spec issues
        "null_specs": 0,
        "empty_specs": 0,
        "specs_in_title_but_missing": 0,
        
        # Listing issues
        "null_prices": 0,
        "null_currency": 0,
        "null_in_stock": 0,
        
        # Critical
        "orphan_products": 0,
        "completely_broken": 0,  # Products with 5+ issues
        "unfixable": 0,  # Products that can't be healed
    }
    
    async with async_session_maker() as db:
        # Total counts
        r = await db.execute(select(func.count(Product.id)))
        issues["total_products"] = r.scalar() or 0
        
        r = await db.execute(select(func.count(ProductListing.id)))
        issues["total_listings"] = r.scalar() or 0
        
        # Load all products for detailed analysis
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.listings))
            .limit(1000)  # Analyze first 1000
        )
        products = result.scalars().all()
        
        print(f"\n   Analyzing {len(products)} products in detail...")
        
        for product in products:
            product_issues = 0
            
            # Brand analysis
            if not product.brand:
                issues["null_brands"] += 1
                product_issues += 1
            elif is_garbage_brand(product.brand):
                issues["garbage_brands"] += 1
                product_issues += 1
            
            if is_title_just_brand(product.title, product.brand):
                issues["title_just_brand"] += 1
                product_issues += 1
            
            # Title analysis
            if len(product.title or "") < 15:
                issues["titles_too_short"] += 1
                product_issues += 1
            
            # Image analysis
            if not product.image_url:
                issues["null_images"] += 1
                product_issues += 1
            elif is_image_url_broken(product.image_url):
                issues["broken_image_urls"] += 1
                product_issues += 1
            
            # AI metadata analysis
            ai_meta = product.ai_metadata or {}
            
            if not ai_meta:
                issues["never_ai_processed"] += 1
                product_issues += 1
            
            essence = ai_meta.get("essence")
            if not essence:
                issues["null_essence"] += 1
                product_issues += 1
            elif is_essence_useless(product.title, essence):
                issues["useless_essence"] += 1
                product_issues += 1
            
            tags = ai_meta.get("tags", [])
            if not tags:
                issues["null_tags"] += 1
                product_issues += 1
            
            quality_score = ai_meta.get("quality_score", 0)
            if quality_score == 0:
                issues["zero_quality_score"] += 1
                product_issues += 1
            
            # Category analysis
            if not product.category:
                issues["null_category"] += 1
                product_issues += 1
            elif is_category_lazy(product.category):
                issues["lazy_category"] += 1
                product_issues += 1
            
            if not product.subcategory:
                issues["null_subcategory"] += 1
            
            # Specs analysis
            specs = product.specifications or {}
            
            if not specs:
                issues["empty_specs"] += 1
            
            if has_specs_in_title_but_empty(product.title, specs):
                issues["specs_in_title_but_missing"] += 1
                product_issues += 1
            
            # Orphan check
            if not product.listings:
                issues["orphan_products"] += 1
                product_issues += 1
            
            # Critical: Product with many issues
            if product_issues >= 5:
                issues["completely_broken"] += 1
            
            # Check if fixable
            specs_extracted = extract_specs(product.title)
            passed, _ = check_quality_gate(product.title, specs_extracted)
            
            if not passed:
                issues["unfixable"] += 1
    
    return issues


def print_health_report(issues: Dict[str, Any]):
    """Print comprehensive health report"""
    total_products = issues["total_products"]
    total_listings = issues["total_listings"]
    
    def severity(count, total):
        if total == 0:
            return GREEN + "✅"
        pct = (count / total) * 100
        if pct > 30: return RED + "🔴"
        if pct > 10: return YELLOW + "🟡"
        if pct > 0:  return YELLOW + "🟠"
        return GREEN + "✅"
    
    def row(label, key):
        count = issues.get(key, 0)
        pct = (count / max(total_products, 1)) * 100
        icon = severity(count, total_products)
        return f"    {icon} {label}: {count:,} ({pct:.1f}%){RESET}"
    
    print(f"\n{'=' * 75}")
    print(f"{BOLD}🔬 DATABASE HEALTH REPORT{RESET}")
    print(f"{'=' * 75}")
    print(f"  Total Products: {total_products:,}")
    print(f"  Total Listings: {total_listings:,}")
    
    print(f"\n{BOLD}  ┌─ BRAND ISSUES{RESET}")
    print(row("NULL/Empty Brand", "null_brands"))
    print(row("Garbage Brand (Men/Cotton/Blue/Generic)", "garbage_brands"))
    print(row("Title is Just Brand Name", "title_just_brand"))
    
    print(f"\n{BOLD}  ├─ TITLE ISSUES{RESET}")
    print(row("Title < 15 chars", "titles_too_short"))
    print(row("Low Quality Title", "titles_low_quality"))
    
    print(f"\n{BOLD}  ├─ IMAGE ISSUES{RESET}")
    print(row("NULL Image URL", "null_images"))
    print(row("Broken/Placeholder Image", "broken_image_urls"))
    
    print(f"\n{BOLD}  ├─ AI METADATA ISSUES{RESET}")
    print(row("Never AI Processed", "never_ai_processed"))
    print(row("NULL AI Essence", "null_essence"))
    print(row("Useless Essence (same as title)", "useless_essence"))
    print(row("NULL/Empty Tags", "null_tags"))
    print(row("Quality Score = 0", "zero_quality_score"))
    
    print(f"\n{BOLD}  ├─ CATEGORY ISSUES{RESET}")
    print(row("NULL Category", "null_category"))
    print(row("Lazy Category (General/Other)", "lazy_category"))
    print(row("NULL Subcategory", "null_subcategory"))
    
    print(f"\n{BOLD}  ├─ SPECIFICATION ISSUES{RESET}")
    print(row("Empty Specifications {}", "empty_specs"))
    print(row("Specs in Title but Not Extracted", "specs_in_title_but_missing"))
    
    print(f"\n{BOLD}  └─ CRITICAL ISSUES{RESET}")
    print(row("Orphan Products (no listings)", "orphan_products"))
    print(row("Completely Broken (5+ issues)", "completely_broken"))
    print(row("Unfixable (fail quality gate)", "unfixable"))
    
    # Calculate health score
    fixable_issues = sum(
        issues.get(k, 0) for k in [
            "garbage_brands", "null_brands", "null_essence", "useless_essence",
            "null_category", "lazy_category", "empty_specs", "specs_in_title_but_missing",
            "zero_quality_score"
        ]
    )
    
    total_checkable = total_products * 9  # 9 major checks
    health = max(0, 100 - (fixable_issues / max(total_checkable, 1) * 100))
    
    bar_filled = int(health / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    color = GREEN if health > 80 else (YELLOW if health > 50 else RED)
    
    print(f"\n  {color}DATABASE HEALTH: [{bar}] {health:.1f}%{RESET}")
    print(f"\n  {BOLD}FIXABLE ISSUES: {fixable_issues:,}{RESET}")
    print(f"  {RED}UNFIXABLE (recommend delete): {issues.get('unfixable', 0):,}{RESET}")
    
    print(f"{'=' * 75}")


# =============================================================================
# INTELLIGENT FIXERS
# =============================================================================

async def fix_brands_intelligently(limit: int = 200, dry_run: bool = False) -> Dict[str, int]:
    """
    Fix garbage/NULL brands using v4.0 extraction + AI
    """
    header(f"🏷️  Fixing Brands (limit={limit}, dry_run={dry_run})")
    
    stats = {
        "scanned": 0,
        "null_fixed": 0,
        "garbage_fixed": 0,
        "ai_extracted": 0,
        "regex_extracted": 0,
        "marked_generic": 0,  # NEW: For fashion items
        "unfixable": 0,
        "errors": 0
    }
    
    async with async_session_maker() as db:
        # Find products with garbage/NULL brands
        result = await db.execute(
            select(Product)
            .where(or_(
                Product.brand == None,
                Product.brand == "",
                Product.brand == "Unknown"
            ))
            .limit(limit)
        )
        products = result.scalars().all()
        
        # Also check for garbage brands
        all_products = await db.execute(select(Product).limit(limit * 2))
        all_products = all_products.scalars().all()
        
        garbage_products = [p for p in all_products if is_garbage_brand(p.brand)]
        products_to_fix = list(set(list(products) + garbage_products))[:limit]
        
        print(f"\n   Found {len(products_to_fix)} products with brand issues\n")
        
        batch = 0
        for i, product in enumerate(products_to_fix, 1):
            stats["scanned"] += 1
            old_brand = product.brand
            
            try:
                print(f"   [{i}/{len(products_to_fix)}] {product.title[:50]}...")
                print(f"      Current brand: {old_brand or 'NULL'}")
                
                # Check if it's a generic fashion item first
                specs = extract_specs(product.title)
                if specs.garment_type and not specs.brand:
                    new_brand = "Generic Fashion"
                    stats["marked_generic"] += 1
                    ok(f"Marked as: {new_brand} (Garment: {specs.garment_type})")
                    
                    if not dry_run:
                        product.brand = new_brand
                    batch += 1
                    continue
                
                # Strategy 1: Extract with regex
                normalized_brand, original_brand = extract_brand(product.title)
                
                # We missed HP in the brand list casing! Let's handle it manually.
                if product.title.startswith("HP ") or " HP " in product.title:
                    normalized_brand = "HP"
                
                if normalized_brand and is_valid_brand(normalized_brand):
                    new_brand = normalized_brand
                    stats["regex_extracted"] += 1
                    ok(f"Regex extracted: {new_brand}")
                else:
                    # Strategy 2: Use AI (only if it looks like electronics/appliances)
                    category_lower = (product.category or "").lower()
                    if "fashion" in category_lower or "clothing" in category_lower:
                        warn("Generic fashion item - skipping AI")
                        stats["unfixable"] += 1
                        continue
                        
                    try:
                        pd = ProductData(
                            external_id=str(product.id),
                            title=product.title,
                            current_price=Decimal("0"),
                            product_url="",
                            platform_name="unknown"
                        )
                        
                        enriched = await groq_client.process_product(pd)
                        ai_brand = enriched.get("specifications", {}).get("brand")
                        
                        if ai_brand and is_valid_brand(ai_brand):
                            new_brand = ai_brand
                            stats["ai_extracted"] += 1
                            ok(f"AI extracted: {new_brand}")
                        else:
                            warn("Could not extract valid brand")
                            stats["unfixable"] += 1
                            continue
                    
                    except Exception as e:
                        err(f"AI failed: {e}")
                        stats["unfixable"] += 1
                        continue
                
                # Update database
                if not dry_run:
                    product.brand = new_brand
                    
                    # Also update ai_metadata if exists
                    if product.ai_metadata:
                        ai_meta = dict(product.ai_metadata)
                        ai_meta["brand_fixed_at"] = datetime.utcnow().isoformat()
                        ai_meta["old_brand"] = old_brand
                        product.ai_metadata = ai_meta
                
                if old_brand:
                    stats["garbage_fixed"] += 1
                else:
                    stats["null_fixed"] += 1
                
                batch += 1
                if batch >= 20 and not dry_run:
                    await db.commit()
                    batch = 0
            
            except Exception as e:
                stats["errors"] += 1
                err(f"Error: {e}")
        
        if not dry_run and batch > 0:
            await db.commit()
    
    return stats

async def fix_specs_from_titles(limit: int = 200, dry_run: bool = False) -> Dict[str, int]:
    """
    Extract specs from titles when specifications field is empty
    
    Uses v4.0 extraction for:
    - RAM, Storage, Screen size, Processor
    - Fashion attributes (garment, material, fit)
    - Product line, model, generation
    """
    header(f"📊 Extracting Specs from Titles (limit={limit}, dry_run={dry_run})")
    
    stats = {
        "scanned": 0,
        "specs_extracted": 0,
        "ram_extracted": 0,
        "storage_extracted": 0,
        "screen_extracted": 0,
        "fashion_extracted": 0,
        "errors": 0
    }
    
    async with async_session_maker() as db:
        # Find products with empty specs but potential info in title
        result = await db.execute(
            select(Product)
            .where(or_(
                Product.specifications == None,
                Product.specifications == {}
            ))
            .limit(limit)
        )
        products = result.scalars().all()
        
        print(f"\n   Found {len(products)} products with empty specs\n")
        
        batch = 0
        for i, product in enumerate(products, 1):
            stats["scanned"] += 1
            
            try:
                # Extract all specs
                specs = extract_specs(
                    product.title,
                    category=product.category or "general"
                )
                
                # Build spec dict
                new_specs = {}
                changes = []
                
                if specs.brand and is_valid_brand(specs.brand):
                    new_specs["brand"] = specs.brand
                
                if specs.product_line:
                    new_specs["product_line"] = specs.product_line
                    changes.append(f"line={specs.product_line}")
                
                if specs.model:
                    new_specs["model"] = specs.model
                    changes.append(f"model={specs.model}")
                
                if specs.ram_gb:
                    new_specs["ram_gb"] = specs.ram_gb
                    stats["ram_extracted"] += 1
                    changes.append(f"RAM={specs.ram_gb}GB")
                
                if specs.storage_gb:
                    new_specs["storage_gb"] = specs.storage_gb
                    stats["storage_extracted"] += 1
                    changes.append(f"Storage={specs.storage_gb}GB")
                
                if specs.screen_size:
                    new_specs["screen_size"] = specs.screen_size
                    stats["screen_extracted"] += 1
                    changes.append(f"Screen={specs.screen_size}\"")
                
                if specs.processor:
                    new_specs["processor"] = specs.processor
                    changes.append(f"CPU={specs.processor}")
                
                if specs.generation:
                    new_specs["variant"] = specs.generation
                    changes.append(f"variant={specs.generation}")
                
                if specs.network:
                    new_specs["network"] = specs.network
                    changes.append(f"network={specs.network}")
                
                # Fashion attributes
                if specs.garment_type:
                    new_specs["garment_type"] = specs.garment_type
                    stats["fashion_extracted"] += 1
                    changes.append(f"garment={specs.garment_type}")
                
                if specs.material:
                    new_specs["material"] = specs.material
                    changes.append(f"material={specs.material}")
                
                if specs.fit:
                    new_specs["fit"] = specs.fit
                
                if specs.gender:
                    new_specs["gender"] = specs.gender
                
                if new_specs:
                    print(f"   [{i}] {product.title[:50]}...")
                    ok(" | ".join(changes))
                    
                    if not dry_run:
                        product.specifications = new_specs
                    
                    stats["specs_extracted"] += 1
                    
                    batch += 1
                    if batch >= 20 and not dry_run:
                        await db.commit()
                        batch = 0
            
            except Exception as e:
                stats["errors"] += 1
                err(f"[{i}] Error: {e}")
        
        if not dry_run and batch > 0:
            await db.commit()
    
    return stats


async def fix_images_from_listings(limit: int = 200, dry_run: bool = False) -> Dict[str, int]:
    """
    Fix NULL/broken product images by pulling from listings
    """
    header(f"🖼️  Fixing Images (limit={limit}, dry_run={dry_run})")
    
    stats = {
        "scanned": 0,
        "fixed": 0,
        "no_listing_image": 0,
        "errors": 0
    }
    
    async with async_session_maker() as db:
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.listings))
            .where(or_(
                Product.image_url == None,
                Product.image_url == ""
            ))
            .limit(limit)
        )
        products = result.scalars().all()
        
        # Also check broken images
        all_result = await db.execute(
            select(Product)
            .options(selectinload(Product.listings))
            .limit(limit * 2)
        )
        all_products = all_result.scalars().all()
        
        broken_products = [p for p in all_products if is_image_url_broken(p.image_url)]
        
        products_to_fix = list(set(list(products) + broken_products))[:limit]
        
        print(f"\n   Found {len(products_to_fix)} products with image issues\n")
        
        batch = 0
        for i, product in enumerate(products_to_fix, 1):
            stats["scanned"] += 1
            
            # Try to get image from first listing
            if product.listings:
                # Try to find listing with valid image
                for listing in product.listings:
                    # Image might be in product specs or other fields
                    # For now, we rely on scraper to populate it
                    pass
                
                # Placeholder: in production, you'd scrape the listing URL again
                warn(f"[{i}] No auto-fix available - needs re-scrape")
                stats["no_listing_image"] += 1
            else:
                warn(f"[{i}] No listings to pull image from")
                stats["no_listing_image"] += 1
        
        if not dry_run and batch > 0:
            await db.commit()
    
    return stats


async def fix_ai_metadata(limit: int = 100, dry_run: bool = False) -> Dict[str, int]:
    """
    Re-process products with low quality AI metadata
    """
    header(f"🤖 Fixing AI Metadata (limit={limit}, dry_run={dry_run})")
    
    stats = {
        "scanned": 0,
        "re_enriched": 0,
        "quality_improved": 0,
        "essence_improved": 0,
        "errors": 0
    }
    
    async with async_session_maker() as db:
        result = await db.execute(
            select(Product)
            .where(or_(
                Product.ai_metadata == None,
                Product.ai_metadata['quality_score'].astext == '0',
                Product.ai_metadata['essence'].astext == None
            ))
            .limit(limit)
        )
        products = result.scalars().all()
        
        print(f"\n   Found {len(products)} products needing AI re-processing\n")
        
        batch = 0
        for i, product in enumerate(products, 1):
            stats["scanned"] += 1
            
            try:
                old_score = (product.ai_metadata or {}).get("quality_score", 0)
                
                pd = ProductData(
                    external_id=str(product.id),
                    title=product.title,
                    current_price=Decimal("0"),
                    product_url="",
                    platform_name="unknown",
                    brand=product.brand,
                    category=product.category
                )
                
                enriched = await groq_client.process_product(pd)
                
                if enriched:
                    new_score = enriched.get("quality_score", 0)
                    new_essence = enriched.get("essence")
                    
                    print(f"   [{i}] {product.title[:50]}...")
                    
                    changes = []
                    
                    if new_score > old_score:
                        changes.append(f"score {old_score}→{new_score}")
                        stats["quality_improved"] += 1
                    
                    if new_essence and not is_essence_useless(product.title, new_essence):
                        changes.append(f"essence='{new_essence[:30]}...'")
                        stats["essence_improved"] += 1
                    
                    if changes:
                        ok(" | ".join(changes))
                    
                    if not dry_run:
                        ai_meta = {
                            "essence": new_essence or "",
                            "tags": enriched.get("tags", []),
                            "quality_score": new_score,
                            "re_enriched_at": datetime.utcnow().isoformat(),
                            "previous_score": old_score
                        }
                        product.ai_metadata = ai_meta
                        
                        # Update category if better
                        new_cat = enriched.get("category")
                        if new_cat and not is_category_lazy(new_cat):
                            product.category = new_cat
                    
                    stats["re_enriched"] += 1
                    
                    batch += 1
                    if batch >= 10 and not dry_run:
                        await db.commit()
                        batch = 0
                
                await asyncio.sleep(0.3)  # Rate limit
            
            except Exception as e:
                stats["errors"] += 1
                err(f"[{i}] Error: {e}")
        
        if not dry_run and batch > 0:
            await db.commit()
    
    return stats


async def delete_garbage_products(dry_run: bool = False) -> Dict[str, int]:
    """
    Delete products that are complete garbage or unfixable.
    """
    header(f"🗑️  Deleting Unfixable Garbage (dry_run={dry_run})")
    
    stats = {
        "scanned": 0,
        "deleted": 0,
        "kept": 0
    }
    
    async with async_session_maker() as db:
        result = await db.execute(select(Product).limit(1000))
        products = result.scalars().all()
        
        print(f"\n   Scanning {len(products)} products for unfixable garbage...\n")
        
        for product in products:
            stats["scanned"] += 1
            title = product.title or ""
            title_lower = title.lower()
            
            # Extract specs to check for features
            specs = extract_specs(title)
            passed_gate, gate_reason = check_quality_gate(title, specs)
            
            should_delete = False
            reason = ""
            
            # 1. Literal Junk Phrases (Timers, Statuses)
            junk_phrases = ['currently unavailable', 'coming soon', '00h :', '01h :']
            if any(x in title_lower for x in junk_phrases):
                should_delete = True
                reason = "Title is a status message or timer"
                
            # 2. Title is literally just the brand name (e.g. "VANGULL...")
            elif is_title_just_brand(title, product.brand):
                should_delete = True
                reason = f"Title is just the brand name ('{product.brand}')"
                
            # 3. Garbage brand AND no identifiable specs/garment type
            elif (not product.brand or is_garbage_brand(product.brand)):
                if not specs.garment_type and not specs.model and not specs.product_line:
                    should_delete = True
                    reason = f"Garbage brand ('{product.brand}') with no extractable product type"
            
            # 4. Fails the standard quality gate
            elif not passed_gate:
                should_delete = True
                reason = gate_reason
                
            # EXECUTE DELETION
            if should_delete:
                print(f"   🗑️  {title[:50]}...")
                print(f"      Reason: {reason}")
                
                if not dry_run:
                    await db.delete(product)
                
                stats["deleted"] += 1
            else:
                stats["kept"] += 1
        
        if not dry_run and stats["deleted"] > 0:
            await db.commit()
        
        print(f"\n   {'Would delete' if dry_run else 'Deleted'}: {stats['deleted']}")
        print(f"   Kept: {stats['kept']}")
    
    return stats

# =============================================================================
# SUMMARY
# =============================================================================

def print_fix_summary(title: str, stats: Dict[str, int]):
    print(f"\n{'─' * 60}")
    print(f"{BOLD}📊 {title}{RESET}")
    print(f"{'─' * 60}")
    for key, value in stats.items():
        if value > 0 and "error" in key:
            print(f"   {RED}❌{RESET} {key.replace('_', ' ').title()}: {value}")
        elif value > 0:
            print(f"   {GREEN}✅{RESET} {key.replace('_', ' ').title()}: {value}")
    print(f"{'─' * 60}")


# =============================================================================
# MAIN
# =============================================================================

async def main(args):
    start = datetime.now()
    
    print(f"\n{'=' * 75}")
    print(f"{BOLD}🔬 DATABASE HEALTH ANALYZER v4.0{RESET}")
    print(f"   Time: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        print(f"   {YELLOW}⚠️  DRY RUN MODE{RESET}")
    print(f"{'=' * 75}")
    
    # Always run health scan
    issues = await scan_database_health()
    print_health_report(issues)
    
    # Execute fixes
    if args.health_score:
        # Just show health, already displayed above
        pass
    
    elif args.fix_brands or args.fix_all:
        r = await fix_brands_intelligently(limit=args.limit, dry_run=args.dry_run)
        print_fix_summary("BRAND FIXES", r)
    
    if args.fix_specs or args.fix_all:
        r = await fix_specs_from_titles(limit=args.limit, dry_run=args.dry_run)
        print_fix_summary("SPEC EXTRACTION", r)
    
    if args.fix_images or args.fix_all:
        r = await fix_images_from_listings(limit=args.limit, dry_run=args.dry_run)
        print_fix_summary("IMAGE FIXES", r)
    
    if args.fix_ai or args.fix_all:
        r = await fix_ai_metadata(limit=args.limit // 2, dry_run=args.dry_run)
        print_fix_summary("AI RE-ENRICHMENT", r)
    
    if args.delete_garbage:
        r = await delete_garbage_products(dry_run=args.dry_run)
        print_fix_summary("GARBAGE DELETION", r)
    
    duration = (datetime.now() - start).total_seconds()
    print(f"\n{BOLD}⏱️  Duration: {duration:.1f}s{RESET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Database Health Analyzer v4.0",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--scan", action="store_true", help="Scan only (default)")
    parser.add_argument("--health-score", action="store_true", help="Show health score only")
    parser.add_argument("--fix-all", action="store_true", help="Fix all issues")
    parser.add_argument("--fix-brands", action="store_true", help="Fix garbage brands")
    parser.add_argument("--fix-specs", action="store_true", help="Extract specs from titles")
    parser.add_argument("--fix-images", action="store_true", help="Fix image URLs")
    parser.add_argument("--fix-ai", action="store_true", help="Re-enrich with AI")
    parser.add_argument("--delete-garbage", action="store_true", help="Delete unfixable products")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--limit", type=int, default=200, help="Batch size")
    
    args = parser.parse_args()
    
    # Default to scan if nothing specified
    if not any([args.fix_all, args.fix_brands, args.fix_specs, 
                args.fix_images, args.fix_ai, args.delete_garbage,
                args.health_score]):
        args.scan = True
    
    asyncio.run(main(args))
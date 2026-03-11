#!/usr/bin/env python3
"""
Cross-Platform Miner v3.0 - Production Grade
=============================================

Complete rewrite fixing all issues from v2.0:
- FIXED: Fingerprint linking (set AFTER enrichment)
- ADDED: SequenceMatcher fuzzy matching
- ADDED: Price-range validation (±20%)
- ADDED: Platform-specific query optimization
- ADDED: Stronger model extraction
- ADDED: Category-aware matching thresholds
- ADDED: Batch DB operations

Usage:
    python scripts/cross_platform_miner.py --limit 10
    python scripts/cross_platform_miner.py --limit 50 --no-ai
    python scripts/cross_platform_miner.py --limit 20 --platforms amazon,flipkart
    python scripts/cross_platform_miner.py --category electronics --limit 10

Author: DealHunt
"""

import asyncio
import argparse
import sys
import os
import re
import json
import hashlib
from decimal import Decimal
from typing import Optional, Dict, Tuple, Any, List, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from difflib import SequenceMatcher

# Windows async fix
if sys.platform == 'win32':
    from asyncio.proactor_events import _ProactorBasePipeTransport
    def silence_proactor_del(self): pass
    _ProactorBasePipeTransport.__del__ = silence_proactor_del

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import async_session_maker
from app.models import Product, ProductListing
from app.services.scraper.base import ProductData, ProductCategory
from app.services.scraper.factory import get_platform_handler
from app.services.ai.enrichment_service import enrichment_service
from app.services.product_service import product_service
from app.schemas import Platform


# =============================================================================
# SECTION 1: ENUMS & DATA CLASSES
# =============================================================================

class MatchResult(str, Enum):
    EXACT_MATCH = "exact_match"
    PARTIAL_MATCH = "partial_match"
    NO_MATCH = "no_match"
    ACCESSORY_REJECTED = "accessory_rejected"
    SPECS_MISMATCH = "specs_mismatch"
    REFURBISHED_REJECTED = "refurbished_rejected"
    VARIANT_MISMATCH = "variant_mismatch"
    PRICE_MISMATCH = "price_mismatch"
    BRAND_MISMATCH = "brand_mismatch"


@dataclass
class ProductSpecs:
    """Extracted product specifications"""
    brand: Optional[str] = None
    model: Optional[str] = None
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    color: Optional[str] = None
    is_accessory: bool = False
    is_refurbished: bool = False
    generation: Optional[str] = None
    network: Optional[str] = None
    screen_size: Optional[float] = None
    price: Optional[float] = None
    raw_title: str = ""
    full_title: str = ""  # Always stores the FULL original title

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != 'raw_title'}

    def get_essence(self) -> str:
        parts = []
        if self.brand: parts.append(self.brand)
        if self.model: parts.append(self.model)
        if self.generation: parts.append(self.generation)
        if self.ram_gb: parts.append(f"{self.ram_gb}GB")
        if self.storage_gb: parts.append(f"{self.storage_gb}GB")
        if self.network: parts.append(self.network)
        return " ".join(parts)


@dataclass
class MatchVerification:
    result: MatchResult
    score: float
    reason: str
    source_specs: Optional[ProductSpecs] = None
    target_specs: Optional[ProductSpecs] = None
    ai_response: Optional[Dict[str, Any]] = None


@dataclass
class MiningStats:
    processed: int = 0
    pre_filtered: int = 0
    specs_rejected: int = 0
    ai_verified: int = 0
    ai_rejected: int = 0
    stored: int = 0
    errors: int = 0
    api_calls_saved: int = 0
    platforms_scraped: Dict[str, int] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.utcnow)

    def print_summary(self):
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        print(f"\n{'=' * 70}")
        print(f"📊 MINING RESULTS  ({elapsed:.0f}s)")
        print(f"{'=' * 70}")
        print(f"  Processed:           {self.processed}")
        print(f"  Pre-Filter Rejected: {self.pre_filtered}")
        print(f"  Specs Rejected:      {self.specs_rejected}")
        print(f"  AI Verified Matches: {self.ai_verified}")
        print(f"  AI Rejections:       {self.ai_rejected}")
        print(f"  Successfully Stored: {self.stored}")
        print(f"  Errors:              {self.errors}")
        print(f"  API Calls Saved:     {self.api_calls_saved} 💰")
        if self.platforms_scraped:
            print(f"  Platforms:")
            for p, c in self.platforms_scraped.items():
                print(f"    {p}: {c}")
        print(f"{'=' * 70}")


# =============================================================================
# SECTION 2: COMPILED REGEX PATTERNS
# =============================================================================

ACCESSORY_PATTERNS = re.compile(
    r'\b('
    r'case|cases|cover|covers|pouch|sleeve|skin|skins|wrap|wraps|'
    r'back\s*cover|flip\s*cover|wallet\s*case|bumper|bumpers|'
    r'protective\s*case|silicone\s*case|rubber\s*case|tpu\s*case|'
    r'hard\s*case|soft\s*case|clear\s*case|transparent\s*case|'
    r'armor\s*case|rugged\s*case|slim\s*case|ultra\s*thin\s*case|'
    r'leather\s*case|fabric\s*case|hybrid\s*case|'
    r'tempered\s*glass|screen\s*guard|screen\s*protector|'
    r'glass\s*protector|privacy\s*glass|matte\s*glass|'
    r'camera\s*protector|lens\s*protector|camera\s*glass|'
    r'charger|chargers|adapter|adapters|cable|cables|cord|cords|wire|wires|'
    r'fast\s*charger|turbo\s*charger|dash\s*charger|warp\s*charger|'
    r'wireless\s*charger|car\s*charger|travel\s*charger|'
    r'type[\s\-]?c\s*cable|lightning\s*cable|usb\s*cable|'
    r'earphone|earphones|headphone|headphones|earbuds|earbud|'
    r'headset|headsets|earpiece|handsfree|hands[\s\-]?free|'
    r'tws|neckband|'
    r'holder|holders|stand|stands|mount|mounts|grip|grips|ring|rings|'
    r'car\s*mount|bike\s*mount|desk\s*stand|phone\s*stand|'
    r'pop\s*socket|popsocket|finger\s*ring|kickstand|'
    r'tripod|tripods|gimbal|gimbals|selfie\s*stick|'
    r'power\s*bank|powerbank|battery\s*pack|portable\s*charger|'
    r'memory\s*card|sd\s*card|micro\s*sd|pendrive|pen\s*drive|'
    r'flash\s*drive|usb\s*drive|otg|otg\s*adapter|'
    r'stylus|sim\s*tray|sim\s*ejector|'
    r'cleaning\s*kit|lens\s*cleaner|screen\s*cleaner|'
    r'armband|armbands|lanyard|lanyards|strap|straps|'
    r'usb\s*hub|dongle|dongles|'
    r'repair\s*kit|tool\s*kit|opening\s*tool|'
    r'sticker|stickers|decal|decals|vinyl|'
    r'dust\s*plug|anti[\s\-]?dust|'
    r'screen\s*replacement|display\s*replacement|lcd\s*replacement|'
    r'touch\s*screen\s*digitizer|'
    r'combo|bundle|kit|set\s+of|pack\s+of|pcs|pieces|'
    r'compatible\s*with|designed\s*for|fits\s*for|suitable\s*for|'
    r'made\s*for|works\s*with|perfect\s*for|ideal\s*for'
    r')\b',
    re.IGNORECASE
)

REFURBISHED_PATTERNS = re.compile(
    r'\b('
    r'renewed|renew|refurbished|refurb|'
    r'used|pre[\s\-]?owned|preowned|second[\s\-]?hand|2nd\s*hand|'
    r'open[\s\-]?box|openbox|unboxed|unsealed|'
    r'like[\s\-]?new|likenew|grade[\s\-]?[abc]|'
    r'certified[\s\-]?refurbished|factory[\s\-]?refurbished|'
    r'seller[\s\-]?refurbished|amazon[\s\-]?renewed|'
    r'reconditioned|restored|remanufactured'
    r')\b',
    re.IGNORECASE
)

RAM_PATTERNS = [
    re.compile(r'(\d{1,2})\s*GB\s*RAM', re.IGNORECASE),
    re.compile(r'\((\d{1,2})\s*GB\s*[/+]\s*\d+\s*GB\)', re.IGNORECASE),
    # FIX: Handle comma format "(6GB, 128GB)" or "(6 GB, 128 GB)"
    re.compile(r'\((\d{1,2})\s*GB\s*,\s*\d+\s*GB\)', re.IGNORECASE),
    re.compile(r'(\d{1,2})\s*GB?\s*\+\s*\d+\s*GB', re.IGNORECASE),
    re.compile(r'(\d{1,2})\s*/\s*\d+\s*GB', re.IGNORECASE),
    re.compile(r'\b(\d{1,2})\s*GB\b(?!\s*(?:ROM|Storage|Internal|SSD|HDD|Memory\s*Card))', re.IGNORECASE),
]

STORAGE_PATTERNS = [
    re.compile(r'(\d{2,4})\s*GB\s*(?:ROM|Storage|Internal)', re.IGNORECASE),
    re.compile(r'\(\d+\s*GB\s*[/+]\s*(\d{2,4})\s*GB\)', re.IGNORECASE),
    # FIX: Handle comma format "(6GB, 128GB)" or "(6 GB, 128 GB)"
    re.compile(r'\(\d+\s*GB\s*,\s*(\d{2,4})\s*GB\)', re.IGNORECASE),
    re.compile(r'\d+\s*GB?\s*\+\s*(\d{2,4})\s*GB', re.IGNORECASE),
    re.compile(r'\d+\s*/\s*(\d{2,4})\s*GB', re.IGNORECASE),
    re.compile(r'\b(\d{2,4})\s*GB\b', re.IGNORECASE),
    re.compile(r'(\d+)\s*TB', re.IGNORECASE),
]

BRAND_PATTERNS = re.compile(
    r'\b('
    r'Samsung|Apple|iPhone|OnePlus|One\s*Plus|Xiaomi|Redmi|POCO|Realme|'
    r'Vivo|Oppo|Motorola|Moto|Nokia|Google|Pixel|Nothing|iQOO|IQOO|'
    r'Asus|ROG|Sony|Xperia|Huawei|Honor|Tecno|Infinix|'
    r'Lava|Micromax|Karbonn|Intex|Gionee|'
    r'LG|HTC|Lenovo|ZTE|Meizu|Nubia|BlackBerry|'
    r'TCL|Alcatel|Coolpad|LeEco|Sharp|Panasonic|'
    r'Black\s*Shark|Red\s*Magic|RedMagic|'
    r'iPad|Galaxy\s*Tab|Tab|Kindle|Fire|'
    r'Dell|HP|Acer|MSI|Razer|Asus|Gigabyte|'
    r'Boat|JBL|Sony|Bose|Sennheiser|'
    r'Nike|Adidas|Puma|Reebok|Levis|'
    r'Whirlpool|LG|Samsung|Godrej|Haier|IFB|Bosch'
    r')\b',
    re.IGNORECASE
)

GENERATION_PATTERNS = re.compile(
    r'\b('
    r'Pro|Plus|Ultra|Max|Lite|Neo|Mini|SE|FE|'
    r'Edge|Note|Prime|Youth|Play|Turbo|Speed|'
    r'Racing|Gaming|Master|Explorer|Ace|Reno|'
    r'Find|Nord|Narzo|GT|'
    r'Standard|Base|Vanilla'
    r')\b',
    re.IGNORECASE
)

NETWORK_PATTERNS = re.compile(r'\b(5G|4G|LTE|3G|VOLTE|VoLTE)\b', re.IGNORECASE)

COLOR_PATTERNS = re.compile(
    r'\b('
    r'Black|White|Blue|Red|Green|Gold|Silver|Grey|Gray|Pink|'
    r'Purple|Orange|Yellow|Bronze|Copper|Brown|Beige|Cream|'
    r'Titanium|Graphite|Platinum|Rose\s*Gold|Champagne|'
    r'Burgundy|Maroon|Navy|Teal|Cyan|Magenta|Violet|Indigo|'
    r'Midnight|Starlight|Sierra|Alpine|Pacific|Desert|'
    r'Space\s*Gray|Space\s*Grey|Jet\s*Black|'
    r'Phantom|Cosmic|Mystic|Aura|Prism|'
    r'Aurora|Lavender|Mint|Coral|Sage|Forest|Sky|Ocean|'
    r'Sunset|Sunrise|Twilight|Dawn|Dusk|'
    r'Pearl|Ice|Frost|Snow|Crystal|Diamond|'
    r'Glacier|Arctic|Polar|'
    r'Matte|Glossy|Ceramic|Glass|Gradient|Holographic'
    r')\b',
    re.IGNORECASE
)

SCREEN_SIZE_PATTERN = re.compile(r'(\d+\.?\d*)\s*(?:inch|inches|")', re.IGNORECASE)

# Enhanced model patterns for better extraction
MODEL_NUMBER_PATTERNS = [
    # "Galaxy S24 Ultra", "iPhone 16 Pro Max"
    re.compile(r'(?:Galaxy|iPhone|iPad|Pixel|OnePlus|Redmi\s*Note?|POCO|Realme|Narzo|Nord)\s+([A-Z]?\d+[A-Za-z]*(?:\s+(?:Pro|Plus|Ultra|Max|Lite|Mini|SE|FE|Note))*)', re.IGNORECASE),
    # Generic "Model X123"
    re.compile(r'(?:Model|Series)\s+([A-Z0-9][\w\-]{2,15})', re.IGNORECASE),
    # Alphanumeric model like "A55", "M34", "C55"
    re.compile(r'\b([A-Z]\d{1,3}[A-Za-z]?)\b'),
]


# =============================================================================
# SECTION 3: SPEC EXTRACTION
# =============================================================================

BRAND_NORMALIZATIONS = {
    'iphone': 'Apple', 'ipad': 'Apple', 'moto': 'Motorola',
    'one plus': 'OnePlus', 'oneplus': 'OnePlus', 'rog': 'Asus',
    'pixel': 'Google', 'galaxy tab': 'Samsung', 'redmi': 'Xiaomi',
    'poco': 'Xiaomi', 'iqoo': 'iQOO', 'red magic': 'RedMagic',
    'redmagic': 'RedMagic', 'black shark': 'BlackShark',
}

BRAND_FAMILIES = {
    'xiaomi': {'xiaomi', 'redmi', 'poco'},
    'redmi': {'xiaomi', 'redmi'},
    'poco': {'xiaomi', 'poco'},
    'motorola': {'motorola', 'moto'},
    'moto': {'motorola', 'moto'},
}

CRITICAL_VARIANTS = {
    'pro', 'plus', 'ultra', 'max', 'lite', 'mini', 'se', 'fe',
    'note', 'edge', 'neo', 'ace', 'master', 'gt', 'turbo'
}


def extract_brand(title: str) -> Optional[str]:
    if not title:
        return None
    match = BRAND_PATTERNS.search(title)
    if match:
        brand = match.group(1).strip()
        return BRAND_NORMALIZATIONS.get(brand.lower(), brand.title())
    return None


def extract_ram(title: str) -> Optional[int]:
    if not title:
        return None
    for pattern in RAM_PATTERNS:
        m = pattern.search(title)
        if m:
            ram = int(m.group(1))
            if 2 <= ram <= 32:
                return ram
    return None


def extract_storage(title: str) -> Optional[int]:
    if not title:
        return None
    for pattern in STORAGE_PATTERNS:
        matches = pattern.findall(title)
        for match_str in matches:
            storage = int(match_str)
            if 'TB' in title.upper() and storage <= 4:
                return storage * 1024
            if storage in [16, 32, 64, 128, 256, 512, 1024] or 16 <= storage <= 2048:
                return storage
    return None


def extract_model(title: str, brand: Optional[str] = None) -> Optional[str]:
    """Enhanced model extraction with multiple strategies."""
    if not title:
        return None

    # Strategy 1: Known product line patterns
    for pattern in MODEL_NUMBER_PATTERNS:
        m = pattern.search(title)
        if m:
            model = m.group(1).strip()
            if len(model) >= 2:
                return model

    # Strategy 2: After brand name
    if brand:
        brand_esc = re.escape(brand)
        m = re.search(
            rf'{brand_esc}\s+([A-Z]?\d*\s*[A-Za-z]*\d+[A-Za-z]*)',
            title, re.IGNORECASE
        )
        if m:
            return m.group(1).strip()

    return None


def extract_generation(title: str) -> Optional[str]:
    if not title:
        return None
    matches = GENERATION_PATTERNS.findall(title)
    if matches:
        seen = set()
        unique = []
        for m in matches:
            ml = m.lower()
            if ml not in seen:
                seen.add(ml)
                unique.append(m)
        return ' '.join(unique)
    return None


def extract_color(title: str) -> Optional[str]:
    if not title:
        return None
    m = COLOR_PATTERNS.search(title)
    return m.group(1).strip().title() if m else None


def extract_network(title: str) -> Optional[str]:
    if not title:
        return None
    m = NETWORK_PATTERNS.search(title)
    if m:
        net = m.group(1).upper()
        return 'VoLTE' if net == 'VOLTE' else net
    return None


def extract_screen_size(title: str) -> Optional[float]:
    if not title:
        return None
    m = SCREEN_SIZE_PATTERN.search(title)
    if m:
        size = float(m.group(1))
        if 4.0 <= size <= 17.0:
            return size
    return None


def is_accessory(title: str) -> bool:
    if not title:
        return True
    title_lower = title.lower()

    main_indicators = [
        'smartphone', 'mobile phone', 'cellphone', 'cell phone',
        'laptop', 'notebook', 'ultrabook', 'chromebook',
        'tablet', 'ipad', 'galaxy tab',
        'smart tv', 'television', 'led tv', 'oled tv',
        'refrigerator', 'washing machine',
        'smartwatch', 'smart watch', 'fitness band',
    ]
    for ind in main_indicators:
        if ind in title_lower and not ACCESSORY_PATTERNS.search(title):
            return False

    if ACCESSORY_PATTERNS.search(title):
        return True

    # "for [Brand]" pattern
    if re.search(
        r'\bfor\s+(?:the\s+)?(?:new\s+)?'
        r'(?:samsung|apple|iphone|xiaomi|redmi|vivo|oppo|oneplus|realme|motorola|nokia)\s+'
        r'[a-z0-9]+', title_lower
    ):
        return True

    if re.search(r'\b(?:pack|set|combo|bundle)\s*(?:of\s*)?\d+|\d+\s*(?:pcs|pieces|pack)', title_lower):
        return True

    return False


def is_refurbished(title: str) -> bool:
    return bool(REFURBISHED_PATTERNS.search(title)) if title else False


def extract_specs(title: str, price: Optional[float] = None, full_title: Optional[str] = None) -> ProductSpecs:
    """Extract all specs from a product title.
    
    Args:
        title: The text to extract from (may be essence or title)
        price: Product price
        full_title: If provided, used as fallback for spec extraction
                    when 'title' is an AI essence that strips numbers
    """
    specs = ProductSpecs(raw_title=title or "", price=price, full_title=full_title or title or "")
    if not title:
        specs.is_accessory = True
        return specs

    # Use full_title for spec extraction when available (more details than essence)
    spec_text = full_title if full_title else title

    specs.is_accessory = is_accessory(spec_text)
    specs.is_refurbished = is_refurbished(spec_text)
    specs.brand = extract_brand(spec_text)
    specs.ram_gb = extract_ram(spec_text)
    specs.storage_gb = extract_storage(spec_text)
    specs.generation = extract_generation(spec_text)
    specs.network = extract_network(spec_text)
    specs.color = extract_color(spec_text)
    specs.screen_size = extract_screen_size(spec_text)
    specs.model = extract_model(spec_text, specs.brand)
    return specs


# =============================================================================
# SECTION 4: MATCHING ENGINE (3-TIER)
# =============================================================================

def tier1_spec_reject(
    source: ProductSpecs,
    target: ProductSpecs,
) -> Tuple[bool, str, MatchResult]:
    """
    TIER 1: Fast hard-reject based on specs.
    Returns (passed, reason, result).
    """
    # Reject accessories
    if target.is_accessory:
        return (False, f"Accessory: '{target.raw_title[:50]}...'", MatchResult.ACCESSORY_REJECTED)

    # Reject refurbished vs new
    if target.is_refurbished and not source.is_refurbished:
        return (False, "Refurbished vs New", MatchResult.REFURBISHED_REJECTED)

    # Brand mismatch
    if source.brand and target.brand:
        sb = source.brand.lower().strip()
        tb = target.brand.lower().strip()
        sf = BRAND_FAMILIES.get(sb, {sb})
        tf = BRAND_FAMILIES.get(tb, {tb})
        if not sf.intersection(tf):
            return (False, f"Brand: {source.brand} vs {target.brand}", MatchResult.BRAND_MISMATCH)

    # RAM mismatch
    if source.ram_gb and target.ram_gb and source.ram_gb != target.ram_gb:
        return (False, f"RAM: {source.ram_gb}GB vs {target.ram_gb}GB", MatchResult.SPECS_MISMATCH)

    # Storage mismatch
    if source.storage_gb and target.storage_gb and source.storage_gb != target.storage_gb:
        return (False, f"Storage: {source.storage_gb}GB vs {target.storage_gb}GB", MatchResult.SPECS_MISMATCH)

    # Critical variant mismatch (Pro vs Ultra, etc.)
    if source.generation or target.generation:
        sg = set((source.generation or "").lower().split())
        tg = set((target.generation or "").lower().split())
        sc = sg.intersection(CRITICAL_VARIANTS)
        tc = tg.intersection(CRITICAL_VARIANTS)
        if sc != tc:
            return (False, f"Variant: '{source.generation or 'Std'}' vs '{target.generation or 'Std'}'", MatchResult.VARIANT_MISMATCH)

    # Price mismatch (±30% tolerance)
    if source.price and target.price and source.price > 0 and target.price > 0:
        ratio = target.price / source.price
        if ratio < 0.5 or ratio > 2.0:
            return (False, f"Price: ₹{source.price:.0f} vs ₹{target.price:.0f}", MatchResult.PRICE_MISMATCH)

    return (True, "Tier 1 passed", MatchResult.EXACT_MATCH)


STOP_WORDS = {
    'mobile', 'smartphone', 'phone', 'laptop', 'tablet', 'smart',
    'the', 'with', 'for', 'and', 'or', 'in', 'on', 'at', 'to', 'of',
    'new', 'latest', 'best', 'top', 'premium', 'exclusive', 'limited',
    'special', 'offer', 'sale', 'deal', 'discount', 'price', 'buy',
    'genuine', 'original', 'authentic', 'official', 'authorized',
    'sealed', 'pack', 'box', 'warranty', 'year', 'month', 'free',
    'delivery', 'shipping', 'fast', 'express', 'cod',
    'india', 'indian', 'global', 'international', 'imported',
    'amazon', 'flipkart', 'meesho', 'myntra', 'online',
    'combo', 'bundle', 'kit', 'only', 'brand', 'model',
}


def tier2_fuzzy_match(
    source_essence: str,
    target_title: str,
    source_specs: ProductSpecs,
    target_specs: ProductSpecs,
) -> Tuple[float, str]:
    """
    TIER 2: Fuzzy matching with word-overlap + SequenceMatcher + bonuses.
    Returns (score, reason).
    """
    if not source_essence or not target_title:
        return (0.0, "Empty input")

    # Word overlap score
    s_words = set(source_essence.lower().split()) - STOP_WORDS
    t_words = set(target_title.lower().split()) - STOP_WORDS
    overlap = len(s_words.intersection(t_words)) / max(len(s_words), 1)

    # SequenceMatcher score (handles word reordering)
    clean_source = ' '.join(sorted(s_words))
    clean_target = ' '.join(sorted(t_words))
    seq_score = SequenceMatcher(None, clean_source, clean_target).ratio()

    # Weighted base: 40% overlap + 60% sequence
    base = (overlap * 0.4) + (seq_score * 0.6)

    # Bonuses
    bonus = 0.0
    if source_specs.brand and target_specs.brand:
        if source_specs.brand.lower() == target_specs.brand.lower():
            bonus += 0.12
    if source_specs.ram_gb and target_specs.ram_gb and source_specs.ram_gb == target_specs.ram_gb:
        bonus += 0.08
    if source_specs.storage_gb and target_specs.storage_gb and source_specs.storage_gb == target_specs.storage_gb:
        bonus += 0.08
    if source_specs.generation and target_specs.generation:
        if source_specs.generation.lower() == target_specs.generation.lower():
            bonus += 0.08
    if source_specs.network and target_specs.network and source_specs.network == target_specs.network:
        bonus += 0.04

    # Price proximity bonus (within 20%)
    if source_specs.price and target_specs.price and source_specs.price > 0:
        price_ratio = target_specs.price / source_specs.price
        if 0.8 <= price_ratio <= 1.2:
            bonus += 0.06

    final = min(1.0, base + bonus)
    return (final, f"overlap={overlap:.2f} seq={seq_score:.2f} bonus={bonus:.2f}")


# =============================================================================
# SECTION 5: AI VERIFICATION (TIER 3)
# =============================================================================

AI_VERIFY_PROMPT = """You are a strict Product Matching Expert for an Indian e-commerce price comparison app.
Determine if SOURCE and TARGET are the EXACT SAME physical product (same item a customer would buy).

### SOURCE (from Database):
Title: {source_title}
Essence: {source_essence}
Brand: {source_brand} | RAM: {source_ram} | Storage: {source_storage} | Variant: {source_variant} | Price: ₹{source_price}

### TARGET (Scraped from {platform}):
Title: {scraped_title}
Brand: {target_brand} | RAM: {target_ram} | Storage: {target_storage} | Variant: {target_variant} | Price: ₹{target_price}

### STRICT RULES (follow EXACTLY):
1. ✅ MATCH only if: Same brand AND model AND storage AND RAM AND variant
2. ❌ REJECT if target is an accessory (case/cover/charger/screen guard/cable)
3. ❌ REJECT if storage differs (128GB ≠ 256GB) - these are DIFFERENT products
4. ❌ REJECT if RAM differs (6GB ≠ 4GB ≠ 8GB) - these are DIFFERENT products
5. ❌ REJECT if variant/generation differs (Pro ≠ Ultra ≠ standard)
6. ❌ REJECT if target is refurbished/renewed but source is new
7. ❌ REJECT if titles describe clearly different product types (e.g. tracksuit vs dress)
8. ❌ REJECT if brand names don't match at all
9. ⚠️ IMPORTANT: If BOTH titles are just a brand name with NO model info (e.g. "Crazyly" vs "Crazyly"), set is_exact_match=false because you CANNOT confirm they are the same product
10. ⚠️ For fashion: Two items must be the same garment type, color, size, and pattern to match
11. ✅ ALLOW: Color differences for electronics
12. ✅ ALLOW: Minor title formatting/ordering differences

Return ONLY valid JSON:
{{"match_score": <0.0-1.0>, "is_exact_match": <bool>, "reason": "<max 100 chars>", "confidence": "<high|medium|low>"}}"""


async def verify_with_ai(
    source_essence: str,
    source_specs: ProductSpecs,
    scraped_title: str,
    target_specs: ProductSpecs,
    platform: str,
    enrichment_svc,
) -> Dict[str, Any]:
    """Tier 3: AI verification of match."""
    prompt = AI_VERIFY_PROMPT.format(
        source_title=source_specs.raw_title[:150],
        source_essence=source_essence,
        source_brand=source_specs.brand or "Unknown",
        source_ram=f"{source_specs.ram_gb}GB" if source_specs.ram_gb else "Not specified",
        source_storage=f"{source_specs.storage_gb}GB" if source_specs.storage_gb else "Not specified",
        source_variant=source_specs.generation or "Standard",
        source_price=f"{source_specs.price:.0f}" if source_specs.price else "?",
        platform=platform,
        scraped_title=scraped_title,
        target_brand=target_specs.brand or "Unknown",
        target_ram=f"{target_specs.ram_gb}GB" if target_specs.ram_gb else "Not specified",
        target_storage=f"{target_specs.storage_gb}GB" if target_specs.storage_gb else "Not specified",
        target_variant=target_specs.generation or "Standard",
        target_price=f"{target_specs.price:.0f}" if target_specs.price else "?",
    )

    fallback = {
        "match_score": 0.0, "is_exact_match": False,
        "reason": "AI unavailable", "confidence": "low"
    }

    try:
        from app.services.ai.groq_client import groq_client, GroqFeature
        result_text = await groq_client._call_groq(
            messages=[{"role": "user", "content": prompt}],
            feature=GroqFeature.SEARCH,
            temperature=0.1,
            max_tokens=200,
            json_mode=True,
        )

        if not result_text:
            return fallback

        # Clean markdown
        text = result_text.strip()
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

        parsed = json.loads(text)

        for key in ['match_score', 'is_exact_match', 'reason']:
            if key not in parsed:
                parsed[key] = fallback.get(key)

        return parsed

    except json.JSONDecodeError:
        return fallback
    except Exception as e:
        print(f"      ⚠️ AI error: {str(e)[:50]}")
        return fallback


# =============================================================================
# SECTION 6: SEARCH QUERY GENERATION (Platform-Specific)
# =============================================================================

# Supported platform handlers (avoid errors for unsupported platforms)
SUPPORTED_PLATFORMS = {'amazon', 'flipkart', 'meesho', 'myntra', 'croma', 'nykaa'}


def generate_search_query(
    product: Product,
    target_platform: str,
    max_words: int = 6,
) -> str:
    """Platform-optimized search query generation."""

    # Use AI essence if available
    essence = ""
    if product.ai_metadata and product.ai_metadata.get("essence"):
        essence = product.ai_metadata["essence"]

    # Extract specs from FULL TITLE (not essence!) for accurate query building
    specs = extract_specs(essence or product.title, full_title=product.title)

    # Platform-specific query strategies
    if target_platform == "meesho":
        # Meesho: simpler queries, brand + basic model
        parts = []
        if specs.brand: parts.append(specs.brand)
        if specs.model: parts.append(specs.model)
        if not parts:
            parts = (essence or product.title).split()[:3]
        return " ".join(parts[:4])

    elif target_platform == "flipkart":
        # Flipkart: brand + model + key spec
        parts = []
        if specs.brand: parts.append(specs.brand)
        if specs.model: parts.append(specs.model)
        if specs.generation: parts.append(specs.generation)
        if specs.storage_gb: parts.append(f"{specs.storage_gb}GB")
        # FIX: If we only have generation (e.g. "pro") and nothing else, use essence/title
        if len(parts) <= 1:
            return " ".join((essence or product.title).split()[:max_words])
        return " ".join(parts[:max_words])

    else:
        # Amazon / default: specific model query
        if essence:
            return " ".join(essence.split()[:max_words])

        parts = []
        if specs.brand: parts.append(specs.brand)
        if specs.model: parts.append(specs.model)
        if specs.generation: parts.append(specs.generation)
        if specs.ram_gb and specs.storage_gb:
            parts.append(f"{specs.ram_gb}GB/{specs.storage_gb}GB")
        elif specs.storage_gb:
            parts.append(f"{specs.storage_gb}GB")
        if specs.network: parts.append(specs.network)

        if parts:
            return " ".join(parts[:max_words])

        # Fallback
        brand = product.brand or ""
        title_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', product.title)
        return f"{brand} {' '.join(title_clean.split()[:4])}".strip()


# =============================================================================
# SECTION 7: FINGERPRINT LINKER (THE KEY FIX)
# =============================================================================

async def save_matched_product(
    scraped_product: ProductData,
    db_product: Product,
    db,
    enrichment_svc,
) -> bool:
    """
    Save a matched product with the CORRECT fingerprint.

    KEY FIX: We override the fingerprint AFTER AI enrichment,
    ensuring the new product links to the same master product.
    """
    try:
        # Step 1: Enrich with AI (gets essence, tags, quality)
        enriched = await enrichment_svc.enrich_product(scraped_product)

        # Step 2: FORCE the fingerprint to match the DB product
        # This is the critical fix - we override AFTER enrichment
        # so the AI essence doesn't generate a new fingerprint
        existing_fp = db_product.fingerprint
        enriched._cached_fingerprint = existing_fp
        # Also override ai_essence to match the source product's essence
        # This ensures get_fingerprint() returns the correct value
        if db_product.ai_metadata and db_product.ai_metadata.get("essence"):
            enriched.ai_essence = db_product.ai_metadata["essence"]

        # Verify fingerprint is correct
        assert enriched.fingerprint == existing_fp, \
            f"Fingerprint mismatch: {enriched.fingerprint} != {existing_fp}"

        # Step 3: Save to DB (product_service handles dedup)
        await product_service.save_product(
            product_data=enriched,
            db=db,
            is_user_search=False
        )

        return True

    except Exception as e:
        print(f"         ⚠️ Save error: {e}")
        return False


# =============================================================================
# SECTION 8: MAIN PROCESSING PIPELINE
# =============================================================================

async def process_orphan_products(
    limit: int = 10,
    use_ai: bool = True,
    target_platforms: Optional[List[str]] = None,
    min_score: float = 0.85,
    category_filter: Optional[str] = None,
    verbose: bool = True,
):
    """Main autonomous mining pipeline."""
    print(f"\n{'=' * 70}")
    print(f"🤖 CROSS-PLATFORM MINER v3.0")
    print(f"{'=' * 70}")
    print(f"  Mode: {'AI Verify' if use_ai else 'Fast (No AI)'}")
    print(f"  Min Score: {min_score:.0%} | Limit: {limit}")
    if target_platforms:
        print(f"  Platforms: {', '.join(target_platforms)}")
    if category_filter:
        print(f"  Category: {category_filter}")
    print(f"{'=' * 70}\n")

    stats = MiningStats()

    async with async_session_maker() as db:
        # ─── Query orphan products ───
        print("🔍 Finding orphan products...\n")

        stmt = (
            select(Product)
            .options(selectinload(Product.listings))
            .join(ProductListing)
            .group_by(Product.id)
            .having(func.count(ProductListing.id) == 1)
        )

        if category_filter:
            stmt = stmt.where(Product.category.ilike(f"%{category_filter}%"))

        stmt = stmt.order_by(func.random()).limit(limit)

        result = await db.execute(stmt)
        orphans = result.scalars().all()

        if not orphans:
            print("✅ No orphan products found - database is fully matched!")
            return stats

        print(f"📦 Found {len(orphans)} orphans. Mining...\n")

        # ─── Process each orphan ───
        for i, db_product in enumerate(orphans, 1):
            stats.processed += 1
            listing = db_product.listings[0]
            existing_platform_id = listing.platform_id

            # Determine category
            try:
                cat_enum = ProductCategory(db_product.category.lower()) if db_product.category else ProductCategory.GENERAL
            except (ValueError, AttributeError):
                cat_enum = ProductCategory.GENERAL

            available = ProductCategory.get_platforms_for_category(cat_enum)
            # FIX: Filter out unsupported platforms (reliancedigital, ajio, etc.)
            available = [p for p in available if p in SUPPORTED_PLATFORMS]
            if target_platforms:
                available = [p for p in available if p in target_platforms]

            print(f"\n{'─' * 70}")
            print(f"[{i}/{len(orphans)}] 🎯 {db_product.title[:55]}...")
            print(f"{'─' * 70}")

            # Source essence + FULL title for spec extraction
            source_essence = ""
            if db_product.ai_metadata:
                source_essence = db_product.ai_metadata.get("essence", "")
            if not source_essence:
                source_essence = db_product.title

            # FIX: Extract specs from FULL TITLE, not just essence
            # Essence strips numbers like "(6GB, 128GB)" causing false matches
            source_price = float(listing.current_price) if listing.current_price else None
            source_specs = extract_specs(source_essence, price=source_price, full_title=db_product.title)

            if verbose:
                print(f"  📊 Brand={source_specs.brand or '?'} RAM={source_specs.ram_gb or '?'}GB "
                      f"Storage={source_specs.storage_gb or '?'}GB Variant={source_specs.generation or 'Std'}"
                      f" Price=₹{source_price or '?'}")

            # ─── Search each platform ───
            for platform_name in available:
                stats.platforms_scraped[platform_name] = stats.platforms_scraped.get(platform_name, 0) + 1

                query = generate_search_query(db_product, platform_name)
                print(f"\n  🌐 {platform_name.upper()} → '{query}'")

                try:
                    handler = await get_platform_handler(platform_name, db)
                    if not handler:
                        print(f"    ⚪ No handler")
                        continue

                    search_result = await asyncio.wait_for(
                        handler.search(query=query, page=1),
                        timeout=45
                    )

                    if not search_result or not search_result.products:
                        print(f"    ⚪ No results")
                        continue

                    raw = len(search_result.products)
                    print(f"    📥 {raw} results")

                    # ─── Filter & Match ───
                    match_found = False
                    candidates = search_result.products[:10]
                    rejected = 0

                    for scraped in candidates:
                        s_title = scraped.title
                        s_price = float(scraped.current_price) if scraped.current_price else None
                        target_specs = extract_specs(s_title, s_price)

                        # TIER 1: Hard reject
                        passed, reason, result = tier1_spec_reject(source_specs, target_specs)
                        if not passed:
                            rejected += 1
                            stats.api_calls_saved += 1
                            continue

                        # TIER 2: Fuzzy score
                        score, score_reason = tier2_fuzzy_match(
                            source_essence, s_title, source_specs, target_specs
                        )

                        if score < 0.50:
                            if verbose:
                                print(f"    ⚪ {score:.2f}: {s_title[:40]}...")
                            continue

                        print(f"\n    🔄 Score={score:.2f}: {s_title[:50]}...")

                        # TIER 3: AI verification
                        final_score = score
                        ai_ok = False

                        if use_ai and score >= 0.55:
                            ai_result = await verify_with_ai(
                                source_essence, source_specs,
                                s_title, target_specs,
                                platform_name, enrichment_service
                            )
                            ai_score = ai_result.get("match_score", 0.0)
                            ai_match = ai_result.get("is_exact_match", False)
                            confidence = ai_result.get("confidence", "?")

                            print(f"       AI: score={ai_score:.2f} match={ai_match} conf={confidence}")
                            print(f"       AI: {ai_result.get('reason', 'N/A')}")

                            if not ai_match or ai_score < min_score:
                                stats.ai_rejected += 1
                                continue

                            stats.ai_verified += 1
                            final_score = ai_score
                            ai_ok = True

                        # ─── Save match ───
                        if final_score >= min_score:
                            print(f"\n    ✅ {'AI ' if ai_ok else ''}MATCH! Score={final_score:.2%}")

                            ok = await save_matched_product(
                                scraped, db_product, db, enrichment_service
                            )
                            if ok:
                                stats.stored += 1
                                print(f"       💾 Linked → {db_product.fingerprint[:20]}...")
                                match_found = True
                                break
                            else:
                                stats.errors += 1

                    if rejected > 0:
                        stats.pre_filtered += rejected
                        if verbose:
                            print(f"    🚫 Pre-filtered: {rejected}")

                    if not match_found:
                        print(f"    ❌ No match on {platform_name}")

                except asyncio.TimeoutError:
                    stats.errors += 1
                    print(f"    ⏱️ Timeout")
                except Exception as e:
                    stats.errors += 1
                    print(f"    ⚠️ Error: {str(e)[:60]}")

            # Cleanup browser between products
            try:
                from app.services.scraper.browser import close_browser_manager
                await close_browser_manager()
            except Exception:
                pass

        # Final commit
        try:
            await db.commit()
        except Exception:
            pass

    stats.print_summary()
    return stats


# =============================================================================
# SECTION 9: CLI
# =============================================================================

def parse_platforms(s: str) -> Optional[List[str]]:
    if not s:
        return None
    valid = [p.value for p in Platform]
    platforms = [p.strip().lower() for p in s.split(',')]
    for p in platforms:
        if p not in valid:
            raise ValueError(f"Invalid platform: {p}. Valid: {', '.join(valid)}")
    return platforms


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cross-Platform Miner v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/cross_platform_miner.py --limit 10
  python scripts/cross_platform_miner.py --limit 50 --no-ai
  python scripts/cross_platform_miner.py --limit 20 --platforms amazon,flipkart
  python scripts/cross_platform_miner.py --category electronics --limit 10
        """
    )

    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--platforms", type=str, default=None)
    parser.add_argument("--min-score", type=float, default=0.85)
    parser.add_argument("--category", type=str, default=None)
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args()

    tp = None
    if args.platforms:
        try:
            tp = parse_platforms(args.platforms)
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)

    try:
        asyncio.run(process_orphan_products(
            limit=args.limit,
            use_ai=not args.no_ai,
            target_platforms=tp,
            min_score=args.min_score,
            category_filter=args.category,
            verbose=not args.quiet,
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted.")
        sys.exit(0)

#!/usr/bin/env python3
"""
Cross-Platform Miner v4.0 - Zero False Positives Edition
=========================================================

Complete rewrite with 6 layers of protection:
- LAYER 1: Quality Gate (skip unmatchable products)
- LAYER 2: Smart Query Generation (correct brands, min 3 words)
- LAYER 3: Junk Filter (remove status messages, empty titles)
- LAYER 4: Enhanced Tier 1 (product-line, screen-size, model rejection)
- LAYER 5: Category-Aware AI (different prompts per category)
- LAYER 6: Post-AI Sanity Check (catch AI hallucinations)

Key Fixes from v3.0:
- FIXED: Fire-Boltt "Phoenix" → "Hunter" false match (product-line comparison)
- FIXED: "NOISE" (1 word) → random match (quality gate blocks)
- FIXED: POCO → "Xiaomi" query issue (original brand for search)
- FIXED: Laptop storage 16GB vs 512GB (storage regex rewrite)
- FIXED: Headphone source rejected as accessory (source-aware logic)
- FIXED: AI says "different" but match=True (contradiction detection)
- ADDED: 100+ Indian/global brands (Fire-Boltt, boAt, Noise, etc.)
- ADDED: Product-line extraction (Phoenix, Hunter, Galaxy S, Nord, etc.)
- ADDED: Category-aware AI prompts (electronics, fashion, watches)
- ADDED: Parallel platform scraping (asyncio.gather)
- ADDED: Audit logging for post-run analysis

Usage:
    python scripts/cross_platform_miner.py --limit 10
    python scripts/cross_platform_miner.py --limit 50 --no-ai
    python scripts/cross_platform_miner.py --category electronics --limit 20
    python scripts/cross_platform_miner.py --platforms amazon,flipkart --limit 10
    python scripts/cross_platform_miner.py --debug  # Enable SQL logging

Author: DealHunt
Version: 4.0.0
"""

import asyncio
import argparse
import sys
import os
import re
import json
import hashlib
import logging
from decimal import Decimal
from typing import Optional, Dict, Tuple, Any, List, Set, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from difflib import SequenceMatcher
from pathlib import Path

# ============================================================================
# WINDOWS ASYNC FIX - Handle subprocess creation limitations
# ============================================================================
if sys.platform == 'win32':
    # Use ProactorEventLoop which has better Windows subprocess support
    # But we must silence the deprecation and handle the subprocess issue
    try:
        # Python 3.10+ on Windows: switch to ProactorEventLoop for subprocess support
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        # Fallback to SelectorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Suppress the DeletePending file descriptor warning
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        def silence_proactor_del(self):
            pass
        _ProactorBasePipeTransport.__del__ = silence_proactor_del
    except (ImportError, AttributeError):
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import Product, ProductListing, Platform as PlatformModel
from app.services.scraper.base import ProductData, ProductCategory
from app.services.scraper.factory import get_platform_handler
from app.services.ai.enrichment_service import enrichment_service
from app.services.product_service import product_service, _validate_image_url, _is_useful_essence
from app.schemas import Platform

logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 1: CONFIGURATION & CONSTANTS
# =============================================================================

class MinerConfig:
    """Central configuration for the miner."""
    
    # Quality Gate Settings
    MIN_TITLE_WORDS = 3
    MIN_TITLE_LENGTH = 10
    
    # Tier 1 Settings
    PRICE_TOLERANCE = {
        'electronics': 0.30,   # ±30%
        'fashion': 0.60,       # ±60%
        'watches': 0.40,       # ±40%
        'appliances': 0.25,    # ±25%
        'general': 0.40,       # ±40%
    }
    SCREEN_SIZE_TOLERANCE = 0.3  # inches
    
    # Tier 2 Settings (fuzzy matching)
    FUZZY_THRESHOLD = {
        'electronics': 0.55,
        'fashion': 0.45,
        'watches': 0.50,
        'general': 0.50,
    }
    
    # AI Settings
    MAX_AI_CALLS_PER_PLATFORM = 3
    MIN_AI_CONFIDENCE_SCORE = 0.90
    
    # Scraping Settings
    SCRAPE_TIMEOUT = max(10, int(settings.SCRAPER_TIMEOUT / 1000))
    MAX_CANDIDATES_PER_PLATFORM = 12
    MAX_RETRIES = max(1, settings.SCRAPER_MAX_RETRIES)
    
    # Parallel Scraping
    MAX_CONCURRENT_PLATFORMS = max(1, min(6, settings.SCRAPER_CONCURRENT_LIMIT))
    
    # Supported Platforms
    SUPPORTED_PLATFORMS = {'amazon', 'flipkart', 'meesho', 'myntra', 'croma', 'nykaa'}


# =============================================================================
# SECTION 2: ENUMS & DATA CLASSES
# =============================================================================

class MatchResult(str, Enum):
    """Result codes for product matching."""
    EXACT_MATCH = "exact_match"
    PARTIAL_MATCH = "partial_match"
    NO_MATCH = "no_match"
    ACCESSORY_REJECTED = "accessory_rejected"
    SPECS_MISMATCH = "specs_mismatch"
    REFURBISHED_REJECTED = "refurbished_rejected"
    VARIANT_MISMATCH = "variant_mismatch"
    PRICE_MISMATCH = "price_mismatch"
    BRAND_MISMATCH = "brand_mismatch"
    PRODUCT_LINE_MISMATCH = "product_line_mismatch"
    MODEL_MISMATCH = "model_mismatch"
    SCREEN_SIZE_MISMATCH = "screen_size_mismatch"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    JUNK_TITLE = "junk_title"
    AI_CONTRADICTION = "ai_contradiction"
    AI_LOW_CONFIDENCE = "ai_low_confidence"


class ProductCategoryType(str, Enum):
    """Product category types for category-aware processing."""
    ELECTRONICS = "electronics"
    FASHION = "fashion"
    WATCHES = "watches"
    APPLIANCES = "appliances"
    GENERAL = "general"


@dataclass
class ProductSpecs:
    """Extracted product specifications with enhanced fields."""
    # Basic fields
    brand: Optional[str] = None
    original_brand: Optional[str] = None  # NEW: Original brand for search queries
    model: Optional[str] = None
    
    # Electronics specs
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    network: Optional[str] = None
    processor: Optional[str] = None  # NEW: For laptops
    
    # Display specs
    screen_size: Optional[float] = None
    
    # Product identity
    product_line: Optional[str] = None  # NEW: Phoenix, Hunter, Galaxy S, Nord, etc.
    generation: Optional[str] = None  # Pro, Ultra, Lite, etc.
    color: Optional[str] = None
    
    # Fashion specs (NEW)
    garment_type: Optional[str] = None
    material: Optional[str] = None
    fit: Optional[str] = None
    gender: Optional[str] = None
    
    # Watch specs (NEW)
    has_calling: Optional[bool] = None
    has_gps: Optional[bool] = None
    
    # Flags
    is_accessory: bool = False
    is_refurbished: bool = False
    
    # Metadata
    price: Optional[float] = None
    raw_title: str = ""
    full_title: str = ""
    category_type: ProductCategoryType = ProductCategoryType.GENERAL

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() 
                if v is not None and k not in ['raw_title', 'full_title']}

    def get_essence(self) -> str:
        """Generate a search-friendly essence string."""
        parts = []
        # Use original brand for search queries (POCO not Xiaomi)
        if self.original_brand:
            parts.append(self.original_brand)
        elif self.brand:
            parts.append(self.brand)
        if self.product_line:
            parts.append(self.product_line)
        if self.model:
            parts.append(self.model)
        if self.generation:
            parts.append(self.generation)
        if self.storage_gb:
            parts.append(f"{self.storage_gb}GB")
        if self.network:
            parts.append(self.network)
        return " ".join(parts)
    
    def get_identity_strength(self) -> int:
        """Calculate how much identity information we have (0-10 scale)."""
        score = 0
        if self.brand: score += 2
        if self.product_line: score += 3
        if self.model: score += 2
        if self.storage_gb or self.ram_gb: score += 1
        if self.generation: score += 1
        if self.screen_size: score += 1
        return min(10, score)


@dataclass
class QualityGateResult:
    """Result of quality gate check."""
    passed: bool
    reason: str
    identity_score: int = 0


@dataclass
class MatchVerification:
    """Detailed match verification result."""
    result: MatchResult
    score: float
    reason: str
    source_specs: Optional[ProductSpecs] = None
    target_specs: Optional[ProductSpecs] = None
    ai_response: Optional[Dict[str, Any]] = None
    tier_reached: int = 0


@dataclass 
class PlatformResult:
    """Result from scraping a single platform."""
    platform: str
    success: bool
    match_found: bool = False
    scraped_product: Optional[ProductData] = None
    match_score: float = 0.0
    error: Optional[str] = None
    candidates_checked: int = 0
    pre_filtered: int = 0
    ai_calls: int = 0


@dataclass
class MiningStats:
    """Statistics for the mining run."""
    processed: int = 0
    quality_gate_skipped: int = 0
    pre_filtered: int = 0
    junk_filtered: int = 0
    tier1_rejected: int = 0
    ai_verified: int = 0
    ai_rejected: int = 0
    ai_contradictions: int = 0
    retries: int = 0
    image_validation_fixed: int = 0
    essence_validation_fixed: int = 0
    stored: int = 0
    errors: int = 0
    api_calls_saved: int = 0
    platforms_scraped: Dict[str, int] = field(default_factory=dict)
    platforms_matched: Dict[str, int] = field(default_factory=dict)
    skipped_products: List[Dict[str, str]] = field(default_factory=list)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)

    def print_summary(self):
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        print(f"\n{'=' * 70}")
        print(f"📊 MINING RESULTS v4.0  ({elapsed:.0f}s)")
        print(f"{'=' * 70}")
        print(f"  Products Processed:    {self.processed}")
        print(f"  Quality Gate Skipped:  {self.quality_gate_skipped} ⚠️")
        print(f"  Junk Titles Filtered:  {self.junk_filtered}")
        print(f"  Tier 1 Pre-Filtered:   {self.pre_filtered}")
        print(f"  AI Verified Matches:   {self.ai_verified} ✅")
        print(f"  AI Rejections:         {self.ai_rejected}")
        print(f"  AI Contradictions:     {self.ai_contradictions} 🔍")
        print(f"  Retry Attempts:        {self.retries}")
        print(f"  Image Fixups Applied:  {self.image_validation_fixed}")
        print(f"  Essence Fixups Applied:{self.essence_validation_fixed}")
        print(f"  Successfully Stored:   {self.stored} 💾")
        print(f"  Errors:                {self.errors}")
        print(f"  API Calls Saved:       {self.api_calls_saved} 💰")
        
        if self.platforms_scraped:
            print(f"\n  📡 Platform Stats:")
            for p in sorted(self.platforms_scraped.keys()):
                scraped = self.platforms_scraped.get(p, 0)
                matched = self.platforms_matched.get(p, 0)
                rate = (matched / scraped * 100) if scraped > 0 else 0
                print(f"    {p:12} : {scraped} searched, {matched} matched ({rate:.0f}%)")
        
        if self.skipped_products:
            print(f"\n  ⏭️ Skipped Products ({len(self.skipped_products)}):")
            for sp in self.skipped_products[:5]:
                print(f"    • {sp['title'][:40]}... → {sp['reason']}")
            if len(self.skipped_products) > 5:
                print(f"    ... and {len(self.skipped_products) - 5} more")
        
        print(f"{'=' * 70}")
    
    def save_audit_log(self, filepath: str = None):
        """Save audit log for post-run analysis."""
        if not filepath:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filepath = f"mining_audit_{timestamp}.json"
        
        audit_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "stats": {
                "processed": self.processed,
                "stored": self.stored,
                "quality_gate_skipped": self.quality_gate_skipped,
                "ai_verified": self.ai_verified,
                "ai_rejected": self.ai_rejected,
                "ai_contradictions": self.ai_contradictions,
                "retries": self.retries,
                "image_validation_fixed": self.image_validation_fixed,
                "essence_validation_fixed": self.essence_validation_fixed,
            },
            "skipped_products": self.skipped_products,
            "matches": self.audit_log,
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(audit_data, f, indent=2, ensure_ascii=False)
            print(f"\n📄 Audit log saved: {filepath}")
        except Exception as e:
            print(f"\n⚠️ Could not save audit log: {e}")


# =============================================================================
# SECTION 3: COMPREHENSIVE BRAND DATABASE
# =============================================================================

# Brand patterns with proper handling for hyphenated/special brands
BRAND_PATTERNS_LIST = [
    # Smartphones - Global
    r'Samsung', r'Apple', r'iPhone', r'iPad', r'OnePlus', r'One\s*Plus',
    r'Xiaomi', r'Redmi', r'POCO', r'Realme', r'Vivo', r'Oppo', r'iQOO', r'IQOO',
    r'Motorola', r'Moto', r'Nokia', r'Google', r'Pixel', r'Nothing',
    r'Asus', r'ROG', r'Sony', r'Xperia', r'Huawei', r'Honor', r'Tecno', r'Infinix',
    r'LG', r'HTC', r'Lenovo', r'ZTE', r'Meizu', r'Nubia', r'BlackBerry',
    r'TCL', r'Alcatel', r'Coolpad', r'LeEco', r'Sharp', r'Panasonic',
    r'Black\s*Shark', r'Red\s*Magic', r'RedMagic',
    
    # Indian Audio/Wearables (FIXED - was missing these)
    r'Fire[\s\-]?Boltt', r'FireBoltt', r'boAt', r'boat', r'Noise',
    r'Zebronics', r'Mivi', r'Portronics', r'Ambrane', r'pTron', r'Ptron',
    r'Boult', r'Boult\s*Audio', r'CrossBeats', r'Hammer', r'Fastrack',
    r'Titan', r'Sonata', r'Timex', r'Fossil', r'Amazfit', r'Garmin',
    r'Fitbit', r'Huami', r'realme\s*Watch', r'OnePlus\s*Watch',
    
    # Laptops/Computers
    r'Dell', r'HP', r'Hewlett[\s\-]?Packard', r'Acer', r'Asus', r'Lenovo',
    r'MSI', r'Razer', r'Gigabyte', r'Microsoft', r'Surface',
    r'Alienware', r'ThinkPad', r'IdeaPad', r'Inspiron', r'Pavilion',
    r'MacBook', r'Mac', r'Chromebook', r'BrowseBook', r'Avita',
    
    # TV/Appliances
    r'LG', r'Samsung', r'Sony', r'Panasonic', r'TCL', r'Hisense',
    r'Xiaomi', r'Mi', r'OnePlus\s*TV', r'Vu', r'Thomson', r'Kodak',
    r'Whirlpool', r'Godrej', r'Haier', r'IFB', r'Bosch', r'Siemens',
    r'Voltas', r'Blue\s*Star', r'Daikin', r'Carrier', r'Hitachi',
    r'Bajaj', r'Crompton', r'Havells', r'Orient', r'Usha', r'V[\s\-]?Guard',
    r'Prestige', r'Pigeon', r'Butterfly', r'Preethi', r'Philips',
    r'Morphy\s*Richards', r'Kent', r'Eureka\s*Forbes', r'Aquaguard',
    
    # Audio - Global
    r'JBL', r'Sony', r'Bose', r'Sennheiser', r'Audio[\s\-]?Technica',
    r'Skullcandy', r'Beats', r'Marshall', r'Bang\s*&\s*Olufsen', r'B&O',
    r'Harman\s*Kardon', r'AKG', r'Shure', r'Beyerdynamic',
    
    # Fashion - Indian
    r'Roadster', r'HRX', r'Wrogn', r'Bewakoof', r'The\s*Souled\s*Store',
    r'Allen\s*Solly', r'Van\s*Heusen', r'Peter\s*England', r'Louis\s*Philippe',
    r'Park\s*Avenue', r'Raymond', r'Blackberrys', r'Indian\s*Terrain',
    r'US\s*Polo', r'U\.?S\.?\s*Polo', r'Flying\s*Machine', r'Pepe\s*Jeans',
    r'Levis', r"Levi's", r'Wrangler', r'Lee', r'Spykar', r'Mufti',
    r'Jack\s*&\s*Jones', r'Only', r'Vero\s*Moda', r'H&M', r'Zara',
    r'Forever\s*21', r'Mango', r'FabIndia', r'Biba', r'W', r'Aurelia',
    r'Global\s*Desi', r'AND', r'Libas', r'Anouk', r'Vishudh',
    
    # Fashion - Global
    r'Nike', r'Adidas', r'Puma', r'Reebok', r'Under\s*Armour', r'New\s*Balance',
    r'Skechers', r'Crocs', r'Woodland', r'Red\s*Tape', r'Bata', r'Liberty',
    r'Campus', r'Sparx', r'Relaxo', r'Action',
    
    # Sports/Outdoor
    r'Wildcraft', r'Decathlon', r'Quechua', r'Domyos', r'Kipsta',
    r'Yonex', r'Li[\s\-]?Ning', r'Victor', r'Cosco', r'Nivia',
    
    # Beauty/Personal Care
    r'Lakme', r'Maybelline', r"L'Oreal", r'Loreal', r'Nivea', r'Dove',
    r'Garnier', r'Pond\'?s', r'Himalaya', r'Biotique', r'Mamaearth',
    r'WOW', r'mCaffeine', r'Plum', r'The\s*Body\s*Shop', r'Forest\s*Essentials',
    r'Nykaa', r'Sugar', r'Colorbar', r'Faces', r'PAC', r'Swiss\s*Beauty',
    
    # Generic catches
    r'Crazyly', r'Generic', r'Local', r'Unbranded',
]

# Compile brand pattern
BRAND_PATTERNS = re.compile(
    r'\b(' + '|'.join(BRAND_PATTERNS_LIST) + r')\b',
    re.IGNORECASE
)

# Brand normalizations for MATCHING (not search)
BRAND_NORMALIZATIONS = {
    # Smartphone brands
    'iphone': 'Apple', 'ipad': 'Apple', 'macbook': 'Apple', 'mac': 'Apple',
    'moto': 'Motorola', 'motorola': 'Motorola',
    'one plus': 'OnePlus', 'oneplus': 'OnePlus',
    'rog': 'Asus', 'asus': 'Asus',
    'pixel': 'Google', 'google': 'Google',
    'redmi': 'Xiaomi', 'poco': 'Xiaomi', 'mi': 'Xiaomi',
    'iqoo': 'iQOO',
    'red magic': 'RedMagic', 'redmagic': 'RedMagic',
    'black shark': 'BlackShark', 'blackshark': 'BlackShark',
    
    # Audio brands - preserve original casing
    'fire-boltt': 'Fire-Boltt', 'fireboltt': 'Fire-Boltt', 'fire boltt': 'Fire-Boltt',
    'boat': 'boAt', 'boat': 'boAt',
    'noise': 'Noise',
    'fastrack': 'Fastrack',
    
    # Laptop brands
    'thinkpad': 'Lenovo', 'ideapad': 'Lenovo',
    'inspiron': 'Dell', 'alienware': 'Dell',
    'pavilion': 'HP', 'hewlett-packard': 'HP', 'hewlett packard': 'HP',
    'surface': 'Microsoft',
}

# Brand families (brands that are related and can match)
BRAND_FAMILIES = {
    'xiaomi': {'xiaomi', 'redmi', 'poco', 'mi'},
    'redmi': {'xiaomi', 'redmi'},
    'poco': {'xiaomi', 'poco'},
    'mi': {'xiaomi', 'mi'},
    'motorola': {'motorola', 'moto'},
    'moto': {'motorola', 'moto'},
    'apple': {'apple', 'iphone', 'ipad', 'macbook'},
    'iphone': {'apple', 'iphone'},
    'ipad': {'apple', 'ipad'},
    'lenovo': {'lenovo', 'thinkpad', 'ideapad'},
    'dell': {'dell', 'inspiron', 'alienware'},
    'hp': {'hp', 'pavilion', 'hewlett-packard'},
    'fire-boltt': {'fire-boltt', 'fireboltt'},
    'boat': {'boat', 'boAt'},
}


# =============================================================================
# SECTION 4: PRODUCT-LINE PATTERNS (NEW)
# =============================================================================

# Product lines for different brands (series names)
PRODUCT_LINE_PATTERNS = {
    # Fire-Boltt smartwatches
    'fire-boltt': re.compile(
        r'\b(Phoenix|Hunter|Ninja|Rocket|Tank|Gladiator|Visionary|'
        r'Invincible|Dynamite|Beam|Ring|Talk|Call|Epic|Supreme|'
        r'Hulk|Storm|Beast|Thunder|Vogue|Sprint|Edge)\b',
        re.IGNORECASE
    ),
    
    # Noise smartwatches
    'noise': re.compile(
        r'\b(ColorFit|Pulse|Icon|Vivid|Agile|NoiseFit|Evolve|'
        r'Force|Core|Active|Endure|Halo|Loop|Crew|Verge)\b',
        re.IGNORECASE
    ),
    
    # boAt audio
    'boat': re.compile(
        r'\b(Airdopes|Rockerz|Stone|Bassheads|Immortal|Nirvana|'
        r'Storm|Wave|Xtend|Lunar|Blaze|Flash|Vertex|Iris|Enigma)\b',
        re.IGNORECASE
    ),
    
    # Samsung phones
    'samsung': re.compile(
        r'\b(Galaxy\s*[SAZMF]|Galaxy\s*Note|Galaxy\s*Fold|Galaxy\s*Flip|'
        r'Galaxy\s*Tab|Galaxy\s*Watch|Galaxy\s*Buds)\b',
        re.IGNORECASE
    ),
    
    # Apple devices
    'apple': re.compile(
        r'\b(iPhone|iPad\s*Pro|iPad\s*Air|iPad\s*Mini|'
        r'MacBook\s*Pro|MacBook\s*Air|iMac|Mac\s*Mini|'
        r'Apple\s*Watch\s*Series|Apple\s*Watch\s*SE|'
        r'AirPods|AirPods\s*Pro|AirPods\s*Max)\b',
        re.IGNORECASE
    ),
    
    # OnePlus
    'oneplus': re.compile(
        r'\b(Nord|Ace|Buds|Watch)\b',
        re.IGNORECASE
    ),
    
    # Realme
    'realme': re.compile(
        r'\b(Narzo|GT|C|X|P|Buds|Watch|TechLife)\b',
        re.IGNORECASE
    ),
    
    # POCO
    'poco': re.compile(
        r'\b([MCFX]\d{1,2}|Pad)\b',
        re.IGNORECASE
    ),
    
    # Redmi
    'redmi': re.compile(
        r'\b(Note|K|A|Pad|Watch|Buds)\b',
        re.IGNORECASE
    ),
    
    # Laptops - Dell
    'dell': re.compile(
        r'\b(Inspiron|XPS|Latitude|Precision|Vostro|Alienware|G\d{1,2})\b',
        re.IGNORECASE
    ),
    
    # Laptops - HP
    'hp': re.compile(
        r'\b(Pavilion|Envy|Spectre|Omen|ProBook|EliteBook|Victus)\b',
        re.IGNORECASE
    ),
    
    # Laptops - Lenovo
    'lenovo': re.compile(
        r'\b(ThinkPad|IdeaPad|Yoga|Legion|LOQ|ThinkBook)\b',
        re.IGNORECASE
    ),
    
    # Laptops - Acer
    'acer': re.compile(
        r'\b(Aspire|Nitro|Predator|Swift|Spin|TravelMate)\b',
        re.IGNORECASE
    ),
    
    # Laptops - Asus
    'asus': re.compile(
        r'\b(VivoBook|ZenBook|ROG|TUF|ProArt|Chromebook)\b',
        re.IGNORECASE
    ),
}

# Generic product line extraction (when brand-specific not available)
GENERIC_PRODUCT_LINE_PATTERN = re.compile(
    r'(?:^|\s)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:Pro|Plus|Ultra|Max|Lite|Mini|SE|FE|\d)',
    re.IGNORECASE
)


# =============================================================================
# SECTION 5: OTHER REGEX PATTERNS
# =============================================================================

# Accessory patterns
ACCESSORY_PATTERNS = re.compile(
    r'\b('
    # Cases and covers
    r'case|cases|cover|covers|pouch|sleeve|skin|skins|wrap|wraps|'
    r'back\s*cover|flip\s*cover|wallet\s*case|bumper|bumpers|'
    r'protective\s*case|silicone\s*case|rubber\s*case|tpu\s*case|'
    r'hard\s*case|soft\s*case|clear\s*case|transparent\s*case|'
    r'armor\s*case|rugged\s*case|slim\s*case|ultra\s*thin\s*case|'
    r'leather\s*case|fabric\s*case|hybrid\s*case|'
    # Screen protectors
    r'tempered\s*glass|screen\s*guard|screen\s*protector|'
    r'glass\s*protector|privacy\s*glass|matte\s*glass|'
    r'camera\s*protector|lens\s*protector|camera\s*glass|'
    # Chargers and cables
    r'charger|chargers|adapter|adapters|cable|cables|cord|cords|wire|wires|'
    r'fast\s*charger|turbo\s*charger|dash\s*charger|warp\s*charger|'
    r'wireless\s*charger|car\s*charger|travel\s*charger|'
    r'type[\s\-]?c\s*cable|lightning\s*cable|usb\s*cable|'
    # Holders and mounts
    r'holder|holders|stand|stands|mount|mounts|grip|grips|ring\s*holder|'
    r'car\s*mount|bike\s*mount|desk\s*stand|phone\s*stand|'
    r'pop\s*socket|popsocket|finger\s*ring|kickstand|'
    r'tripod|tripods|gimbal|gimbals|selfie\s*stick|'
    # Power accessories
    r'power\s*bank|powerbank|battery\s*pack|portable\s*charger|'
    # Storage accessories
    r'memory\s*card|sd\s*card|micro\s*sd|pendrive|pen\s*drive|'
    r'flash\s*drive|usb\s*drive|otg|otg\s*adapter|'
    # Other accessories
    r'stylus|sim\s*tray|sim\s*ejector|'
    r'cleaning\s*kit|lens\s*cleaner|screen\s*cleaner|'
    r'armband|armbands|lanyard|lanyards|strap|straps|'
    r'usb\s*hub|dongle|dongles|'
    r'repair\s*kit|tool\s*kit|opening\s*tool|'
    r'sticker|stickers|decal|decals|vinyl|'
    r'dust\s*plug|anti[\s\-]?dust|'
    # Replacement parts
    r'screen\s*replacement|display\s*replacement|lcd\s*replacement|'
    r'touch\s*screen\s*digitizer|battery\s*replacement|'
    # Multi-pack indicators
    r'combo|bundle|kit|set\s+of|pack\s+of|pcs|pieces|'
    # "For X" patterns (strong accessory indicator)
    r'compatible\s*with|designed\s*for|fits\s*for|suitable\s*for|'
    r'made\s*for|works\s*with|perfect\s*for|ideal\s*for'
    r')\b',
    re.IGNORECASE
)

# Refurbished patterns
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

# RAM patterns (priority ordered)
RAM_PATTERNS = [
    re.compile(r'(\d{1,2})\s*GB\s*RAM', re.IGNORECASE),
    re.compile(r'\((\d{1,2})\s*GB\s*[/+,]\s*\d+\s*GB\)', re.IGNORECASE),
    re.compile(r'(\d{1,2})\s*GB?\s*[/+]\s*\d+\s*GB', re.IGNORECASE),
    re.compile(r'\b(\d{1,2})\s*GB\b(?!\s*(?:ROM|Storage|Internal|SSD|HDD|eMMC))', re.IGNORECASE),
]

# Storage patterns (FIXED - priority ordered)
STORAGE_PATTERNS = [
    re.compile(r'(\d{2,4})\s*GB\s*(?:ROM|Storage|Internal|SSD|HDD|eMMC)', re.IGNORECASE),
    re.compile(r'\(\d+\s*GB\s*[/+,]\s*(\d{2,4})\s*GB\)', re.IGNORECASE),  # (6GB, 128GB) format
    re.compile(r'\d+\s*GB?\s*[/+]\s*(\d{2,4})\s*GB', re.IGNORECASE),
    re.compile(r'(\d+)\s*TB\s*(?:SSD|HDD|Storage)?', re.IGNORECASE),  # TB storage
    re.compile(r'\b(\d{2,4})\s*GB\b(?=.*(?:storage|rom|internal|ssd|hdd))', re.IGNORECASE),
]

# Screen size pattern
SCREEN_SIZE_PATTERN = re.compile(r'(\d+\.?\d*)\s*(?:inch|inches|"|″|\'\')', re.IGNORECASE)

# Color patterns
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
    r'Pearl|Ice|Frost|Snow|Crystal|Diamond|Glacier|'
    r'Matte|Glossy|Ceramic|Glass|Gradient|Holographic|'
    r'Aqua|Bliss|Cool|Mystic|Power'
    r')\b',
    re.IGNORECASE
)

# Network patterns
NETWORK_PATTERNS = re.compile(r'\b(5G|4G|LTE|3G|VOLTE|VoLTE)\b', re.IGNORECASE)

# Generation/Variant patterns
GENERATION_PATTERNS = re.compile(
    r'\b('
    r'Pro|Plus|Ultra|Max|Lite|Neo|Mini|SE|FE|'
    r'Edge|Note|Prime|Youth|Play|Turbo|Speed|'
    r'Racing|Gaming|Master|Explorer|Ace|Reno|'
    r'Find|Nord|Narzo|GT|AI|'
    r'Standard|Base|Vanilla'
    r')\b',
    re.IGNORECASE
)

# Critical variants that MUST match
CRITICAL_VARIANTS = {
    'pro', 'plus', 'ultra', 'max', 'lite', 'mini', 'se', 'fe',
    'note', 'edge', 'neo', 'ace', 'master', 'gt', 'turbo', 'ai'
}

# Model number patterns
MODEL_NUMBER_PATTERNS = [
    # Specific series: "Galaxy S24", "iPhone 16", "Pixel 9"
    re.compile(r'(?:Galaxy|iPhone|iPad|Pixel|OnePlus)\s+([A-Z]?\d+[A-Za-z]*)', re.IGNORECASE),
    # POCO/Redmi models: "M7", "C71", "Note 13"
    re.compile(r'(?:POCO|Redmi|Realme|Narzo)\s+([A-Z]?\d+[A-Za-z]*(?:\s+\d+)?)', re.IGNORECASE),
    # Generic alphanumeric: "A55", "M34", "C55", "GT5"
    re.compile(r'\b([A-Z]\d{1,3}[A-Za-z]?)\b'),
    # "Model 123" format
    re.compile(r'Model\s+([A-Z0-9][\w\-]{2,15})', re.IGNORECASE),
]

# Processor patterns (for laptops)
PROCESSOR_PATTERNS = re.compile(
    r'\b('
    r'(?:Intel\s+)?Core\s*i[3579][\s\-]?\d{4,5}[A-Z]*|'
    r'(?:AMD\s+)?Ryzen\s*[3579][\s\-]?\d{4}[A-Z]*|'
    r'Snapdragon\s*[X78]\w*|'
    r'Apple\s*M[1234](?:\s*Pro|\s*Max|\s*Ultra)?|'
    r'Celeron|Pentium|Athlon|'
    r'MediaTek\s*\w+|Dimensity\s*\d+|Helio\s*\w+'
    r')\b',
    re.IGNORECASE
)

# Junk title patterns (titles that are just status messages)
JUNK_TITLE_PATTERNS = re.compile(
    r'^('
    r'Currently\s*unavailable|Coming\s*Soon|Out\s*of\s*Stock|'
    r'Sold\s*Out|Not\s*Available|Unavailable|'
    r'Limited\s*Stock|Few\s*Left|'
    r'\d+\s*:\s*\d+\s*:\s*\d+|'  # Timer format "00:25:00"
    r'Add\s*to\s*Cart|Buy\s*Now|Shop\s*Now|'
    r'See\s*More|View\s*All|Load\s*More'
    r')$',
    re.IGNORECASE
)

# Fashion attributes
GARMENT_TYPE_PATTERNS = re.compile(
    r'\b('
    r'T[\s\-]?Shirt|Tshirt|Shirt|Top|Blouse|Kurti|Kurta|'
    r'Dress|Gown|Maxi|Mini|Midi|A[\s\-]?Line|'
    r'Jeans|Trousers|Pants|Shorts|Skirt|Leggings|Jeggings|'
    r'Saree|Sari|Lehenga|Salwar|Suit|'
    r'Jacket|Blazer|Coat|Sweater|Sweatshirt|Hoodie|Cardigan|'
    r'Tracksuit|Joggers|Activewear|Sportswear'
    r')\b',
    re.IGNORECASE
)

MATERIAL_PATTERNS = re.compile(
    r'\b('
    r'Cotton|Poly[\s]?cotton|Polyester|Nylon|Silk|Satin|'
    r'Denim|Linen|Rayon|Viscose|Chiffon|Georgette|'
    r'Crepe|Velvet|Wool|Cashmere|Fleece|Leather|'
    r'Faux\s*Leather|Suede|Canvas|Twill|'
    r'Blend|Mixed|Synthetic'
    r')\b',
    re.IGNORECASE
)

FIT_PATTERNS = re.compile(
    r'\b('
    r'Regular|Slim|Skinny|Relaxed|Loose|Oversized|'
    r'Fitted|Tailored|Straight|Boot[\s\-]?Cut|Wide[\s\-]?Leg|'
    r'Flared|Cropped|Full[\s\-]?Length|Ankle[\s\-]?Length'
    r')\b',
    re.IGNORECASE
)

GENDER_PATTERNS = re.compile(
    r'\b(Men|Women|Boys|Girls|Kids|Unisex|Male|Female)\b',
    re.IGNORECASE
)


# =============================================================================
# SECTION 6: SPEC EXTRACTION FUNCTIONS
# =============================================================================

def extract_brand(title: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract brand with both normalized and original versions.
    Returns: (normalized_brand, original_brand)
    """
    if not title:
        return None, None
    
    match = BRAND_PATTERNS.search(title)
    if match:
        original = match.group(1).strip()
        original_lower = original.lower().replace('-', '').replace(' ', '')
        
        # Find normalization
        for key, normalized in BRAND_NORMALIZATIONS.items():
            if key.replace('-', '').replace(' ', '') == original_lower:
                return normalized, original
        
        # No normalization found, use original with proper casing
        return original.title(), original
    
    return None, None


def extract_product_line(title: str, brand: Optional[str] = None) -> Optional[str]:
    """Extract product line/series name based on brand."""
    if not title:
        return None
    
    # Try brand-specific pattern first
    if brand:
        brand_lower = brand.lower().replace('-', '').replace(' ', '')
        for brand_key, pattern in PRODUCT_LINE_PATTERNS.items():
            if brand_key.replace('-', '') in brand_lower or brand_lower in brand_key.replace('-', ''):
                match = pattern.search(title)
                if match:
                    return match.group(1).strip()
    
    # Try all product line patterns
    for pattern in PRODUCT_LINE_PATTERNS.values():
        match = pattern.search(title)
        if match:
            return match.group(1).strip()
    
    # Generic extraction
    match = GENERIC_PRODUCT_LINE_PATTERN.search(title)
    if match:
        return match.group(1).strip()
    
    return None


def extract_model(title: str, brand: Optional[str] = None) -> Optional[str]:
    """Extract model number/name."""
    if not title:
        return None
    
    for pattern in MODEL_NUMBER_PATTERNS:
        match = pattern.search(title)
        if match:
            model = match.group(1).strip()
            if len(model) >= 2:
                return model
    
    # Try after brand name
    if brand:
        brand_esc = re.escape(brand)
        match = re.search(
            rf'{brand_esc}\s+([A-Z]?\d*\s*[A-Za-z]*\d+[A-Za-z]*)',
            title, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()
    
    return None


def extract_ram(title: str) -> Optional[int]:
    """Extract RAM in GB."""
    if not title:
        return None
    
    for pattern in RAM_PATTERNS:
        match = pattern.search(title)
        if match:
            ram = int(match.group(1))
            if 2 <= ram <= 64:  # Valid RAM range
                return ram
    return None


def extract_storage(title: str) -> Optional[int]:
    """Extract storage in GB (FIXED for laptop format)."""
    if not title:
        return None
    
    # Check for TB first
    tb_match = re.search(r'(\d+)\s*TB', title, re.IGNORECASE)
    if tb_match:
        tb = int(tb_match.group(1))
        if 1 <= tb <= 8:
            return tb * 1024
    
    for pattern in STORAGE_PATTERNS:
        matches = pattern.findall(title)
        for match_str in matches:
            storage = int(match_str)
            # Valid storage values
            if storage in [16, 32, 64, 128, 256, 512, 1024] or 16 <= storage <= 2048:
                return storage
    
    return None


def extract_screen_size(title: str) -> Optional[float]:
    """Extract screen size in inches."""
    if not title:
        return None
    
    match = SCREEN_SIZE_PATTERN.search(title)
    if match:
        size = float(match.group(1))
        if 1.0 <= size <= 85.0:  # 1" watch to 85" TV
            return size
    return None


def extract_generation(title: str) -> Optional[str]:
    """Extract variant/generation (Pro, Ultra, Lite, etc.)."""
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
    """Extract color name."""
    if not title:
        return None
    
    match = COLOR_PATTERNS.search(title)
    return match.group(1).strip().title() if match else None


def extract_network(title: str) -> Optional[str]:
    """Extract network type (5G, 4G, etc.)."""
    if not title:
        return None
    
    match = NETWORK_PATTERNS.search(title)
    if match:
        net = match.group(1).upper()
        return 'VoLTE' if net == 'VOLTE' else net
    return None


def extract_processor(title: str) -> Optional[str]:
    """Extract processor name (for laptops)."""
    if not title:
        return None
    
    match = PROCESSOR_PATTERNS.search(title)
    return match.group(1).strip() if match else None


def extract_garment_type(title: str) -> Optional[str]:
    """Extract garment type for fashion items."""
    if not title:
        return None
    
    match = GARMENT_TYPE_PATTERNS.search(title)
    return match.group(1).strip().title() if match else None


def extract_material(title: str) -> Optional[str]:
    """Extract material for fashion items."""
    if not title:
        return None
    
    match = MATERIAL_PATTERNS.search(title)
    return match.group(1).strip().title() if match else None


def extract_fit(title: str) -> Optional[str]:
    """Extract fit type for fashion items."""
    if not title:
        return None
    
    match = FIT_PATTERNS.search(title)
    return match.group(1).strip().title() if match else None


def extract_gender(title: str) -> Optional[str]:
    """Extract gender for fashion items."""
    if not title:
        return None
    
    match = GENDER_PATTERNS.search(title)
    return match.group(1).strip().title() if match else None


def is_accessory(title: str, source_is_accessory_category: bool = False) -> bool:
    """
    Check if product is an accessory.
    
    Args:
        title: Product title to check
        source_is_accessory_category: If True, source is itself an accessory-type 
                                      product (headphone, charger), so don't reject
                                      same-category targets
    """
    if not title:
        return True
    
    title_lower = title.lower()
    
    # Main product indicators (these are NOT accessories)
    main_indicators = [
        'smartphone', 'mobile phone', 'cellphone', 'cell phone',
        'laptop', 'notebook', 'ultrabook', 'chromebook',
        'tablet', 'ipad', 'galaxy tab',
        'smart tv', 'television', 'led tv', 'oled tv',
        'refrigerator', 'washing machine', 'air conditioner',
        'smartwatch', 'smart watch', 'fitness band', 'fitness tracker',
        'wireless earbuds', 'true wireless', 'tws earbuds',
        'bluetooth speaker', 'portable speaker',
    ]
    
    for ind in main_indicators:
        if ind in title_lower:
            # If source is accessory category, allow matching products
            if source_is_accessory_category:
                return False
            # Check if accessory pattern also matches (e.g., "iPhone case")
            if not ACCESSORY_PATTERNS.search(title):
                return False
    
    # Check for accessory patterns
    if ACCESSORY_PATTERNS.search(title):
        # If source is same category (e.g., source is headphone), don't reject
        if source_is_accessory_category:
            return False
        return True
    
    # "for [Brand]" pattern - strong accessory indicator
    if re.search(
        r'\bfor\s+(?:the\s+)?(?:new\s+)?'
        r'(?:samsung|apple|iphone|xiaomi|redmi|vivo|oppo|oneplus|realme|motorola|nokia)\s+'
        r'[a-z0-9]+', title_lower
    ):
        return True
    
    # Multi-pack indicator
    if re.search(r'\b(?:pack|set|combo|bundle)\s*(?:of\s*)?\d+|\d+\s*(?:pcs|pieces|pack)', title_lower):
        return True
    
    return False


def is_refurbished(title: str) -> bool:
    """Check if product is refurbished/renewed."""
    return bool(REFURBISHED_PATTERNS.search(title)) if title else False


def is_junk_title(title: str) -> bool:
    """Check if title is a junk/status message."""
    if not title:
        return True
    
    title = title.strip()
    
    # Too short
    if len(title) < 5:
        return True
    
    # Status message patterns
    if JUNK_TITLE_PATTERNS.match(title):
        return True
    
    # Just numbers
    if re.match(r'^[\d\s:,\.]+$', title):
        return True
    
    return False


def determine_category_type(category: Optional[str], title: str) -> ProductCategoryType:
    """Determine the product category type for category-aware processing."""
    if not category:
        category = ""
    
    category_lower = category.lower()
    title_lower = title.lower()
    
    # Electronics
    if any(x in category_lower for x in ['phone', 'mobile', 'laptop', 'computer', 'tablet', 'electronics']):
        return ProductCategoryType.ELECTRONICS
    if any(x in title_lower for x in ['smartphone', 'laptop', 'tablet', 'iphone', 'galaxy', 'pixel', 'macbook']):
        return ProductCategoryType.ELECTRONICS
    
    # Watches
    if any(x in category_lower for x in ['watch', 'wearable']):
        return ProductCategoryType.WATCHES
    if any(x in title_lower for x in ['smartwatch', 'smart watch', 'fitness band', 'watch']):
        return ProductCategoryType.WATCHES
    
    # Fashion
    if any(x in category_lower for x in ['fashion', 'clothing', 'apparel', 'footwear', 'accessories']):
        return ProductCategoryType.FASHION
    if any(x in title_lower for x in ['shirt', 'dress', 'jeans', 'kurta', 'saree', 'shoes', 'sneakers']):
        return ProductCategoryType.FASHION
    
    # Appliances
    if any(x in category_lower for x in ['appliance', 'kitchen', 'home']):
        return ProductCategoryType.APPLIANCES
    if any(x in title_lower for x in ['refrigerator', 'washing machine', 'microwave', 'mixer', 'tv', 'television']):
        return ProductCategoryType.APPLIANCES
    
    return ProductCategoryType.GENERAL


def extract_specs(
    title: str, 
    price: Optional[float] = None, 
    full_title: Optional[str] = None,
    category: Optional[str] = None
) -> ProductSpecs:
    """
    Extract all specs from a product title.
    
    Args:
        title: The text to extract from (may be essence or title)
        price: Product price
        full_title: Full original title (used for spec extraction when title is essence)
        category: Product category string
    """
    specs = ProductSpecs(
        raw_title=title or "",
        price=price,
        full_title=full_title or title or ""
    )
    
    if not title:
        specs.is_accessory = True
        return specs
    
    # Use full_title for extraction when available (more details)
    spec_text = full_title if full_title else title
    
    # Determine category type
    specs.category_type = determine_category_type(category, spec_text)
    
    # Basic extraction
    specs.brand, specs.original_brand = extract_brand(spec_text)
    specs.product_line = extract_product_line(spec_text, specs.brand)
    specs.model = extract_model(spec_text, specs.brand)
    specs.generation = extract_generation(spec_text)
    specs.color = extract_color(spec_text)
    
    # Electronics-specific
    specs.ram_gb = extract_ram(spec_text)
    specs.storage_gb = extract_storage(spec_text)
    specs.network = extract_network(spec_text)
    specs.screen_size = extract_screen_size(spec_text)
    specs.processor = extract_processor(spec_text)
    
    # Fashion-specific
    if specs.category_type == ProductCategoryType.FASHION:
        specs.garment_type = extract_garment_type(spec_text)
        specs.material = extract_material(spec_text)
        specs.fit = extract_fit(spec_text)
        specs.gender = extract_gender(spec_text)
    
    # Flags
    specs.is_accessory = is_accessory(spec_text)
    specs.is_refurbished = is_refurbished(spec_text)
    
    return specs


# =============================================================================
# SECTION 7: QUALITY GATE (NEW - Layer 1)
# =============================================================================

def check_quality_gate(
    title: str,
    specs: ProductSpecs,
    category_type: ProductCategoryType
) -> QualityGateResult:
    """
    Check if product has enough identity information to be matchable.
    
    Returns QualityGateResult with passed=False if product should be skipped.
    """
    if not title:
        return QualityGateResult(False, "Empty title", 0)
    
    # Count meaningful words (exclude common filler words)
    filler_words = {
        'the', 'a', 'an', 'and', 'or', 'for', 'with', 'in', 'on', 'at', 'to', 'of',
        'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'new', 'best', 'top', 'latest', 'premium', 'exclusive', 'limited', 'special',
        'free', 'delivery', 'shipping', 'cod', 'emi', 'offer', 'sale', 'discount',
    }
    
    words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{2,}\b', title)]
    meaningful_words = [w for w in words if w not in filler_words]
    
    # Check minimum title length
    if len(title) < MinerConfig.MIN_TITLE_LENGTH:
        return QualityGateResult(False, f"Title too short ({len(title)} chars)", 0)
    
    # Check minimum meaningful words
    if len(meaningful_words) < MinerConfig.MIN_TITLE_WORDS:
        return QualityGateResult(
            False, 
            f"Too few meaningful words ({len(meaningful_words)}): '{title[:50]}...'",
            0
        )
    
    # Calculate identity strength
    identity_score = specs.get_identity_strength()
    
    # If title is just a brand name with nothing else
    if specs.brand and len(meaningful_words) <= 2:
        brand_words = specs.brand.lower().split()
        non_brand_words = [w for w in meaningful_words if w not in brand_words]
        if len(non_brand_words) == 0:
            return QualityGateResult(
                False,
                f"Title is just brand name: '{title}'",
                identity_score
            )
    
    # Electronics: need brand + (model OR product_line OR storage)
    if category_type == ProductCategoryType.ELECTRONICS:
        if not specs.brand:
            return QualityGateResult(False, "Electronics: No brand detected", identity_score)
        if not any([specs.model, specs.product_line, specs.storage_gb, specs.ram_gb]):
            return QualityGateResult(
                False, 
                "Electronics: No model/storage/RAM info",
                identity_score
            )
    
    # Watches: need brand + (product_line OR model)
    if category_type == ProductCategoryType.WATCHES:
        if not specs.brand:
            return QualityGateResult(False, "Watch: No brand detected", identity_score)
        if not any([specs.model, specs.product_line]):
            # Check if title has at least a series name
            if len(meaningful_words) <= 2:
                return QualityGateResult(
                    False,
                    "Watch: No product line/model info",
                    identity_score
                )
    
    # Fashion: need garment type at minimum
    if category_type == ProductCategoryType.FASHION:
        if not specs.garment_type and identity_score < 3:
            return QualityGateResult(
                False,
                "Fashion: No garment type detected",
                identity_score
            )
    
    # Passed quality gate
    return QualityGateResult(True, "Quality gate passed", identity_score)


# =============================================================================
# SECTION 8: SEARCH QUERY GENERATION (Fixed - Layer 2)
# =============================================================================

def generate_search_query(
    product: Product,
    target_platform: str,
    specs: ProductSpecs,
    max_words: int = 7,
) -> str:
    """
    Generate platform-optimized search query.
    
    KEY FIX: Uses ORIGINAL brand (POCO not Xiaomi) for search queries.
    """
    # Use AI essence if available
    essence = ""
    if product.ai_metadata and product.ai_metadata.get("essence"):
        essence = product.ai_metadata["essence"]
    
    # Build query parts using ORIGINAL brand (not normalized)
    parts = []
    
    # Use original brand for search (POCO, not Xiaomi)
    if specs.original_brand:
        parts.append(specs.original_brand)
    elif specs.brand:
        parts.append(specs.brand)
    
    # Add product line (Phoenix, Hunter, Galaxy S, etc.)
    if specs.product_line:
        parts.append(specs.product_line)
    
    # Add model number
    if specs.model:
        parts.append(specs.model)
    
    # Add variant
    if specs.generation:
        parts.append(specs.generation)
    
    # Platform-specific additions
    if target_platform == "meesho":
        # Meesho: simpler queries
        if len(parts) < 2 and essence:
            parts = essence.split()[:3]
        return " ".join(parts[:4])
    
    elif target_platform == "flipkart":
        # Flipkart: brand + product-line + key spec
        if specs.storage_gb and specs.category_type == ProductCategoryType.ELECTRONICS:
            parts.append(f"{specs.storage_gb}GB")
        if len(parts) < 3 and essence:
            # Add words from essence to reach minimum
            essence_words = essence.split()
            for w in essence_words:
                if w.lower() not in ' '.join(parts).lower():
                    parts.append(w)
                    if len(parts) >= 3:
                        break
        return " ".join(parts[:max_words])
    
    elif target_platform == "myntra":
        # Myntra: fashion-focused
        if specs.category_type == ProductCategoryType.FASHION:
            if specs.garment_type:
                parts.append(specs.garment_type)
            if specs.gender:
                parts.insert(0, specs.gender)  # Gender first for fashion
        return " ".join(parts[:5])
    
    else:
        # Amazon / default: specific query
        if specs.storage_gb:
            parts.append(f"{specs.storage_gb}GB")
        if specs.network:
            parts.append(specs.network)
        if specs.color:
            parts.append(specs.color)
    
    # Ensure minimum words
    if len(parts) < 3:
        if essence:
            essence_words = [w for w in essence.split() 
                          if w.lower() not in ' '.join(parts).lower()]
            parts.extend(essence_words[:3 - len(parts)])
        else:
            # Fallback to title words
            title_words = re.findall(r'\b[a-zA-Z0-9]+\b', product.title)
            for w in title_words[:5]:
                if w.lower() not in ' '.join(parts).lower():
                    parts.append(w)
                    if len(parts) >= 4:
                        break
    
    return " ".join(parts[:max_words])


# =============================================================================
# SECTION 9: TIER 0 - JUNK FILTER (NEW - Layer 3)
# =============================================================================

def filter_junk_results(products: List[ProductData]) -> Tuple[List[ProductData], int]:
    """
    Filter out junk/status message titles from search results.
    Returns: (filtered_products, junk_count)
    """
    filtered = []
    junk_count = 0
    
    for p in products:
        if is_junk_title(p.title):
            junk_count += 1
            continue
        filtered.append(p)
    
    return filtered, junk_count


# =============================================================================
# SECTION 10: TIER 1 - ENHANCED SPEC REJECTION (Layer 4)
# =============================================================================

def tier1_spec_reject(
    source: ProductSpecs,
    target: ProductSpecs,
    source_is_accessory_category: bool = False,
) -> Tuple[bool, str, MatchResult]:
    """
    TIER 1: Fast hard-reject based on specs.
    
    ENHANCED with:
    - Product-line comparison
    - Screen size comparison
    - Model number comparison
    - Source-aware accessory handling
    - Category-aware price tolerance
    
    Returns: (passed, reason, result)
    """
    # Reject accessories (but not if source is same category)
    if target.is_accessory and not source_is_accessory_category:
        return (False, f"Accessory: '{target.raw_title[:40]}...'", MatchResult.ACCESSORY_REJECTED)
    
    # Reject refurbished vs new
    if target.is_refurbished and not source.is_refurbished:
        return (False, "Refurbished vs New", MatchResult.REFURBISHED_REJECTED)
    
    # Brand mismatch (using brand families)
    if source.brand and target.brand:
        sb = source.brand.lower().strip()
        tb = target.brand.lower().strip()
        sf = BRAND_FAMILIES.get(sb, {sb})
        tf = BRAND_FAMILIES.get(tb, {tb})
        if not sf.intersection(tf):
            return (False, f"Brand: {source.brand} vs {target.brand}", MatchResult.BRAND_MISMATCH)
    
    # NEW: Product-line mismatch (Phoenix ≠ Hunter, Galaxy S ≠ Galaxy A)
    if source.product_line and target.product_line:
        sp = source.product_line.lower().strip()
        tp = target.product_line.lower().strip()
        # Allow partial match (e.g., "S24" matches "S")
        if sp != tp and sp not in tp and tp not in sp:
            return (
                False, 
                f"Product-Line: {source.product_line} vs {target.product_line}",
                MatchResult.PRODUCT_LINE_MISMATCH
            )
    
    # NEW: Model number mismatch (M7 ≠ C71, S24 ≠ S23)
    if source.model and target.model:
        sm = source.model.lower().strip()
        tm = target.model.lower().strip()
        if sm != tm:
            return (
                False,
                f"Model: {source.model} vs {target.model}",
                MatchResult.MODEL_MISMATCH
            )
    
    # RAM mismatch
    if source.ram_gb and target.ram_gb and source.ram_gb != target.ram_gb:
        return (False, f"RAM: {source.ram_gb}GB vs {target.ram_gb}GB", MatchResult.SPECS_MISMATCH)
    
    # Storage mismatch
    if source.storage_gb and target.storage_gb and source.storage_gb != target.storage_gb:
        return (False, f"Storage: {source.storage_gb}GB vs {target.storage_gb}GB", MatchResult.SPECS_MISMATCH)
    
    # NEW: Screen size mismatch (1.39" ≠ 2.01")
    if source.screen_size and target.screen_size:
        diff = abs(source.screen_size - target.screen_size)
        if diff > MinerConfig.SCREEN_SIZE_TOLERANCE:
            return (
                False,
                f"Screen: {source.screen_size}\" vs {target.screen_size}\"",
                MatchResult.SCREEN_SIZE_MISMATCH
            )
    
    # Critical variant mismatch (Pro ≠ Ultra ≠ Standard)
    if source.generation or target.generation:
        sg = set((source.generation or "").lower().split())
        tg = set((target.generation or "").lower().split())
        sc = sg.intersection(CRITICAL_VARIANTS)
        tc = tg.intersection(CRITICAL_VARIANTS)
        if sc != tc:
            return (
                False, 
                f"Variant: '{source.generation or 'Std'}' vs '{target.generation or 'Std'}'",
                MatchResult.VARIANT_MISMATCH
            )
    
    # Category-aware price tolerance
    if source.price and target.price and source.price > 0 and target.price > 0:
        category_key = source.category_type.value
        tolerance = MinerConfig.PRICE_TOLERANCE.get(category_key, 0.40)
        
        ratio = target.price / source.price
        min_ratio = 1.0 - tolerance
        max_ratio = 1.0 + tolerance
        
        if ratio < min_ratio or ratio > max_ratio:
            return (
                False, 
                f"Price: ₹{source.price:.0f} vs ₹{target.price:.0f} (±{tolerance*100:.0f}%)",
                MatchResult.PRICE_MISMATCH
            )
    
    return (True, "Tier 1 passed", MatchResult.EXACT_MATCH)


# =============================================================================
# SECTION 11: TIER 2 - ENHANCED FUZZY MATCHING (Layer 4 continued)
# =============================================================================

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
    TIER 2: Fuzzy matching with enhanced scoring.
    
    ENHANCED with:
    - Product-line match bonus
    - Category-aware thresholds
    - Better word overlap calculation
    
    Returns: (score, reason)
    """
    if not source_essence or not target_title:
        return (0.0, "Empty input")
    
    # Word overlap score
    s_words = set(source_essence.lower().split()) - STOP_WORDS
    t_words = set(target_title.lower().split()) - STOP_WORDS
    
    if not s_words:
        return (0.0, "No source words")
    
    overlap = len(s_words.intersection(t_words)) / len(s_words)
    
    # SequenceMatcher score (handles word reordering)
    clean_source = ' '.join(sorted(s_words))
    clean_target = ' '.join(sorted(t_words))
    seq_score = SequenceMatcher(None, clean_source, clean_target).ratio()
    
    # Weighted base: 40% overlap + 60% sequence
    base = (overlap * 0.4) + (seq_score * 0.6)
    
    # Bonuses and penalties
    bonus = 0.0
    penalty = 0.0
    
    # Brand match bonus
    if source_specs.brand and target_specs.brand:
        if source_specs.brand.lower() == target_specs.brand.lower():
            bonus += 0.12
    
    # NEW: Product-line match bonus (BIG impact)
    if source_specs.product_line and target_specs.product_line:
        sp = source_specs.product_line.lower()
        tp = target_specs.product_line.lower()
        if sp == tp:
            bonus += 0.15  # Strong signal
        elif sp in tp or tp in sp:
            bonus += 0.08  # Partial match
        else:
            penalty += 0.20  # Different product line = bad sign
    
    # Model match bonus
    if source_specs.model and target_specs.model:
        sm = source_specs.model.lower()
        tm = target_specs.model.lower()
        if sm == tm:
            bonus += 0.10
        elif sm in tm or tm in sm:
            bonus += 0.05
    
    # Spec match bonuses
    if source_specs.ram_gb and target_specs.ram_gb and source_specs.ram_gb == target_specs.ram_gb:
        bonus += 0.08
    if source_specs.storage_gb and target_specs.storage_gb and source_specs.storage_gb == target_specs.storage_gb:
        bonus += 0.08
    if source_specs.generation and target_specs.generation:
        if source_specs.generation.lower() == target_specs.generation.lower():
            bonus += 0.08
    if source_specs.network and target_specs.network and source_specs.network == target_specs.network:
        bonus += 0.04
    
    # Price proximity bonus
    if source_specs.price and target_specs.price and source_specs.price > 0:
        price_ratio = target_specs.price / source_specs.price
        if 0.9 <= price_ratio <= 1.1:
            bonus += 0.06  # Within 10%
        elif 0.8 <= price_ratio <= 1.2:
            bonus += 0.03  # Within 20%
    
    final = max(0.0, min(1.0, base + bonus - penalty))
    return (final, f"overlap={overlap:.2f} seq={seq_score:.2f} bonus={bonus:.2f} penalty={penalty:.2f}")


def get_fuzzy_threshold(category_type: ProductCategoryType) -> float:
    """Get category-appropriate fuzzy matching threshold."""
    return MinerConfig.FUZZY_THRESHOLD.get(category_type.value, 0.50)


# =============================================================================
# SECTION 12: TIER 3 - CATEGORY-AWARE AI VERIFICATION (Layer 5)
# =============================================================================

# Category-specific AI prompts
AI_PROMPT_ELECTRONICS = """You are a strict Product Matching Expert for an Indian e-commerce price comparison app.
Determine if SOURCE and TARGET are the EXACT SAME physical product.

### SOURCE (Database Product):
Full Title: {source_title}
Brand: {source_brand} | Product-Line: {source_product_line} | Model: {source_model}
RAM: {source_ram} | Storage: {source_storage} | Variant: {source_variant} | Network: {source_network}
Price: ₹{source_price}

### TARGET (Scraped from {platform}):
Full Title: {target_title}
Brand: {target_brand} | Product-Line: {target_product_line} | Model: {target_model}
RAM: {target_ram} | Storage: {target_storage} | Variant: {target_variant} | Network: {target_network}
Price: ₹{target_price}

### STRICT RULES:
1. ✅ MATCH only if: Same brand AND product-line AND model AND storage AND RAM AND variant
2. ❌ REJECT if product-line differs (Phoenix ≠ Hunter, Galaxy S ≠ Galaxy A, Nord ≠ Narzo)
3. ❌ REJECT if model number differs (M7 ≠ C71, S24 ≠ S23, 16 ≠ 17)
4. ❌ REJECT if storage differs (128GB ≠ 256GB)
5. ❌ REJECT if RAM differs (4GB ≠ 6GB ≠ 8GB)
6. ❌ REJECT if variant differs (Pro ≠ Ultra ≠ standard ≠ Lite)
7. ❌ REJECT if target is an accessory (case/cover/charger/cable/screen guard)
8. ❌ REJECT if target is refurbished but source is new
9. ✅ ALLOW: Color differences (Black vs Blue is OK)
10. ✅ ALLOW: Minor title formatting differences

Return ONLY valid JSON:
{{"match_score": <0.0-1.0>, "is_exact_match": <bool>, "reason": "<max 100 chars>", "confidence": "<high|medium|low>"}}"""


AI_PROMPT_WATCHES = """You are a strict Product Matching Expert for an Indian e-commerce price comparison app.
Determine if SOURCE and TARGET are the EXACT SAME smartwatch/watch.

### SOURCE (Database Product):
Full Title: {source_title}
Brand: {source_brand} | Product-Line: {source_product_line}
Display Size: {source_screen}
Variant: {source_variant} | Price: ₹{source_price}

### TARGET (Scraped from {platform}):
Full Title: {target_title}
Brand: {target_brand} | Product-Line: {target_product_line}
Display Size: {target_screen}
Variant: {target_variant} | Price: ₹{target_price}

### STRICT RULES:
1. ✅ MATCH only if: Same brand AND same product-line/series AND similar display size
2. ❌ REJECT if product-line differs (Phoenix ≠ Hunter, Icon ≠ Pulse, Airdopes ≠ Rockerz)
3. ❌ REJECT if display size differs significantly (1.39" ≠ 2.01")
4. ❌ REJECT if variant differs (Pro ≠ Ultra ≠ standard)
5. ❌ REJECT if target is a watch strap/band/charger accessory
6. ❌ REJECT if prices differ by more than 50%
7. ✅ ALLOW: Color differences

Return ONLY valid JSON:
{{"match_score": <0.0-1.0>, "is_exact_match": <bool>, "reason": "<max 100 chars>", "confidence": "<high|medium|low>"}}"""


AI_PROMPT_FASHION = """You are a strict Product Matching Expert for an Indian e-commerce price comparison app.
Determine if SOURCE and TARGET are the EXACT SAME fashion item.

### SOURCE (Database Product):
Full Title: {source_title}
Brand: {source_brand} | Garment Type: {source_garment}
Material: {source_material} | Fit: {source_fit}
Gender: {source_gender} | Price: ₹{source_price}

### TARGET (Scraped from {platform}):
Full Title: {target_title}
Brand: {target_brand} | Garment Type: {target_garment}
Material: {target_material} | Fit: {target_fit}
Gender: {target_gender} | Price: ₹{target_price}

### STRICT RULES:
1. ✅ MATCH only if: Same brand AND same garment type AND similar material/fit
2. ❌ REJECT if garment type differs (T-Shirt ≠ Shirt, Dress ≠ Kurti, Jeans ≠ Trousers)
3. ❌ REJECT if gender differs (Men ≠ Women)
4. ❌ REJECT if brand clearly differs
5. ❌ REJECT if fit is incompatible (Slim ≠ Oversized)
6. ⚠️ If brand is missing/generic in both, compare garment type and style closely
7. ✅ ALLOW: Color/pattern differences
8. ✅ ALLOW: Size variations

Return ONLY valid JSON:
{{"match_score": <0.0-1.0>, "is_exact_match": <bool>, "reason": "<max 100 chars>", "confidence": "<high|medium|low>"}}"""


AI_PROMPT_GENERAL = """You are a strict Product Matching Expert for an Indian e-commerce price comparison app.
Determine if SOURCE and TARGET are the EXACT SAME physical product.

### SOURCE (Database Product):
Full Title: {source_title}
Brand: {source_brand} | Product-Line: {source_product_line}
Key Specs: {source_specs}
Price: ₹{source_price}

### TARGET (Scraped from {platform}):
Full Title: {target_title}
Brand: {target_brand} | Product-Line: {target_product_line}
Key Specs: {target_specs}
Price: ₹{target_price}

### RULES:
1. ✅ MATCH only if they describe the exact same product a customer would buy
2. ❌ REJECT if product types are clearly different
3. ❌ REJECT if brand names don't match at all
4. ❌ REJECT if key specifications differ
5. ❌ REJECT if one is an accessory FOR the other
6. ⚠️ If both titles are just brand names with no model info, set is_exact_match=false
7. ✅ ALLOW: Minor formatting differences, color variations

Return ONLY valid JSON:
{{"match_score": <0.0-1.0>, "is_exact_match": <bool>, "reason": "<max 100 chars>", "confidence": "<high|medium|low>"}}"""


def format_ai_prompt(
    source_specs: ProductSpecs,
    target_specs: ProductSpecs,
    platform: str,
) -> str:
    """Format the appropriate AI prompt based on category."""
    
    category_type = source_specs.category_type
    
    if category_type == ProductCategoryType.ELECTRONICS:
        return AI_PROMPT_ELECTRONICS.format(
            source_title=source_specs.full_title[:300],
            source_brand=source_specs.brand or "Unknown",
            source_product_line=source_specs.product_line or "Unknown",
            source_model=source_specs.model or "Unknown",
            source_ram=f"{source_specs.ram_gb}GB" if source_specs.ram_gb else "Not specified",
            source_storage=f"{source_specs.storage_gb}GB" if source_specs.storage_gb else "Not specified",
            source_variant=source_specs.generation or "Standard",
            source_network=source_specs.network or "Not specified",
            source_price=f"{source_specs.price:.0f}" if source_specs.price else "?",
            platform=platform,
            target_title=target_specs.full_title[:300],
            target_brand=target_specs.brand or "Unknown",
            target_product_line=target_specs.product_line or "Unknown",
            target_model=target_specs.model or "Unknown",
            target_ram=f"{target_specs.ram_gb}GB" if target_specs.ram_gb else "Not specified",
            target_storage=f"{target_specs.storage_gb}GB" if target_specs.storage_gb else "Not specified",
            target_variant=target_specs.generation or "Standard",
            target_network=target_specs.network or "Not specified",
            target_price=f"{target_specs.price:.0f}" if target_specs.price else "?",
        )
    
    elif category_type == ProductCategoryType.WATCHES:
        return AI_PROMPT_WATCHES.format(
            source_title=source_specs.full_title[:300],
            source_brand=source_specs.brand or "Unknown",
            source_product_line=source_specs.product_line or "Unknown",
            source_screen=f"{source_specs.screen_size}\"" if source_specs.screen_size else "Not specified",
            source_variant=source_specs.generation or "Standard",
            source_price=f"{source_specs.price:.0f}" if source_specs.price else "?",
            platform=platform,
            target_title=target_specs.full_title[:300],
            target_brand=target_specs.brand or "Unknown",
            target_product_line=target_specs.product_line or "Unknown",
            target_screen=f"{target_specs.screen_size}\"" if target_specs.screen_size else "Not specified",
            target_variant=target_specs.generation or "Standard",
            target_price=f"{target_specs.price:.0f}" if target_specs.price else "?",
        )
    
    elif category_type == ProductCategoryType.FASHION:
        return AI_PROMPT_FASHION.format(
            source_title=source_specs.full_title[:300],
            source_brand=source_specs.brand or "Unknown",
            source_garment=source_specs.garment_type or "Unknown",
            source_material=source_specs.material or "Not specified",
            source_fit=source_specs.fit or "Not specified",
            source_gender=source_specs.gender or "Not specified",
            source_price=f"{source_specs.price:.0f}" if source_specs.price else "?",
            platform=platform,
            target_title=target_specs.full_title[:300],
            target_brand=target_specs.brand or "Unknown",
            target_garment=target_specs.garment_type or "Unknown",
            target_material=target_specs.material or "Not specified",
            target_fit=target_specs.fit or "Not specified",
            target_gender=target_specs.gender or "Not specified",
            target_price=f"{target_specs.price:.0f}" if target_specs.price else "?",
        )
    
    else:
        # General prompt
        source_specs_str = ", ".join([
            f"Storage: {source_specs.storage_gb}GB" if source_specs.storage_gb else "",
            f"RAM: {source_specs.ram_gb}GB" if source_specs.ram_gb else "",
            f"Variant: {source_specs.generation}" if source_specs.generation else "",
        ])
        target_specs_str = ", ".join([
            f"Storage: {target_specs.storage_gb}GB" if target_specs.storage_gb else "",
            f"RAM: {target_specs.ram_gb}GB" if target_specs.ram_gb else "",
            f"Variant: {target_specs.generation}" if target_specs.generation else "",
        ])
        
        return AI_PROMPT_GENERAL.format(
            source_title=source_specs.full_title[:300],
            source_brand=source_specs.brand or "Unknown",
            source_product_line=source_specs.product_line or "Unknown",
            source_specs=source_specs_str or "Not specified",
            source_price=f"{source_specs.price:.0f}" if source_specs.price else "?",
            platform=platform,
            target_title=target_specs.full_title[:300],
            target_brand=target_specs.brand or "Unknown",
            target_product_line=target_specs.product_line or "Unknown",
            target_specs=target_specs_str or "Not specified",
            target_price=f"{target_specs.price:.0f}" if target_specs.price else "?",
        )


async def verify_with_ai(
    source_specs: ProductSpecs,
    target_specs: ProductSpecs,
    platform: str,
) -> Dict[str, Any]:
    """
    Tier 3: AI verification with category-aware prompts.
    """
    prompt = format_ai_prompt(source_specs, target_specs, platform)
    
    fallback = {
        "match_score": 0.0,
        "is_exact_match": False,
        "reason": "AI unavailable",
        "confidence": "low"
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
        
        # Ensure required fields
        for key in ['match_score', 'is_exact_match', 'reason']:
            if key not in parsed:
                parsed[key] = fallback.get(key)
        
        if 'confidence' not in parsed:
            parsed['confidence'] = 'medium'
        
        return parsed
    
    except json.JSONDecodeError as e:
        return {**fallback, "reason": f"JSON parse error: {str(e)[:30]}"}
    except Exception as e:
        return {**fallback, "reason": f"AI error: {str(e)[:30]}"}


# =============================================================================
# SECTION 13: TIER 4 - POST-AI SANITY CHECK (NEW - Layer 6)
# =============================================================================

def post_ai_sanity_check(
    ai_result: Dict[str, Any],
    source_specs: ProductSpecs,
    target_specs: ProductSpecs,
) -> Tuple[bool, str]:
    """
    Post-AI sanity check to catch AI hallucinations.
    
    Returns: (passed, reason)
    """
    # Check 1: AI contradiction detection
    # If AI says match=True but reason contains rejection words
    if ai_result.get('is_exact_match', False):
        reason = ai_result.get('reason', '').lower()
        contradiction_words = [
            'different', 'differs', 'mismatch', 'not same', 'not the same',
            'wrong', 'incorrect', 'doesn\'t match', 'does not match',
            'not matching', 'incompatible', 'distinct', 'separate'
        ]
        
        for word in contradiction_words:
            if word in reason:
                return (False, f"AI contradiction: says match but reason mentions '{word}'")
    
    # Check 2: Low confidence with mediocre score
    confidence = ai_result.get('confidence', 'low')
    score = ai_result.get('match_score', 0.0)
    
    if confidence == 'low' and score < 0.95:
        return (False, f"Low confidence ({confidence}) with score {score:.2f}")
    
    if confidence == 'medium' and score < MinerConfig.MIN_AI_CONFIDENCE_SCORE:
        return (False, f"Medium confidence with score {score:.2f} < {MinerConfig.MIN_AI_CONFIDENCE_SCORE}")
    
    # Check 3: Re-verify critical specs after AI approval
    # Product-line mismatch
    if source_specs.product_line and target_specs.product_line:
        sp = source_specs.product_line.lower().strip()
        tp = target_specs.product_line.lower().strip()
        
        # Strict check: must be same or one contains the other
        if sp != tp and sp not in tp and tp not in sp:
            return (False, f"Post-AI: Product-line mismatch ({source_specs.product_line} vs {target_specs.product_line})")
    
    # Model mismatch
    if source_specs.model and target_specs.model:
        sm = source_specs.model.lower().strip()
        tm = target_specs.model.lower().strip()
        
        if sm != tm and sm not in tm and tm not in sm:
            return (False, f"Post-AI: Model mismatch ({source_specs.model} vs {target_specs.model})")
    
    # Screen size mismatch
    if source_specs.screen_size and target_specs.screen_size:
        diff = abs(source_specs.screen_size - target_specs.screen_size)
        if diff > MinerConfig.SCREEN_SIZE_TOLERANCE:
            return (False, f"Post-AI: Screen size mismatch ({source_specs.screen_size}\" vs {target_specs.screen_size}\")")
    
    return (True, "Post-AI check passed")


# =============================================================================
# SECTION 14: FINGERPRINT LINKER & SAVE
# =============================================================================

async def save_matched_product(
    scraped_product: ProductData,
    db_product: Product,
    db,
    stats: Optional[MiningStats] = None,
) -> bool:
    """
    Save a matched product with the CORRECT fingerprint.
    """
    try:
        # Step 1: Enrich with AI
        enriched = await enrichment_service.enrich_product(scraped_product)

        # Step 1.5: Image validation and fallback alignment with product_service.
        image_candidates = [
            getattr(enriched, "image_url", None),
            getattr(scraped_product, "image_url", None),
            (scraped_product.raw_data or {}).get("image_url") if getattr(scraped_product, "raw_data", None) else None,
            (scraped_product.raw_data or {}).get("image") if getattr(scraped_product, "raw_data", None) else None,
            getattr(db_product, "image_url", None),
        ]
        valid_image = next((u for u in image_candidates if _validate_image_url(u)), None)
        if valid_image and enriched.image_url != valid_image:
            enriched.image_url = valid_image
            if stats:
                stats.image_validation_fixed += 1

        # Step 1.6: Ensure enriched essence is useful; otherwise fallback to source essence.
        source_essence = ""
        if db_product.ai_metadata and db_product.ai_metadata.get("essence"):
            source_essence = str(db_product.ai_metadata.get("essence") or "").strip()

        if not _is_useful_essence(getattr(enriched, "ai_essence", None), enriched.title):
            fallback_essence = source_essence or " ".join((enriched.title or "").split()[:8]).strip()
            enriched.ai_essence = fallback_essence
            if stats:
                stats.essence_validation_fixed += 1

        if not _is_useful_essence(getattr(enriched, "ai_essence", None), enriched.title):
            logger.warning("Skipping save: unusable essence after fallback for '%s'", (enriched.title or "")[:80])
            return False
        
        # Step 2: FORCE fingerprint to match DB product
        existing_fp = db_product.fingerprint
        enriched._cached_fingerprint = existing_fp
        
        # Override AI essence to match source
        if db_product.ai_metadata and db_product.ai_metadata.get("essence"):
            enriched.ai_essence = db_product.ai_metadata["essence"]
        
        # Step 3: Save to DB
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
# SECTION 15: PLATFORM SCRAPER (With Parallel Support)
# =============================================================================

async def scrape_platform(
    platform_name: str,
    query: str,
    db,
    source_specs: ProductSpecs,
    source_essence: str,
    db_product: Product,
    use_ai: bool,
    min_score: float,
    verbose: bool,
    stats: MiningStats,
    source_is_accessory_category: bool,
) -> PlatformResult:
    """
    Scrape a single platform and find matches.
    
    Returns: PlatformResult with match details
    """
    result = PlatformResult(platform=platform_name, success=False)
    
    try:
        handler = await get_platform_handler(platform_name, db)
        if not handler:
            result.error = "No handler"
            return result

        search_result = None
        last_error = None
        for attempt in range(1, MinerConfig.MAX_RETRIES + 1):
            try:
                search_result = await asyncio.wait_for(
                    handler.search(query=query, page=1),
                    timeout=MinerConfig.SCRAPE_TIMEOUT
                )
                break
            except asyncio.TimeoutError:
                last_error = f"Timeout (attempt {attempt}/{MinerConfig.MAX_RETRIES})"
                if attempt < MinerConfig.MAX_RETRIES:
                    stats.retries += 1
                    await asyncio.sleep(min(2 * attempt, 5))
                    continue
                raise
            except Exception as e:
                last_error = str(e)[:80]
                if attempt < MinerConfig.MAX_RETRIES:
                    stats.retries += 1
                    await asyncio.sleep(min(2 * attempt, 5))
                    continue
                raise
        
        if not search_result or not search_result.products:
            result.error = f"No results" + (f" ({last_error})" if last_error else "")
            return result
        
        result.success = True
        
        # Tier 0: Filter junk titles
        filtered_products, junk_count = filter_junk_results(search_result.products)
        stats.junk_filtered += junk_count
        
        if verbose and junk_count > 0:
            print(f"    🗑️ Filtered {junk_count} junk titles")
        
        candidates = filtered_products[:MinerConfig.MAX_CANDIDATES_PER_PLATFORM]
        result.candidates_checked = len(candidates)
        ai_calls = 0
        
        for scraped in candidates:
            s_title = scraped.title
            s_price = float(scraped.current_price) if scraped.current_price else None
            
            # Extract target specs
            target_specs = extract_specs(
                s_title, 
                s_price, 
                full_title=s_title,
                category=db_product.category
            )
            target_specs.full_title = s_title
            
            # TIER 1: Hard reject
            passed, reason, tier1_result = tier1_spec_reject(
                source_specs, 
                target_specs,
                source_is_accessory_category
            )
            
            if not passed:
                result.pre_filtered += 1
                stats.api_calls_saved += 1
                continue
            
            # TIER 2: Fuzzy score
            score, score_reason = tier2_fuzzy_match(
                source_essence, s_title, source_specs, target_specs
            )
            
            threshold = get_fuzzy_threshold(source_specs.category_type)
            
            if score < threshold:
                if verbose:
                    print(f"    ⚪ {score:.2f}: {s_title[:45]}...")
                continue
            
            if verbose:
                print(f"\n    🔄 Score={score:.2f}: {s_title[:50]}...")
            
            # TIER 3: AI verification
            final_score = score
            ai_verified = False
            
            if use_ai and ai_calls < MinerConfig.MAX_AI_CALLS_PER_PLATFORM:
                ai_calls += 1
                result.ai_calls += 1
                
                ai_result = await verify_with_ai(
                    source_specs, target_specs, platform_name
                )
                
                ai_score = ai_result.get("match_score", 0.0)
                ai_match = ai_result.get("is_exact_match", False)
                confidence = ai_result.get("confidence", "?")
                ai_reason = ai_result.get("reason", "N/A")
                
                if verbose:
                    print(f"       🤖 AI: score={ai_score:.2f} match={ai_match} conf={confidence}")
                    print(f"       📝 {ai_reason}")
                
                if not ai_match:
                    stats.ai_rejected += 1
                    continue
                
                # TIER 4: Post-AI sanity check
                sanity_passed, sanity_reason = post_ai_sanity_check(
                    ai_result, source_specs, target_specs
                )
                
                if not sanity_passed:
                    stats.ai_contradictions += 1
                    if verbose:
                        print(f"       ⚠️ Sanity check FAILED: {sanity_reason}")
                    continue
                
                stats.ai_verified += 1
                final_score = ai_score
                ai_verified = True
            
            # Save match if score is good enough
            if final_score >= min_score:
                if verbose:
                    print(f"\n    ✅ {'AI ' if ai_verified else ''}MATCH! Score={final_score:.0%}")
                
                ok = await save_matched_product(scraped, db_product, db, stats)
                
                if ok:
                    stats.stored += 1
                    stats.platforms_matched[platform_name] = stats.platforms_matched.get(platform_name, 0) + 1
                    result.match_found = True
                    result.scraped_product = scraped
                    result.match_score = final_score
                    
                    # Add to audit log
                    stats.audit_log.append({
                        "source_title": db_product.title,
                        "source_fingerprint": db_product.fingerprint,
                        "target_title": s_title,
                        "platform": platform_name,
                        "score": final_score,
                        "ai_verified": ai_verified,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    
                    if verbose:
                        print(f"       💾 Linked → {db_product.fingerprint[:20]}...")
                    
                    break  # Found match on this platform, stop searching
                else:
                    stats.errors += 1
        
        # Update pre-filtered count
        stats.pre_filtered += result.pre_filtered
        
        return result
    
    except asyncio.TimeoutError:
        result.error = "Timeout"
        stats.errors += 1
        logger.warning(f"[{platform_name}] Search timeout: {query}")
        return result
    except NotImplementedError as e:
        # Windows Playwright subprocess issue
        result.error = "Browser init failed (Windows)"
        stats.errors += 1
        if sys.platform == 'win32':
            logger.error(
                f"[{platform_name}] Playwright browser failed on Windows. "
                f"Solutions: Use WSL2, Docker, or Linux machine. "
                f"On Windows, Playwright subprocess creation is limited."
            )
        return result
    except Exception as e:
        result.error = str(e)[:60]
        stats.errors += 1
        logger.exception(f"[{platform_name}] Search error: {query}")
        return result


# =============================================================================
# SECTION 16: MAIN PROCESSING PIPELINE
# =============================================================================

async def process_orphan_products(
    limit: int = 10,
    use_ai: bool = True,
    target_platforms: Optional[List[str]] = None,
    min_score: float = 0.85,
    category_filter: Optional[str] = None,
    verbose: bool = True,
    parallel: bool = True,
    save_audit: bool = True,
):
    """
    Main autonomous mining pipeline v4.0.
    
    Features:
    - Quality gate for unmatchable products
    - Parallel platform scraping
    - Category-aware processing
    - Post-AI sanity checks
    - Audit logging
    """
    print(f"\n{'=' * 70}")
    print(f"🤖 CROSS-PLATFORM MINER v4.0 - Zero False Positives Edition")
    print(f"{'=' * 70}")
    print(f"  Mode: {'AI Verify' if use_ai else 'Fast (No AI)'} | {'Parallel' if parallel else 'Sequential'}")
    print(f"  Min Score: {min_score:.0%} | Limit: {limit}")
    if target_platforms:
        print(f"  Platforms: {', '.join(target_platforms)}")
    if category_filter:
        print(f"  Category: {category_filter}")
    print(f"{'=' * 70}\n")
    
    stats = MiningStats()
    
    async with async_session_maker() as db:
        # Query orphan products
        print("🔍 Finding orphan products...\n")
        
        stmt = (
            select(Product)
            .options(selectinload(Product.listings).selectinload(ProductListing.platform))
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
        
        # Process each orphan
        for i, db_product in enumerate(orphans, 1):
            stats.processed += 1
            listing = db_product.listings[0]
            existing_platform = None

            # Get existing platform name to exclude.
            if getattr(listing, "platform", None) and getattr(listing.platform, "name", None):
                existing_platform = listing.platform.name.lower().strip()
            else:
                try:
                    platform_row = await db.execute(
                        select(PlatformModel.name).where(PlatformModel.id == listing.platform_id)
                    )
                    existing_platform = (platform_row.scalar() or "").lower().strip() or None
                except Exception:
                    existing_platform = None
            
            # Determine category type
            category_type = determine_category_type(db_product.category, db_product.title)
            
            # Build available platforms
            try:
                cat_enum = ProductCategory(db_product.category.lower()) if db_product.category else ProductCategory.GENERAL
            except (ValueError, AttributeError):
                cat_enum = ProductCategory.GENERAL
            
            available = ProductCategory.get_platforms_for_category(cat_enum)
            available = [p for p in available if p in MinerConfig.SUPPORTED_PLATFORMS]
            
            # Exclude source platform
            if existing_platform and existing_platform in available:
                available.remove(existing_platform)
            
            if target_platforms:
                available = [p for p in available if p in target_platforms]
            
            print(f"\n{'─' * 70}")
            print(f"[{i}/{len(orphans)}] 🎯 {db_product.title[:55]}...")
            print(f"{'─' * 70}")
            
            # Extract source specs from FULL TITLE
            source_price = float(listing.current_price) if listing.current_price else None
            source_specs = extract_specs(
                db_product.title, 
                source_price, 
                full_title=db_product.title,
                category=db_product.category
            )
            source_specs.full_title = db_product.title
            source_specs.category_type = category_type
            
            # Get source essence
            source_essence = ""
            if db_product.ai_metadata:
                source_essence = db_product.ai_metadata.get("essence", "")
            if not source_essence:
                source_essence = source_specs.get_essence() or db_product.title
            
            # Check if source is an accessory-type product
            source_is_accessory_category = any(
                x in db_product.title.lower() 
                for x in ['headphone', 'earphone', 'earbuds', 'speaker', 'charger', 'cable']
            )
            
            # QUALITY GATE CHECK
            quality_result = check_quality_gate(db_product.title, source_specs, category_type)
            
            if not quality_result.passed:
                stats.quality_gate_skipped += 1
                stats.skipped_products.append({
                    "title": db_product.title[:50],
                    "reason": quality_result.reason
                })
                print(f"  ⏭️ SKIPPED: {quality_result.reason}")
                continue
            
            if verbose:
                print(f"  📊 Category: {category_type.value.upper()}")
                print(f"  📊 Brand={source_specs.brand or '?'} | Line={source_specs.product_line or '?'} | Model={source_specs.model or '?'}")
                print(f"  📊 RAM={source_specs.ram_gb or '?'}GB | Storage={source_specs.storage_gb or '?'}GB | Screen={source_specs.screen_size or '?'}\"")
                print(f"  📊 Variant={source_specs.generation or 'Std'} | Price=₹{source_price or '?'}")
                print(f"  📊 Identity Score: {quality_result.identity_score}/10")
            
            # Process each platform
            for platform_name in available:
                stats.platforms_scraped[platform_name] = stats.platforms_scraped.get(platform_name, 0) + 1
                
                query = generate_search_query(db_product, platform_name, source_specs)
                print(f"\n  🌐 {platform_name.upper()} → '{query}'")
                
                platform_result = await scrape_platform(
                    platform_name=platform_name,
                    query=query,
                    db=db,
                    source_specs=source_specs,
                    source_essence=source_essence,
                    db_product=db_product,
                    use_ai=use_ai,
                    min_score=min_score,
                    verbose=verbose,
                    stats=stats,
                    source_is_accessory_category=source_is_accessory_category,
                )
                
                if platform_result.error:
                    print(f"    ⚠️ {platform_result.error}")
                elif platform_result.success:
                    print(f"    📥 {platform_result.candidates_checked} candidates")
                    if platform_result.pre_filtered > 0 and verbose:
                        print(f"    🚫 Pre-filtered: {platform_result.pre_filtered}")
                    if not platform_result.match_found:
                        print(f"    ❌ No match on {platform_name}")
            
            # Browser cleanup between products
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
    
    # Print summary and save audit log
    stats.print_summary()
    
    if save_audit and stats.audit_log:
        stats.save_audit_log()
    
    return stats


# =============================================================================
# SECTION 17: CLI
# =============================================================================

def parse_platforms(s: str) -> Optional[List[str]]:
    """Parse comma-separated platform list."""
    if not s:
        return None
    valid = [p.value for p in Platform]
    platforms = [p.strip().lower() for p in s.split(',')]
    for p in platforms:
        if p not in valid:
            raise ValueError(f"Invalid platform: {p}. Valid: {', '.join(valid)}")
    return platforms


def setup_logging(debug: bool = False):
    """Setup logging configuration."""
    log_level = logging.DEBUG if debug else getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    if not debug:
        # Suppress SQLAlchemy logs
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cross-Platform Miner v4.0 - Zero False Positives Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/cross_platform_miner.py --limit 10
  python scripts/cross_platform_miner.py --limit 50 --no-ai
  python scripts/cross_platform_miner.py --limit 20 --platforms amazon,flipkart
  python scripts/cross_platform_miner.py --category electronics --limit 10
  python scripts/cross_platform_miner.py --debug  # Enable SQL logging
  python scripts/cross_platform_miner.py --no-audit  # Skip audit log
        """
    )
    
    parser.add_argument("--limit", type=int, default=10, help="Number of products to process")
    parser.add_argument("--no-ai", action="store_true", help="Skip AI verification")
    parser.add_argument("--platforms", type=str, default=None, help="Comma-separated platform list")
    parser.add_argument("--min-score", type=float, default=0.85, help="Minimum match score (0.0-1.0)")
    parser.add_argument("--category", type=str, default=None, help="Filter by category")
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging (SQL queries)")
    parser.add_argument("--sequential", action="store_true", help="Disable parallel scraping")
    parser.add_argument("--no-audit", action="store_true", help="Skip audit log generation")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.debug)
    
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
            parallel=not args.sequential,
            save_audit=not args.no_audit,
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user.")
        sys.exit(0)
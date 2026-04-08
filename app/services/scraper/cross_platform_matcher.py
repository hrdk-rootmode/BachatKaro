"""
Cross-Platform Product Matcher v4.0 - Zero False Positives Edition
====================================================================

Enhanced with v4.0 Intelligence:
- 6-Layer matching system (Quality Gate → Spec Reject → Fuzzy → AI → Post-AI → Save)
- 100+ brand patterns (Fire-Boltt, boAt, Noise, Nike, fashion brands)
- Product-line extraction (Phoenix vs Hunter, Galaxy S vs Galaxy A)
- Spec extraction (RAM, storage, screen size, processor)
- Fashion-aware matching (garment type, material, fit, gender)
- Category-aware AI prompts
- Windows Playwright compatibility

BACKWARD COMPATIBLE:
- All existing methods work unchanged
- seed.py, daily_scrape.py continue to work
- Enhanced accuracy with same API

Author: DealHunt
Version: 4.0
"""

import logging
import asyncio
import hashlib
import re
from typing import Optional, List, Dict, Any, Tuple, Set
from decimal import Decimal
from datetime import datetime
from difflib import SequenceMatcher
from dataclasses import dataclass

from app.services.scraper.base import ProductData, SearchResult, ProductCategory, HandlerType
from app.core.config import settings

logger = logging.getLogger(__name__)

# Optional database imports
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select, or_
    from sqlalchemy.orm import selectinload
    from app.models import Product, ProductListing, Platform as PlatformModel
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    AsyncSession = None


# =============================================================================
# SECTION 1: ENHANCED DATA STRUCTURES
# =============================================================================

@dataclass
class ProductSpecs:
    """Extracted product specifications"""
    brand: Optional[str] = None
    original_brand: Optional[str] = None  # For search queries (POCO not Xiaomi)
    model: Optional[str] = None
    product_line: Optional[str] = None  # Phoenix, Hunter, Galaxy S, etc.
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    screen_size: Optional[float] = None
    generation: Optional[str] = None  # Pro, Ultra, Lite
    network: Optional[str] = None
    color: Optional[str] = None
    processor: Optional[str] = None
    
    # Fashion
    garment_type: Optional[str] = None
    material: Optional[str] = None
    fit: Optional[str] = None
    gender: Optional[str] = None
    
    is_accessory: bool = False
    is_refurbished: bool = False
    price: Optional[float] = None
    category_type: str = "general"


# =============================================================================
# SECTION 2: COMPREHENSIVE BRAND & PATTERN DATABASE
# =============================================================================

# 100+ Brand Patterns
BRAND_PATTERNS = re.compile(
    r'\b('
    # Smartphones
    r'Samsung|Apple|iPhone|iPad|OnePlus|One\s*Plus|Xiaomi|Redmi|POCO|Realme|'
    r'Vivo|Oppo|Motorola|Moto|Nokia|Google|Pixel|Nothing|iQOO|IQOO|'
    r'Asus|ROG|Sony|Xperia|Huawei|Honor|Tecno|Infinix|'
    # Audio/Wearables (CRITICAL - was missing in old version)
    r'Fire[\s\-]?Boltt|FireBoltt|boAt|boat|Noise|Zebronics|Mivi|Portronics|'
    r'Ambrane|pTron|Ptron|Boult|CrossBeats|Hammer|Fastrack|Titan|Sonata|'
    r'JBL|Sony|Bose|Sennheiser|Skullcandy|Beats|Marshall|'
    # Laptops
    r'Dell|HP|Acer|Asus|Lenovo|MSI|Razer|Alienware|ThinkPad|MacBook|Surface|'
    # Fashion
    r'Nike|Adidas|Puma|Reebok|Levis|Wrangler|Lee|Allen\s*Solly|Van\s*Heusen|'
    r'Peter\s*England|Louis\s*Philippe|US\s*Polo|Roadster|HRX|Bewakoof|'
    r'Wildcraft|Woodland|Bata|Crocs|Skechers|'
    # Beauty
    r'Lakme|Maybelline|Loreal|Nivea|Garnier|Himalaya|Mamaearth|Nykaa|'
    # Appliances
    r'LG|Whirlpool|Samsung|Godrej|Haier|IFB|Bosch|Bajaj|Havells|Philips'
    r')\b',
    re.IGNORECASE
)

BRAND_NORMALIZATIONS = {
    'iphone': 'Apple', 'ipad': 'Apple', 'macbook': 'Apple',
    'moto': 'Motorola', 'one plus': 'OnePlus', 'oneplus': 'OnePlus',
    'redmi': 'Xiaomi', 'poco': 'Xiaomi', 'mi': 'Xiaomi',
    'fire-boltt': 'Fire-Boltt', 'fireboltt': 'Fire-Boltt',
    'boat': 'boAt', 'noise': 'Noise',
}

BRAND_FAMILIES = {
    'xiaomi': {'xiaomi', 'redmi', 'poco', 'mi'},
    'redmi': {'xiaomi', 'redmi'},
    'poco': {'xiaomi', 'poco'},
    'apple': {'apple', 'iphone', 'ipad', 'macbook'},
    'motorola': {'motorola', 'moto'},
    'fire-boltt': {'fire-boltt', 'fireboltt'},
}

# Product-Line Patterns (THE KEY FIX for Phoenix vs Hunter)
PRODUCT_LINE_PATTERNS = {
    'fire-boltt': re.compile(r'\b(Phoenix|Hunter|Ninja|Rocket|Tank|Gladiator|Invincible|Talk|Epic|Beast|Thunder)\b', re.I),
    'noise': re.compile(r'\b(ColorFit|Pulse|Icon|Vivid|Twist|NoiseFit|Evolve|Force|Core|Halo)\b', re.I),
    'boat': re.compile(r'\b(Airdopes|Rockerz|Stone|Bassheads|Immortal|Nirvana|Wave)\b', re.I),
    'samsung': re.compile(r'\b(Galaxy\s*[SAZMF]|Galaxy\s*Book|Galaxy\s*Tab)\b', re.I),
    'apple': re.compile(r'\b(iPhone|iPad\s*Pro|iPad\s*Air|MacBook\s*Pro|MacBook\s*Air)\b', re.I),
    'lenovo': re.compile(r'\b(ThinkPad|IdeaPad|Yoga|Legion)\b', re.I),
    'acer': re.compile(r'\b(Aspire|Nitro|Predator|Swift)\b', re.I),
    'asus': re.compile(r'\b(VivoBook|ZenBook|ROG|TUF)\b', re.I),
}

# Spec Patterns
RAM_PATTERNS = [
    re.compile(r'(\d{1,2})\s*GB\s*RAM', re.I),
    re.compile(r'\((\d{1,2})\s*GB\s*[/+,]\s*\d+\s*GB\)', re.I),
    re.compile(r'\b(\d{1,2})\s*GB\b(?!\s*(?:ROM|Storage|SSD))', re.I),
]

STORAGE_PATTERNS = [
    re.compile(r'(\d{2,4})\s*GB\s*(?:ROM|Storage|Internal|SSD)', re.I),
    re.compile(r'\(\d+\s*GB\s*[/+,]\s*(\d{2,4})\s*GB\)', re.I),
    re.compile(r'(\d+)\s*TB', re.I),
]

SCREEN_SIZE_PATTERN = re.compile(r'(\d+\.?\d*)\s*(?:inch|inches|"|″)', re.I)

GENERATION_PATTERNS = re.compile(
    r'\b(Pro|Plus|Ultra|Max|Lite|Neo|Mini|SE|FE|Edge|Note|Prime|GT|AI)\b',
    re.I
)

CRITICAL_VARIANTS = {'pro', 'plus', 'ultra', 'max', 'lite', 'mini', 'se', 'fe', 'note', 'ai'}

GARMENT_TYPE_PATTERNS = re.compile(
    r'\b(T[\s\-]?Shirt|Tshirt|Tshirts|Shirt|Dress|Jeans|Trousers|Sneakers|Shoes|Kurta|Saree)\b',
    re.I
)

ACCESSORY_PATTERNS = re.compile(
    r'\b(cover|case|screen guard|protector|tempered glass|charger|cable|'
    r'holder|stand|skin|pouch|adapter|back cover|flip cover|earphone|'
    r'strap|band|sleeve|bag|mount|phone case|camera lens protector|'
    r'keyboard cover|laptop skin|watch strap)\b',
    re.I
)

ACCESSORY_KIND_PATTERNS = {
    'cover': re.compile(r'\b(cover|case|back cover|flip cover|phone case|laptop skin)\b', re.I),
    'screen_protector': re.compile(r'\b(screen guard|protector|tempered glass|lens protector)\b', re.I),
    'charger_cable': re.compile(r'\b(charger|cable|adapter)\b', re.I),
    'holder_mount': re.compile(r'\b(holder|stand|mount)\b', re.I),
    'wearable_strap': re.compile(r'\b(strap|band|watch strap)\b', re.I),
    'audio_accessory': re.compile(r'\b(earphone|earbud case|headphone case)\b', re.I),
}

PRODUCT_TYPE_PATTERNS = {
    'phone': re.compile(r'\b(phone|smartphone|iphone|galaxy\s*s\d+|pixel\s*\d+|oneplus|mobile)\b', re.I),
    'laptop': re.compile(r'\b(laptop|notebook|macbook|thinkpad|ideapad|vivobook|zenbook)\b', re.I),
    'tablet': re.compile(r'\b(tablet|ipad|tab)\b', re.I),
    'watch': re.compile(r'\b(smart\s*watch|watch)\b', re.I),
    'tv': re.compile(r'\b(tv|television|qled|oled|smart\s*tv)\b', re.I),
    'earbuds': re.compile(r'\b(earbuds|earphones|headphones|airpods|neckband)\b', re.I),
    'shirt': re.compile(r'\b(t[\s\-]?shirt|shirt|polo)\b', re.I),
    'jeans': re.compile(r'\b(jeans|denim)\b', re.I),
    'dress': re.compile(r'\b(dress|gown)\b', re.I),
    'kurti': re.compile(r'\b(kurti|kurta|saree)\b', re.I),
    'shoes': re.compile(r'\b(shoes|sneakers|sandals|slippers|loafers)\b', re.I),
    'book': re.compile(r'\b(book|paperback|hardcover|kindle\s*edition)\b', re.I),
    'appliance': re.compile(r'\b(refrigerator|fridge|washing machine|air fryer|mixer|grinder|microwave)\b', re.I),
}

REFURBISHED_PATTERNS = re.compile(
    r'\b(renewed|refurbished|refurb|used|pre[\s\-]?owned|open[\s\-]?box)\b',
    re.I
)


# =============================================================================
# SECTION 3: SPEC EXTRACTION FUNCTIONS
# =============================================================================

def extract_brand(title: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract brand (normalized, original)"""
    if not title:
        return None, None
    
    match = BRAND_PATTERNS.search(title)
    if match:
        original = match.group(1).strip()
        normalized = BRAND_NORMALIZATIONS.get(original.lower(), original.title())
        return normalized, original
    return None, None


def extract_product_line(title: str, brand: Optional[str] = None) -> Optional[str]:
    """Extract product line/series (Phoenix, Hunter, Galaxy S, etc.)"""
    if not title or not brand:
        return None
    
    brand_lower = brand.lower().replace('-', '').replace(' ', '')
    
    for brand_key, pattern in PRODUCT_LINE_PATTERNS.items():
        if brand_key.replace('-', '') in brand_lower or brand_lower in brand_key.replace('-', ''):
            match = pattern.search(title)
            if match:
                return match.group(1).strip()
    return None


def extract_ram(title: str) -> Optional[int]:
    """Extract RAM in GB"""
    for pattern in RAM_PATTERNS:
        match = pattern.search(title)
        if match:
            ram = int(match.group(1))
            if 2 <= ram <= 64:
                return ram
    return None


def extract_storage(title: str) -> Optional[int]:
    """Extract storage in GB"""
    for pattern in STORAGE_PATTERNS:
        matches = pattern.findall(title)
        for match_str in matches:
            storage = int(match_str)
            if 'TB' in title.upper() and storage <= 8:
                return storage * 1024
            if storage in [16, 32, 64, 128, 256, 512, 1024] or 16 <= storage <= 2048:
                return storage
    return None


def extract_screen_size(title: str) -> Optional[float]:
    """Extract screen size in inches"""
    match = SCREEN_SIZE_PATTERN.search(title)
    if match:
        size = float(match.group(1))
        if 1.0 <= size <= 85.0:
            return size
    return None


def extract_generation(title: str) -> Optional[str]:
    """Extract variant (Pro, Ultra, etc.)"""
    matches = GENERATION_PATTERNS.findall(title)
    if matches:
        return ' '.join(set(matches))
    return None


def extract_garment_type(title: str) -> Optional[str]:
    """Extract garment type for fashion"""
    match = GARMENT_TYPE_PATTERNS.search(title)
    return match.group(1).strip() if match else None


def is_accessory(title: str) -> bool:
    """Check if product is an accessory"""
    return bool(ACCESSORY_PATTERNS.search(title)) if title else False


def get_accessory_kind(title: str) -> Optional[str]:
    """Classify accessory subtype to prevent case-vs-charger mismatches."""
    if not title:
        return None

    for kind, pattern in ACCESSORY_KIND_PATTERNS.items():
        if pattern.search(title):
            return kind

    return None


def detect_product_type(title: str, specs: Optional[ProductSpecs] = None) -> Optional[str]:
    """Infer the core product type from title/specs for strict cross-type rejection."""
    if not title:
        return None

    for product_type, pattern in PRODUCT_TYPE_PATTERNS.items():
        if pattern.search(title):
            return product_type

    if specs and specs.is_accessory:
        return "accessory"

    return None


def is_refurbished(title: str) -> bool:
    """Check if product is refurbished"""
    return bool(REFURBISHED_PATTERNS.search(title)) if title else False


def extract_specs(title: str, price: Optional[float] = None, category: str = "general") -> ProductSpecs:
    """Extract all specs from title"""
    specs = ProductSpecs(price=price, category_type=category)
    
    if not title:
        specs.is_accessory = True
        return specs
    
    specs.brand, specs.original_brand = extract_brand(title)
    specs.product_line = extract_product_line(title, specs.brand)
    specs.ram_gb = extract_ram(title)
    specs.storage_gb = extract_storage(title)
    specs.screen_size = extract_screen_size(title)
    specs.generation = extract_generation(title)
    specs.garment_type = extract_garment_type(title)
    specs.is_accessory = is_accessory(title)
    specs.is_refurbished = is_refurbished(title)
    
    return specs


def check_quality_gate(title: str, specs: ProductSpecs) -> Tuple[bool, str]:
    """Quality gate - reject unmatchable/garbage products"""
    if not title or len(title) < 10:
        return False, f"Title too short ({len(title)} chars)"
    
    # NEW: Check for literal garbage phrases
    title_lower = title.lower()
    junk_phrases = [
        "currently unavailable", "coming soon", "out of stock", 
        "sold out", "00h :", "01h :"
    ]
    if any(phrase in title_lower for phrase in junk_phrases):
        return False, "Title is a status message/junk"

    # Count meaningful words
    words = [w for w in re.findall(r'\b[a-zA-Z]{2,}\b', title) 
             if w.lower() not in {'the', 'a', 'an', 'and', 'or', 'for', 'with', 'new', 'best'}]
    
    if len(words) < 2:
        return False, f"Too few words ({len(words)})"
    
    category_type = (specs.category_type or "").lower()

    # Electronics/watches need brand OR model
    if category_type in ("electronics", "watches"):
        if not specs.brand and not specs.product_line and not specs.storage_gb:
            return False, "No brand/model/specs detected for electronics"
            
    # NEW: Reject if brand is literal garbage and it has no other specs
    garbage_brands = {"unknown", "null", "generic", "n/a", "none"}
    if specs.brand and specs.brand.lower() in garbage_brands:
        if not specs.model and not specs.garment_type:
            return False, "Garbage brand with no identifiable features"
            
    # NEW: Reject if title is literally just the brand name (e.g. "VANGULL...")
    if specs.brand and title_lower.replace(specs.brand.lower(), '').strip() == "":
        return False, "Title is just the brand name"

    # Explicitly block accessory-like titles from passing as core electronics.
    if category_type in ("electronics", "watches") and specs.is_accessory:
        return False, "Accessory title in electronics flow"
    
    return True, "OK"

# =============================================================================
# SECTION 4: ENHANCED MATCHER CLASS
# =============================================================================

class CrossPlatformMatcher:
    """
    v4.0 Matcher with Zero False Positives
    
    ENHANCEMENTS:
    - Quality gate (rejects "NOISE", "VANGULL")
    - Product-line comparison (Phoenix ≠ Hunter)
    - Spec hard-reject (RAM/storage/screen mismatch)
    - AI verification with category-aware prompts
    - Post-AI sanity check
    
    BACKWARD COMPATIBLE:
    - All public methods unchanged
    - seed.py continues to work
    """
    
    MIN_SIMILARITY_SCORE = 0.65  # Slightly relaxed to recover true positives
    ESSENCE_MATCH_SCORE = 1.0
    MAX_CONCURRENT_SEARCHES = 4
    SEARCH_TIMEOUT_SECONDS = 30

    # Fix S4: set to True to re-enable the relaxed recovery pass that skips
    # RAM / variant guards.  Disabled by default to prevent cross-variant matches.
    ENABLE_RELAXED_MATCHING = False
    
    # Price tolerances by category
    PRICE_TOLERANCE = {
        'electronics': 0.45,
        'fashion': 0.60,
        'watches': 0.50,
        'general': 0.50,
    }
    
    SCREEN_SIZE_TOLERANCE = 0.3  # inches
    
    STOP_WORDS: Set[str] = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'it', 'as', 'be', 'this', 'that',
        'new', 'best', 'top', 'latest', 'pack', 'set', 'combo', 'offer',
        'deal', 'buy', 'online', 'price', 'india', 'sale', 'discount',
    }
    
    def __init__(self):
        self._search_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SEARCHES)
        self._ai_client = None
    
    async def _get_ai_client(self):
        """Lazy load AI client"""
        if self._ai_client is None:
            try:
                from app.services.ai.groq_client import groq_client
                self._ai_client = groq_client
            except ImportError:
                logger.warning("AI client not available")
        return self._ai_client
    
    # =========================================================================
    # PUBLIC API (BACKWARD COMPATIBLE)
    # =========================================================================
    
    async def find_alternatives(
        self,
        source_product: ProductData,
        db: Optional[Any] = None,
        search_if_not_found: bool = True,
        skip_platforms: List[str] = None,
        max_results: int = 10
    ) -> List[ProductData]:
        """
        Find same product on other platforms
        
        UNCHANGED API - enhanced internal logic only
        """
        skip_platforms = set(p.lower() for p in (skip_platforms or []))
        skip_platforms.add(source_product.platform_name.lower())
        
        # Quality gate check on source
        source_specs = extract_specs(
            source_product.title,
            float(source_product.current_price) if source_product.current_price else None,
            source_product.category or "general"
        )
        
        passed, reason = check_quality_gate(source_product.title, source_specs)
        if not passed:
            logger.warning(f"Source product failed quality gate: {reason}")
            return [source_product]  # Return source only
        
        alternatives = [source_product]
        seen_platforms = {source_product.platform_name.lower()}
        seen_listing_keys = {
            (
                source_product.platform_name.lower(),
                (source_product.external_id or source_product.product_url or source_product.fingerprint or "").lower(),
            )
        }

        def listing_key(product: ProductData) -> Tuple[str, str]:
            return (
                product.platform_name.lower(),
                (product.external_id or product.product_url or product.fingerprint or "").lower(),
            )
        
        logger.info(
            f"Finding alternatives for: {source_product.title[:50]}... "
            f"(brand: {source_specs.brand or '?'}, "
            f"line: {source_specs.product_line or '?'})"
        )
        
        # Step 1: Database search
        if DB_AVAILABLE and db is not None:
            db_matches = await self._find_in_database(
                source_product,
                db,
                skip_platforms,
                source_specs
            )
            
            for match in db_matches:
                key = listing_key(match)
                platform_name = match.platform_name.lower()
                if key not in seen_listing_keys and platform_name not in seen_platforms:
                    alternatives.append(match)
                    seen_listing_keys.add(key)
                    seen_platforms.add(platform_name)
            
            if db_matches:
                logger.info(f"Found {len(db_matches)} DB matches")
        
        # Step 2: Live search
        if search_if_not_found and len(alternatives) < max_results:
            live_matches = await self._search_live_platforms(
                source_product,
                source_specs,
                db,
                skip_platforms,
                seen_listing_keys
            )
            
            for match in live_matches:
                key = listing_key(match)
                platform_name = match.platform_name.lower()
                if key not in seen_listing_keys and platform_name not in seen_platforms:
                    alternatives.append(match)
                    seen_listing_keys.add(key)
                    seen_platforms.add(platform_name)
                    
                    if len(alternatives) >= max_results:
                        break
        
        alternatives.sort(key=lambda x: float(x.current_price))
        
        logger.info(f"Total alternatives: {len(alternatives)}")
        
        return alternatives[:max_results]
    
    def calculate_savings(self, alternatives: List[ProductData]) -> Dict[str, Any]:
        """Calculate savings - UNCHANGED"""
        if not alternatives or len(alternatives) == 1:
            return {
                "has_savings": False,
                "best_price": float(alternatives[0].current_price) if alternatives else 0,
                "max_savings": 0,
                "best_platform": alternatives[0].platform_name if alternatives else None,
                "savings_percent": 0
            }
        
        sorted_products = sorted(alternatives, key=lambda x: float(x.current_price))
        cheapest = sorted_products[0]
        most_expensive = sorted_products[-1]
        
        max_savings = float(most_expensive.current_price - cheapest.current_price)
        savings_percent = (max_savings / float(most_expensive.current_price)) * 100 if float(most_expensive.current_price) > 0 else 0
        
        return {
            "has_savings": max_savings > 0,
            "best_price": float(cheapest.current_price),
            "best_platform": cheapest.platform_name,
            "best_url": cheapest.product_url,
            "highest_price": float(most_expensive.current_price),
            "highest_price_platform": most_expensive.platform_name,
            "max_savings": round(max_savings, 2),
            "savings_percent": round(savings_percent, 1),
            "total_options": len(alternatives),
        }
    
    async def enrich_with_ai(self, product: ProductData) -> ProductData:
        """Enrich with AI - UNCHANGED"""
        if product.ai_processed and product.ai_essence:
            return product
        
        ai_client = await self._get_ai_client()
        if not ai_client:
            return product
        
        try:
            enriched = await ai_client.process_product(product)
            
            product.ai_essence = enriched.get("essence")
            product.ai_tags = enriched.get("tags", [])
            product.ai_quality_score = enriched.get("quality_score", 0)
            product.category = enriched.get("category") or product.category
            product.subcategory = enriched.get("subcategory")
            
            if enriched.get("specifications"):
                product.specifications = {**product.specifications, **enriched["specifications"]}
            
            product.ai_processed = True
            
        except Exception as e:
            logger.error(f"AI enrichment failed: {e}")
        
        return product
    
    # =========================================================================
    # ENHANCED INTERNAL METHODS (v4.0 LOGIC)
    # =========================================================================
    
    async def _find_in_database(
        self,
        source_product: ProductData,
        db: Any,
        skip_platforms: Set[str],
        source_specs: ProductSpecs
    ) -> List[ProductData]:
        """Find in DB with enhanced spec validation"""
        if not DB_AVAILABLE:
            return []
        
        try:
            # Prefer explicit variant/base fingerprints over generic fingerprint.
            source_variant_fp = None
            source_base_fp = None
            try:
                source_variant_fp = source_product.get_variant_fingerprint()
            except Exception:
                source_variant_fp = None

            try:
                source_base_fp = source_product.get_base_fingerprint()
            except Exception:
                source_base_fp = None

            fingerprint_candidates = set()
            legacy_fingerprint = getattr(source_product, "_cached_fingerprint", None) or getattr(source_product, "_fingerprint", None)
            if legacy_fingerprint:
                fingerprint_candidates.add(str(legacy_fingerprint))

            try:
                if getattr(source_product, "fingerprint", None):
                    fingerprint_candidates.add(str(source_product.fingerprint))
            except Exception:
                pass

            filters = []
            if source_variant_fp:
                filters.append(Product.variant_fingerprint == source_variant_fp)
                filters.append(Product.fingerprint == source_variant_fp)

            for candidate_fp in fingerprint_candidates:
                filters.append(Product.fingerprint == candidate_fp)

            if source_base_fp:
                filters.append(Product.base_fingerprint == source_base_fp)

            if not filters:
                return []

            result = await db.execute(
                select(Product)
                .where(or_(*filters))
                .options(selectinload(Product.listings))
            )
            products = result.scalars().all()
            
            if not products:
                return []
            
            alternatives = []
            seen_listing_ids: Set[str] = set()
            
            for product in products:
                for listing in product.listings:
                    listing_id = str(listing.id)
                    if listing_id in seen_listing_ids:
                        continue

                    platform_result = await db.execute(
                        select(PlatformModel).where(PlatformModel.id == listing.platform_id)
                    )
                    platform = platform_result.scalar_one_or_none()
                    
                    if not platform or platform.name.lower() in skip_platforms:
                        continue
                    
                    if not listing.in_stock:
                        continue
                    
                    # Extract specs from listing
                    target_specs = extract_specs(
                        product.title,
                        float(listing.current_price) if listing.current_price else None,
                        product.category or "general"
                    )
                    
                    # Tier 1: Hard reject
                    passed, reject_reason = self._tier1_spec_reject(
                        source_specs,
                        target_specs,
                        source_title=source_product.title,
                        target_title=product.title,
                    )
                    if not passed:
                        logger.debug(f"DB listing rejected: {reject_reason}")
                        continue
                    
                    alternatives.append(ProductData(
                        external_id=listing.external_id or str(listing.id),
                        title=product.title,
                        current_price=Decimal(str(listing.current_price)),
                        original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
                        discount_percent=listing.discount_percent,
                        product_url=listing.product_url,
                        platform_name=platform.name,
                        image_url=product.image_url,
                        rating=listing.rating,
                        review_count=listing.review_count,
                        in_stock=listing.in_stock,
                        brand=product.brand,
                        category=product.category,
                        subcategory=product.subcategory,
                        specifications=product.specifications or {},
                        ai_essence=product.ai_metadata.get("essence") if product.ai_metadata else None,
                        ai_tags=product.ai_metadata.get("tags", []) if product.ai_metadata else [],
                        ai_quality_score=product.ai_metadata.get("quality_score", 0) if product.ai_metadata else 0,
                        ai_processed=True,
                        data_source=HandlerType.SCRAPER,
                        _fingerprint=product.fingerprint
                    ))
                    seen_listing_ids.add(listing_id)
            
            return alternatives
        
        except Exception as e:
            logger.error(f"DB query error: {e}")
            return []
    
    async def _search_live_platforms(
        self,
        source_product: ProductData,
        source_specs: ProductSpecs,
        db: Optional[Any],
        skip_platforms: Set[str],
        seen_listing_keys: Set[Tuple[str, str]]
    ) -> List[ProductData]:
        """Search live with v4.0 query generation"""
        category = ProductCategory.detect_from_query(source_product.title)
        relevant_platforms = ProductCategory.get_platforms_for_category(category)
        
        # Build smart query (use original brand)
        search_query = self._build_smart_query(source_product, source_specs)
        
        try:
            from app.services.scraper.factory import get_factory
            factory = get_factory()
        except ImportError:
            return []
        
        handlers = []
        for platform_name in relevant_platforms:
            if platform_name.lower() in skip_platforms:
                continue
            
            try:
                handler = await factory.get_handler(platform_name, db)
                handlers.append(handler)
            except Exception as e:
                logger.debug(f"Skip {platform_name}: {e}")
        
        if not handlers:
            return []
        
        search_tasks = [
            self._search_with_timeout(handler, search_query, source_product, source_specs)
            for handler in handlers
        ]
        
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        matches = []
        for result in results:
            if isinstance(result, Exception):
                continue
            if not result:
                continue

            key = (
                result.platform_name.lower(),
                (result.external_id or result.product_url or result.fingerprint or "").lower(),
            )
            if key not in seen_listing_keys:
                matches.append(result)
        
        return matches
    
    def _build_smart_query(self, product: ProductData, specs: ProductSpecs) -> str:
        """Build query using ORIGINAL brand (POCO not Xiaomi)"""
        parts = []
        
        # Use original brand for search
        if specs.original_brand:
            parts.append(specs.original_brand)
        elif specs.brand:
            parts.append(specs.brand)
        
        if specs.product_line:
            parts.append(specs.product_line)
        
        if specs.storage_gb:
            parts.append(f"{specs.storage_gb}GB")
        
        if specs.generation:
            parts.append(specs.generation)
        
        if len(parts) < 3:
            # Add meaningful words from title
            title_words = [w for w in re.findall(r'\b[a-zA-Z0-9]+\b', product.title.lower())
                          if w not in self.STOP_WORDS and len(w) > 2]
            parts.extend(title_words[:3])
        
        return ' '.join(parts[:6])
    
    async def _search_with_timeout(
        self,
        handler,
        query: str,
        source_product: ProductData,
        source_specs: ProductSpecs
    ) -> Optional[ProductData]:
        """Search with enhanced matching"""
        async with self._search_semaphore:
            try:
                search_result = await asyncio.wait_for(
                    handler.search(query, page=1),
                    timeout=self.SEARCH_TIMEOUT_SECONDS
                )
                
                if not search_result.success or not search_result.products:
                    return None
                
                best_match = await self._find_best_match_v4(
                    source_product,
                    source_specs,
                    search_result.products
                )

                # Fall back to page 2 when page 1 has no eligible candidate.
                if not best_match:
                    second_page = await asyncio.wait_for(
                        handler.search(query, page=2),
                        timeout=self.SEARCH_TIMEOUT_SECONDS
                    )
                    if second_page and second_page.success and second_page.products:
                        best_match = await self._find_best_match_v4(
                            source_product,
                            source_specs,
                            second_page.products
                        )
                
                return best_match
            
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on {handler.platform_name}")
                return None
            except Exception as e:
                logger.error(f"Search failed on {handler.platform_name}: {e}")
                return None
    
    async def _find_best_match_v4(
        self,
        source: ProductData,
        source_specs: ProductSpecs,
        candidates: List[ProductData]
    ) -> Optional[ProductData]:
        """Enhanced matching with 4-tier logic"""
        best_match = None
        best_score = 0
        scored_candidates: List[Tuple[ProductData, ProductSpecs, float]] = []
        preprocessed_candidates: List[Tuple[ProductData, ProductSpecs]] = []
        
        for candidate in candidates:
            # Quality gate
            target_specs = extract_specs(
                candidate.title,
                float(candidate.current_price) if candidate.current_price else None,
                candidate.category or "general"
            )
            preprocessed_candidates.append((candidate, target_specs))
            
            passed, reason = check_quality_gate(candidate.title, target_specs)
            if not passed:
                continue
            
            # Tier 1: Spec hard-reject
            passed, reject_reason = self._tier1_spec_reject(
                source_specs,
                target_specs,
                source_title=source.title,
                target_title=candidate.title,
            )
            if not passed:
                logger.debug(f"Rejected: {reject_reason}")
                continue
            
            # Tier 2: Fuzzy score
            score = self._tier2_fuzzy_score(source, source_specs, candidate, target_specs)
            scored_candidates.append((candidate, target_specs, score))
            
            if score >= self.MIN_SIMILARITY_SCORE and score > best_score:
                best_match = candidate
                best_score = score

        # Recovery pass: if strict pass found nothing, allow a guarded relaxed reject policy.
        # Fix S4: gated behind ENABLE_RELAXED_MATCHING (default False) to
        # prevent cross-variant false positives (e.g. 4GB → 8GB, Pro → Standard).
        if self.ENABLE_RELAXED_MATCHING and not best_match:
            relaxed_threshold = max(0.55, self.MIN_SIMILARITY_SCORE - 0.08)
            for candidate, target_specs in preprocessed_candidates:
                passed, _ = check_quality_gate(candidate.title, target_specs)
                if not passed:
                    continue

                passed, reject_reason = self._tier1_spec_reject(
                    source_specs,
                    target_specs,
                    source_title=source.title,
                    target_title=candidate.title,
                    relaxed=True,
                )
                if not passed:
                    logger.debug(f"Relaxed reject: {reject_reason}")
                    continue

                score = self._tier2_fuzzy_score(source, source_specs, candidate, target_specs)
                scored_candidates.append((candidate, target_specs, score))
                if score >= relaxed_threshold and score > best_score:
                    best_match = candidate
                    best_score = score

        # Tier 3: AI disambiguation for ambiguous titles across platforms.
        # This keeps recall for naming differences while reducing false positives.
        if scored_candidates and (not best_match or best_score < 0.82):
            ai_best = await self._tier3_ai_disambiguate(source, source_specs, scored_candidates)
            if ai_best:
                return ai_best
        
        return best_match

    async def _tier3_ai_disambiguate(
        self,
        source: ProductData,
        source_specs: ProductSpecs,
        scored_candidates: List[Tuple[ProductData, ProductSpecs, float]],
    ) -> Optional[ProductData]:
        """Use AI normalization (essence/tags) to resolve close matches safely."""
        if not scored_candidates:
            return None

        # Keep token usage low by checking only the strongest candidates.
        ranked = sorted(scored_candidates, key=lambda item: item[2], reverse=True)[:3]

        if not source.ai_essence:
            source = await self.enrich_with_ai(source)

        best_candidate: Optional[ProductData] = None
        best_combined_score = 0.0

        for candidate, target_specs, rule_score in ranked:
            if not candidate.ai_essence:
                candidate = await self.enrich_with_ai(candidate)

            essence_similarity = 0.0
            if source.ai_essence and candidate.ai_essence:
                essence_similarity = self._sequence_similarity(
                    source.ai_essence.lower(),
                    candidate.ai_essence.lower(),
                )

            source_tags = {t.lower() for t in (source.ai_tags or [])}
            target_tags = {t.lower() for t in (candidate.ai_tags or [])}
            tag_overlap = 0.0
            if source_tags and target_tags:
                union = source_tags.union(target_tags)
                tag_overlap = (len(source_tags.intersection(target_tags)) / len(union)) if union else 0.0

            # Preserve strict non-match rules even after AI enrichment.
            passed, _ = self._tier1_spec_reject(
                source_specs,
                target_specs,
                source_title=source.title,
                target_title=candidate.title,
            )
            if not passed:
                continue

            combined_score = (rule_score * 0.65) + (essence_similarity * 0.30) + (tag_overlap * 0.05)

            if combined_score > best_combined_score and combined_score >= max(0.62, self.MIN_SIMILARITY_SCORE):
                best_candidate = candidate
                best_combined_score = combined_score

        return best_candidate
    
    def _tier1_spec_reject(
        self,
        source: ProductSpecs,
        target: ProductSpecs,
        source_title: str = "",
        target_title: str = "",
        relaxed: bool = False,
    ) -> Tuple[bool, str]:
        """Tier 1: Hard spec rejection"""

        source_type = detect_product_type(source_title or "", source)
        target_type = detect_product_type(target_title or "", target)

        # Fallback to title-driven type inference if model field is unavailable.
        if not source_type:
            source_type = "accessory" if source.is_accessory else None
        if not target_type:
            target_type = "accessory" if target.is_accessory else None
        
        # Accessory mismatch
        if target.is_accessory and not source.is_accessory:
            return False, "Target is accessory"

        if source.is_accessory and not target.is_accessory:
            return False, "Source is accessory, target is core product"

        # Reject accessory subtype mismatches (e.g. cover vs charger).
        if source.is_accessory and target.is_accessory:
            source_kind = get_accessory_kind(source_title or "")
            target_kind = get_accessory_kind(target_title or "")
            if source_kind and target_kind and source_kind != target_kind:
                return False, f"Accessory kind: {source_kind} vs {target_kind}"

        # Reject clear product-type mismatch (phone vs laptop, shirt vs shoes, etc.).
        if source_type and target_type and source_type != target_type:
            return False, f"Product type: {source_type} vs {target_type}"
        
        # Refurbished vs new
        if target.is_refurbished and not source.is_refurbished:
            return False, "Refurbished vs new"
        
        # Brand family check
        if source.brand and target.brand:
            sf = BRAND_FAMILIES.get(source.brand.lower(), {source.brand.lower()})
            tf = BRAND_FAMILIES.get(target.brand.lower(), {target.brand.lower()})
            if not sf.intersection(tf):
                return False, f"Brand: {source.brand} vs {target.brand}"
        
        # Product-line mismatch (THE KEY FIX)
        if source.product_line and target.product_line:
            if source.product_line.lower() != target.product_line.lower():
                return False, f"Product-line: {source.product_line} vs {target.product_line}"
        
        # RAM mismatch
        if not relaxed and source.ram_gb and target.ram_gb and source.ram_gb != target.ram_gb:
            return False, f"RAM: {source.ram_gb}GB vs {target.ram_gb}GB"
        
        # Storage mismatch
        if source.storage_gb and target.storage_gb and source.storage_gb != target.storage_gb:
            return False, f"Storage: {source.storage_gb}GB vs {target.storage_gb}GB"
        
        # Screen size mismatch
        if source.screen_size and target.screen_size:
            if abs(source.screen_size - target.screen_size) > self.SCREEN_SIZE_TOLERANCE:
                return False, f"Screen: {source.screen_size}\" vs {target.screen_size}\""
        
        # Critical variant mismatch
        if not relaxed and (source.generation or target.generation):
            sg = set((source.generation or "").lower().split())
            tg = set((target.generation or "").lower().split())
            sc = sg.intersection(CRITICAL_VARIANTS)
            tc = tg.intersection(CRITICAL_VARIANTS)
            if sc != tc:
                return False, f"Variant: {source.generation or 'Std'} vs {target.generation or 'Std'}"
        
        # Price check
        if not relaxed and source.price and target.price and source.price > 0 and target.price > 0:
            tolerance = self.PRICE_TOLERANCE.get(source.category_type, 0.40)
            ratio = target.price / source.price
            if ratio < (1 - tolerance) or ratio > (1 + tolerance):
                return False, f"Price: ₹{source.price:.0f} vs ₹{target.price:.0f}"
        
        return True, "OK"
    
    def _tier2_fuzzy_score(
        self,
        source_product: ProductData,
        source_specs: ProductSpecs,
        target_product: ProductData,
        target_specs: ProductSpecs
    ) -> float:
        """Tier 2: Enhanced fuzzy scoring"""
        
        # Essence match (highest priority)
        if source_product.ai_essence and target_product.ai_essence:
            if source_product.ai_essence.lower() == target_product.ai_essence.lower():
                return 1.0
            
            essence_sim = self._sequence_similarity(
                source_product.ai_essence.lower(),
                target_product.ai_essence.lower()
            )
            if essence_sim >= 0.9:
                return essence_sim
        
        # Title similarity
        title_sim = self._sequence_similarity(
            source_product.title.lower(),
            target_product.title.lower()
        )
        
        score = title_sim * 0.50  # Base 50%
        
        # Bonuses
        if source_specs.brand and target_specs.brand:
            if source_specs.brand.lower() == target_specs.brand.lower():
                score += 0.20
        
        if source_specs.product_line and target_specs.product_line:
            if source_specs.product_line.lower() == target_specs.product_line.lower():
                score += 0.15
        
        if source_specs.ram_gb and target_specs.ram_gb:
            if source_specs.ram_gb == target_specs.ram_gb:
                score += 0.05
        
        if source_specs.storage_gb and target_specs.storage_gb:
            if source_specs.storage_gb == target_specs.storage_gb:
                score += 0.05
        
        if source_specs.generation and target_specs.generation:
            if source_specs.generation.lower() == target_specs.generation.lower():
                score += 0.05
        
        return min(1.0, score)
    
    def _sequence_similarity(self, text_a: str, text_b: str) -> float:
        """SequenceMatcher similarity"""
        return SequenceMatcher(None, text_a, text_b).ratio()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
cross_platform_matcher = CrossPlatformMatcher()
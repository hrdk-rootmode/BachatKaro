"""
Trend Hunter & Database Seeder
Automatically populates database with trending products from external sources

FLOW:
1. Get rotation state (which category/platform was last used)
2. Build search queries: "{category} {keyword}" (e.g., "Smartphones Best Selling")
3. Scrape search results from platform
4. Check fingerprint BEFORE AI call (save Groq quota)
5. AI enrich new products only
6. Save to DB with DYNAMIC scoring (no fake views)
7. Update rotation state for next run
8. Log everything to SystemLog

SCORING: Products earn their rank from real signals:
- Rating, reviews, discount, AI quality, brand, image

SCHEDULE: Runs daily at 3:00 AM IST (after daily price scrape)

Author: DealHunt
"""

import logging
import asyncio
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
import traceback

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert

from app.core.database import async_session_maker
from app.core.redis_client import redis_client
from app.core.config import settings
from app.models import Product, ProductListing, Platform, SystemLog
from app.services.scraper.factory import get_platform_handler
from app.services.scraper.generic_scraper import GenericAIScraper
from app.services.scraper.base import ProductData
from app.services.scraper.url_detector import url_detector
from app.services.ai.groq_client import groq_client

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

TREND_KEYWORDS = [
    "Best Selling",
    "Trending",
    "Top Rated",
    "Most Popular",
    "New Launch 2025",
]

SEEDING_CATEGORIES = [
    "Smartphones",
    "Laptops",
    "Headphones",
    "Smartwatches",
    "Men Fashion",
    "Women Fashion",
    "Kitchen Appliances",
    "Beauty Products",
    "Shoes",
    "Gaming",
]

SEEDING_PLATFORMS = ["amazon", "flipkart"]

# =============================================================================
# DYNAMIC SCORING (No fake views - earned naturally)
# =============================================================================

PRODUCTS_PER_KEYWORD = 20          # Max products to scrape per keyword
MAX_PRODUCTS_PER_RUN = 10         # Total cap per job run
SCRAPE_TIMEOUT_SECONDS = 30        # Timeout per scrape operation


def calculate_seed_score(product_data: ProductData) -> dict:
    """
    Calculate initial stats based on REAL product signals
    No fake views - score is earned from actual product quality
    
    Signals:
    - Rating (0-25 pts): Real social proof from buyers
    - Reviews (0-30 pts): Volume of real purchases
    - Discount (0-10 pts): Deal attractiveness
    - AI Quality (0-10 pts): Data completeness
    - Brand (0-5 pts): Trust signal
    - Image (0-3 pts): Display readiness
    
    Max possible seed_score: ~83 (exceptional product)
    Typical seed_score: 20-50 (decent product)
    """
    score = 0
    
    # 1. Has rating = real social proof
    if product_data.rating and product_data.rating > 0:
        score += int(product_data.rating * 5)  # 4.5 stars = +22
    
    # 2. Has reviews = people bought it
    if product_data.review_count and product_data.review_count > 0:
        if product_data.review_count > 1000:
            score += 30
        elif product_data.review_count > 100:
            score += 20
        elif product_data.review_count > 10:
            score += 10
        else:
            score += 5
    
    # 3. Has discount = deal worth showing
    if product_data.discount_percent and product_data.discount_percent > 20:
        score += int(product_data.discount_percent / 5)  # 50% off = +10
    
    # 4. AI quality score
    if product_data.ai_quality_score and product_data.ai_quality_score > 50:
        score += int(product_data.ai_quality_score / 10)  # 80 quality = +8
    
    # 5. Has brand = trustworthy
    if product_data.brand:
        score += 5
    
    # 6. Has image = displayable
    if product_data.image_url:
        score += 3
    
    return {
        "views": 0,           # Real views only
        "clicks": 0,          # Real clicks only
        "watches": 0,
        "searches": 0,
        "conversions": 0,
        "seed_score": score,   # Earned quality score
        "seeded": True,
        "seeded_at": datetime.utcnow().isoformat(),
    }


def calculate_rediscovery_boost(existing_stats: dict, product_data: ProductData) -> dict:
    """
    When product is found trending again, boost seed_score
    No fake views - just acknowledges continued relevance
    
    Each rediscovery adds +5 to seed_score (capped at 100)
    """
    current_seed = existing_stats.get("seed_score", 0)
    
    # Small boost for being found trending again (+5 per rediscovery, cap at 100)
    new_seed = min(current_seed + 5, 100)
    
    return {
        **existing_stats,
        "seed_score": new_seed,
        "last_seeded": datetime.utcnow().isoformat(),
    }


# =============================================================================
# ROTATION STATE MANAGEMENT (Redis-based)
# =============================================================================

ROTATION_STATE_KEY = "seeding:rotation:state"


async def get_rotation_state() -> Dict[str, int]:
    """
    Get current rotation indices from Redis
    Returns: {"category_index": 0, "platform_index": 0, "keyword_index": 0}
    """
    await redis_client._ensure_connected()
    
    state = await redis_client.get_all_hash(ROTATION_STATE_KEY)
    
    if not state:
        # First run - initialize state
        return {
            "category_index": 0,
            "platform_index": 0,
            "keyword_index": 0,
            "last_run": "",
        }
    
    return {
        "category_index": int(state.get("category_index", 0)),
        "platform_index": int(state.get("platform_index", 0)),
        "keyword_index": int(state.get("keyword_index", 0)),
        "last_run": state.get("last_run", ""),
    }


async def save_rotation_state(
    category_index: int,
    platform_index: int,
    keyword_index: int
) -> None:
    """Save rotation state to Redis for next run"""
    await redis_client._ensure_connected()
    
    await redis_client.set_hash(ROTATION_STATE_KEY, "category_index", str(category_index))
    await redis_client.set_hash(ROTATION_STATE_KEY, "platform_index", str(platform_index))
    await redis_client.set_hash(ROTATION_STATE_KEY, "keyword_index", str(keyword_index))
    await redis_client.set_hash(ROTATION_STATE_KEY, "last_run", datetime.utcnow().isoformat())


def get_next_rotation(state: Dict[str, int]) -> Tuple[str, str, str, Dict[str, int]]:
    """
    Calculate next category, platform, keyword to use
    Returns: (category, platform, keyword, new_state)
    """
    cat_idx = state["category_index"]
    plat_idx = state["platform_index"]
    kw_idx = state["keyword_index"]
    
    # Get current values
    category = SEEDING_CATEGORIES[cat_idx % len(SEEDING_CATEGORIES)]
    platform = SEEDING_PLATFORMS[plat_idx % len(SEEDING_PLATFORMS)]
    keyword = TREND_KEYWORDS[kw_idx % len(TREND_KEYWORDS)]
    
    # Calculate next state (rotate through all combinations)
    kw_idx += 1
    if kw_idx >= len(TREND_KEYWORDS):
        kw_idx = 0
        plat_idx += 1
        if plat_idx >= len(SEEDING_PLATFORMS):
            plat_idx = 0
            cat_idx += 1
            if cat_idx >= len(SEEDING_CATEGORIES):
                cat_idx = 0  # Full rotation complete, start over
    
    new_state = {
        "category_index": cat_idx,
        "platform_index": plat_idx,
        "keyword_index": kw_idx,
    }
    
    return category, platform, keyword, new_state


# =============================================================================
# DUPLICATE DETECTION (BEFORE AI CALL)
# =============================================================================

async def check_product_exists(
    fingerprint: str,
    db: AsyncSession
) -> Optional[Product]:
    """
    Check if product exists by fingerprint BEFORE calling AI
    This saves Groq API quota
    """
    result = await db.execute(
        select(Product).where(Product.fingerprint == fingerprint)
    )
    return result.scalar_one_or_none()


async def generate_fingerprint(product_data: ProductData) -> str:
    """
    Generate fingerprint for duplicate detection
    Uses existing fingerprint if available, otherwise creates one
    """
    if product_data.fingerprint:
        return product_data.fingerprint
    
    # Fallback: create basic fingerprint from title + platform
    import hashlib
    raw = f"{product_data.title.lower().strip()}_{product_data.platform_name.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


# =============================================================================
# AI ENRICHMENT (Reused from search.py pattern)
# =============================================================================

async def enrich_product_with_ai(product_data: ProductData) -> ProductData:
    """
    Enrich product data using AI (Groq)
    Reuses the same pattern as search.py
    """
    if product_data.ai_processed:
        return product_data
    
    try:
        enriched = await groq_client.process_product(product_data)
        
        product_data.ai_essence = enriched.get("essence")
        product_data.ai_tags = enriched.get("tags", [])
        product_data.ai_quality_score = enriched.get("quality_score", 50)
        product_data.category = enriched.get("category") or product_data.category
        product_data.subcategory = enriched.get("subcategory")
        
        if enriched.get("specifications"):
            product_data.specifications = {
                **(product_data.specifications or {}),
                **enriched["specifications"]
            }
        
        product_data.ai_processed = True
        
        logger.debug(
            f"AI enriched: {product_data.title[:40]}... → "
            f"{product_data.ai_essence[:30] if product_data.ai_essence else 'N/A'}"
        )
        
    except Exception as e:
        logger.warning(f"AI enrichment failed (using raw data): {e}")
        product_data.ai_processed = False
    
    return product_data


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

async def save_seeded_product(
    product_data: ProductData,
    db: AsyncSession,
    is_new: bool = True
) -> Optional[Product]:
    """
    Save seeded product to database with dynamic scoring
    
    NEW: No fake views. Score earned from real product signals.
    
    Args:
        product_data: Enriched product data
        db: Database session
        is_new: True for new products, False for re-discovered
    """
    try:
        fingerprint = await generate_fingerprint(product_data)
        
        # Check again (in case of race condition)
        existing = await check_product_exists(fingerprint, db)
        
        # Build AI metadata
        ai_metadata = {
            "essence": product_data.ai_essence or product_data.title[:100].lower(),
            "tags": product_data.ai_tags or [],
            "quality_score": product_data.ai_quality_score or 50,
            "processed_at": datetime.utcnow().isoformat(),
            "seeded": True,
            "seeded_at": datetime.utcnow().isoformat(),
        }
        
        if existing:
            # RE-DISCOVERED: Dynamic boost based on real signals
            existing.stats = calculate_rediscovery_boost(
                existing.stats or {}, product_data
            )
            
            # Update AI metadata if quality is better
            old_score = (existing.ai_metadata or {}).get("quality_score", 0)
            if product_data.ai_quality_score and product_data.ai_quality_score > old_score:
                existing.ai_metadata = ai_metadata
            
            await db.commit()
            
            logger.debug(
                f"♻️ Rediscovered (seed_score={existing.stats.get('seed_score', 0)}): "
                f"{existing.title[:40]}..."
            )
            return existing
        
        else:
            # NEW PRODUCT: Calculate score from real product signals
            dynamic_stats = calculate_seed_score(product_data)
            
            product = Product(
                fingerprint=fingerprint,
                title=product_data.title,
                brand=product_data.brand,
                category=product_data.category or "General",
                subcategory=product_data.subcategory,
                image_url=product_data.image_url,
                specifications=product_data.specifications or {},
                ai_metadata=ai_metadata,
                stats=dynamic_stats,
            )
            db.add(product)
            await db.flush()
            
            # Get or create platform
            platform_result = await db.execute(
                select(Platform).where(Platform.name == product_data.platform_name.lower())
            )
            platform = platform_result.scalar_one_or_none()
            
            if not platform:
                platform = Platform(
                    name=product_data.platform_name.lower(),
                    base_url=f"https://www.{product_data.platform_name.lower()}.com",
                    is_active=True,
                    selectors={},
                )
                db.add(platform)
                await db.flush()
            
            # Create listing
            listing = ProductListing(
                product_id=product.id,
                platform_id=platform.id,
                external_id=product_data.external_id,
                product_url=product_data.product_url,
                affiliate_url=url_detector.get_affiliate_url(product_data.product_url),
                current_price=float(product_data.current_price),
                original_price=float(product_data.original_price) if product_data.original_price else None,
                discount_percent=product_data.discount_percent,
                rating=product_data.rating,
                review_count=product_data.review_count,
                in_stock=product_data.in_stock,
                last_scraped=datetime.utcnow(),
            )
            db.add(listing)
            
            await db.commit()
            await db.refresh(product)
            
            logger.debug(
                f"✨ New (seed_score={dynamic_stats.get('seed_score', 0)}): "
                f"{product.title[:40]}..."
            )
            return product
            
    except Exception as e:
        logger.error(f"Failed to save seeded product: {e}")
        await db.rollback()
        return None


# =============================================================================
# SCRAPING LOGIC
# =============================================================================

async def scrape_trending_products(
    category: str,
    platform: str,
    keyword: str,
    db: AsyncSession,
    max_products: int = PRODUCTS_PER_KEYWORD
) -> List[ProductData]:
    """
    Scrape trending products using GenericAIScraper.search()
    Returns: SearchResult.products (List[ProductData])
    """
    search_query = f"{category} {keyword}"
    products = []
    
    logger.info(f"🔍 Scraping: '{search_query}' on {platform}")
    
    try:
        # Try platform-specific handler first
        try:
            handler = await get_platform_handler(platform, db)
            
            if hasattr(handler, 'search'):
                result = await asyncio.wait_for(
                    handler.search(query=search_query, page=1),
                    timeout=SCRAPE_TIMEOUT_SECONDS
                )
                
                if result and result.success and result.products:
                    products.extend(result.products[:max_products])
                    logger.info(
                        f"✅ Platform handler found {result.product_count} products "
                        f"for '{search_query}' on {platform}"
                    )
                    
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Platform handler timeout for {platform}")
        except Exception as e:
            logger.warning(f"Platform handler failed: {e}")
        
        # Fallback to generic AI scraper
        if not products:
            try:
                generic_scraper = GenericAIScraper(platform)
                
                result = await asyncio.wait_for(
                    generic_scraper.search(query=search_query, page=1),
                    timeout=SCRAPE_TIMEOUT_SECONDS
                )
                
                if result and result.success and result.products:
                    products.extend(result.products[:max_products])
                    logger.info(
                        f"✅ Generic scraper found {result.product_count} products "
                        f"for '{search_query}' on {platform}"
                    )
                else:
                    error_msg = result.error_message if result else "No result"
                    logger.warning(f"Generic scraper returned no products: {error_msg}")
                    
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Generic scraper timeout for {platform}")
            except Exception as e:
                logger.warning(f"Generic scraper failed: {e}")
        
        logger.info(f"📦 Total: {len(products)} products for '{search_query}' on {platform}")
        
    except Exception as e:
        logger.error(f"Scraping failed for {category}/{platform}/{keyword}: {e}")
    
    return products[:max_products]


# =============================================================================
# SYSTEM LOG INTEGRATION
# =============================================================================

async def log_seeding_results(
    db: AsyncSession,
    category: str,
    platform: str,
    keyword: str,
    products_found: int,
    new_products: int,
    updated_products: int,
    errors: int,
    duration_seconds: float
) -> None:
    """Log seeding results to SystemLog table"""
    try:
        today = date.today()
        
        # Get or create today's log
        result = await db.execute(
            select(SystemLog).where(SystemLog.log_date == today)
        )
        system_log = result.scalar_one_or_none()
        
        seeding_data = {
            "category": category,
            "platform": platform,
            "keyword": keyword,
            "products_found": products_found,
            "new_products": new_products,
            "updated_products": updated_products,
            "errors": errors,
            "duration_seconds": round(duration_seconds, 2),
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if system_log:
            # Update existing log
            scraping_summary = system_log.scraping_summary or {}
            seeding_history = scraping_summary.get("seeding", [])
            
            if not isinstance(seeding_history, list):
                seeding_history = []
            
            seeding_history.append(seeding_data)
            scraping_summary["seeding"] = seeding_history
            scraping_summary["last_seeding"] = seeding_data
            
            system_log.scraping_summary = scraping_summary
        else:
            # Create new log entry
            system_log = SystemLog(
                log_date=today,
                scraping_summary={
                    "seeding": [seeding_data],
                    "last_seeding": seeding_data,
                },
                analytics={},
                ml_processing={},
            )
            db.add(system_log)
        
        await db.commit()
        
    except Exception as e:
        logger.error(f"Failed to log seeding results: {e}")


# =============================================================================
# MAIN JOB FUNCTION
# =============================================================================

async def run_seed_products() -> Dict[str, Any]:
    """
    Main seeding job - runs daily at 3:00 AM IST
    
    Returns:
        Dict with job results for scheduler logging
    """
    # Check if seeding is enabled
    if not getattr(settings, 'ENABLE_PRODUCT_SEEDING', True):
        logger.info("⏭️ Product seeding is DISABLED in settings")
        return {
            "success": True,
            "skipped": True,
            "reason": "ENABLE_PRODUCT_SEEDING is False"
        }
    
    start_time = datetime.utcnow()
    logger.info("🌱 Starting Trend Hunter & Database Seeder")
    
    # Stats tracking
    total_found = 0
    total_new = 0
    total_updated = 0
    total_errors = 0
    processed_products = 0
    
    try:
        # Get rotation state
        state = await get_rotation_state()
        category, platform, keyword, new_state = get_next_rotation(state)
        
        logger.info(
            f"📍 Rotation: Category={category}, Platform={platform}, Keyword={keyword}"
        )
        
        async with async_session_maker() as db:
            # Scrape products
            products = await scrape_trending_products(
                category=category,
                platform=platform,
                keyword=keyword,
                db=db,
                max_products=PRODUCTS_PER_KEYWORD
            )
            
            total_found = len(products)
            
            if not products:
                logger.warning(f"No products found for {category}/{platform}/{keyword}")
            else:
                # Process each product
                for product_data in products:
                    if processed_products >= MAX_PRODUCTS_PER_RUN:
                        logger.info(f"Reached max products per run ({MAX_PRODUCTS_PER_RUN})")
                        break
                    
                    try:
                        # Generate fingerprint first
                        fingerprint = await generate_fingerprint(product_data)
                        product_data.fingerprint = fingerprint
                        
                        # Check if exists BEFORE AI call (save quota!)
                        existing = await check_product_exists(fingerprint, db)
                        
                        if existing:
                            # Re-discovered - dynamic boost (no AI call needed)
                            existing.stats = calculate_rediscovery_boost(
                                existing.stats or {}, product_data
                            )
                            await db.commit()
                            
                            total_updated += 1
                            logger.debug(
                                f"♻️ Boosted (seed_score="
                                f"{existing.stats.get('seed_score', 0)}): "
                                f"{existing.title[:40]}..."
                            )
                            
                        else:
                            # New product - need AI enrichment
                            product_data = await enrich_product_with_ai(product_data)
                            
                            # Save with dynamic scoring
                            saved = await save_seeded_product(
                                product_data=product_data,
                                db=db,
                                is_new=True
                            )
                            
                            if saved:
                                total_new += 1
                                logger.debug(
                                    f"✨ New (seed_score="
                                    f"{saved.stats.get('seed_score', 0)}): "
                                    f"{saved.title[:40]}..."
                                )
                            else:
                                total_errors += 1
                        
                        processed_products += 1
                        
                    except Exception as e:
                        total_errors += 1
                        logger.error(f"Error processing product: {e}")
                        continue
            
            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            # Log results to SystemLog
            await log_seeding_results(
                db=db,
                category=category,
                platform=platform,
                keyword=keyword,
                products_found=total_found,
                new_products=total_new,
                updated_products=total_updated,
                errors=total_errors,
                duration_seconds=duration,
            )
        
        # Save rotation state for next run
        await save_rotation_state(
            category_index=new_state["category_index"],
            platform_index=new_state["platform_index"],
            keyword_index=new_state["keyword_index"],
        )
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Clear trending cache so new products appear
        await redis_client.delete("trending:products:top50")
        
        logger.info(
            f"🌱 Seeding COMPLETED in {duration:.1f}s | "
            f"Found: {total_found} | New: {total_new} | "
            f"Updated: {total_updated} | Errors: {total_errors}"
        )
        
        return {
            "success": True,
            "category": category,
            "platform": platform,
            "keyword": keyword,
            "products_found": total_found,
            "new_products": total_new,
            "updated_products": total_updated,
            "errors": total_errors,
            "duration_seconds": round(duration, 2),
            "next_rotation": new_state,
        }
        
    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"❌ Seeding job FAILED: {e}\n{traceback.format_exc()}")
        
        return {
            "success": False,
            "error": str(e),
            "products_found": total_found,
            "new_products": total_new,
            "updated_products": total_updated,
            "errors": total_errors,
            "duration_seconds": round(duration, 2),
        }


# =============================================================================
# MANUAL TRIGGER SUPPORT
# =============================================================================

async def seed_specific(
    category: str,
    platform: str,
    keyword: str
) -> Dict[str, Any]:
    """
    Manually seed a specific category/platform/keyword
    Useful for admin dashboard or testing
    
    Usage:
        from jobs.seed_products import seed_specific
        result = await seed_specific("Smartphones", "amazon", "Best Selling")
    """
    logger.info(f"🎯 Manual seed: {category}/{platform}/{keyword}")
    
    start_time = datetime.utcnow()
    total_new = 0
    total_updated = 0
    total_errors = 0
    
    async with async_session_maker() as db:
        products = await scrape_trending_products(
            category=category,
            platform=platform,
            keyword=keyword,
            db=db,
        )
        
        for product_data in products[:MAX_PRODUCTS_PER_RUN]:
            try:
                fingerprint = await generate_fingerprint(product_data)
                product_data.fingerprint = fingerprint
                
                existing = await check_product_exists(fingerprint, db)
                
                if existing:
                    # Re-discovered - dynamic boost
                    existing.stats = calculate_rediscovery_boost(
                        existing.stats or {}, product_data
                    )
                    await db.commit()
                    total_updated += 1
                else:
                    # New product - enrich and save
                    product_data = await enrich_product_with_ai(product_data)
                    saved = await save_seeded_product(product_data, db, is_new=True)
                    if saved:
                        total_new += 1
                    else:
                        total_errors += 1
                        
            except Exception as e:
                total_errors += 1
                logger.error(f"Manual seed error: {e}")
    
    # Clear trending cache
    await redis_client.delete("trending:products:top50")
    
    duration = (datetime.utcnow() - start_time).total_seconds()
    
    return {
        "success": True,
        "category": category,
        "platform": platform,
        "keyword": keyword,
        "products_found": len(products),
        "new_products": total_new,
        "updated_products": total_updated,
        "errors": total_errors,
        "duration_seconds": round(duration, 2),
    }
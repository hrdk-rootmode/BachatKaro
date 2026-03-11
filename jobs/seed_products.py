"""
Product Seeder with Rotation System
===================================

Runs at 3:00 AM IST to add new products via category/platform rotation

Features:
- Rotation-based seeding (different category/platform each day)
- Fingerprint check BEFORE AI call (saves quota)
- AI enrichment for new products only
- Dynamic scoring (no fake views)
- State persistence for rotation continuity

Rotation Flow:
Day 1: Electronics + Amazon
Day 2: Fashion + Amazon
Day 3: Beauty + Amazon
Day 4: Home + Amazon
Day 5: Grocery + Amazon
Day 6: Electronics + Flipkart
... (cycles through all combinations)

Author: DealHunt
Version: 2.0 (Cleaned & Enhanced)
"""

import logging
import asyncio
import hashlib
import json
from datetime import datetime, date
from typing import Dict, List, Any, Optional
from decimal import Decimal

# Add parent directory to Python path for imports
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import Product, ProductListing, Platform, SystemLog

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

CATEGORIES = ["Electronics", "Fashion", "Beauty", "Home", "Grocery"]
PLATFORMS = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
PRODUCTS_PER_RUN = 10
SEARCH_KEYWORDS = ["Best Selling", "Top Rated", "Trending", "Popular"]


# =============================================================================
# PRODUCT SEEDER CLASS
# =============================================================================

class ProductSeeder:
    """Efficient product seeder with rotation and AI enrichment"""
    
    def __init__(self):
        self.stats = {
            "products_fetched": 0,
            "products_saved": 0,
            "duplicates_skipped": 0,
            "ai_enriched": 0,
            "errors": []
        }
    
    async def get_rotation_state(self, db: AsyncSession) -> Dict[str, Any]:
        """Get current rotation state from database"""
        try:
            today = date.today()
            
            result = await db.execute(
                select(SystemLog).where(SystemLog.log_date == today)
            )
            system_log = result.scalar_one_or_none()
            
            if system_log and system_log.ml_processing:
                state = system_log.ml_processing.get("seeder_rotation")
                if state:
                    return state
            
            # Default rotation state
            return {
                "category_index": 0,
                "platform_index": 0,
                "last_run": None
            }
            
        except Exception as e:
            logger.warning(f"Error getting rotation state: {e}")
            return {
                "category_index": 0,
                "platform_index": 0,
                "last_run": None
            }
    
    async def update_rotation_state(self, db: AsyncSession, state: Dict[str, Any]):
        """Update rotation state in database"""
        try:
            today = date.today()
            
            result = await db.execute(
                select(SystemLog).where(SystemLog.log_date == today)
            )
            system_log = result.scalar_one_or_none()
            
            if system_log:
                ml_processing = system_log.ml_processing or {}
                ml_processing["seeder_rotation"] = state
                system_log.ml_processing = ml_processing
            else:
                system_log = SystemLog(
                    log_date=today,
                    scraping_summary={},
                    analytics={},
                    ml_processing={"seeder_rotation": state}
                )
                db.add(system_log)
            
            await db.commit()
            
        except Exception as e:
            logger.warning(f"Error updating rotation state: {e}")
    
    def generate_fingerprint(self, title: str, brand: str = None) -> str:
        """Generate product fingerprint for deduplication"""
        normalized = title.lower().strip()
        if brand:
            normalized = f"{brand.lower().strip()}_{normalized}"
        
        return hashlib.sha256(normalized.encode()).hexdigest()[:64]
    
    async def check_duplicate(self, fingerprint: str, db: AsyncSession) -> bool:
        """Check if product already exists"""
        try:
            result = await db.execute(
                select(Product.id).where(Product.fingerprint == fingerprint).limit(1)
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.warning(f"Error checking duplicate: {e}")
            return False
    
    async def get_platform_id(self, platform_name: str, db: AsyncSession) -> Optional[int]:
        """Get platform ID from database"""
        try:
            result = await db.execute(
                select(Platform.id).where(Platform.name == platform_name.lower())
            )
            row = result.scalar_one_or_none()
            return row if row else None
        except Exception as e:
            logger.warning(f"Error getting platform ID: {e}")
            return None
    
    async def fetch_products_from_platform(
        self, 
        platform_name: str, 
        category: str, 
        db: AsyncSession
    ) -> List[Any]:
        """Fetch products from platform"""
        products = []
        
        try:
            from app.services.scraper.factory import get_platform_handler
            
            handler = await get_platform_handler(platform_name, db)
            if not handler:
                logger.warning(f"No handler for platform: {platform_name}")
                return products
            
            # Try different search queries
            for keyword in SEARCH_KEYWORDS:
                if len(products) >= PRODUCTS_PER_RUN:
                    break
                
                query = f"{category} {keyword}"
                logger.info(f"🔍 Searching {platform_name}: {query}")
                
                try:
                    result = await asyncio.wait_for(
                        handler.search(query=query, page=1),
                        timeout=30
                    )
                    
                    if result and result.success and result.products:
                        for p in result.products:
                            if len(products) >= PRODUCTS_PER_RUN:
                                break
                            p.platform_name = platform_name
                            products.append(p)
                            self.stats["products_fetched"] += 1
                            
                except asyncio.TimeoutError:
                    logger.debug(f"Timeout searching {platform_name}")
                except Exception as e:
                    logger.debug(f"Search error: {e}")
            
            logger.info(f"✅ Found {len(products)} products from {platform_name}")
            
        except Exception as e:
            error_msg = f"Error fetching from {platform_name}: {e}"
            logger.error(error_msg)
            self.stats["errors"].append(error_msg)
        
        return products
    
    async def enrich_product_with_ai(self, product_data) -> bool:
        """Enrich product with AI"""
        try:
            from app.services.ai.groq_client import groq_client
            
            # Generate essence
            title = getattr(product_data, 'title', '')
            brand = getattr(product_data, 'brand', None)
            specs = getattr(product_data, 'specifications', {})
            
            essence = await groq_client.generate_essence(
                title=title,
                brand=brand,
                specs=specs or {}
            )
            
            # Generate tags
            tags = await groq_client.generate_tags(
                title=title,
                description=None
            )
            
            # Set AI metadata
            product_data.ai_essence = essence
            product_data.ai_tags = tags
            product_data.ai_quality_score = self._calculate_quality_score(product_data)
            product_data.ai_processed = True
            
            self.stats["ai_enriched"] += 1
            logger.debug(f"🤖 AI enriched: {title[:30]}...")
            
            return True
            
        except Exception as e:
            logger.debug(f"AI enrichment skipped: {e}")
            return False
    
    def _calculate_quality_score(self, product_data) -> int:
        """Calculate quality score for product"""
        score = 40  # Base score
        
        # Check data completeness
        if getattr(product_data, 'title', None) and len(product_data.title) > 10:
            score += 15
        if getattr(product_data, 'brand', None) and product_data.brand != 'Unknown':
            score += 10
        if getattr(product_data, 'category', None) and product_data.category != 'General':
            score += 10
        if getattr(product_data, 'image_url', None):
            score += 10
        if getattr(product_data, 'ai_essence', None):
            score += 10
        if getattr(product_data, 'ai_tags', None):
            score += 5
        
        return min(score, 100)
    
    def _extract_subcategory(self, title: str, category: str) -> str:
        """Extract subcategory from title"""
        title_lower = title.lower()
        
        subcategory_map = {
            "electronics": {
                "phone": "Mobile Phone",
                "mobile": "Mobile Phone",
                "laptop": "Laptop",
                "headphone": "Headphones",
                "earphone": "Earphones",
                "camera": "Camera",
                "tv": "Television",
                "tablet": "Tablet",
                "watch": "Smart Watch",
            },
            "fashion": {
                "shirt": "Shirt",
                "t-shirt": "T-Shirt",
                "dress": "Dress",
                "jeans": "Jeans",
                "kurta": "Kurta",
                "saree": "Saree",
                "shoes": "Footwear",
            },
            "beauty": {
                "lipstick": "Lipstick",
                "cream": "Cream",
                "shampoo": "Hair Care",
                "perfume": "Fragrance",
            }
        }
        
        keywords = subcategory_map.get(category.lower(), {})
        
        for keyword, subcat in keywords.items():
            if keyword in title_lower:
                return subcat
        
        return "General"
    
    async def save_product_to_database(
        self, 
        product_data, 
        platform_id: int, 
        db: AsyncSession
    ) -> bool:
        """Save product to database"""
        try:
            title = getattr(product_data, 'title', 'Unknown')
            brand = getattr(product_data, 'brand', None)
            
            fingerprint = self.generate_fingerprint(title, brand)
            
            # Build AI metadata
            ai_metadata = {
                "essence": getattr(product_data, 'ai_essence', '') or title[:100].lower(),
                "tags": getattr(product_data, 'ai_tags', []) or [],
                "quality_score": getattr(product_data, 'ai_quality_score', 50) or 50,
                "processed_at": datetime.utcnow().isoformat(),
                "seeded": True
            }
            
            # Create product
            category = getattr(product_data, 'category', None) or "General"
            
            product = Product(
                fingerprint=fingerprint,
                title=title,
                brand=brand or "Unknown",
                image_url=getattr(product_data, 'image_url', None),
                category=category,
                subcategory=self._extract_subcategory(title, category),
                specifications=getattr(product_data, 'specifications', {}) or {},
                ai_metadata=ai_metadata,
                stats={
                    "views": 0,
                    "clicks": 0,
                    "watches": 0,
                    "searches": 0,
                    "conversions": 0,
                    "seed_score": ai_metadata.get("quality_score", 50),
                    "seeded": True
                }
            )
            
            db.add(product)
            await db.flush()
            
            # Create listing
            current_price = getattr(product_data, 'current_price', None)
            original_price = getattr(product_data, 'original_price', None)
            
            listing = ProductListing(
                product_id=product.id,
                platform_id=platform_id,
                product_url=getattr(product_data, 'product_url', ''),
                current_price=float(current_price) if current_price else 0,
                original_price=float(original_price) if original_price else None,
                rating=getattr(product_data, 'rating', None),
                review_count=getattr(product_data, 'review_count', None),
                in_stock=getattr(product_data, 'in_stock', True),
                last_scraped=datetime.utcnow()
            )
            
            db.add(listing)
            
            self.stats["products_saved"] += 1
            logger.info(f"💾 Saved: {title[:40]}...")
            
            return True
            
        except Exception as e:
            error_msg = f"Save failed: {e}"
            logger.error(error_msg)
            self.stats["errors"].append(error_msg)
            return False
    
    async def run_seeding(self) -> Dict[str, Any]:
        """Main seeding process"""
        logger.info("🌱 Starting product seeding...")
        start_time = datetime.utcnow()
        
        try:
            async with async_session_maker() as db:
                # Get rotation state
                rotation_state = await self.get_rotation_state(db)
                
                # Get current category and platform
                category_index = rotation_state["category_index"] % len(CATEGORIES)
                platform_index = rotation_state["platform_index"] % len(PLATFORMS)
                
                current_category = CATEGORIES[category_index]
                current_platform = PLATFORMS[platform_index]
                
                logger.info(f"📂 Category: {current_category} | Platform: {current_platform}")
                
                # Get platform ID
                platform_id = await self.get_platform_id(current_platform, db)
                
                if not platform_id:
                    logger.error(f"Platform not found: {current_platform}")
                    return {
                        "success": False,
                        "error": f"Platform not found: {current_platform}"
                    }
                
                # Fetch products
                products = await self.fetch_products_from_platform(
                    current_platform, 
                    current_category, 
                    db
                )
                
                if not products:
                    logger.info("No products to process")
                else:
                    # Process each product
                    for product_data in products:
                        title = getattr(product_data, 'title', '')
                        brand = getattr(product_data, 'brand', None)
                        
                        fingerprint = self.generate_fingerprint(title, brand)
                        
                        # Check for duplicates BEFORE AI call
                        if await self.check_duplicate(fingerprint, db):
                            self.stats["duplicates_skipped"] += 1
                            logger.debug(f"🔄 Duplicate: {title[:30]}...")
                            continue
                        
                        # Enrich with AI (only for new products)
                        await self.enrich_product_with_ai(product_data)
                        
                        # Save to database
                        await self.save_product_to_database(product_data, platform_id, db)
                    
                    await db.commit()
                
                # Update rotation for next run
                next_category_index = (category_index + 1) % len(CATEGORIES)
                next_platform_index = platform_index
                
                # Rotate platform after all categories
                if next_category_index == 0:
                    next_platform_index = (platform_index + 1) % len(PLATFORMS)
                
                new_rotation_state = {
                    "category_index": next_category_index,
                    "platform_index": next_platform_index,
                    "last_run": datetime.utcnow().isoformat()
                }
                
                await self.update_rotation_state(db, new_rotation_state)
                
                duration = (datetime.utcnow() - start_time).total_seconds()
                
                logger.info("✅ Seeding completed")
                logger.info(
                    f"📊 Results: Fetched={self.stats['products_fetched']}, "
                    f"Saved={self.stats['products_saved']}, "
                    f"Skipped={self.stats['duplicates_skipped']}, "
                    f"AI Enriched={self.stats['ai_enriched']}, "
                    f"Duration={duration:.1f}s"
                )
                
                return {
                    "success": True,
                    "category": current_category,
                    "platform": current_platform,
                    "stats": self.stats,
                    "duration_seconds": round(duration, 2),
                    "next_rotation": new_rotation_state
                }
                
        except Exception as e:
            logger.error(f"❌ Seeding failed: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "error": str(e),
                "stats": self.stats
            }


# =============================================================================
# MAIN JOB FUNCTION
# =============================================================================

async def run_seed_products() -> Dict[str, Any]:
    """Main job function for scheduler"""
    seeder = ProductSeeder()
    return await seeder.run_seeding()


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("🌱 Starting Product Seeding Job...")
    print("=" * 60)
    
    async def main():
        try:
            result = await run_seed_products()
            
            print("\n📊 Results:")
            print(f"   Success: {result.get('success', False)}")
            print(f"   Category: {result.get('category', 'N/A')}")
            print(f"   Platform: {result.get('platform', 'N/A')}")
            
            stats = result.get("stats", {})
            print(f"   Fetched: {stats.get('products_fetched', 0)}")
            print(f"   Saved: {stats.get('products_saved', 0)}")
            print(f"   Skipped: {stats.get('duplicates_skipped', 0)}")
            print(f"   AI Enriched: {stats.get('ai_enriched', 0)}")
            print(f"   Duration: {result.get('duration_seconds', 0)}s")
            
            if result.get("error"):
                print(f"\n❌ Error: {result['error']}")
            else:
                print("\n✅ Job completed successfully!")
                
        except Exception as e:
            print(f"\n💥 Critical error: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(main())
    print("\n🏁 Product seeding job finished.")
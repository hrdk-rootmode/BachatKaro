"""
Fix platforms table - FORCE INSERT data even if exists check fails
Run: python scripts/fix_platforms.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import text
from app.core.database import async_session_maker, engine
from app.core.database import Base

async def fix_platforms():
    """Force insert platforms into database"""
    print("🔧 Fixing platforms table...\n")
    
    async with async_session_maker() as db:
        # First check if table exists and has data
        result = await db.execute(text("SELECT COUNT(*) FROM platforms"))
        count = result.scalar()
        print(f"Current platform count: {count}")
        
        if count > 0:
            print("Deleting existing data...")
            await db.execute(text("DELETE FROM platforms"))
            await db.commit()
        
        # Insert all platforms with proper JSONB selectors
        platforms_sql = """
        INSERT INTO platforms (name, base_url, affiliate_tag, selectors, is_active, scrape_delay_seconds, created_at, updated_at)
        VALUES 
        ('amazon', 'https://www.amazon.in', 'dealhunt-21', 
         '{"search_url_template": "https://www.amazon.in/s?k={query}", "product_title": "#productTitle", "product_price": ".a-price-whole", "product_image": "#landingImage", "product_rating": "#acrPopover", "rate_limit": 30}'::jsonb,
         true, 2, NOW(), NOW()),
         
        ('flipkart', 'https://www.flipkart.com', 'dealhunt',
         '{"search_url_template": "https://www.flipkart.com/search?q={query}", "product_title": "span.B_NuCI", "product_price": "div._30jeq3._16Jk6d", "product_image": "img._396cs4._3exPp9", "product_rating": "div._3LWZlK", "rate_limit": 30}'::jsonb,
         true, 2, NOW(), NOW()),
         
        ('meesho', 'https://www.meesho.com', NULL,
         '{"search_url_template": "https://www.meesho.com/search?q={query}", "rate_limit": 20}'::jsonb,
         true, 2, NOW(), NOW()),
         
        ('myntra', 'https://www.myntra.com', NULL,
         '{"search_url_template": "https://www.myntra.com/search?q={query}", "rate_limit": 25}'::jsonb,
         true, 2, NOW(), NOW()),
         
        ('croma', 'https://www.croma.com', NULL,
         '{"search_url_template": "https://www.croma.com/search?q={query}", "rate_limit": 20}'::jsonb,
         true, 2, NOW(), NOW()),
         
        ('nykaa', 'https://www.nykaa.com', NULL,
         '{"search_url_template": "https://www.nykaa.com/search?q={query}", "rate_limit": 25}'::jsonb,
         true, 2, NOW(), NOW())
        """
        
        await db.execute(text(platforms_sql))
        await db.commit()
        
        # Verify
        result = await db.execute(text("SELECT name, is_active FROM platforms ORDER BY name"))
        rows = result.all()
        print(f"\n✅ Inserted {len(rows)} platforms:")
        for row in rows:
            print(f"   - {row[0]} (active={row[1]})")
        
        print("\n🎉 Platforms table fixed!")

if __name__ == "__main__":
    asyncio.run(fix_platforms())

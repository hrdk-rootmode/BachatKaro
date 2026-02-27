"""
Seed platforms into database
Run once: python scripts/seed_platforms.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session_maker
from app.models import Platform

async def seed_platforms():
    """Seed platform configurations into database"""
    platforms = [
        {
            "name": "amazon",
            "base_url": "https://www.amazon.in",
            "affiliate_tag": "dealhunt-21",
            "selectors": {
                "search_url_template": "https://www.amazon.in/s?k={query}",
                "product_title": "#productTitle",
                "product_price": ".a-price-whole",
                "product_image": "#landingImage",
                "product_rating": "#acrPopover",
                "product_url": "a.a-link-normal.s-no-outline",
                "rate_limit": 30
            }
        },
        {
            "name": "flipkart",
            "base_url": "https://www.flipkart.com",
            "affiliate_tag": "dealhunt",
            "selectors": {
                "search_url_template": "https://www.flipkart.com/search?q={query}",
                "product_title": "span.B_NuCI",
                "product_price": "div._30jeq3._16Jk6d",
                "product_image": "img._396cs4._3exPp9",
                "product_rating": "div._3LWZlK",
                "product_url": "a._1fQZEK",
                "rate_limit": 30
            }
        },
        {
            "name": "meesho",
            "base_url": "https://www.meesho.com",
            "affiliate_tag": None,
            "selectors": {
                "search_url_template": "https://www.meesho.com/search?q={query}",
                "rate_limit": 20
            }
        },
        {
            "name": "myntra",
            "base_url": "https://www.myntra.com",
            "affiliate_tag": None,
            "selectors": {
                "search_url_template": "https://www.myntra.com/search?q={query}",
                "rate_limit": 25
            }
        },
        {
            "name": "croma",
            "base_url": "https://www.croma.com",
            "affiliate_tag": None,
            "selectors": {
                "search_url_template": "https://www.croma.com/search?q={query}",
                "rate_limit": 20
            }
        },
        {
            "name": "nykaa",
            "base_url": "https://www.nykaa.com",
            "affiliate_tag": None,
            "selectors": {
                "search_url_template": "https://www.nykaa.com/search?q={query}",
                "rate_limit": 25
            }
        }
    ]
    
    async with async_session_maker() as db:
        for p in platforms:
            # Check if exists
            from sqlalchemy import select
            result = await db.execute(
                select(Platform).where(Platform.name == p["name"])
            )
            if result.scalar_one_or_none():
                print(f"Skipping {p['name']} - already exists")
                continue
            
            platform = Platform(
                name=p["name"],
                base_url=p["base_url"],
                affiliate_tag=p["affiliate_tag"],
                selectors=p["selectors"],
                is_active=True,
                scrape_delay_seconds=2
            )
            db.add(platform)
            print(f"Added {p['name']}")
        
        await db.commit()
        print("✅ Platforms seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_platforms())

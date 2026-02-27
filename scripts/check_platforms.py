"""
Check platforms table data
Run: python scripts/check_platforms.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import select, func
from app.core.database import async_session_maker
from app.models import Platform

async def check_platforms():
    """Check platforms table data"""
    async with async_session_maker() as db:
        # Count platforms
        result = await db.execute(select(func.count(Platform.id)))
        count = result.scalar()
        print(f"Total platforms in database: {count}")
        
        if count == 0:
            print("❌ Platforms table is EMPTY!")
            return
        
        # List all platforms
        result = await db.execute(select(Platform))
        platforms = result.scalars().all()
        
        print("\n📋 Platforms in database:")
        for p in platforms:
            print(f"  - {p.name}: active={p.is_active}, selectors={len(p.selectors) if p.selectors else 0} keys")

if __name__ == "__main__":
    asyncio.run(check_platforms())

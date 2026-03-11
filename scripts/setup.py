#!/usr/bin/env python3
"""
DealHunt Setup Script
=====================

First-time project setup & health verification.

Features:
- Creates all database tables
- Tests Redis connection
- Seeds platform records (Amazon, Flipkart, etc.)
- Tests Groq AI connection
- Seeds subscription plans
- Prints setup summary

Usage:
    python scripts/setup.py
    python scripts/setup.py --skip-ai      # Skip AI verification
    python scripts/setup.py --reset-db     # Drop and recreate tables
    python scripts/setup.py --seed-plans   # Seed subscription plans only

Author: DealHunt
Version: 1.0
"""

import asyncio
import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from sqlalchemy import text

# Core imports
from app.core.database import engine, async_session_maker, Base
from app.core.redis_client import redis_client
from app.core.config import settings
from app.models import Platform, SubscriptionPlan, AppConfig


# =============================================================================
# CONFIGURATION
# =============================================================================

PLATFORMS_TO_SEED = [
    {
        "name": "amazon",
        "base_url": "https://www.amazon.in",
        "affiliate_tag": getattr(settings, 'AMAZON_AFFILIATE_TAG', None),
        "is_active": True,
    },
    {
        "name": "flipkart",
        "base_url": "https://www.flipkart.com",
        "affiliate_tag": getattr(settings, 'FLIPKART_AFFILIATE_TAG', None),
        "is_active": True,
    },
    {
        "name": "myntra",
        "base_url": "https://www.myntra.com",
        "affiliate_tag": None,
        "is_active": True,
    },
    {
        "name": "nykaa",
        "base_url": "https://www.nykaa.com",
        "affiliate_tag": None,
        "is_active": True,
    },
    {
        "name": "croma",
        "base_url": "https://www.croma.com",
        "affiliate_tag": None,
        "is_active": True,
    },
    {
        "name": "meesho",
        "base_url": "https://www.meesho.com",
        "affiliate_tag": None,
        "is_active": True,
    },
]

SUBSCRIPTION_PLANS = [
    {
        "name": "free",
        "display_name": "Free",
        "price_inr": 0,
        "price_usd": 0,
        "duration_days": 36500,  # ~100 years
        "features": {
            "daily_searches": 10,
            "watchlist_limit": 5,
            "price_alerts": False,
            "ai_chat_queries": 0,
            "ad_free": False,
            "streak_freezes": 2,
            "priority_support": False,
            "export_data": False,
            "api_access": False
        },
        "badge_color": "#6B7280",
        "badge_emoji": "🆓",
        "tagline": "Get started for free",
        "is_popular": False,
        "sort_order": 0
    },
    {
        "name": "pro",
        "display_name": "Pro",
        "price_inr": 49,
        "price_usd": 0.59,
        "duration_days": 30,
        "features": {
            "daily_searches": 50,
            "watchlist_limit": 25,
            "price_alerts": True,
            "ai_chat_queries": 10,
            "ad_free": True,
            "streak_freezes": 5,
            "priority_support": False,
            "export_data": True,
            "api_access": False
        },
        "badge_color": "#3B82F6",
        "badge_emoji": "⭐",
        "tagline": "For smart shoppers",
        "is_popular": True,
        "sort_order": 1
    },
    {
        "name": "premium",
        "display_name": "Premium",
        "price_inr": 149,
        "price_usd": 1.79,
        "duration_days": 30,
        "features": {
            "daily_searches": -1,  # Unlimited
            "watchlist_limit": -1,  # Unlimited
            "price_alerts": True,
            "ai_chat_queries": -1,  # Unlimited
            "ad_free": True,
            "streak_freezes": -1,  # Unlimited
            "priority_support": True,
            "export_data": True,
            "api_access": True
        },
        "badge_color": "#F59E0B",
        "badge_emoji": "👑",
        "tagline": "Unlimited everything",
        "is_popular": False,
        "sort_order": 2
    },
]


# =============================================================================
# SETUP FUNCTIONS
# =============================================================================

async def check_database() -> bool:
    """Test database connection"""
    print("\n📊 Checking Database...")
    
    try:
        async with async_session_maker() as db:
            result = await db.execute(text("SELECT 1"))
            result.scalar()
            
            # Get database info
            size_result = await db.execute(text(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            ))
            db_size = size_result.scalar() or "Unknown"
            
            version_result = await db.execute(text("SELECT version()"))
            version = version_result.scalar() or "Unknown"
            
        print(f"   ✅ Database connected")
        print(f"   📦 Size: {db_size}")
        print(f"   🔢 Version: {version[:50]}...")
        return True
        
    except Exception as e:
        print(f"   ❌ Database connection failed: {e}")
        return False


async def create_tables(reset: bool = False) -> bool:
    """Create all database tables"""
    print("\n🏗️  Creating Tables...")
    
    try:
        async with engine.begin() as conn:
            if reset:
                print("   ⚠️  Dropping all tables...")
                await conn.run_sync(Base.metadata.drop_all)
            
            await conn.run_sync(Base.metadata.create_all)
        
        # Count tables
        async with async_session_maker() as db:
            result = await db.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            table_count = result.scalar() or 0
        
        print(f"   ✅ Created {table_count} tables")
        return True
        
    except Exception as e:
        print(f"   ❌ Table creation failed: {e}")
        return False


async def check_redis() -> bool:
    """Test Redis connection"""
    print("\n🔴 Checking Redis...")
    
    try:
        # Ensure connection
        await redis_client.connect()
        
        # Test ping
        pong = await redis_client.ping()
        if not pong:
            raise Exception("Ping failed")
        
        # Test set/get
        test_key = "setup:test"
        await redis_client.set(test_key, "working", ttl=10)
        value = await redis_client.get(test_key)
        
        if value != "working":
            raise Exception("Set/Get test failed")
        
        # Get info (your RedisClient has this method)
        info = await redis_client.info()
        memory_section = info if isinstance(info, dict) else {}
        memory_used = memory_section.get("used_memory_human", "Unknown")
        
        # Get key count (use the underlying client)
        keys_count = 0
        if redis_client._client:
            keys_count = await redis_client._client.dbsize()
        
        print(f"   ✅ Redis connected")
        print(f"   💾 Memory: {memory_used}")
        print(f"   🔑 Keys: {keys_count}")
        return True
        
    except Exception as e:
        print(f"   ❌ Redis connection failed: {e}")
        return False

async def seed_platforms() -> int:
    """Seed platform records"""
    print("\n🌐 Seeding Platforms...")
    
    from sqlalchemy import select
    
    created = 0
    updated = 0
    
    try:
        async with async_session_maker() as db:
            for platform_data in PLATFORMS_TO_SEED:
                # Check if exists
                result = await db.execute(
                    select(Platform).where(Platform.name == platform_data["name"])
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update
                    existing.base_url = platform_data["base_url"]
                    existing.affiliate_tag = platform_data["affiliate_tag"]
                    existing.is_active = platform_data["is_active"]
                    updated += 1
                else:
                    # Create
                    platform = Platform(
                        name=platform_data["name"],
                        base_url=platform_data["base_url"],
                        affiliate_tag=platform_data["affiliate_tag"],
                        is_active=platform_data["is_active"],
                        selectors={}
                    )
                    db.add(platform)
                    created += 1
            
            await db.commit()
        
        print(f"   ✅ Platforms: {created} created, {updated} updated")
        
        for p in PLATFORMS_TO_SEED:
            status = "🟢" if p["is_active"] else "🔴"
            print(f"      {status} {p['name'].capitalize()}")
        
        return created + updated
        
    except Exception as e:
        print(f"   ❌ Platform seeding failed: {e}")
        return 0


async def seed_subscription_plans() -> int:
    """Seed subscription plan records"""
    print("\n💳 Seeding Subscription Plans...")
    
    from sqlalchemy import select
    
    created = 0
    updated = 0
    
    try:
        async with async_session_maker() as db:
            for plan_data in SUBSCRIPTION_PLANS:
                # Check if exists
                result = await db.execute(
                    select(SubscriptionPlan).where(SubscriptionPlan.name == plan_data["name"])
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update
                    for key, value in plan_data.items():
                        setattr(existing, key, value)
                    updated += 1
                else:
                    # Create
                    plan = SubscriptionPlan(**plan_data)
                    db.add(plan)
                    created += 1
            
            await db.commit()
        
        print(f"   ✅ Plans: {created} created, {updated} updated")
        
        for p in SUBSCRIPTION_PLANS:
            print(f"      {p['badge_emoji']} {p['display_name']} - ₹{p['price_inr']}/month")
        
        return created + updated
        
    except Exception as e:
        print(f"   ❌ Plan seeding failed: {e}")
        return 0


async def check_groq_ai() -> bool:
    """Test Groq AI connection"""
    print("\n🤖 Checking Groq AI...")
    
    try:
        from app.services.ai.groq_client import groq_client
        
        # Check if API key is configured
        has_key = any(key for key in groq_client.api_keys.values() if key)
        
        if not has_key:
            print("   ⚠️  No Groq API keys configured")
            return False
        
        # Get quota status
        quota_status = await groq_client.get_quota_status()
        
        print(f"   ✅ Groq AI configured")
        print(f"   📊 Quota Status:")
        
        for feature, status in quota_status.items():
            remaining = status.get("remaining", 0)
            limit = status.get("limit", 0)
            print(f"      • {feature}: {remaining}/{limit} remaining")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Groq AI check failed: {e}")
        return False


async def seed_app_config() -> int:
    """Seed default app configuration"""
    print("\n⚙️  Seeding App Config...")
    
    from sqlalchemy import select
    
    default_configs = [
        {
            "key": "maintenance_mode",
            "value": "false",
            "value_type": "boolean",
            "description": "Enable/disable maintenance mode",
            "category": "system",
            "is_public": True
        },
        {
            "key": "max_search_results",
            "value": "50",
            "value_type": "number",
            "description": "Maximum search results per query",
            "category": "limits",
            "is_public": True
        },
        {
            "key": "trending_cache_ttl",
            "value": "3600",
            "value_type": "number",
            "description": "Trending products cache TTL in seconds",
            "category": "cache",
            "is_public": False
        },
    ]
    
    created = 0
    
    try:
        async with async_session_maker() as db:
            for config_data in default_configs:
                result = await db.execute(
                    select(AppConfig).where(AppConfig.key == config_data["key"])
                )
                existing = result.scalar_one_or_none()
                
                if not existing:
                    config = AppConfig(**config_data, updated_by="setup_script")
                    db.add(config)
                    created += 1
            
            await db.commit()
        
        print(f"   ✅ Configs: {created} created")
        return created
        
    except Exception as e:
        print(f"   ❌ Config seeding failed: {e}")
        return 0


def print_summary(results: dict):
    """Print setup summary"""
    print("\n" + "=" * 60)
    print("📋 SETUP SUMMARY")
    print("=" * 60)
    
    all_passed = all([
        results.get("database", False),
        results.get("tables", False),
        results.get("redis", False),
        results.get("platforms", 0) > 0,
    ])
    
    status = "✅ READY" if all_passed else "⚠️  INCOMPLETE"
    
    print(f"\n   Database:     {'✅' if results.get('database') else '❌'}")
    print(f"   Tables:       {'✅' if results.get('tables') else '❌'}")
    print(f"   Redis:        {'✅' if results.get('redis') else '❌'}")
    print(f"   Platforms:    {'✅' if results.get('platforms', 0) > 0 else '❌'} ({results.get('platforms', 0)})")
    print(f"   Plans:        {'✅' if results.get('plans', 0) > 0 else '❌'} ({results.get('plans', 0)})")
    print(f"   Groq AI:      {'✅' if results.get('groq') else '⚠️  (optional)'}")
    
    print(f"\n   Status: {status}")
    print("=" * 60)
    
    if all_passed:
        print("\n🚀 DealHunt is ready! Start the server with:")
        print("   uvicorn app.main:app --reload")
    else:
        print("\n⚠️  Fix the failed checks above before starting.")


# =============================================================================
# MAIN
# =============================================================================

async def main(args):
    """Main setup function"""
    print("=" * 60)
    print("🚀 DEALHUNT SETUP")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = {}
    
    # Step 1: Database
    results["database"] = await check_database()
    
    if not results["database"]:
        print("\n❌ Cannot proceed without database connection!")
        return
    
    # Step 2: Tables
    results["tables"] = await create_tables(reset=args.reset_db)
    
    # Step 3: Redis
    results["redis"] = await check_redis()
    
    # Step 4: Platforms
    results["platforms"] = await seed_platforms()
    
    # Step 5: Plans
    if args.seed_plans or not args.skip_plans:
        results["plans"] = await seed_subscription_plans()
    else:
        results["plans"] = 0
    
    # Step 6: App Config
    await seed_app_config()
    
    # Step 7: Groq AI (optional)
    if not args.skip_ai:
        results["groq"] = await check_groq_ai()
    else:
        results["groq"] = None
        print("\n🤖 Skipping Groq AI check (--skip-ai)")
    
    # Summary
    print_summary(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DealHunt Setup Script")
    parser.add_argument("--skip-ai", action="store_true", help="Skip Groq AI verification")
    parser.add_argument("--skip-plans", action="store_true", help="Skip subscription plans seeding")
    parser.add_argument("--reset-db", action="store_true", help="Drop and recreate all tables")
    parser.add_argument("--seed-plans", action="store_true", help="Seed subscription plans only")
    
    args = parser.parse_args()
    
    asyncio.run(main(args))
#!/usr/bin/env python3
"""
CEO Dashboard Script
====================

Terminal-based status dashboard for DealHunt.

Shows:
- Database stats (products, listings, users)
- Scraper health per platform
- Redis memory usage & key count
- Groq AI quota remaining
- User stats (DAU, MAU, plan breakdown)
- Revenue summary (MRR, today's earnings)

Usage:
    python scripts/status.py
    python scripts/status.py --json
    python scripts/status.py --watch     # Auto-refresh

Author: DealHunt
Version: 1.0
"""

import asyncio
import argparse
import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import glob

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select, func, text
from app.core.database import async_session_maker
from app.core.redis_client import redis_client
from app.core.config import settings
from app.models import User, Product, ProductListing, Platform, Transaction
from app.services.analytics import analytics_service


# =============================================================================
# STATUS FUNCTIONS
# =============================================================================

async def get_database_stats() -> dict:
    """Get database statistics"""
    stats = {}
    
    async with async_session_maker() as db:
        # Products
        result = await db.execute(select(func.count(Product.id)))
        stats["total_products"] = result.scalar() or 0
        
        # Listings
        result = await db.execute(select(func.count(ProductListing.id)))
        stats["total_listings"] = result.scalar() or 0
        
        # In-stock listings
        result = await db.execute(
            select(func.count(ProductListing.id))
            .where(ProductListing.in_stock == True)
        )
        stats["in_stock_listings"] = result.scalar() or 0
        
        # Users
        result = await db.execute(select(func.count(User.id)))
        stats["total_users"] = result.scalar() or 0
        
        # Active users (last 24h)
        yesterday = datetime.utcnow() - timedelta(days=1)
        result = await db.execute(
            select(func.count(User.id))
            .where(User.last_active >= yesterday)
        )
        stats["active_users_24h"] = result.scalar() or 0
        
        # Database size
        result = await db.execute(text(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        ))
        stats["database_size"] = result.scalar() or "Unknown"
    
    return stats


async def get_user_stats() -> dict:
    """Get user statistics"""
    stats = {}
    
    async with async_session_maker() as db:
        # By plan
        result = await db.execute(
            select(User.plan, func.count(User.id))
            .group_by(User.plan)
        )
        plan_counts = {row[0]: row[1] for row in result.all()}
        
        stats["free_users"] = plan_counts.get("free", 0)
        stats["pro_users"] = plan_counts.get("pro", 0)
        stats["premium_users"] = plan_counts.get("premium", 0)
        
        # DAU/WAU/MAU
        stats["dau"] = await analytics_service.get_active_users_count(db, "daily")
        stats["wau"] = await analytics_service.get_active_users_count(db, "weekly")
        stats["mau"] = await analytics_service.get_active_users_count(db, "monthly")
        
        # MRR
        stats["mrr"] = await analytics_service.calculate_mrr(db)
    
    return stats


async def get_platform_stats() -> dict:
    """Get per-platform statistics"""
    stats = {}
    
    async with async_session_maker() as db:
        result = await db.execute(
            select(Platform).where(Platform.is_active == True)
        )
        platforms = result.scalars().all()
        
        for platform in platforms:
            listing_result = await db.execute(
                select(
                    func.count(ProductListing.id),
                    func.count(ProductListing.id).filter(ProductListing.in_stock == True)
                )
                .where(ProductListing.platform_id == platform.id)
            )
            row = listing_result.one()
            
            stats[platform.name] = {
                "total_listings": row[0],
                "in_stock": row[1],
                "has_affiliate": bool(platform.affiliate_tag),
            }
    
    return stats


async def get_redis_stats() -> dict:
    """Get Redis statistics"""
    stats = {}
    
    try:
        # Ensure connected
        await redis_client.connect()
        
        # Test ping
        pong = await redis_client.ping()
        
        if pong:
            stats["status"] = "connected"
            
            # Get memory info
            info = await redis_client.info()
            if isinstance(info, dict):
                stats["memory_used"] = info.get("used_memory_human", "Unknown")
                stats["memory_peak"] = info.get("used_memory_peak_human", "Unknown")
            else:
                stats["memory_used"] = "Unknown"
                stats["memory_peak"] = "Unknown"
            
            # Get total keys
            if redis_client._client:
                stats["total_keys"] = await redis_client._client.dbsize()
            else:
                stats["total_keys"] = 0
        else:
            stats["status"] = "ping failed"
            
    except Exception as e:
        stats["status"] = f"error: {e}"
    
    return stats

async def get_groq_stats() -> dict:
    """Get Groq AI quota statistics"""
    stats = {}
    
    try:
        from app.services.ai.groq_client import groq_client
        
        quota_status = await groq_client.get_quota_status()
        
        total_used = 0
        total_remaining = 0
        
        for feature, status in quota_status.items():
            total_used += status.get("used", 0)
            total_remaining += status.get("remaining", 0)
        
        stats["total_used_today"] = total_used
        stats["total_remaining"] = total_remaining
        stats["by_feature"] = quota_status
        
    except Exception as e:
        stats["error"] = str(e)
    
    return stats


async def get_revenue_stats() -> dict:
    """Get revenue statistics"""
    stats = {}
    
    async with async_session_maker() as db:
        # Today's revenue
        today = datetime.utcnow().replace(hour=0, minute=0, second=0)
        
        result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.type == "payment",
                Transaction.status == "success",
                Transaction.created_at >= today
            )
        )
        stats["today_revenue"] = float(result.scalar() or 0)
        
        # Affiliate clicks today
        result = await db.execute(
            select(func.count(Transaction.id))
            .where(
                Transaction.type == "affiliate_click",
                Transaction.created_at >= today
            )
        )
        stats["affiliate_clicks_today"] = result.scalar() or 0
        
        # MRR
        stats["mrr"] = await analytics_service.calculate_mrr(db)
    
    return stats


async def get_cross_platform_mining_stats() -> dict:
    """Get cross-platform mining statistics from latest audit log"""
    stats = {
        "status": "no_runs",
        "processed": 0,
        "quality_gate_skipped": 0,
        "stored": 0,
        "ai_verified": 0,
        "ai_rejected": 0,
        "ai_contradictions": 0,
        "retries": 0,
        "image_validations": 0,
        "essence_validations": 0,
        "errors": 0,
        "platforms_matched": {},
        "last_run": None,
    }
    
    try:
        # Find latest mining_audit_*.json file
        audit_files = glob.glob("mining_audit_*.json")
        
        if not audit_files:
            return stats
        
        # Get most recent audit file
        latest_file = max(audit_files, key=os.path.getctime)
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            audit_data = json.load(f)
        
        # Extract summary stats
        if "stats" in audit_data:
            s = audit_data["stats"]
            stats.update({
                "processed": s.get("processed", 0),
                "quality_gate_skipped": s.get("quality_gate_skipped", 0),
                "stored": s.get("stored", 0),
                "ai_verified": s.get("ai_verified", 0),
                "ai_rejected": s.get("ai_rejected", 0),
                "ai_contradictions": s.get("ai_contradictions", 0),
                "retries": s.get("retries", 0),
                "image_validations": s.get("image_validation_fixed", 0),
                "essence_validations": s.get("essence_validation_fixed", 0),
                "errors": s.get("errors", 0),
            })
        
        # Extract platform matches
        if "matches" in audit_data and isinstance(audit_data["matches"], list):
            for match in audit_data["matches"]:
                platform = match.get("platform", "unknown").lower()
                if platform not in stats["platforms_matched"]:
                    stats["platforms_matched"][platform] = 0
                stats["platforms_matched"][platform] += 1
        
        # Get timestamp from filename (mining_audit_YYYYMMDD_HHMMSS.json)
        file_name = os.path.basename(latest_file)
        if "mining_audit_" in file_name:
            time_str = file_name.replace("mining_audit_", "").replace(".json", "")
            try:
                stats["last_run"] = datetime.strptime(time_str, "%Y%m%d_%H%M%S").isoformat()
            except ValueError:
                stats["last_run"] = file_name
        
        stats["status"] = "success"
        
    except Exception as e:
        stats["status"] = f"error: {str(e)[:50]}"
    
    return stats


def print_dashboard(data: dict):
    """Print beautiful terminal dashboard"""
    print("\n" + "═" * 70)
    print("║" + " " * 24 + "📊 DEALHUNT STATUS" + " " * 26 + "║")
    print("║" + " " * 20 + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " * 27 + "║")
    print("═" * 70)
    
    # Database
    db = data.get("database", {})
    print("\n📦 DATABASE")
    print("─" * 40)
    print(f"   Products:     {db.get('total_products', 0):,}")
    print(f"   Listings:     {db.get('total_listings', 0):,} ({db.get('in_stock_listings', 0):,} in stock)")
    print(f"   Users:        {db.get('total_users', 0):,} ({db.get('active_users_24h', 0)} active today)")
    print(f"   Size:         {db.get('database_size', 'N/A')}")
    
    # Users
    users = data.get("users", {})
    print("\n👥 USERS")
    print("─" * 40)
    print(f"   Free:         {users.get('free_users', 0):,}")
    print(f"   Pro:          {users.get('pro_users', 0):,}")
    print(f"   Premium:      {users.get('premium_users', 0):,}")
    print(f"   DAU/WAU/MAU:  {users.get('dau', 0)}/{users.get('wau', 0)}/{users.get('mau', 0)}")
    
    # Platforms
    platforms = data.get("platforms", {})
    print("\n🌐 PLATFORMS")
    print("─" * 40)
    for name, stats in platforms.items():
        affiliate = "💰" if stats.get("has_affiliate") else "  "
        print(f"   {affiliate} {name.capitalize():12} {stats.get('in_stock', 0):,} products")
    
    # Redis
    redis_stats = data.get("redis", {})
    print("\n🔴 REDIS")
    print("─" * 40)
    print(f"   Status:       {redis_stats.get('status', 'unknown')}")
    print(f"   Memory:       {redis_stats.get('memory_used', 'N/A')}")
    print(f"   Keys:         {redis_stats.get('total_keys', 0):,}")
    
    # Groq
    groq = data.get("groq", {})
    print("\n🤖 GROQ AI")
    print("─" * 40)
    print(f"   Used Today:   {groq.get('total_used_today', 0):,}")
    print(f"   Remaining:    {groq.get('total_remaining', 0):,}")
    
    # Revenue
    revenue = data.get("revenue", {})
    print("\n💰 REVENUE")
    print("─" * 40)
    print(f"   Today:        ₹{revenue.get('today_revenue', 0):,.2f}")
    print(f"   MRR:          ₹{revenue.get('mrr', 0):,.2f}")
    print(f"   Aff. Clicks:  {revenue.get('affiliate_clicks_today', 0)}")
    
    # Cross-Platform Mining
    mining = data.get("mining", {})
    if mining.get("status") != "no_runs":
        print("\n⛏️ CROSS-PLATFORM MINING")
        print("─" * 40)
        print(f"   Status:       {mining.get('status')}")
        if mining.get("last_run"):
            print(f"   Last Run:     {mining.get('last_run')}")
        print(f"   Processed:    {mining.get('processed', 0)}")
        print(f"   Quality Skip: {mining.get('quality_gate_skipped', 0)}")
        print(f"   Stored:       {mining.get('stored', 0)} ✅")
        print(f"   AI Verified:  {mining.get('ai_verified', 0)} 🤖")
        print(f"   AI Rejected:  {mining.get('ai_rejected', 0)}")
        print(f"   Contradicts:  {mining.get('ai_contradictions', 0)}")
        print(f"   Retries:      {mining.get('retries', 0)}")
        print(f"   Img Fixups:   {mining.get('image_validations', 0)}")
        print(f"   Ess. Fixups:  {mining.get('essence_validations', 0)}")
        print(f"   Errors:       {mining.get('errors', 0)}")
        
        # Platform breakdown
        platforms_matched = mining.get("platforms_matched", {})
        if platforms_matched:
            print(f"   Matches by platform:")
            for platform, count in sorted(platforms_matched.items()):
                print(f"      • {platform.capitalize():12} {count} matched")
    else:
        print("\n⛏️ CROSS-PLATFORM MINING")
        print("─" * 40)
        print("   Status:       No runs yet (run: python scripts/cross_platform_miner.py)")
    
    print("\n" + "═" * 70)


async def collect_all_stats() -> dict:
    """Collect all statistics"""
    return {
        "database": await get_database_stats(),
        "users": await get_user_stats(),
        "platforms": await get_platform_stats(),
        "redis": await get_redis_stats(),
        "groq": await get_groq_stats(),
        "revenue": await get_revenue_stats(),
        "mining": await get_cross_platform_mining_stats(),
        "timestamp": datetime.utcnow().isoformat(),
    }


# =============================================================================
# MAIN
# =============================================================================

async def main(args):
    """Main status function"""
    
    if args.watch:
        print("👀 Watch mode (Ctrl+C to exit)")
        while True:
            data = await collect_all_stats()
            
            # Clear screen
            os.system('cls' if os.name == 'nt' else 'clear')
            
            if args.json:
                print(json.dumps(data, indent=2, default=str))
            else:
                print_dashboard(data)
            
            await asyncio.sleep(args.interval)
    else:
        data = await collect_all_stats()
        
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            print_dashboard(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DealHunt Status Dashboard")
    
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--watch", "-w", action="store_true",
                        help="Auto-refresh mode")
    parser.add_argument("--interval", "-i", type=int, default=10,
                        help="Refresh interval in seconds (default: 10)")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n👋 Bye!")
#!/usr/bin/env python3
"""
Job Runner Script
=================

Command-line tool to trigger any APScheduler job manually.

Usage:
    python scripts/run_job.py daily_scrape_trending
    python scripts/run_job.py --list
    python scripts/run_job.py --status
    python scripts/run_job.py seed_products --wait

Author: DealHunt
Version: 1.0
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from jobs.scheduler import (
    trigger_job_manually,
    get_scheduler_status,
    start_scheduler,
    shutdown_scheduler
)


# =============================================================================
# AVAILABLE JOBS
# =============================================================================

AVAILABLE_JOBS = {
    "daily_scrape": {
        "name": "Daily Price Scrape",
        "description": "Update prices for all tracked products",
        "schedule": "2:00 AM IST"
    },
    "daily_scrape_trending": {
        "name": "Daily Trending Products",
        "description": "Fetch trending products from all platforms",
        "schedule": "2:30 AM IST"
    },
    "seed_products": {
        "name": "Seed Products",
        "description": "Add new products via rotation system",
        "schedule": "3:00 AM IST"
    },
    "load_trending_redis": {
        "name": "Load Trending to Redis",
        "description": "Cache trending products in Redis",
        "schedule": "5:00 AM IST"
    },
    "check_price_alerts": {
        "name": "Check Price Alerts",
        "description": "Send notifications for price drops",
        "schedule": "Every 6 hours"
    },
    "send_streak_reminders": {
        "name": "Send Streak Reminders",
        "description": "Remind users to maintain streaks",
        "schedule": "8:00 PM IST"
    },
    "sync_subscriptions": {
        "name": "Sync Subscriptions",
        "description": "Sync Google Play subscription status",
        "schedule": "Every hour"
    },
    "monthly_archive": {
        "name": "Monthly Archive",
        "description": "Archive old data and cleanup",
        "schedule": "1st of month, 1:00 AM IST"
    },
}


# =============================================================================
# FUNCTIONS
# =============================================================================

def list_jobs():
    """List all available jobs"""
    print("\n📋 Available Jobs")
    print("=" * 60)
    
    for job_id, info in AVAILABLE_JOBS.items():
        print(f"\n   📌 {job_id}")
        print(f"      Name:     {info['name']}")
        print(f"      About:    {info['description']}")
        print(f"      Schedule: {info['schedule']}")
    
    print("\n" + "=" * 60)
    print("\nUsage: python scripts/run_job.py <job_id>")


def show_status():
    """Show scheduler status"""
    print("\n📊 Scheduler Status")
    print("=" * 60)
    
    try:
        status = get_scheduler_status()
        
        print(f"\n   Running: {'✅ Yes' if status['running'] else '❌ No'}")
        print(f"   Uptime:  {status.get('uptime_seconds', 0) // 60} minutes")
        print(f"   Jobs:    {status.get('jobs_count', 0)}")
        
        if status.get("jobs"):
            print("\n   Job Status:")
            print("   " + "-" * 50)
            
            for job in status["jobs"]:
                status_icon = "🟢" if job.get("last_status") == "success" else "🔴" if job.get("last_status") == "failed" else "⚪"
                running_icon = "🔄" if job.get("is_running") else ""
                
                print(f"   {status_icon} {job['job_id']:<25} {running_icon}")
                print(f"      Last run: {job.get('last_run', 'Never')}")
                print(f"      Next run: {job.get('next_run', 'N/A')}")
                print(f"      Success/Error: {job.get('success_count', 0)}/{job.get('error_count', 0)}")
        
    except Exception as e:
        print(f"\n   ❌ Error getting status: {e}")
        print("   Note: Scheduler may not be running")
    
    print("\n" + "=" * 60)


async def run_job(job_id: str, wait: bool = True):
    """Run a specific job"""
    
    if job_id not in AVAILABLE_JOBS:
        print(f"\n❌ Unknown job: {job_id}")
        print(f"   Available jobs: {', '.join(AVAILABLE_JOBS.keys())}")
        return
    
    job_info = AVAILABLE_JOBS[job_id]
    
    print("\n" + "=" * 60)
    print(f"🚀 Running Job: {job_id}")
    print("=" * 60)
    print(f"   Name:        {job_info['name']}")
    print(f"   Description: {job_info['description']}")
    print(f"   Started at:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    start_time = datetime.now()
    
    try:
        result = await trigger_job_manually(job_id)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "-" * 60)
        
        if result.get("success"):
            print(f"✅ Job completed successfully!")
            print(f"   Duration: {duration:.1f}s")
            
            if result.get("result"):
                print(f"\n   Result:")
                for key, value in result["result"].items():
                    print(f"      {key}: {value}")
        else:
            print(f"❌ Job failed!")
            print(f"   Error: {result.get('error', 'Unknown error')}")
        
    except Exception as e:
        print(f"\n❌ Error running job: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run DealHunt Background Jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/run_job.py daily_scrape_trending
    python scripts/run_job.py --list
    python scripts/run_job.py --status
    python scripts/run_job.py seed_products
        """
    )
    
    parser.add_argument("job_id", nargs="?", type=str,
                        help="Job ID to run")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List all available jobs")
    parser.add_argument("--status", "-s", action="store_true",
                        help="Show scheduler status")
    parser.add_argument("--wait", "-w", action="store_true", default=True,
                        help="Wait for job to complete (default: True)")
    
    args = parser.parse_args()
    
    if args.list:
        list_jobs()
        return
    
    if args.status:
        show_status()
        return
    
    if not args.job_id:
        parser.print_help()
        print("\n❌ Please specify a job_id or use --list to see available jobs")
        return
    
    # Run the job
    asyncio.run(run_job(args.job_id, args.wait))


if __name__ == "__main__":
    main()
"""
Background Jobs Package
=======================

Automated tasks that run on schedule:
- Daily price scraping (2:00 AM IST)
- Daily trending products (2:30 AM IST)
- Seed products rotation (3:00 AM IST)
- Trending cache refresh (5:00 AM IST)
- Price alert checks (every 6 hours)
- Streak reminders (8:00 PM IST)
- Google Play subscription sync (every 1 hour)
- Monthly data archival (1st of month, 1:00 AM IST)

Usage:
    from jobs import start_scheduler, shutdown_scheduler
    
    # In main.py startup
    start_scheduler()
    
    # In main.py shutdown
    shutdown_scheduler()
    
    # Get status
    status = get_scheduler_status()
    
    # Manual job trigger
    result = await run_job_now("daily_scrape")

Author: DealHunt
Version: 2.0 (Cleaned & Fixed)
"""

from jobs.scheduler import (
    scheduler,
    start_scheduler,
    shutdown_scheduler,
    get_scheduler_status,
    run_job_now,
    trigger_job_manually,
    JobStatus,
)

# Import individual job functions for manual triggering
try:
    from jobs.daily_scrape import run_daily_scrape
except ImportError:
    run_daily_scrape = None

try:
    from jobs.daily_scrape_trending import run_daily_trending_products
except ImportError:
    run_daily_trending_products = None

try:
    from jobs.seed_products import run_seed_products
except ImportError:
    run_seed_products = None

try:
    from jobs.load_trending_redis import run_load_trending
except ImportError:
    run_load_trending = None

try:
    from jobs.check_price_alerts import run_check_price_alerts
except ImportError:
    run_check_price_alerts = None

try:
    from jobs.send_streak_reminders import run_streak_reminders
except ImportError:
    run_streak_reminders = None

try:
    from jobs.sync_subscriptions import run_sync_subscriptions
except ImportError:
    run_sync_subscriptions = None

try:
    from jobs.monthly_archive import run_monthly_archive
except ImportError:
    run_monthly_archive = None


__all__ = [
    # Scheduler management
    "scheduler",
    "start_scheduler",
    "shutdown_scheduler",
    "get_scheduler_status",
    "run_job_now",
    "trigger_job_manually",
    "JobStatus",
    
    # Individual job functions
    "run_daily_scrape",
    "run_daily_trending_products",
    "run_seed_products",
    "run_load_trending",
    "run_check_price_alerts",
    "run_streak_reminders",
    "run_sync_subscriptions",
    "run_monthly_archive",
]

__version__ = "2.0.0"
__author__ = "DealHunt"
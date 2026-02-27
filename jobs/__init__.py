"""
Background Jobs Package

Automated tasks that run on schedule:
- Daily price scraping (2 AM IST)
- Seed trending products (3 AM IST) ← NEW!
- Trending cache refresh (5 AM IST)
- Price alert checks (every 6 hours)
- Streak reminders (8 PM IST)
- Google Play subscription sync (every 1 hour)
- Monthly data archival (1st of month, 1 AM IST)

Usage:
    from jobs import start_scheduler, shutdown_scheduler
    
    # In main.py startup
    start_scheduler()
    
    # In main.py shutdown
    shutdown_scheduler()
    
    # Manual seeding (admin/testing)
    from jobs import run_seed_products, seed_specific
    await run_seed_products()
    await seed_specific("Electronics", "amazon", "Best Selling")
"""

from jobs.scheduler import (
    scheduler,
    start_scheduler,
    shutdown_scheduler,
    get_scheduler_status,
    run_job_now,
    JobStatus
)

# Import seeding functions for manual triggering
try:
    from jobs.seed_products import (
        run_seed_products,
        seed_specific,
    )
    _SEEDING_AVAILABLE = True
except ImportError:
    # Seeding module not yet created
    run_seed_products = None
    seed_specific = None
    _SEEDING_AVAILABLE = False

__all__ = [
    # Scheduler
    "scheduler",
    "start_scheduler",
    "shutdown_scheduler",
    "get_scheduler_status",
    "run_job_now",
    "JobStatus",
    # Seeding (manual trigger)
    "run_seed_products",
    "seed_specific",
]
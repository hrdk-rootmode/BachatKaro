"""
Background Jobs Package

Automated tasks that run on schedule:
- Daily price scraping (2 AM IST)
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
"""

from jobs.scheduler import (
    scheduler,
    start_scheduler,
    shutdown_scheduler,
    get_scheduler_status,
    run_job_now,
    JobStatus
)

__all__ = [
    "scheduler",
    "start_scheduler",
    "shutdown_scheduler",
    "get_scheduler_status",
    "run_job_now",
    "JobStatus"
]
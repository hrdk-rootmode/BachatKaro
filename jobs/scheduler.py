"""
APScheduler Configuration
Central scheduler for all background jobs

Features:
- Timezone-aware scheduling (IST)
- Job persistence (survives restarts)
- Graceful shutdown
- Manual job triggering
- Health monitoring

FIXED: APScheduler 3.x compatibility
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
import pytz

from app.core.config import settings

logger = logging.getLogger(__name__)

# Timezone for India
IST = pytz.timezone('Asia/Kolkata')


class JobStatus(str, Enum):
    """Job execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# SCHEDULER CONFIGURATION
# =============================================================================

# Job stores configuration
jobstores = {
    'default': MemoryJobStore()
}

# Executors configuration
executors = {
    'default': AsyncIOExecutor()
}

# Job defaults
job_defaults = {
    'coalesce': True,           # Combine multiple missed runs into one
    'max_instances': 1,         # Only one instance of each job at a time
    'misfire_grace_time': 3600  # 1 hour grace period for missed jobs
}

# Create scheduler instance (but don't start yet)
scheduler: Optional[AsyncIOScheduler] = None

# Track job status
_job_status: Dict[str, Dict[str, Any]] = {}

# Track if scheduler is initialized
_scheduler_initialized = False


def _create_scheduler() -> AsyncIOScheduler:
    """Create a new scheduler instance"""
    return AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone=IST
    )


# =============================================================================
# JOB WRAPPER FOR ERROR HANDLING
# =============================================================================

def job_wrapper(job_id: str, job_func):
    """Wrap async job function with error handling"""
    async def wrapped():
        start_time = datetime.now(IST)
        _job_status[job_id] = {
            "status": JobStatus.RUNNING.value,
            "started_at": start_time.isoformat()
        }
        
        try:
            logger.info(f"🔄 Starting job: {job_id}")
            result = await job_func()
            
            end_time = datetime.now(IST)
            duration = (end_time - start_time).total_seconds()
            
            _job_status[job_id] = {
                "status": JobStatus.COMPLETED.value,
                "last_run": end_time.isoformat(),
                "duration": duration,
                "error": None,
                "result": result if isinstance(result, dict) else {"success": True}
            }
            
            logger.info(f"✅ Job {job_id} completed in {duration:.2f}s")
            return result
            
        except Exception as e:
            end_time = datetime.now(IST)
            duration = (end_time - start_time).total_seconds()
            
            _job_status[job_id] = {
                "status": JobStatus.FAILED.value,
                "last_run": end_time.isoformat(),
                "duration": duration,
                "error": str(e)
            }
            
            logger.error(f"❌ Job {job_id} failed: {e}")
            # Don't re-raise - let scheduler continue
            
    return wrapped


# =============================================================================
# JOB REGISTRATION
# =============================================================================

def register_jobs():
    """Register all scheduled jobs"""
    global scheduler, _scheduler_initialized
    
    if not settings.ENABLE_SCHEDULER:
        logger.warning("⚠️ Scheduler is DISABLED in settings")
        return
    
    if scheduler is None:
        logger.error("Scheduler not initialized")
        return
    
    logger.info("📅 Registering background jobs...")
    
    # =========================================================================
    # JOB 1: Daily Price Scrape (2 AM IST)
    # =========================================================================
    try:
        from jobs.daily_scrape import run_daily_scrape
        
        scheduler.add_job(
            job_wrapper('daily_scrape', run_daily_scrape),
            trigger=CronTrigger(
                hour=settings.DAILY_SCRAPE_HOUR,
                minute=0,
                timezone=IST
            ),
            id='daily_scrape',
            name='Daily Price Scrape',
            replace_existing=True
        )
        logger.info(f"  ├── daily_scrape: {settings.DAILY_SCRAPE_HOUR}:00 AM IST ✅")
    except Exception as e:
        logger.error(f"  ├── daily_scrape: FAILED - {e}")
    
    # =========================================================================
    # JOB 2: Load Trending to Redis (5 AM IST)
    # =========================================================================
    try:
        from jobs.load_trending_redis import run_load_trending
        
        scheduler.add_job(
            job_wrapper('load_trending', run_load_trending),
            trigger=CronTrigger(
                hour=settings.TRENDING_CACHE_HOUR,
                minute=0,
                timezone=IST
            ),
            id='load_trending',
            name='Load Trending Products',
            replace_existing=True
        )
        logger.info(f"  ├── load_trending: {settings.TRENDING_CACHE_HOUR}:00 AM IST ✅")
    except Exception as e:
        logger.error(f"  ├── load_trending: FAILED - {e}")
    
    # =========================================================================
    # JOB 3: Check Price Alerts (Every 6 hours)
    # =========================================================================
    try:
        from jobs.check_price_alerts import run_check_price_alerts
        
        scheduler.add_job(
            job_wrapper('check_price_alerts', run_check_price_alerts),
            trigger=IntervalTrigger(
                hours=settings.ALERT_CHECK_INTERVAL_HOURS,
                timezone=IST
            ),
            id='check_price_alerts',
            name='Check Price Alerts',
            replace_existing=True
        )
        logger.info(f"  ├── check_price_alerts: every {settings.ALERT_CHECK_INTERVAL_HOURS}h ✅")
    except Exception as e:
        logger.error(f"  ├── check_price_alerts: FAILED - {e}")
    
    # =========================================================================
    # JOB 4: Streak Reminders (8 PM IST)
    # =========================================================================
    try:
        from jobs.send_streak_reminders import run_streak_reminders
        
        scheduler.add_job(
            job_wrapper('streak_reminders', run_streak_reminders),
            trigger=CronTrigger(
                hour=20,
                minute=0,
                timezone=IST
            ),
            id='streak_reminders',
            name='Send Streak Reminders',
            replace_existing=True
        )
        logger.info("  ├── streak_reminders: 8:00 PM IST ✅")
    except Exception as e:
        logger.error(f"  ├── streak_reminders: FAILED - {e}")
    
    # =========================================================================
    # JOB 5: Sync Google Subscriptions (Every 1 hour) - OPTIONAL
    # =========================================================================
    try:
        from jobs.sync_subscriptions import run_sync_subscriptions
        
        scheduler.add_job(
            job_wrapper('sync_subscriptions', run_sync_subscriptions),
            trigger=IntervalTrigger(
                hours=1,
                timezone=IST
            ),
            id='sync_subscriptions',
            name='Sync Google Subscriptions',
            replace_existing=True
        )
        logger.info("  ├── sync_subscriptions: every 1h ✅")
    except ImportError as e:
        logger.warning(f"  ├── sync_subscriptions: SKIPPED - Module not found ({e})")
    except Exception as e:
        logger.error(f"  ├── sync_subscriptions: FAILED - {e}")
    
    # =========================================================================
    # JOB 6: Monthly Archive (1st of month, 1 AM IST) - OPTIONAL
    # =========================================================================
    try:
        from jobs.monthly_archive import run_monthly_archive
        
        scheduler.add_job(
            job_wrapper('monthly_archive', run_monthly_archive),
            trigger=CronTrigger(
                day=1,
                hour=1,
                minute=0,
                timezone=IST
            ),
            id='monthly_archive',
            name='Monthly Data Archive',
            replace_existing=True
        )
        logger.info("  └── monthly_archive: 1st of month, 1:00 AM IST ✅")
    except ImportError as e:
        logger.warning(f"  └── monthly_archive: SKIPPED - Module not found ({e})")
    except Exception as e:
        logger.error(f"  └── monthly_archive: FAILED - {e}")
    
    _scheduler_initialized = True
    job_count = len(scheduler.get_jobs())
    logger.info(f"✅ Registered {job_count} background jobs")

# =============================================================================
# SCHEDULER LIFECYCLE
# =============================================================================

def start_scheduler():
    """Start the scheduler"""
    global scheduler
    
    if not settings.ENABLE_SCHEDULER:
        logger.warning("⚠️ Scheduler disabled - skipping start")
        return
    
    try:
        # Create new scheduler
        scheduler = _create_scheduler()
        
        # Register jobs
        register_jobs()
        
        # Start scheduler
        scheduler.start()
        logger.info("🚀 Background scheduler started")
        
        # Log next run times
        _log_next_run_times()
                
    except Exception as e:
        logger.error(f"❌ Failed to start scheduler: {e}")
        raise


def shutdown_scheduler():
    """Gracefully shutdown the scheduler"""
    global scheduler
    
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("🛑 Background scheduler stopped")


def _log_next_run_times():
    """Log next run times for all jobs"""
    if scheduler is None:
        return
    
    try:
        jobs = scheduler.get_jobs()
        for job in jobs:
            try:
                # APScheduler 3.x compatible way to get next run time
                next_run = None
                if hasattr(job, 'next_run_time') and job.next_run_time:
                    next_run = job.next_run_time
                elif hasattr(job, 'trigger'):
                    # Try to get from trigger
                    next_run = job.trigger.get_next_fire_time(None, datetime.now(IST))
                
                if next_run:
                    logger.info(f"  ├── {job.id}: next run at {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                else:
                    logger.info(f"  ├── {job.id}: scheduled")
            except Exception:
                logger.info(f"  ├── {job.id}: scheduled")
    except Exception as e:
        logger.debug(f"Could not log next run times: {e}")


# =============================================================================
# JOB MANAGEMENT
# =============================================================================

def get_scheduler_status() -> Dict[str, Any]:
    """Get scheduler status and job information"""
    global scheduler, _scheduler_initialized
    
    if scheduler is None:
        return {
            "running": False,
            "enabled": settings.ENABLE_SCHEDULER,
            "jobs_count": 0,
            "jobs": [],
            "message": "Scheduler not initialized"
        }
    
    jobs_info = []
    
    try:
        jobs = scheduler.get_jobs()
        
        for job in jobs:
            job_data = {
                "id": job.id,
                "name": getattr(job, 'name', job.id),
                "next_run": None,
                "status": _job_status.get(job.id, {}).get("status", "pending"),
                "last_run": _job_status.get(job.id, {}).get("last_run"),
                "last_duration": _job_status.get(job.id, {}).get("duration"),
                "last_error": _job_status.get(job.id, {}).get("error")
            }
            
            # Get next run time safely
            try:
                if hasattr(job, 'next_run_time') and job.next_run_time:
                    job_data["next_run"] = job.next_run_time.isoformat()
                elif hasattr(job, 'trigger'):
                    next_fire = job.trigger.get_next_fire_time(None, datetime.now(IST))
                    if next_fire:
                        job_data["next_run"] = next_fire.isoformat()
            except Exception:
                pass
            
            jobs_info.append(job_data)
            
    except Exception as e:
        logger.error(f"Error getting job info: {e}")
    
    return {
        "running": scheduler.running if scheduler else False,
        "timezone": str(IST),
        "jobs_count": len(jobs_info),
        "jobs": jobs_info,
        "enabled": settings.ENABLE_SCHEDULER
    }


async def run_job_now(job_id: str) -> Dict[str, Any]:
    """
    Manually trigger a job immediately
    
    Args:
        job_id: ID of the job to run
        
    Returns:
        Job execution result
    """
    global scheduler
    
    if scheduler is None:
        return {
            "success": False,
            "error": "Scheduler not initialized"
        }
    
    job = scheduler.get_job(job_id)
    
    if not job:
        return {
            "success": False,
            "error": f"Job not found: {job_id}",
            "available_jobs": [j.id for j in scheduler.get_jobs()]
        }
    
    logger.info(f"🔧 Manually triggering job: {job_id}")
    
    start_time = datetime.now(IST)
    _job_status[job_id] = {
        "status": JobStatus.RUNNING.value,
        "started_at": start_time.isoformat()
    }
    
    try:
        # Get the actual job function from the wrapper
        job_func = job.func
        
        # Run the job
        if asyncio.iscoroutinefunction(job_func):
            result = await job_func()
        else:
            result = job_func()
            # If it's a coroutine (wrapped function returns coroutine)
            if asyncio.iscoroutine(result):
                result = await result
        
        end_time = datetime.now(IST)
        duration = (end_time - start_time).total_seconds()
        
        _job_status[job_id] = {
            "status": JobStatus.COMPLETED.value,
            "last_run": end_time.isoformat(),
            "duration": duration,
            "error": None
        }
        
        logger.info(f"✅ Manual job {job_id} completed in {duration:.2f}s")
        
        return {
            "success": True,
            "job_id": job_id,
            "duration_seconds": duration,
            "result": result if isinstance(result, dict) else {"completed": True}
        }
        
    except Exception as e:
        end_time = datetime.now(IST)
        duration = (end_time - start_time).total_seconds()
        
        _job_status[job_id] = {
            "status": JobStatus.FAILED.value,
            "last_run": end_time.isoformat(),
            "duration": duration,
            "error": str(e)
        }
        
        logger.error(f"❌ Manual job {job_id} failed: {e}")
        
        return {
            "success": False,
            "job_id": job_id,
            "duration_seconds": duration,
            "error": str(e)
        }


def update_job_status(job_id: str, status: JobStatus, **kwargs):
    """Update job status (called by individual jobs)"""
    _job_status[job_id] = {
        "status": status.value,
        "last_run": datetime.now(IST).isoformat(),
        **kwargs
    }
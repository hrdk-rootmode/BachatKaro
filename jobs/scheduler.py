"""
APScheduler Configuration
=========================

Central scheduler for all background jobs with:
- Timezone-aware scheduling (IST)
- Job persistence (memory-based)
- Graceful shutdown
- Manual job triggering
- Health monitoring
- Error recovery

Schedule Overview:
├─ 2:00 AM  - daily_scrape (price updates)
├─ 2:30 AM  - daily_scrape_trending (trending products)
├─ 3:00 AM  - seed_products (comprehensive seeding with cross-platform matching)
├─ 5:00 AM  - load_trending_redis (cache refresh)
├─ 6h cycle - check_price_alerts (6AM, 12PM, 6PM, 12AM)
├─ 8:00 PM  - send_streak_reminders
├─ Hourly   - sync_subscriptions (Google Play)
└─ Monthly  - monthly_archive (1st of month, 1AM)

Author: DealHunt
Version: 2.0 (Cleaned & Enhanced)
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import pytz

# Add parent directory to Python path for imports
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# ERROR NOTIFICATION SYSTEM
# =============================================================================

try:
    import smtplib
    from email.mime.text import MimeText
    from email.mime.multipart import MimeMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    logger.warning("Email modules not available - error notifications disabled")

async def send_error_notification(job_name: str, error: str, traceback_info: str = None):
    """Send error notification via email (configurable)"""
    if not EMAIL_AVAILABLE:
        logger.error(f"🚨 JOB FAILED: {job_name}")
        logger.error(f"Error: {error}")
        return
    
    try:
        # Check if error notifications are enabled
        if not getattr(settings, 'ENABLE_ERROR_NOTIFICATIONS', False):
            return
        
        recipient = getattr(settings, 'ERROR_NOTIFICATION_EMAIL', '')
        if not recipient:
            return
        
        # Create email content
        subject = f"🚨 Job Failed: {job_name} - DealHunt Scheduler"
        
        branch_info = await get_current_branch()
        traceback_section = f"Traceback:\n{traceback_info}" if traceback_info else ""
        
        body = f"""Job Failure Report
=================

Job Name: {job_name}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Branch: {branch_info}

Error:
{error}

{traceback_section}

Please check the logs and investigate the issue.

--
DealHunt Scheduler"""
        
        # Send email (configure your SMTP settings in .env)
        if hasattr(settings, 'SMTP_HOST') and settings.SMTP_HOST:
            msg = MimeMultipart()
            msg['From'] = getattr(settings, 'SMTP_FROM', 'scheduler@dealhunt.com')
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MimeText(body, 'plain'))
            
            server = smtplib.SMTP(settings.SMTP_HOST, getattr(settings, 'SMTP_PORT', 587))
            if getattr(settings, 'SMTP_USE_TLS', True):
                server.starttls()
            if hasattr(settings, 'SMTP_USERNAME') and settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"📧 Error notification sent for {job_name}")
        else:
            # Log to console if email not configured
            logger.error(f"🚨 JOB FAILED: {job_name}")
            logger.error(f"Branch: {await get_current_branch()}")
            logger.error(f"Error: {error}")
            if traceback_info:
                logger.error(f"Traceback: {traceback_info}")
    
    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")

async def validate_branch() -> bool:
    """Validate we're running on the correct branch"""
    try:
        current_branch = await get_current_branch()
        expected_branch = getattr(settings, 'SCHEDULER_BRANCH', 'current')
        
        # If set to 'current', always accept whatever branch we're on
        if expected_branch == 'current':
            logger.info(f"✅ Branch validation passed: {current_branch} (current mode)")
            return True
        
        if current_branch != expected_branch:
            logger.error(f"🚨 WRONG BRANCH: Running on '{current_branch}' but expected '{expected_branch}'")
            await send_error_notification(
                "Branch Validation", 
                f"Scheduler running on wrong branch: {current_branch} (expected: {expected_branch})"
            )
            return False
        
        logger.info(f"✅ Branch validation passed: {current_branch}")
        return True
    except Exception as e:
        logger.error(f"Branch validation failed: {e}")
        return False

async def get_current_branch() -> str:
    """Get current git branch"""
    try:
        import subprocess
        result = subprocess.run(['git', 'branch', '--show-current'], 
                              capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or 'unknown'
    except:
        return 'unknown'


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class JobStatus(str, Enum):
    """Job execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class JobResult:
    """Result of a job execution"""
    job_id: str
    status: JobStatus
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class JobInfo:
    """Job information and statistics"""
    job_id: str
    name: str
    description: str
    schedule: str
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    success_count: int = 0
    error_count: int = 0
    last_status: JobStatus = JobStatus.PENDING
    last_error: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None
    is_running: bool = False


# =============================================================================
# SCHEDULER CONFIGURATION
# =============================================================================

# IST Timezone
IST = pytz.timezone('Asia/Kolkata')

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
    'coalesce': True,  # Combine multiple pending executions
    'max_instances': 1,  # Only one instance at a time
    'misfire_grace_time': 3600  # 1 hour grace time
}

# Initialize scheduler
scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
    timezone=IST
)

# Scheduler start time
_scheduler_start_time: Optional[datetime] = None


# =============================================================================
# JOB STATUS TRACKING
# =============================================================================

_job_registry: Dict[str, JobInfo] = {
    'daily_scrape': JobInfo(
        job_id='daily_scrape',
        name='Daily Price Scrape',
        description='Update prices for all tracked products',
        schedule='2:00 AM IST'
    ),
    'daily_scrape_trending': JobInfo(
        job_id='daily_scrape_trending',
        name='Daily Trending Products',
        description='Fetch trending products from all platforms',
        schedule='2:30 AM IST'
    ),
    'seed_products': JobInfo(
        job_id='seed_products',
        name='Seed Products',
        description='Comprehensive seeding with cross-platform matching',
        schedule='3:00 AM IST'
    ),
    'load_trending_redis': JobInfo(
        job_id='load_trending_redis',
        name='Load Trending to Redis',
        description='Cache trending products in Redis',
        schedule='5:00 AM IST'
    ),
    'check_price_alerts': JobInfo(
        job_id='check_price_alerts',
        name='Check Price Alerts',
        description='Send notifications for price drops',
        schedule='Every 6 hours'
    ),
    'send_streak_reminders': JobInfo(
        job_id='send_streak_reminders',
        name='Send Streak Reminders',
        description='Remind users to maintain streaks',
        schedule='8:00 PM IST'
    ),
    'sync_subscriptions': JobInfo(
        job_id='sync_subscriptions',
        name='Sync Subscriptions',
        description='Sync Google Play subscription status',
        schedule='Every hour'
    ),
    'monthly_archive': JobInfo(
        job_id='monthly_archive',
        name='Monthly Archive',
        description='Archive old data and cleanup',
        schedule='1st of month, 1:00 AM IST'
    ),
}


# =============================================================================
# JOB WRAPPER (Error Handling & Tracking)
# =============================================================================

def create_job_wrapper(job_id: str, job_func: Callable) -> Callable:
    """
    Create a wrapper for job functions with:
    - Error handling
    - Status tracking
    - Duration logging
    - Result capture
    """
    async def wrapped_job():
        job_info = _job_registry.get(job_id)
        if not job_info:
            logger.error(f"Unknown job: {job_id}")
            return
        
        # Validate branch before running
        if not await validate_branch():
            logger.error(f"⚠️ Skipping job {job_id} due to branch validation failure")
            job_info.last_status = JobStatus.SKIPPED
            job_info.last_error = "Wrong branch"
            return {"success": False, "error": "Wrong branch"}
        
        # Mark as running
        job_info.is_running = True
        job_info.last_run = datetime.now(IST)
        started_at = datetime.utcnow()
        
        logger.info(f"🚀 Starting job: {job_id} ({job_info.name}) on branch {await get_current_branch()}")
        
        try:
            # Execute job
            result = await job_func()
            
            # Calculate duration
            finished_at = datetime.utcnow()
            duration = (finished_at - started_at).total_seconds()
            
            # Update status
            job_info.success_count += 1
            job_info.last_status = JobStatus.SUCCESS
            job_info.last_error = None
            job_info.last_result = result if isinstance(result, dict) else {"result": str(result)}
            
            logger.info(
                f"✅ Job completed: {job_id} | "
                f"Duration: {duration:.2f}s | "
                f"Result: {result}"
            )
            
            return result
            
        except Exception as e:
            # Calculate duration
            finished_at = datetime.utcnow()
            duration = (finished_at - started_at).total_seconds()
            
            # Get traceback for debugging
            import traceback
            traceback_info = traceback.format_exc()
            
            # Update status
            job_info.error_count += 1
            job_info.last_status = JobStatus.FAILED
            job_info.last_error = str(e)
            
            logger.error(
                f"❌ Job failed: {job_id} | "
                f"Duration: {duration:.2f}s | "
                f"Error: {e}"
            )
            
            # Send error notification
            try:
                await send_error_notification(job_id, str(e), traceback_info)
            except Exception as notification_error:
                logger.error(f"Failed to send error notification: {notification_error}")
            
            # Don't raise - let scheduler continue
            return {"success": False, "error": str(e)}
            
        finally:
            job_info.is_running = False
            
            # Update next run time
            job = scheduler.get_job(job_id)
            if job:
                job_info.next_run = job.next_run_time
    
    return wrapped_job


# =============================================================================
# JOB IMPORT FUNCTIONS
# =============================================================================

async def _run_daily_scrape():
    """Import and run daily scrape"""
    from jobs.daily_scrape import run_daily_scrape
    return await run_daily_scrape()


async def _run_daily_scrape_trending():
    """Import and run trending scrape"""
    from jobs.daily_scrape_trending import run_daily_trending_products
    return await run_daily_trending_products()


async def _run_seed_products():
    """Import and run seed products - using comprehensive seeding"""
    try:
        # Add current directory to Python path and import directly
        import sys
        import os
        current_dir = os.path.abspath('.')
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        
        # Import and run seeding with explicit hardened defaults.
        from scripts.seed import seed_smart_rotate
        result = await seed_smart_rotate(
            categories=["Electronics", "Fashion", "Home & Kitchen", "Accessories", "Books"],
            products_per_category=4,
            enable_ai=True,
            enable_cross_match=True,
            timeout_seconds=60,
            query_interval_seconds=8.0,
            cooldown_buffer_seconds=12,
        )
        
        return {"success": True, "output": str(result)}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _run_load_trending_redis():
    """Import and run trending cache refresh"""
    from jobs.load_trending_redis import run_load_trending
    return await run_load_trending()


async def _run_check_price_alerts():
    """Import and run price alerts check"""
    from jobs.check_price_alerts import run_check_price_alerts
    return await run_check_price_alerts()


async def _run_send_streak_reminders():
    """Import and run streak reminders"""
    from jobs.send_streak_reminders import run_streak_reminders
    return await run_streak_reminders()


async def _run_sync_subscriptions():
    """Import and run subscription sync"""
    from jobs.sync_subscriptions import run_sync_subscriptions
    return await run_sync_subscriptions()


async def _run_monthly_archive():
    """Import and run monthly archive"""
    from jobs.monthly_archive import run_monthly_archive
    return await run_monthly_archive()


# =============================================================================
# SCHEDULER EVENT LISTENERS
# =============================================================================

def job_executed_listener(event):
    """Handle successful job execution"""
    logger.debug(f"Job executed: {event.job_id}")


def job_error_listener(event):
    """Handle job execution errors"""
    logger.error(f"Job error: {event.job_id} - {event.exception}")


# =============================================================================
# SCHEDULER MANAGEMENT
# =============================================================================

def start_scheduler():
    """
    Start the scheduler with all jobs registered
    
    Call this in FastAPI lifespan startup
    """
    global _scheduler_start_time
    
    if scheduler.running:
        logger.warning("Scheduler is already running")
        return
    
    try:
        # Add event listeners
        scheduler.add_listener(job_executed_listener, EVENT_JOB_EXECUTED)
        scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
        
        # Register all jobs
        _register_all_jobs()
        
        # Start scheduler
        scheduler.start()
        _scheduler_start_time = datetime.now(IST)
        
        logger.info("🚀 Scheduler started successfully")
        
        # Log all registered jobs
        jobs = scheduler.get_jobs()
        logger.info(f"📅 Registered {len(jobs)} jobs:")
        for job in jobs:
            next_run = "N/A"
            if hasattr(job, 'next_run_time') and job.next_run_time:
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z")
            logger.info(f"   • {job.id}: {job.name} → Next: {next_run}")
        
    except Exception as e:
        logger.error(f"❌ Failed to start scheduler: {e}")
        raise


def shutdown_scheduler():
    """
    Gracefully shutdown the scheduler
    
    Call this in FastAPI lifespan shutdown
    """
    global _scheduler_start_time
    
    if not scheduler.running:
        logger.warning("Scheduler is not running")
        return
    
    try:
        scheduler.shutdown(wait=True)
        _scheduler_start_time = None
        logger.info("🛑 Scheduler shutdown successfully")
        
    except Exception as e:
        logger.error(f"❌ Error shutting down scheduler: {e}")


def _register_all_jobs():
    """Register all scheduled jobs"""
    
    # 2:00 AM - Daily Price Scrape
    scheduler.add_job(
        create_job_wrapper('daily_scrape', _run_daily_scrape),
        CronTrigger(hour=2, minute=0, timezone=IST),
        id='daily_scrape',
        name='Daily Price Scrape',
        replace_existing=True
    )
    
    # 2:30 AM - Daily Trending Products
    scheduler.add_job(
        create_job_wrapper('daily_scrape_trending', _run_daily_scrape_trending),
        CronTrigger(hour=2, minute=30, timezone=IST),
        id='daily_scrape_trending',
        name='Daily Trending Products',
        replace_existing=True
    )
    
    # 3:00 AM - Seed Products
    scheduler.add_job(
        create_job_wrapper('seed_products', _run_seed_products),
        CronTrigger(hour=3, minute=0, timezone=IST),
        id='seed_products',
        name='Seed Products',
        replace_existing=True
    )
    
    # 5:00 AM - Load Trending to Redis
    scheduler.add_job(
        create_job_wrapper('load_trending_redis', _run_load_trending_redis),
        CronTrigger(hour=5, minute=0, timezone=IST),
        id='load_trending_redis',
        name='Load Trending to Redis',
        replace_existing=True
    )
    
    # Every 6 hours - Check Price Alerts (6AM, 12PM, 6PM, 12AM)
    scheduler.add_job(
        create_job_wrapper('check_price_alerts', _run_check_price_alerts),
        CronTrigger(hour='0,6,12,18', minute=0, timezone=IST),
        id='check_price_alerts',
        name='Check Price Alerts',
        replace_existing=True
    )
    
    # 8:00 PM - Send Streak Reminders
    scheduler.add_job(
        create_job_wrapper('send_streak_reminders', _run_send_streak_reminders),
        CronTrigger(hour=20, minute=0, timezone=IST),
        id='send_streak_reminders',
        name='Send Streak Reminders',
        replace_existing=True
    )
    
    # Every hour - Sync Subscriptions
    scheduler.add_job(
        create_job_wrapper('sync_subscriptions', _run_sync_subscriptions),
        CronTrigger(minute=0, timezone=IST),
        id='sync_subscriptions',
        name='Sync Subscriptions',
        replace_existing=True
    )
    
    # 1st of month, 1:00 AM - Monthly Archive
    scheduler.add_job(
        create_job_wrapper('monthly_archive', _run_monthly_archive),
        CronTrigger(day=1, hour=1, minute=0, timezone=IST),
        id='monthly_archive',
        name='Monthly Archive',
        replace_existing=True
    )
    
    # Update next run times
    for job in scheduler.get_jobs():
        if job.id in _job_registry:
            if hasattr(job, 'next_run_time'):
                _job_registry[job.id].next_run = job.next_run_time


# =============================================================================
# STATUS & MANUAL TRIGGERING
# =============================================================================

def get_scheduler_status() -> Dict[str, Any]:
    """
    Get comprehensive scheduler status
    
    Returns:
        Dictionary with scheduler state and all job statuses
    """
    uptime = None
    if _scheduler_start_time:
        uptime = int((datetime.now(IST) - _scheduler_start_time).total_seconds())
    
    # Update next run times
    for job in scheduler.get_jobs():
        if job.id in _job_registry:
            _job_registry[job.id].next_run = job.next_run_time
    
    jobs_list = []
    for job_id, job_info in _job_registry.items():
        jobs_list.append({
            "job_id": job_info.job_id,
            "name": job_info.name,
            "description": job_info.description,
            "schedule": job_info.schedule,
            "last_run": job_info.last_run.isoformat() if job_info.last_run else None,
            "next_run": job_info.next_run.isoformat() if job_info.next_run else None,
            "success_count": job_info.success_count,
            "error_count": job_info.error_count,
            "last_status": job_info.last_status.value,
            "last_error": job_info.last_error,
            "is_running": job_info.is_running
        })
    
    return {
        "running": scheduler.running,
        "uptime_seconds": uptime,
        "jobs_count": len(_job_registry),
        "jobs": jobs_list,
        "timezone": str(IST)
    }


async def run_job_now(job_id: str) -> Dict[str, Any]:
    """
    Manually trigger a job immediately
    
    Args:
        job_id: ID of the job to run
        
    Returns:
        Job execution result
    """
    return await trigger_job_manually(job_id)


async def trigger_job_manually(job_id: str) -> Dict[str, Any]:
    """
    Manually trigger a job
    
    Args:
        job_id: ID of the job to run
        
    Returns:
        Dictionary with execution result
    """
    job_functions = {
        'daily_scrape': _run_daily_scrape,
        'daily_scrape_trending': _run_daily_scrape_trending,
        'seed_products': _run_seed_products,
        'load_trending_redis': _run_load_trending_redis,
        'check_price_alerts': _run_check_price_alerts,
        'send_streak_reminders': _run_send_streak_reminders,
        'sync_subscriptions': _run_sync_subscriptions,
        'monthly_archive': _run_monthly_archive,
    }
    
    if job_id not in job_functions:
        return {
            "success": False,
            "job_id": job_id,
            "error": f"Unknown job: {job_id}. Available: {list(job_functions.keys())}"
        }
    
    job_info = _job_registry.get(job_id)
    
    if job_info and job_info.is_running:
        return {
            "success": False,
            "job_id": job_id,
            "error": "Job is already running"
        }
    
    logger.info(f"🔧 Manually triggering job: {job_id}")
    
    try:
        # Run the wrapped job
        wrapped = create_job_wrapper(job_id, job_functions[job_id])
        result = await wrapped()
        
        return {
            "success": True,
            "job_id": job_id,
            "result": result,
            "triggered_at": datetime.now(IST).isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Manual job trigger failed: {job_id} - {e}")
        return {
            "success": False,
            "job_id": job_id,
            "error": str(e),
            "triggered_at": datetime.now(IST).isoformat()
        }


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import asyncio
    
    print("🧪 Testing Scheduler...")
    print("=" * 60)
    
    # Start scheduler
    start_scheduler()
    
    # Print status
    status = get_scheduler_status()
    print(f"\n📊 Scheduler Status:")
    print(f"   Running: {status['running']}")
    print(f"   Jobs: {status['jobs_count']}")
    
    print("\n📅 Registered Jobs:")
    for job in status['jobs']:
        print(f"   • {job['job_id']}: {job['name']}")
        print(f"     Schedule: {job['schedule']}")
        print(f"     Next Run: {job['next_run']}")
    
    # Keep running for a bit
    print("\n⏳ Scheduler running (Ctrl+C to stop)...")
    
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("\n🛑 Stopping scheduler...")
        shutdown_scheduler()
        print("✅ Done!")
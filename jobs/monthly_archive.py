"""
Monthly Data Archive Job
========================

Runs on 1st of each month at 1:00 AM IST to archive old data

Features:
- Archives price history older than retention period
- Compresses and stores in archives directory
- Optionally commits to Git
- Cleans up old system logs
- Generates monthly summary report

Author: DealHunt
Version: 2.0 (Complete Implementation)
"""

import logging
import json
import gzip
import os
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, List
from pathlib import Path

# Add parent directory to Python path for imports
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 🔧 WINDOWS FIX: Silence Proactor Event Loop Warning
if sys.platform == 'win32':
    from asyncio.proactor_events import _ProactorBasePipeTransport
    def silence_proactor_del(self): pass
    _ProactorBasePipeTransport.__del__ = silence_proactor_del

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, text

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import PriceHistory, SystemLog

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

ARCHIVE_DIR = Path("archives")
PRICE_HISTORY_RETENTION_DAYS = settings.PRICE_HISTORY_DAYS  # From config (120)
SYSTEM_LOG_RETENTION_DAYS = 90
BATCH_SIZE = 1000


# =============================================================================
# MAIN JOB FUNCTION
# =============================================================================

async def run_monthly_archive() -> Dict[str, Any]:
    """
    Main monthly archive job
    
    Process:
    1. Archive price history older than retention period
    2. Clean up old system logs
    3. Generate monthly summary
    4. Optionally commit to Git
    5. Update archive metadata
    
    Returns:
        Dictionary with archive statistics
    """
    logger.info("📦 Starting monthly archive...")
    start_time = datetime.utcnow()
    
    stats = {
        "price_history_archived": 0,
        "price_history_deleted": 0,
        "system_logs_archived": 0,
        "system_logs_deleted": 0,
        "archive_file": None,
        "archive_size_mb": 0,
        "git_committed": False,
        "errors": [],
        "duration_seconds": 0
    }
    
    try:
        # Ensure archive directory exists
        _ensure_archive_dir()
        
        async with async_session_maker() as db:
            # Step 1: Archive price history
            price_stats = await _archive_price_history(db)
            stats["price_history_archived"] = price_stats["archived"]
            stats["price_history_deleted"] = price_stats["deleted"]
            
            if price_stats.get("error"):
                stats["errors"].append(price_stats["error"])
            
            # Step 2: Archive and clean system logs
            log_stats = await _archive_system_logs(db)
            stats["system_logs_archived"] = log_stats["archived"]
            stats["system_logs_deleted"] = log_stats["deleted"]
            
            if log_stats.get("error"):
                stats["errors"].append(log_stats["error"])
            
            # Step 3: Generate monthly summary
            summary = await _generate_monthly_summary(db)
            
            # Step 4: Save archive file
            archive_result = await _save_archive(summary, price_stats, log_stats)
            stats["archive_file"] = archive_result.get("file")
            stats["archive_size_mb"] = archive_result.get("size_mb", 0)
            
            # Step 5: Commit to Git (if enabled)
            if settings.ARCHIVE_TO_GIT and settings.GITHUB_TOKEN:
                git_result = await _commit_to_git(archive_result.get("file"))
                stats["git_committed"] = git_result
            
            # Step 6: Update archive metadata in system log
            await _log_archive_results(db, stats, start_time)
            
            stats["duration_seconds"] = round(
                (datetime.utcnow() - start_time).total_seconds(), 2
            )
            
            logger.info(
                f"✅ Monthly archive completed | "
                f"Price History: {stats['price_history_archived']} archived, {stats['price_history_deleted']} deleted | "
                f"System Logs: {stats['system_logs_archived']} archived, {stats['system_logs_deleted']} deleted | "
                f"Duration: {stats['duration_seconds']}s"
            )
            
            return stats
            
    except Exception as e:
        logger.error(f"❌ Monthly archive failed: {e}")
        stats["error"] = str(e)
        stats["duration_seconds"] = round(
            (datetime.utcnow() - start_time).total_seconds(), 2
        )
        return stats


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _ensure_archive_dir():
    """Create archives directory if it doesn't exist"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Archive directory: {ARCHIVE_DIR.absolute()}")


async def _archive_price_history(db: AsyncSession) -> Dict[str, Any]:
    """Archive and delete old price history"""
    result = {
        "archived": 0,
        "deleted": 0,
        "data": [],
        "error": None
    }
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=PRICE_HISTORY_RETENTION_DAYS)
        
        # Count records to archive
        count_query = select(func.count(PriceHistory.id)).where(
            PriceHistory.recorded_at < cutoff_date
        )
        count_result = await db.execute(count_query)
        total_to_archive = count_result.scalar() or 0
        
        if total_to_archive == 0:
            logger.info("No price history to archive")
            return result
        
        logger.info(f"📊 Archiving {total_to_archive} price history records")
        
        # Fetch records in batches for archiving
        archived_data = []
        offset = 0
        
        while offset < total_to_archive:
            query = (
                select(PriceHistory)
                .where(PriceHistory.recorded_at < cutoff_date)
                .order_by(PriceHistory.recorded_at.asc())
                .offset(offset)
                .limit(BATCH_SIZE)
            )
            
            batch_result = await db.execute(query)
            batch = batch_result.scalars().all()
            
            if not batch:
                break
            
            # Convert to dict for archiving
            for record in batch:
                archived_data.append({
                    "id": record.id,
                    "product_listing_id": str(record.product_listing_id),
                    "price": float(record.price),
                    "in_stock": record.in_stock,
                    "recorded_at": record.recorded_at.isoformat()
                })
            
            offset += len(batch)
            result["archived"] = len(archived_data)
        
        result["data"] = archived_data
        
        # Delete archived records
        delete_query = delete(PriceHistory).where(
            PriceHistory.recorded_at < cutoff_date
        )
        
        delete_result = await db.execute(delete_query)
        result["deleted"] = delete_result.rowcount
        
        await db.commit()
        
        logger.info(f"✅ Archived {result['archived']} price history records, deleted {result['deleted']}")
        
    except Exception as e:
        logger.error(f"Error archiving price history: {e}")
        result["error"] = str(e)
        await db.rollback()
    
    return result


async def _archive_system_logs(db: AsyncSession) -> Dict[str, Any]:
    """Archive and delete old system logs"""
    result = {
        "archived": 0,
        "deleted": 0,
        "data": [],
        "error": None
    }
    
    try:
        cutoff_date = date.today() - timedelta(days=SYSTEM_LOG_RETENTION_DAYS)
        
        # Get old logs
        query = (
            select(SystemLog)
            .where(SystemLog.log_date < cutoff_date)
            .order_by(SystemLog.log_date.asc())
        )
        
        log_result = await db.execute(query)
        old_logs = log_result.scalars().all()
        
        if not old_logs:
            logger.info("No system logs to archive")
            return result
        
        logger.info(f"📊 Archiving {len(old_logs)} system logs")
        
        # Convert to dict for archiving
        archived_data = []
        for log in old_logs:
            archived_data.append({
                "id": log.id,
                "log_date": log.log_date.isoformat(),
                "scraping_summary": log.scraping_summary,
                "analytics": log.analytics,
                "ml_processing": log.ml_processing,
                "archived_to_git": log.archived_to_git,
                "created_at": log.created_at.isoformat() if log.created_at else None
            })
        
        result["data"] = archived_data
        result["archived"] = len(archived_data)
        
        # Delete old logs
        delete_query = delete(SystemLog).where(
            SystemLog.log_date < cutoff_date
        )
        
        delete_result = await db.execute(delete_query)
        result["deleted"] = delete_result.rowcount
        
        await db.commit()
        
        logger.info(f"✅ Archived {result['archived']} system logs, deleted {result['deleted']}")
        
    except Exception as e:
        logger.error(f"Error archiving system logs: {e}")
        result["error"] = str(e)
        await db.rollback()
    
    return result


async def _generate_monthly_summary(db: AsyncSession) -> Dict[str, Any]:
    """Generate monthly summary statistics"""
    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "month": datetime.utcnow().strftime("%Y-%m"),
        "statistics": {}
    }
    
    try:
        # Get this month's date range
        today = date.today()
        first_of_month = today.replace(day=1)
        
        # Get last month's logs for summary
        last_month_start = (first_of_month - timedelta(days=1)).replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        
        query = (
            select(SystemLog)
            .where(
                SystemLog.log_date >= last_month_start,
                SystemLog.log_date <= last_month_end
            )
            .order_by(SystemLog.log_date.asc())
        )
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        # Aggregate statistics
        total_products_scraped = 0
        total_searches = 0
        total_alerts_sent = 0
        total_affiliate_clicks = 0
        total_revenue = 0
        
        for log in logs:
            scraping = log.scraping_summary or {}
            analytics = log.analytics or {}
            
            total_products_scraped += scraping.get("products_scraped", 0)
            total_searches += analytics.get("searches_performed", 0)
            total_alerts_sent += analytics.get("alerts_sent", 0)
            total_affiliate_clicks += analytics.get("affiliate_clicks", 0)
            total_revenue += analytics.get("revenue_inr", 0)
        
        summary["statistics"] = {
            "period": f"{last_month_start.isoformat()} to {last_month_end.isoformat()}",
            "days_covered": len(logs),
            "total_products_scraped": total_products_scraped,
            "total_searches": total_searches,
            "total_alerts_sent": total_alerts_sent,
            "total_affiliate_clicks": total_affiliate_clicks,
            "total_revenue_inr": total_revenue,
            "avg_products_per_day": round(total_products_scraped / max(len(logs), 1), 1),
            "avg_searches_per_day": round(total_searches / max(len(logs), 1), 1)
        }
        
        logger.info(f"📈 Generated monthly summary for {len(logs)} days")
        
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        summary["error"] = str(e)
    
    return summary


async def _save_archive(
    summary: Dict[str, Any],
    price_stats: Dict[str, Any],
    log_stats: Dict[str, Any]
) -> Dict[str, Any]:
    """Save archive data to compressed file"""
    result = {
        "file": None,
        "size_mb": 0
    }
    
    try:
        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        month = datetime.utcnow().strftime("%Y-%m")
        filename = f"archive_{month}_{timestamp}.json.gz"
        filepath = ARCHIVE_DIR / filename
        
        # Build archive data
        archive_data = {
            "metadata": {
                "created_at": datetime.utcnow().isoformat(),
                "version": "2.0",
                "type": "monthly_archive"
            },
            "summary": summary,
            "price_history": {
                "count": price_stats.get("archived", 0),
                "records": price_stats.get("data", [])
            },
            "system_logs": {
                "count": log_stats.get("archived", 0),
                "records": log_stats.get("data", [])
            }
        }
        
        # Write compressed file
        json_data = json.dumps(archive_data, default=str, indent=2)
        
        with gzip.open(filepath, 'wt', encoding='utf-8') as f:
            f.write(json_data)
        
        # Get file size
        file_size = filepath.stat().st_size
        size_mb = round(file_size / (1024 * 1024), 2)
        
        result["file"] = str(filepath)
        result["size_mb"] = size_mb
        
        logger.info(f"📁 Archive saved: {filepath} ({size_mb} MB)")
        
    except Exception as e:
        logger.error(f"Error saving archive: {e}")
        result["error"] = str(e)
    
    return result


async def _commit_to_git(archive_file: str) -> bool:
    """Commit archive file to Git repository"""
    if not archive_file or not settings.GITHUB_TOKEN:
        return False
    
    try:
        import base64
        import httpx
        
        # Read file content
        with open(archive_file, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
        
        # Get filename
        filename = Path(archive_file).name
        repo_path = f"archives/{filename}"
        
        # GitHub API endpoint
        api_url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/contents/{repo_path}"
        
        headers = {
            "Authorization": f"token {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        payload = {
            "message": f"Archive: {filename}",
            "content": content,
            "branch": settings.GITHUB_BRANCH
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.put(api_url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Archive committed to Git: {repo_path}")
                return True
            else:
                logger.warning(f"Git commit failed: {response.status_code} - {response.text[:200]}")
                return False
                
    except Exception as e:
        logger.error(f"Git commit error: {e}")
        return False


async def _log_archive_results(
    db: AsyncSession,
    stats: Dict[str, Any],
    start_time: datetime
):
    """Log archive results to system_logs"""
    try:
        today = date.today()
        
        result = await db.execute(
            select(SystemLog).where(SystemLog.log_date == today)
        )
        system_log = result.scalar_one_or_none()
        
        archive_data = {
            "job": "monthly_archive",
            "timestamp": start_time.isoformat(),
            "price_history_archived": stats.get("price_history_archived", 0),
            "price_history_deleted": stats.get("price_history_deleted", 0),
            "system_logs_archived": stats.get("system_logs_archived", 0),
            "system_logs_deleted": stats.get("system_logs_deleted", 0),
            "archive_file": stats.get("archive_file"),
            "archive_size_mb": stats.get("archive_size_mb", 0),
            "git_committed": stats.get("git_committed", False),
            "duration_seconds": stats.get("duration_seconds", 0)
        }
        
        if system_log:
            # Update existing log
            ml_processing = system_log.ml_processing or {}
            ml_processing["monthly_archive"] = archive_data
            system_log.ml_processing = ml_processing
            
            # Update archive tracking fields
            system_log.archived_to_git = stats.get("git_committed", False)
            system_log.archive_path = stats.get("archive_file")
            system_log.archive_size_mb = stats.get("archive_size_mb", 0)
            
            if stats.get("git_committed"):
                system_log.github_committed_at = datetime.utcnow()
        else:
            system_log = SystemLog(
                log_date=today,
                scraping_summary={},
                analytics={},
                ml_processing={"monthly_archive": archive_data},
                archived_to_git=stats.get("git_committed", False),
                archive_path=stats.get("archive_file"),
                archive_size_mb=stats.get("archive_size_mb", 0)
            )
            db.add(system_log)
        
        await db.commit()
        
    except Exception as e:
        logger.warning(f"Failed to log archive results: {e}")


# =============================================================================
# CLEANUP FUNCTIONS
# =============================================================================

async def cleanup_old_archives(days_to_keep: int = 365) -> Dict[str, Any]:
    """
    Clean up local archive files older than specified days
    
    Args:
        days_to_keep: Number of days to keep local archives
        
    Returns:
        Dictionary with cleanup statistics
    """
    result = {
        "files_checked": 0,
        "files_deleted": 0,
        "space_freed_mb": 0
    }
    
    try:
        cutoff_time = datetime.utcnow() - timedelta(days=days_to_keep)
        
        for file_path in ARCHIVE_DIR.glob("archive_*.json.gz"):
            result["files_checked"] += 1
            
            # Check file age
            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            
            if file_mtime < cutoff_time:
                file_size = file_path.stat().st_size
                file_path.unlink()
                
                result["files_deleted"] += 1
                result["space_freed_mb"] += file_size / (1024 * 1024)
        
        result["space_freed_mb"] = round(result["space_freed_mb"], 2)
        
        if result["files_deleted"] > 0:
            logger.info(
                f"🗑️ Cleaned up {result['files_deleted']} old archives, "
                f"freed {result['space_freed_mb']} MB"
            )
            
    except Exception as e:
        logger.error(f"Error cleaning up archives: {e}")
        result["error"] = str(e)
    
    return result


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    import asyncio
    
    print("📦 Starting Monthly Archive Job...")
    print("=" * 60)
    
    async def main():
        try:
            result = await run_monthly_archive()
            
            print("\n📊 Results:")
            print(f"   Price History Archived: {result.get('price_history_archived', 0)}")
            print(f"   Price History Deleted: {result.get('price_history_deleted', 0)}")
            print(f"   System Logs Archived: {result.get('system_logs_archived', 0)}")
            print(f"   System Logs Deleted: {result.get('system_logs_deleted', 0)}")
            print(f"   Archive File: {result.get('archive_file', 'N/A')}")
            print(f"   Archive Size: {result.get('archive_size_mb', 0)} MB")
            print(f"   Git Committed: {result.get('git_committed', False)}")
            print(f"   Duration: {result.get('duration_seconds', 0)}s")
            
            if result.get("errors"):
                print(f"\n⚠️ Errors: {result['errors']}")
            
            if result.get("error"):
                print(f"\n❌ Error: {result['error']}")
            else:
                print("\n✅ Job completed successfully!")
                
        except Exception as e:
            print(f"\n💥 Critical error: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(main())
    print("\n🏁 Monthly archive job finished.")
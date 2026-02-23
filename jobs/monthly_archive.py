"""
Monthly Data Archive Job
Runs on 1st of each month at 1 AM IST

FIXED: Auto-create archives directory
"""

import logging
import json
import csv
import os
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
from io import StringIO
import gzip
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, and_

from app.core.config import settings
from app.core.database import async_session_maker

# Import with error handling
try:
    from app.models import PriceHistory, Transaction, SystemLog
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    logging.getLogger(__name__).warning("Models not available")

logger = logging.getLogger(__name__)

# Configuration
PRICE_HISTORY_RETENTION_DAYS = getattr(settings, 'PRICE_HISTORY_DAYS', 120)
TRANSACTION_RETENTION_MONTHS = getattr(settings, 'DATA_RETENTION_MONTHS', 6)
ARCHIVE_DIR = "archives"


async def run_monthly_archive() -> Dict[str, Any]:
    """
    Monthly data archival and cleanup
    
    Process:
    1. Create archive directory if needed
    2. Export old price history to CSV
    3. Delete archived price history from DB
    4. Clean up old transactions
    5. Archive system logs
    6. Generate monthly analytics report
    7. Optional: Push to GitHub
    """
    logger.info("📦 Starting monthly archive...")
    start_time = datetime.utcnow()
    
    if not MODELS_AVAILABLE:
        logger.warning("Models not available - skipping archive")
        return {
            "message": "Models not available",
            "duration_seconds": 0
        }
    
    # Create archive directory
    month_str = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m")
    archive_path = os.path.join(ARCHIVE_DIR, month_str)
    
    try:
        # Create directory and ensure it exists
        Path(archive_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"Archive directory created: {archive_path}")
    except Exception as e:
        logger.error(f"Failed to create archive directory: {e}")
        return {
            "error": f"Failed to create directory: {str(e)}",
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds()
        }
    
    stats = {
        "month": month_str,
        "archive_path": archive_path,
        "price_history_archived": 0,
        "price_history_deleted": 0,
        "transactions_cleaned": 0,
        "logs_archived": 0,
        "files_created": [],
        "total_size_mb": 0,
        "github_pushed": False,
        "duration_seconds": 0
    }
    
    try:
        async with async_session_maker() as db:
            # 1. Archive old price history
            try:
                price_stats = await archive_price_history(db, archive_path)
                stats["price_history_archived"] = price_stats.get("archived", 0)
                stats["price_history_deleted"] = price_stats.get("deleted", 0)
                if price_stats.get("file"):
                    stats["files_created"].append(price_stats["file"])
            except Exception as e:
                logger.warning(f"Price history archive failed: {e}")
                stats["errors"] = [f"Price history: {str(e)}"]
            
            # 2. Clean up old transactions
            try:
                tx_stats = await cleanup_old_transactions(db, archive_path)
                stats["transactions_cleaned"] = tx_stats.get("cleaned", 0)
                if tx_stats.get("file"):
                    stats["files_created"].append(tx_stats["file"])
            except Exception as e:
                logger.warning(f"Transaction cleanup failed: {e}")
            
            # 3. Archive system logs
            try:
                log_stats = await archive_system_logs(db, archive_path)
                stats["logs_archived"] = log_stats.get("archived", 0)
                if log_stats.get("file"):
                    stats["files_created"].append(log_stats["file"])
            except Exception as e:
                logger.warning(f"Log archive failed: {e}")
            
            # 4. Generate monthly report
            try:
                report = await generate_monthly_report(db, month_str)
                report_file = os.path.join(archive_path, "monthly_report.json")
                with open(report_file, "w") as f:
                    json.dump(report, f, indent=2, default=str)
                stats["files_created"].append("monthly_report.json")
            except Exception as e:
                logger.warning(f"Report generation failed: {e}")
            
            # 5. Calculate total archive size
            try:
                total_size = 0
                if os.path.exists(archive_path):
                    for file in os.listdir(archive_path):
                        file_path = os.path.join(archive_path, file)
                        if os.path.isfile(file_path):
                            total_size += os.path.getsize(file_path)
                    stats["total_size_mb"] = round(total_size / (1024 * 1024), 2)
            except Exception as e:
                logger.warning(f"Size calculation failed: {e}")
            
            # 6. Push to GitHub (optional)
            if settings.ARCHIVE_TO_GIT and settings.GITHUB_TOKEN:
                try:
                    pushed = await push_to_github(archive_path, month_str)
                    stats["github_pushed"] = pushed
                except Exception as e:
                    logger.warning(f"GitHub push failed: {e}")
                    stats["github_error"] = str(e)
            
            # Update system log with archive info
            try:
                await log_archive_results(db, stats)
            except Exception as e:
                logger.warning(f"Failed to log archive results: {e}")
            
            stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                f"✅ Monthly archive completed | "
                f"Month: {month_str} | "
                f"Price History: {stats['price_history_archived']} | "
                f"Size: {stats['total_size_mb']}MB | "
                f"Duration: {stats['duration_seconds']:.2f}s"
            )
            
            return stats
            
    except Exception as e:
        logger.error(f"❌ Monthly archive failed: {e}")
        stats["error"] = str(e)
        stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
        raise


async def archive_price_history(
    db: AsyncSession,
    archive_path: str
) -> Dict[str, Any]:
    """Archive and delete old price history records"""
    
    cutoff_date = datetime.utcnow() - timedelta(days=PRICE_HISTORY_RETENTION_DAYS)
    
    try:
        # Get old records
        query = (
            select(PriceHistory)
            .where(PriceHistory.recorded_at < cutoff_date)
            .order_by(PriceHistory.recorded_at)
            .limit(100000)
        )
        
        result = await db.execute(query)
        old_records = result.scalars().all()
        
        if not old_records:
            return {"archived": 0, "deleted": 0}
        
        # Export to CSV
        csv_file = os.path.join(archive_path, "price_history.csv.gz")
        
        with gzip.open(csv_file, "wt", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "product_listing_id", "price", "in_stock", "recorded_at"])
            
            for record in old_records:
                writer.writerow([
                    record.id,
                    str(record.product_listing_id),
                    float(record.price),
                    record.in_stock,
                    record.recorded_at.isoformat()
                ])
        
        archived_count = len(old_records)
        
        # Delete old records
        delete_query = delete(PriceHistory).where(
            PriceHistory.recorded_at < cutoff_date
        )
        result = await db.execute(delete_query)
        deleted_count = result.rowcount
        
        await db.commit()
        
        logger.info(f"Price history: archived {archived_count}, deleted {deleted_count}")
        
        return {
            "archived": archived_count,
            "deleted": deleted_count,
            "file": "price_history.csv.gz"
        }
        
    except Exception as e:
        logger.error(f"Price history archive error: {e}")
        return {"archived": 0, "deleted": 0}


async def cleanup_old_transactions(
    db: AsyncSession,
    archive_path: str
) -> Dict[str, Any]:
    """Archive and clean up old transaction records"""
    
    cutoff_date = datetime.utcnow() - timedelta(days=TRANSACTION_RETENTION_MONTHS * 30)
    
    try:
        # Get old transactions
        query = (
            select(Transaction)
            .where(Transaction.created_at < cutoff_date)
            .order_by(Transaction.created_at)
            .limit(50000)
        )
        
        result = await db.execute(query)
        old_transactions = result.scalars().all()
        
        if not old_transactions:
            return {"cleaned": 0}
        
        # Export summary
        summary_file = os.path.join(archive_path, "transactions_summary.json.gz")
        
        summary = {
            "period_start": None,
            "period_end": None,
            "total_count": len(old_transactions),
            "by_type": {},
            "by_status": {},
            "by_platform": {},
            "total_revenue": 0
        }
        
        for tx in old_transactions:
            if tx.created_at:
                if not summary["period_start"] or tx.created_at < datetime.fromisoformat(summary["period_start"]):
                    summary["period_start"] = tx.created_at.isoformat()
                if not summary["period_end"] or tx.created_at > datetime.fromisoformat(summary["period_end"]):
                    summary["period_end"] = tx.created_at.isoformat()
            
            tx_type = tx.type or "unknown"
            summary["by_type"][tx_type] = summary["by_type"].get(tx_type, 0) + 1
            
            tx_status = tx.status or "unknown"
            summary["by_status"][tx_status] = summary["by_status"].get(tx_status, 0) + 1
            
            platform = getattr(tx, 'platform', None) or "unknown"
            summary["by_platform"][platform] = summary["by_platform"].get(platform, 0) + 1
            
            if tx.status == "success" and tx.type == "payment":
                summary["total_revenue"] += float(tx.amount or 0)
        
        with gzip.open(summary_file, "wt", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        # Clean metadata
        for tx in old_transactions:
            if tx.meta_data:
                safe_meta = {
                    "plan_id": tx.meta_data.get("plan_id"),
                    "plan_name": tx.meta_data.get("plan_name"),
                    "mock_mode": tx.meta_data.get("mock_mode")
                }
                tx.meta_data = safe_meta
            
            tx.razorpay_signature = None
            if hasattr(tx, 'purchase_token'):
                tx.purchase_token = None
        
        await db.commit()
        
        logger.info(f"Transactions: cleaned {len(old_transactions)}")
        
        return {
            "cleaned": len(old_transactions),
            "file": "transactions_summary.json.gz"
        }
        
    except Exception as e:
        logger.error(f"Transaction cleanup error: {e}")
        return {"cleaned": 0}


async def archive_system_logs(
    db: AsyncSession,
    archive_path: str
) -> Dict[str, Any]:
    """Archive old system logs"""
    
    cutoff_date = date.today() - timedelta(days=30)
    
    try:
        query = (
            select(SystemLog)
            .where(SystemLog.log_date < cutoff_date)
            .order_by(SystemLog.log_date)
        )
        
        result = await db.execute(query)
        old_logs = result.scalars().all()
        
        if not old_logs:
            return {"archived": 0}
        
        logs_file = os.path.join(archive_path, "system_logs.json.gz")
        
        logs_data = []
        for log in old_logs:
            logs_data.append({
                "log_date": log.log_date.isoformat(),
                "scraping_summary": log.scraping_summary,
                "analytics": log.analytics,
                "ml_processing": log.ml_processing
            })
        
        with gzip.open(logs_file, "wt", encoding="utf-8") as f:
            json.dump(logs_data, f, indent=2)
        
        archived_count = len(old_logs)
        
        delete_query = delete(SystemLog).where(SystemLog.log_date < cutoff_date)
        await db.execute(delete_query)
        await db.commit()
        
        logger.info(f"System logs: archived {archived_count}")
        
        return {
            "archived": archived_count,
            "file": "system_logs.json.gz"
        }
        
    except Exception as e:
        logger.error(f"System logs archive error: {e}")
        return {"archived": 0}


async def generate_monthly_report(
    db: AsyncSession,
    month_str: str
) -> Dict[str, Any]:
    """Generate monthly analytics summary report"""
    
    try:
        year, month = map(int, month_str.split("-"))
        start_date = date(year, month, 1)
        
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
        
        query = (
            select(SystemLog)
            .where(
                SystemLog.log_date >= start_date,
                SystemLog.log_date < end_date
            )
        )
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        report = {
            "month": month_str,
            "generated_at": datetime.utcnow().isoformat(),
            "days_logged": len(logs),
            "totals": {
                "active_users": 0,
                "new_signups": 0,
                "searches": 0,
                "affiliate_clicks": 0,
                "alerts_sent": 0,
                "revenue_inr": 0,
                "products_scraped": 0
            }
        }
        
        for log in logs:
            analytics = log.analytics or {}
            scraping = log.scraping_summary or {}
            
            report["totals"]["active_users"] = max(
                report["totals"]["active_users"],
                analytics.get("active_users", 0)
            )
            report["totals"]["new_signups"] += analytics.get("new_signups", 0)
            report["totals"]["searches"] += analytics.get("searches_performed", 0)
            report["totals"]["affiliate_clicks"] += analytics.get("affiliate_clicks", 0)
            report["totals"]["alerts_sent"] += analytics.get("alerts_sent", 0)
            report["totals"]["revenue_inr"] += analytics.get("revenue_inr", 0)
            report["totals"]["products_scraped"] += scraping.get("products_scraped", 0)
        
        return report
        
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return {"error": str(e)}


async def push_to_github(archive_path: str, month_str: str) -> bool:
    """Push archive to GitHub repository"""
    
    if not settings.GITHUB_TOKEN or not settings.GITHUB_REPO:
        logger.info("GitHub not configured, skipping push")
        return False
    
    try:
        import httpx
        import base64
        
        for filename in os.listdir(archive_path):
            file_path = os.path.join(archive_path, filename)
            
            if not os.path.isfile(file_path):
                continue
            
            with open(file_path, "rb") as f:
                content = base64.b64encode(f.read()).decode()
            
            api_url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/contents/archives/{month_str}/{filename}"
            
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    api_url,
                    headers={
                        "Authorization": f"token {settings.GITHUB_TOKEN}",
                        "Accept": "application/vnd.github.v3+json"
                    },
                    json={
                        "message": f"Archive {month_str}: {filename}",
                        "content": content,
                        "branch": settings.GITHUB_BRANCH
                    },
                    timeout=30.0
                )
                
                if response.status_code not in [200, 201]:
                    logger.warning(f"GitHub push failed for {filename}: {response.status_code}")
        
        logger.info(f"Archive pushed to GitHub: {settings.GITHUB_REPO}")
        return True
        
    except Exception as e:
        logger.error(f"GitHub push error: {e}")
        return False


async def log_archive_results(
    db: AsyncSession,
    stats: Dict[str, Any]
):
    """Log archive results to today's system log"""
    
    try:
        today = date.today()
        
        result = await db.execute(
            select(SystemLog).where(SystemLog.log_date == today)
        )
        log = result.scalar_one_or_none()
        
        if not log:
            log = SystemLog(log_date=today)
            db.add(log)
        
        log.archived_to_git = stats.get("github_pushed", False)
        log.archive_path = stats.get("archive_path")
        log.archive_size_mb = stats.get("total_size_mb")
        
        if stats.get("github_pushed"):
            log.github_committed_at = datetime.utcnow()
        
        await db.commit()
        
    except Exception as e:
        logger.warning(f"Failed to log archive results: {e}")
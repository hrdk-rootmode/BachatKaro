"""
Google Play Subscription Sync Job
=================================

Runs every hour to sync subscription status with Google Play

Features:
- Syncs Google Play subscription status
- Handles renewals, cancellations, expirations
- Works in mock mode for development
- Graceful fallback when Play API unavailable

Author: DealHunt
Version: 2.0 (Complete Implementation)
"""

import logging
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

# Add parent directory to Python path for imports
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 🔧 WINDOWS FIX: Silence Proactor Event Loop Warning
if sys.platform == 'win32':
    from asyncio.proactor_events import _ProactorBasePipeTransport
    def silence_proactor_del(self): pass
    _ProactorBasePipeTransport.__del__ = silence_proactor_del

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import User, Transaction, SystemLog

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

SYNC_BATCH_SIZE = 100
EXPIRY_BUFFER_HOURS = 24  # Check subscriptions expiring in next 24 hours


# =============================================================================
# MAIN JOB FUNCTION
# =============================================================================

async def run_sync_subscriptions() -> Dict[str, Any]:
    """
    Main subscription sync job
    
    Process:
    1. Get users with Google Play subscriptions
    2. Check subscription status via Google Play API
    3. Update user plan if changed
    4. Handle expirations and renewals
    5. Log results
    
    Returns:
        Dictionary with sync statistics
    """
    logger.info("🔄 Starting subscription sync...")
    start_time = datetime.utcnow()
    
    stats = {
        "subscriptions_checked": 0,
        "renewals_processed": 0,
        "expirations_processed": 0,
        "cancellations_processed": 0,
        "errors": [],
        "mock_mode": settings.GOOGLE_PLAY_MOCK_MODE,
        "duration_seconds": 0
    }
    
    # Skip in mock mode
    if settings.GOOGLE_PLAY_MOCK_MODE:
        logger.info("📱 Google Play sync skipped (mock mode)")
        stats["message"] = "Skipped in mock mode"
        stats["duration_seconds"] = 0.1
        return stats
    
    try:
        async with async_session_maker() as db:
            # Get users with Google Play subscriptions
            users = await _get_google_play_subscribers(db)
            stats["subscriptions_checked"] = len(users)
            
            if not users:
                logger.info("No Google Play subscriptions to sync")
                stats["message"] = "No subscriptions to sync"
                stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
                return stats
            
            logger.info(f"📋 Checking {len(users)} Google Play subscriptions")
            
            # Process each subscription
            for user in users:
                try:
                    result = await _sync_user_subscription(user, db)
                    
                    if result == "renewed":
                        stats["renewals_processed"] += 1
                    elif result == "expired":
                        stats["expirations_processed"] += 1
                    elif result == "cancelled":
                        stats["cancellations_processed"] += 1
                        
                except Exception as e:
                    logger.error(f"Error syncing user {user.id}: {e}")
                    stats["errors"].append(str(e))
            
            # Commit all changes
            await db.commit()
            
            # Log results
            await _log_sync_results(db, stats, start_time)
            
            stats["duration_seconds"] = round(
                (datetime.utcnow() - start_time).total_seconds(), 2
            )
            
            logger.info(
                f"✅ Subscription sync completed | "
                f"Checked: {stats['subscriptions_checked']} | "
                f"Renewals: {stats['renewals_processed']} | "
                f"Expirations: {stats['expirations_processed']} | "
                f"Duration: {stats['duration_seconds']}s"
            )
            
            return stats
            
    except Exception as e:
        logger.error(f"❌ Subscription sync failed: {e}")
        stats["error"] = str(e)
        stats["duration_seconds"] = round(
            (datetime.utcnow() - start_time).total_seconds(), 2
        )
        return stats


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def _get_google_play_subscribers(db: AsyncSession) -> List[User]:
    """Get users with active Google Play subscriptions"""
    try:
        # Get users who subscribed via Android
        query = (
            select(User)
            .where(
                and_(
                    User.subscription_platform == "android",
                    User.plan.in_(["pro", "premium"]),
                    User.is_blocked == False
                )
            )
            .limit(SYNC_BATCH_SIZE)
        )
        
        result = await db.execute(query)
        return list(result.scalars().all())
        
    except Exception as e:
        logger.error(f"Error getting Google Play subscribers: {e}")
        return []


async def _sync_user_subscription(user: User, db: AsyncSession) -> str:
    """Sync subscription status for a single user"""
    try:
        # Get the latest Google Play transaction
        transaction = await _get_latest_transaction(user.id, db)
        
        if not transaction or not transaction.purchase_token:
            return "no_token"
        
        # Check subscription status via Google Play API
        status = await _check_google_play_status(
            purchase_token=transaction.purchase_token,
            product_id=_get_product_id_for_plan(user.plan)
        )
        
        if not status:
            return "api_error"
        
        # Process based on status
        expiry_time = status.get("expiry_time")
        auto_renewing = status.get("auto_renewing", False)
        payment_state = status.get("payment_state")
        cancel_reason = status.get("cancel_reason")
        
        now = datetime.utcnow()
        
        # Check if expired
        if expiry_time and expiry_time < now:
            # Subscription expired
            user.plan = "free"
            user.plan_expires_at = None
            
            # Update transaction status
            transaction.status = "expired"
            
            logger.info(f"Subscription expired for user {user.id}")
            return "expired"
        
        # Check if cancelled
        if cancel_reason is not None:
            # User cancelled but still active until expiry
            logger.info(f"Subscription cancelled for user {user.id}, expires {expiry_time}")
            return "cancelled"
        
        # Check if renewed
        if auto_renewing and expiry_time and expiry_time > user.plan_expires_at:
            # Subscription renewed
            user.plan_expires_at = expiry_time
            
            logger.info(f"Subscription renewed for user {user.id}, new expiry {expiry_time}")
            return "renewed"
        
        return "unchanged"
        
    except Exception as e:
        logger.error(f"Error syncing subscription: {e}")
        return "error"


async def _get_latest_transaction(user_id, db: AsyncSession) -> Optional[Transaction]:
    """Get user's latest Google Play transaction"""
    try:
        query = (
            select(Transaction)
            .where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.platform == "android",
                    Transaction.purchase_token.isnot(None)
                )
            )
            .order_by(Transaction.created_at.desc())
            .limit(1)
        )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.debug(f"Error getting transaction: {e}")
        return None


def _get_product_id_for_plan(plan: str) -> str:
    """Get Google Play product ID for plan"""
    plan_to_sku = settings.google_play_plan_to_sku
    return plan_to_sku.get(plan, settings.GOOGLE_PLAY_PRO_SKU)


async def _check_google_play_status(
    purchase_token: str,
    product_id: str
) -> Optional[Dict[str, Any]]:
    """Check subscription status via Google Play API"""
    try:
        # Skip in mock mode
        if settings.GOOGLE_PLAY_MOCK_MODE:
            return None
        
        # Check if properly configured
        if not settings.is_google_play_configured:
            logger.warning("Google Play not properly configured")
            return None
        
        # Use Google Play API
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        credentials = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_APPLICATION_CREDENTIALS,
            scopes=['https://www.googleapis.com/auth/androidpublisher']
        )
        
        service = build('androidpublisher', 'v3', credentials=credentials)
        
        result = service.purchases().subscriptions().get(
            packageName=settings.GOOGLE_PLAY_PACKAGE_NAME,
            subscriptionId=product_id,
            token=purchase_token
        ).execute()
        
        # Parse response
        expiry_millis = result.get('expiryTimeMillis')
        expiry_time = None
        if expiry_millis:
            expiry_time = datetime.fromtimestamp(int(expiry_millis) / 1000)
        
        return {
            "expiry_time": expiry_time,
            "auto_renewing": result.get('autoRenewing', False),
            "payment_state": result.get('paymentState'),
            "cancel_reason": result.get('cancelReason'),
            "order_id": result.get('orderId')
        }
        
    except Exception as e:
        logger.error(f"Google Play API error: {e}")
        return None


async def _log_sync_results(
    db: AsyncSession,
    stats: Dict[str, Any],
    start_time: datetime
):
    """Log sync results to system_logs"""
    try:
        today = date.today()
        
        result = await db.execute(
            select(SystemLog).where(SystemLog.log_date == today)
        )
        system_log = result.scalar_one_or_none()
        
        sync_data = {
            "job": "sync_subscriptions",
            "timestamp": start_time.isoformat(),
            "subscriptions_checked": stats.get("subscriptions_checked", 0),
            "renewals": stats.get("renewals_processed", 0),
            "expirations": stats.get("expirations_processed", 0),
            "cancellations": stats.get("cancellations_processed", 0),
            "mock_mode": stats.get("mock_mode", True),
            "duration_seconds": stats.get("duration_seconds", 0)
        }
        
        if system_log:
            analytics = system_log.analytics or {}
            analytics["subscription_sync"] = sync_data
            system_log.analytics = analytics
        else:
            system_log = SystemLog(
                log_date=today,
                scraping_summary={},
                analytics={"subscription_sync": sync_data},
                ml_processing={}
            )
            db.add(system_log)
        
        await db.commit()
        
    except Exception as e:
        logger.warning(f"Failed to log sync results: {e}")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    import asyncio
    
    print("🔄 Starting Subscription Sync Job...")
    print("=" * 60)
    
    async def main():
        try:
            result = await run_sync_subscriptions()
            
            print("\n📊 Results:")
            print(f"   Mock Mode: {result.get('mock_mode', True)}")
            print(f"   Subscriptions Checked: {result.get('subscriptions_checked', 0)}")
            print(f"   Renewals: {result.get('renewals_processed', 0)}")
            print(f"   Expirations: {result.get('expirations_processed', 0)}")
            print(f"   Cancellations: {result.get('cancellations_processed', 0)}")
            print(f"   Duration: {result.get('duration_seconds', 0)}s")
            
            if result.get("error"):
                print(f"\n❌ Error: {result['error']}")
            elif result.get("message"):
                print(f"\n📝 Message: {result['message']}")
            else:
                print("\n✅ Job completed successfully!")
                
        except Exception as e:
            print(f"\n💥 Critical error: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(main())
    print("\n🏁 Subscription sync job finished.")
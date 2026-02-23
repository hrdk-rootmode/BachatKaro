"""
Google Play Subscription Sync Job
Runs every 1 hour to sync subscription status with Google Play

PRODUCTION-READY VERSION:
- Works in mock mode (skips gracefully)
- Works with real Google Play credentials (full sync)
- No code changes needed when switching modes
- Handles all edge cases
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)

# Configuration
BATCH_SIZE = 50  # Process 50 subscriptions per batch
SYNC_BUFFER_HOURS = 24  # Re-sync subscriptions expiring within 24h


async def run_sync_subscriptions() -> Dict[str, Any]:
    """
    Sync subscription status with Google Play
    
    MOCK MODE: Returns immediately (no real subscriptions to sync)
    PRODUCTION MODE: Syncs all active Android subscriptions
    
    Process:
    1. Check if Google Play is configured
    2. Get all Android subscriptions
    3. Verify status with Google Play API
    4. Update expired/renewed/cancelled subscriptions
    5. Handle grace periods
    """
    logger.info("🔄 Starting Google Play subscription sync...")
    start_time = datetime.utcnow()
    
    stats = {
        "total_checked": 0,
        "still_active": 0,
        "expired": 0,
        "renewed": 0,
        "cancelled": 0,
        "grace_period": 0,
        "errors": [],
        "duration_seconds": 0
    }
    
    # =========================================================================
    # CHECK 1: Is Google Play client available?
    # =========================================================================
    try:
        from app.services.payments.google_play import google_play_client
        GOOGLE_PLAY_AVAILABLE = True
    except ImportError as e:
        logger.info(f"Google Play client not available: {e}")
        stats["message"] = "Google Play not installed"
        stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
        return stats
    
    # =========================================================================
    # CHECK 2: Is Google Play in mock mode?
    # =========================================================================
    if google_play_client.is_mock_mode:
        logger.info("Google Play in mock mode - skipping real sync")
        stats["message"] = "Mock mode - no real subscriptions to sync"
        stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
        return stats
    
    # =========================================================================
    # CHECK 3: Are models available?
    # =========================================================================
    try:
        from app.models import User, Transaction
        MODELS_AVAILABLE = True
    except ImportError as e:
        logger.error(f"Models not available: {e}")
        stats["message"] = "Database models not available"
        stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
        return stats
    
    # =========================================================================
    # PRODUCTION MODE: Sync real subscriptions
    # =========================================================================
    try:
        async with async_session_maker() as db:
            # Get Android subscriptions to check
            subscriptions = await get_android_subscriptions(db)
            
            stats["total_checked"] = len(subscriptions)
            
            if not subscriptions:
                logger.info("No Android subscriptions to sync")
                stats["message"] = "No active subscriptions found"
                stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
                return stats
            
            # Process in batches
            for i in range(0, len(subscriptions), BATCH_SIZE):
                batch = subscriptions[i:i + BATCH_SIZE]
                batch_stats = await process_subscription_batch(db, batch)
                
                # Merge stats
                stats["still_active"] += batch_stats.get("still_active", 0)
                stats["expired"] += batch_stats.get("expired", 0)
                stats["renewed"] += batch_stats.get("renewed", 0)
                stats["cancelled"] += batch_stats.get("cancelled", 0)
                stats["grace_period"] += batch_stats.get("grace_period", 0)
                
                # Limit error messages
                errors = batch_stats.get("errors", [])
                stats["errors"].extend(errors[:5])  # Max 5 errors per batch
            
            stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                f"✅ Subscription sync completed | "
                f"Checked: {stats['total_checked']} | "
                f"Active: {stats['still_active']} | "
                f"Expired: {stats['expired']} | "
                f"Renewed: {stats['renewed']} | "
                f"Cancelled: {stats['cancelled']} | "
                f"Grace: {stats['grace_period']} | "
                f"Duration: {stats['duration_seconds']:.2f}s"
            )
            
            return stats
            
    except Exception as e:
        logger.error(f"❌ Subscription sync failed: {e}")
        stats["error"] = str(e)
        stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
        raise


async def get_android_subscriptions(db: AsyncSession) -> List[Dict]:
    """
    Get all Android subscriptions that need syncing
    
    Criteria:
    - subscription_platform = 'android'
    - plan in ['pro', 'premium']
    - not blocked
    - has valid purchase_token
    """
    from app.models import User, Transaction
    
    try:
        # Get users with Android subscriptions
        query = (
            select(User)
            .where(
                User.subscription_platform == "android",
                User.plan.in_(["pro", "premium"]),
                User.is_blocked == False
            )
        )
        
        result = await db.execute(query)
        users = result.scalars().all()
        
        subscriptions = []
        
        for user in users:
            # Get the latest successful Android transaction with purchase token
            tx_query = (
                select(Transaction)
                .where(
                    Transaction.user_id == user.id,
                    Transaction.platform == "android",
                    Transaction.status == "success",
                    Transaction.purchase_token.isnot(None)
                )
                .order_by(Transaction.created_at.desc())
                .limit(1)
            )
            
            tx_result = await db.execute(tx_query)
            transaction = tx_result.scalar_one_or_none()
            
            if transaction and transaction.purchase_token:
                # Get product_id from metadata
                product_id = None
                if transaction.meta_data:
                    product_id = transaction.meta_data.get("product_id")
                
                # Derive from plan if not in metadata
                if not product_id:
                    from app.services.payments.google_play import google_play_client
                    product_id = google_play_client.get_sku_from_plan(user.plan)
                
                subscriptions.append({
                    "user_id": str(user.id),
                    "user_email": user.email,
                    "plan": user.plan,
                    "expires_at": user.plan_expires_at,
                    "purchase_token": transaction.purchase_token,
                    "product_id": product_id,
                    "transaction_id": str(transaction.id)
                })
        
        return subscriptions
        
    except Exception as e:
        logger.error(f"Error getting Android subscriptions: {e}")
        return []


async def process_subscription_batch(
    db: AsyncSession,
    batch: List[Dict]
) -> Dict[str, Any]:
    """Process a batch of subscriptions"""
    
    stats = {
        "still_active": 0,
        "expired": 0,
        "renewed": 0,
        "cancelled": 0,
        "grace_period": 0,
        "errors": []
    }
    
    for sub in batch:
        try:
            result = await sync_single_subscription(db, sub)
            
            if result == "active":
                stats["still_active"] += 1
            elif result == "expired":
                stats["expired"] += 1
            elif result == "renewed":
                stats["renewed"] += 1
            elif result == "cancelled":
                stats["cancelled"] += 1
            elif result == "grace_period":
                stats["grace_period"] += 1
                
        except Exception as e:
            error_msg = f"{sub['user_email']}: {str(e)[:100]}"
            stats["errors"].append(error_msg)
            logger.error(f"Failed to sync {sub['user_email']}: {e}")
    
    # Commit all changes in batch
    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Batch commit error: {e}")
        await db.rollback()
    
    return stats


async def sync_single_subscription(
    db: AsyncSession,
    sub: Dict
) -> str:
    """
    Sync a single subscription with Google Play
    
    Returns:
        Status: 'active', 'expired', 'renewed', 'cancelled', 'grace_period'
    """
    from app.models import User
    from app.services.payments.google_play import google_play_client
    
    try:
        # Get subscription status from Google Play API
        status = await google_play_client.get_subscription_status(
            purchase_token=sub["purchase_token"],
            product_id=sub["product_id"]
        )
        
        if not status:
            logger.warning(f"No status returned for {sub['user_email']}")
            return "error"
        
        # Get user from database
        result = await db.execute(
            select(User).where(User.id == UUID(sub["user_id"]))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"User not found: {sub['user_id']}")
            return "error"
        
        # Extract status fields
        is_active = status.get("is_active", False)
        expiry_time = status.get("expiry_time")
        auto_renewing = status.get("auto_renewing", False)
        is_grace_period = status.get("is_grace_period", False)
        
        now = datetime.utcnow()
        
        # =====================================================================
        # HANDLE DIFFERENT SUBSCRIPTION STATES
        # =====================================================================
        
        # STATE 1: Grace Period (payment failed, but still active)
        if is_grace_period:
            logger.info(f"User {sub['user_email']} in grace period")
            
            if user.usage_stats is None:
                user.usage_stats = {}
            user.usage_stats["grace_period_started"] = now.isoformat()
            
            return "grace_period"
        
        # STATE 2: Active & Valid
        elif is_active and expiry_time:
            new_expiry = expiry_time
            
            if isinstance(new_expiry, datetime):
                # Check if subscription renewed (expiry extended)
                if user.plan_expires_at and new_expiry > user.plan_expires_at:
                    logger.info(f"Subscription renewed for {sub['user_email']}")
                    
                    user.plan_expires_at = new_expiry
                    
                    if user.usage_stats is None:
                        user.usage_stats = {}
                    user.usage_stats["last_renewal"] = now.isoformat()
                    
                    # Invalidate cache
                    await invalidate_user_cache(sub["user_id"])
                    
                    return "renewed"
                else:
                    # Still active, no change needed
                    return "active"
            
            return "active"
        
        # STATE 3: Expired or Cancelled
        else:
            if user.plan != "free":
                logger.info(f"Subscription expired for {sub['user_email']}")
                
                # Downgrade to free
                user.plan = "free"
                user.plan_expires_at = None
                
                if user.usage_stats is None:
                    user.usage_stats = {}
                user.usage_stats["subscription_expired_at"] = now.isoformat()
                user.usage_stats["previous_plan"] = sub["plan"]
                
                # Invalidate all user caches
                await invalidate_user_cache(sub["user_id"])
                
                # Determine if cancelled by user or expired naturally
                if not auto_renewing:
                    return "cancelled"
                else:
                    return "expired"
            
            return "expired"
            
    except Exception as e:
        logger.error(f"Error syncing subscription for {sub.get('user_email')}: {e}")
        raise


async def invalidate_user_cache(user_id: str):
    """Invalidate all caches related to a user"""
    try:
        from app.core.redis_client import redis_client
        
        cache_keys = [
            f"subscription:{user_id}",
            f"user:{user_id}",
            f"watchlist:{user_id}",
            f"streak:{user_id}"
        ]
        
        for key in cache_keys:
            try:
                await redis_client.delete(key)
            except Exception as e:
                logger.debug(f"Failed to delete cache key {key}: {e}")
                
    except ImportError:
        # Redis not available, skip caching
        pass
    except Exception as e:
        logger.warning(f"Cache invalidation error: {e}")
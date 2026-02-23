"""
Price Alert Checker
Runs every 6 hours to notify users of price drops

FIXED: Redis and database connection handling
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import User, UserWatchlist, Product, ProductListing, Platform

logger = logging.getLogger(__name__)

# Configuration
MAX_ALERTS_PER_USER = 5
ALERT_COOLDOWN_HOURS = 6


async def run_check_price_alerts() -> Dict[str, Any]:
    """Check all watchlists for price drops and send notifications"""
    logger.info("🔔 Starting price alert check...")
    start_time = datetime.utcnow()
    
    stats = {
        "users_checked": 0,
        "alerts_triggered": 0,
        "notifications_sent": 0,
        "errors": [],
        "duration_seconds": 0
    }
    
    try:
        async with async_session_maker() as db:
            # Get all watchlist items with prices
            alerts_by_user = await get_price_alerts(db)
            
            stats["users_checked"] = len(alerts_by_user)
            
            if not alerts_by_user:
                logger.info("No price alerts to send")
                stats["message"] = "No alerts triggered"
                stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
                return stats
            
            # Process each user's alerts
            for user_id, alerts in alerts_by_user.items():
                try:
                    sent = await process_user_alerts(db, user_id, alerts)
                    stats["alerts_triggered"] += len(alerts)
                    stats["notifications_sent"] += sent
                except Exception as e:
                    stats["errors"].append(f"User {user_id}: {str(e)[:100]}")
                    logger.error(f"Failed to process alerts for user {user_id}: {e}")
            
            stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                f"✅ Price alerts checked | "
                f"Users: {stats['users_checked']} | "
                f"Alerts: {stats['alerts_triggered']} | "
                f"Sent: {stats['notifications_sent']} | "
                f"Duration: {stats['duration_seconds']:.2f}s"
            )
            
            return stats
            
    except Exception as e:
        logger.error(f"❌ Price alert check failed: {e}")
        stats["error"] = str(e)
        stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
        raise


async def get_price_alerts(db: AsyncSession) -> Dict[str, List[Dict]]:
    """Get all watchlist items where price dropped"""
    alerts_by_user: Dict[str, List[Dict]] = {}
    
    try:
        # Get watchlist items with product and listing data
        query = (
            select(
                UserWatchlist,
                User,
                Product,
                ProductListing,
                Platform
            )
            .join(User, UserWatchlist.user_id == User.id)
            .join(Product, UserWatchlist.product_id == Product.id)
            .join(ProductListing, Product.id == ProductListing.product_id)
            .join(Platform, ProductListing.platform_id == Platform.id)
            .where(
                User.is_blocked == False,
                UserWatchlist.notify == True,
                ProductListing.in_stock == True
            )
        )
        
        result = await db.execute(query)
        rows = result.fetchall()
        
        for row in rows:
            watchlist_item, user, product, listing, platform = row
            should_alert = False
            alert_type = None
            
            target_price = watchlist_item.target_price
            current_price = listing.current_price
            
            # Check if target price reached
            if target_price and current_price and current_price <= target_price:
                should_alert = True
                alert_type = "target_reached"
            
            # Check for significant price drop (10%+)
            elif listing.original_price and listing.current_price:
                if current_price < listing.original_price * 0.9:
                    should_alert = True
                    alert_type = "price_drop"
            
            if should_alert:
                # Check cooldown
                is_on_cooldown = await is_alert_on_cooldown(str(user.id), str(product.id))
                if is_on_cooldown:
                    continue
                
                user_id = str(user.id)
                if user_id not in alerts_by_user:
                    alerts_by_user[user_id] = []
                
                # Limit alerts per user
                if len(alerts_by_user[user_id]) >= MAX_ALERTS_PER_USER:
                    continue
                
                alerts_by_user[user_id].append({
                    "watchlist_id": str(watchlist_item.id),
                    "product_id": str(product.id),
                    "product_title": product.title,
                    "product_image": product.image_url,
                    "current_price": current_price,
                    "target_price": target_price,
                    "original_price": listing.original_price,
                    "platform": platform.name,
                    "product_url": listing.product_url,
                    "alert_type": alert_type,
                    "fcm_token": user.fcm_token,
                    "user_email": user.email
                })
                
    except Exception as e:
        logger.error(f"Error getting price alerts: {e}")
    
    return alerts_by_user


async def is_alert_on_cooldown(user_id: str, product_id: str) -> bool:
    """Check if we recently sent an alert for this product"""
    try:
        from app.core.redis_client import redis_client
        
        cache_key = f"alert:cooldown:{user_id}:{product_id}"
        exists = await redis_client.exists(cache_key)
        return bool(exists)
    except Exception:
        return False


async def set_alert_cooldown(user_id: str, product_id: str):
    """Set cooldown for this alert"""
    try:
        from app.core.redis_client import redis_client
        
        cache_key = f"alert:cooldown:{user_id}:{product_id}"
        await redis_client.set(
            cache_key,
            "1",
            ex=ALERT_COOLDOWN_HOURS * 3600
        )
    except Exception as e:
        logger.warning(f"Failed to set alert cooldown: {e}")


async def process_user_alerts(
    db: AsyncSession,
    user_id: str,
    alerts: List[Dict]
) -> int:
    """Process alerts for a single user"""
    if not alerts:
        return 0
    
    sent_count = 0
    
    for alert in alerts:
        try:
            # Send push notification
            if alert.get("fcm_token"):
                success = await send_push_notification(alert)
                if success:
                    sent_count += 1
            
            # Set cooldown
            await set_alert_cooldown(user_id, alert["product_id"])
            
            # Update alert history
            await update_alert_history(db, user_id, alert)
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    return sent_count


async def send_push_notification(alert: Dict) -> bool:
    """Send push notification via Firebase Cloud Messaging"""
    if not settings.ENABLE_PUSH_NOTIFICATIONS:
        logger.debug("Push notifications disabled")
        return False
    
    fcm_token = alert.get("fcm_token")
    if not fcm_token:
        return False
    
    try:
        # Build notification message
        if alert["alert_type"] == "target_reached":
            title = "🎯 Target Price Reached!"
            body = f"{alert['product_title'][:50]} is now ₹{alert['current_price']}"
        else:
            discount = 0
            if alert.get("original_price") and alert.get("current_price"):
                discount = int((1 - alert["current_price"] / alert["original_price"]) * 100)
            title = f"💰 Price Drop Alert! {discount}% OFF"
            body = f"{alert['product_title'][:50]} dropped to ₹{alert['current_price']}"
        
        # Send via Firebase (if configured)
        if settings.FCM_SERVER_KEY:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    headers={
                        "Authorization": f"key={settings.FCM_SERVER_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "to": fcm_token,
                        "notification": {
                            "title": title,
                            "body": body,
                            "click_action": "OPEN_PRODUCT"
                        },
                        "data": {
                            "product_id": alert["product_id"],
                            "product_url": alert["product_url"],
                            "alert_type": alert["alert_type"]
                        }
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.debug(f"Push notification sent to {alert['user_email']}")
                    return True
                else:
                    logger.warning(f"FCM error: {response.status_code}")
                    return False
        else:
            # Log notification (for development)
            logger.info(f"[MOCK PUSH] {title}: {body} -> {alert['user_email']}")
            return True
            
    except Exception as e:
        logger.error(f"Push notification failed: {e}")
        return False


async def update_alert_history(
    db: AsyncSession,
    user_id: str,
    alert: Dict
):
    """Update user's alert history"""
    try:
        from uuid import UUID
        
        result = await db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()
        
        if user:
            history = user.alert_history or []
            
            # Add new alert
            history.insert(0, {
                "product_id": alert["product_id"],
                "product_title": alert["product_title"][:100] if alert.get("product_title") else "Unknown",
                "price": alert["current_price"],
                "alert_type": alert["alert_type"],
                "sent_at": datetime.utcnow().isoformat()
            })
            
            # Keep only last 50 alerts
            user.alert_history = history[:50]
            
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to update alert history: {e}")
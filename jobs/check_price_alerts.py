"""
Price Alert Checker
Runs every 6 hours to evaluate watchlist target/drop alerts.

This job updates user alert history and daily analytics counters.
"""

import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import Notification, Product, ProductListing, SystemLog, UserWatchlist

logger = logging.getLogger(__name__)

MAX_ALERT_HISTORY = 50
TARGET_COOLDOWN_HOURS = 24


def _is_notification_enabled(user, reason: str) -> bool:
    prefs = user.notification_preferences or {}

    if reason == "target_reached":
        return bool(prefs.get("price_drop", prefs.get("price_alerts", True)))

    if reason == "price_drop":
        return bool(prefs.get("price_drop", prefs.get("price_alerts", True)))

    return True


def _build_alert_message(title: str, current_price: float, target_price: Optional[float], reason: str) -> str:
    if reason == "target_reached" and target_price is not None:
        return f"{title} reached your target. Now at INR {current_price:.0f} (target INR {target_price:.0f})."
    return f"{title} dropped in price. Current best price is INR {current_price:.0f}."


async def _send_price_push_notification(user, title: str, body: str, reason: str, payload: Dict[str, Any]) -> bool:
    if not user.fcm_token:
        return False

    if not settings.ENABLE_PUSH_NOTIFICATIONS:
        return False

    # In development, avoid failing job due to missing Firebase setup.
    if settings.DEBUG or settings.ENVIRONMENT == "development":
        logger.info("📱 [MOCK] Price push: %s | %s", title, body)
        return True

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={
                "type": "price_drop",
                "reason": reason,
                "product_id": str(payload.get("product_id", "")),
                "platform": str(payload.get("platform", "")),
            },
            token=user.fcm_token,
        )

        messaging.send(message)
        return True
    except Exception as e:
        logger.warning("Price push send failed for user %s: %s", getattr(user, "id", "unknown"), e)
        return False


def _is_listing_eligible(listing: ProductListing) -> bool:
    """Apply confidence/platform filters to choose reliable listings."""
    if listing is None:
        return False

    if not bool(listing.in_stock):
        return False

    min_confidence = float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))
    if listing.extraction_confidence is not None and listing.extraction_confidence < min_confidence:
        return False

    if (
        hasattr(listing, "platform")
        and listing.platform
        and listing.platform.name.lower() == "croma"
        and not getattr(settings, "CROMA_ENABLED", False)
    ):
        return False

    return listing.current_price is not None


def _pick_best_listing(product: Optional[Product]) -> Optional[ProductListing]:
    """Pick lowest-price eligible listing for alert evaluation."""
    if not product or not getattr(product, "listings", None):
        return None

    candidates = [l for l in product.listings if _is_listing_eligible(l)]
    if not candidates:
        return None

    return min(candidates, key=lambda l: float(l.current_price))


def _get_last_alert(alert_history: List[Dict[str, Any]], product_id: str) -> Optional[Dict[str, Any]]:
    """Fetch latest alert record for a product from user alert history."""
    for entry in reversed(alert_history or []):
        if str(entry.get("product_id")) == product_id:
            return entry
    return None


def _is_recent_duplicate(last_alert: Optional[Dict[str, Any]], reason: str, current_price: float) -> bool:
    """Avoid spamming same alert repeatedly within cooldown window."""
    if not last_alert:
        return False

    if str(last_alert.get("reason")) != reason:
        return False

    last_price = last_alert.get("price")
    if last_price is None:
        return False

    try:
        same_price = abs(float(last_price) - float(current_price)) < 0.01
    except (TypeError, ValueError):
        same_price = False

    if not same_price:
        return False

    ts = last_alert.get("timestamp")
    if not ts:
        return False

    try:
        last_time = datetime.fromisoformat(str(ts))
    except ValueError:
        return False

    return (datetime.utcnow() - last_time) < timedelta(hours=TARGET_COOLDOWN_HOURS)


async def _update_daily_analytics(db: AsyncSession, alerts_sent: int) -> None:
    """Update daily analytics counter for alerts sent."""
    if alerts_sent <= 0:
        return

    today = date.today()

    result = await db.execute(select(SystemLog).where(SystemLog.log_date == today))
    system_log = result.scalar_one_or_none()

    if system_log is None:
        system_log = SystemLog(log_date=today, scraping_summary={}, analytics={}, ml_processing={})
        db.add(system_log)

    analytics = system_log.analytics or {}
    analytics["alerts_sent"] = int(analytics.get("alerts_sent", 0)) + int(alerts_sent)
    system_log.analytics = analytics


async def run_check_price_alerts() -> Dict[str, Any]:
    """Main entrypoint for scheduler/manual runner."""
    start = datetime.utcnow()
    stats: Dict[str, Any] = {
        "watchlist_items_scanned": 0,
        "eligible_items": 0,
        "alerts_triggered": 0,
        "target_price_alerts": 0,
        "drop_alerts": 0,
        "users_notified": 0,
        "push_sent": 0,
        "in_app_notifications_created": 0,
        "errors": 0,
        "duration_seconds": 0.0,
    }

    user_ids_alerted = set()

    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(UserWatchlist)
                .where(UserWatchlist.notify == True)
                .options(
                    selectinload(UserWatchlist.user),
                    selectinload(UserWatchlist.product).selectinload(Product.listings).selectinload(ProductListing.platform),
                )
            )
            items = result.scalars().all()
            stats["watchlist_items_scanned"] = len(items)

            for item in items:
                try:
                    product = item.product
                    if product is None or item.user is None:
                        continue

                    listing = _pick_best_listing(product)
                    if listing is None:
                        continue

                    stats["eligible_items"] += 1
                    current_price = float(listing.current_price)
                    product_id = str(item.product_id)
                    target_price = float(item.target_price) if item.target_price is not None else None

                    reason = None
                    if target_price is not None and current_price <= target_price:
                        reason = "target_reached"
                    else:
                        history = item.user.alert_history or []
                        last_alert = _get_last_alert(history, product_id)
                        if last_alert and last_alert.get("price") is not None:
                            try:
                                previous_price = float(last_alert["price"])
                            except (TypeError, ValueError):
                                previous_price = current_price
                            if current_price < previous_price - 0.01:
                                reason = "price_drop"

                    if reason is None:
                        continue

                    history = item.user.alert_history or []
                    last_alert = _get_last_alert(history, product_id)
                    if _is_recent_duplicate(last_alert, reason, current_price):
                        continue

                    if not _is_notification_enabled(item.user, reason):
                        continue

                    alert_entry = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "product_id": product_id,
                        "title": product.title,
                        "platform": listing.platform.name.lower() if listing.platform else "unknown",
                        "price": current_price,
                        "target_price": target_price,
                        "reason": reason,
                    }

                    history.append(alert_entry)
                    if len(history) > MAX_ALERT_HISTORY:
                        history = history[-MAX_ALERT_HISTORY:]
                    item.user.alert_history = history

                    notif_type = "price_drop"
                    notif_title = "Target Price Reached" if reason == "target_reached" else "Price Dropped"
                    notif_message = _build_alert_message(product.title, current_price, target_price, reason)

                    notification = Notification(
                        user_id=item.user_id,
                        type=notif_type,
                        title=notif_title,
                        message=notif_message,
                        data={
                            "product_id": product_id,
                            "product_title": product.title,
                            "platform": listing.platform.name.lower() if listing.platform else "unknown",
                            "price": current_price,
                            "target_price": target_price,
                            "reason": reason,
                        },
                        is_read=False,
                    )
                    db.add(notification)
                    stats["in_app_notifications_created"] += 1

                    push_ok = await _send_price_push_notification(
                        user=item.user,
                        title=notif_title,
                        body=notif_message,
                        reason=reason,
                        payload=notification.data,
                    )
                    if push_ok:
                        stats["push_sent"] += 1

                    stats["alerts_triggered"] += 1
                    if reason == "target_reached":
                        stats["target_price_alerts"] += 1
                    else:
                        stats["drop_alerts"] += 1

                    user_ids_alerted.add(str(item.user_id))

                except Exception as item_error:
                    stats["errors"] += 1
                    logger.warning("Price alert evaluation failed for item %s: %s", item.id, item_error)

            await _update_daily_analytics(db, stats["alerts_triggered"])
            await db.commit()

        stats["users_notified"] = len(user_ids_alerted)
        stats["duration_seconds"] = round((datetime.utcnow() - start).total_seconds(), 2)

        logger.info(
            "Price alerts completed | scanned=%s eligible=%s alerts=%s users=%s errors=%s duration=%ss",
            stats["watchlist_items_scanned"],
            stats["eligible_items"],
            stats["alerts_triggered"],
            stats["users_notified"],
            stats["errors"],
            stats["duration_seconds"],
        )

        return stats

    except Exception as e:
        stats["errors"] += 1
        stats["duration_seconds"] = round((datetime.utcnow() - start).total_seconds(), 2)
        logger.error("Price alert job failed: %s", e)
        return stats


if __name__ == "__main__":
    import asyncio

    print("Starting Price Alert Checker...")
    print("=" * 60)

    async def _main() -> None:
        result = await run_check_price_alerts()
        print("Results:")
        for key, value in result.items():
            print(f"  {key}: {value}")

    asyncio.run(_main())

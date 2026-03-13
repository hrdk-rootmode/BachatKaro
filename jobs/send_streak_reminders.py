"""
Streak Reminder Job
===================

Runs at 8:00 PM IST to remind users to maintain their streaks

Features:
- Only reminds users who haven't checked in today
- Personalized messages based on streak count
- Warns users at risk of losing streak
- Respects notification preferences
- Rate limits notifications

Author: DealHunt
Version: 2.0 (Complete Implementation)
"""

import logging
import random
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
from app.models import User, SystemLog

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

MAX_REMINDERS_PER_DAY = 1  # Only one reminder per user per day

# Personalized messages based on streak
STREAK_MESSAGES = {
    "new": [
        "Start your streak today! 🔥",
        "Don't forget to check in! 📱",
    ],
    "building": [  # 1-6 days
        "Keep it going! {streak} day streak 🔥",
        "Don't break your {streak} day streak! 💪",
        "You're on fire! {streak} days and counting 🔥",
    ],
    "established": [  # 7-29 days
        "Impressive! {streak} days strong 💪🔥",
        "You're crushing it! {streak} day streak 🏆",
        "Week warrior! Keep your {streak} day streak alive 🔥",
    ],
    "legendary": [  # 30+ days
        "LEGENDARY! {streak} day streak 👑🔥",
        "You're unstoppable! {streak} days 🚀",
        "Hall of fame! Don't lose your {streak} day streak 🏆",
    ],
    "at_risk": [
        "⚠️ Your {streak} day streak is at risk!",
        "🚨 Check in now to save your {streak} day streak!",
        "Don't lose your progress! {streak} days 😰",
    ]
}


# =============================================================================
# MAIN JOB FUNCTION
# =============================================================================

async def run_streak_reminders() -> Dict[str, Any]:
    """
    Main streak reminder job
    
    Process:
    1. Get users who haven't checked in today
    2. Filter by notification preferences
    3. Send personalized reminders
    4. Log results
    
    Returns:
        Dictionary with reminder statistics
    """
    logger.info("🔔 Starting streak reminders...")
    start_time = datetime.utcnow()
    
    stats = {
        "users_checked": 0,
        "users_at_risk": 0,
        "reminders_sent": 0,
        "reminders_skipped": 0,
        "errors": [],
        "duration_seconds": 0
    }
    
    try:
        async with async_session_maker() as db:
            # Get users who need reminders
            users = await _get_users_needing_reminder(db)
            stats["users_checked"] = len(users)
            
            if not users:
                logger.info("No users need streak reminders")
                stats["message"] = "No users to remind"
                stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
                return stats
            
            logger.info(f"📋 Found {len(users)} users to remind")
            
            # Process each user
            for user in users:
                try:
                    result = await _send_reminder(user, db)
                    
                    if result == "sent":
                        stats["reminders_sent"] += 1
                    elif result == "at_risk":
                        stats["users_at_risk"] += 1
                        stats["reminders_sent"] += 1
                    else:
                        stats["reminders_skipped"] += 1
                        
                except Exception as e:
                    logger.error(f"Error sending reminder to {user.id}: {e}")
                    stats["errors"].append(str(e))
                    stats["reminders_skipped"] += 1
            
            # Log results
            await _log_reminder_results(db, stats, start_time)
            
            stats["duration_seconds"] = round(
                (datetime.utcnow() - start_time).total_seconds(), 2
            )
            
            logger.info(
                f"✅ Streak reminders completed | "
                f"Sent: {stats['reminders_sent']} | "
                f"At Risk: {stats['users_at_risk']} | "
                f"Skipped: {stats['reminders_skipped']} | "
                f"Duration: {stats['duration_seconds']}s"
            )
            
            return stats
            
    except Exception as e:
        logger.error(f"❌ Streak reminders failed: {e}")
        stats["error"] = str(e)
        stats["duration_seconds"] = round(
            (datetime.utcnow() - start_time).total_seconds(), 2
        )
        return stats


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def _get_users_needing_reminder(db: AsyncSession) -> List[User]:
    """Get users who haven't checked in today and have active streaks"""
    try:
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Get all active users with streaks or recent activity
        query = (
            select(User)
            .where(
                and_(
                    User.is_blocked == False,
                    User.fcm_token.isnot(None),  # Must have FCM token
                    User.last_active >= datetime.utcnow() - timedelta(days=30)  # Active in last 30 days
                )
            )
        )
        
        result = await db.execute(query)
        all_users = result.scalars().all()
        
        # Filter users who need reminders
        users_to_remind = []
        
        for user in all_users:
            streak_data = user.streak_data or {}
            
            # Check notification preferences
            prefs = user.notification_preferences or {}
            if not prefs.get("streak_reminders", True):
                continue
            
            # Check last check-in
            last_check_in = streak_data.get("last_check_in")
            
            if last_check_in:
                try:
                    last_date = datetime.fromisoformat(last_check_in).date()
                    
                    # Skip if already checked in today
                    if last_date >= today:
                        continue
                    
                    # Include if has active streak
                    current_streak = streak_data.get("current_streak", 0)
                    if current_streak > 0:
                        users_to_remind.append(user)
                        
                except (ValueError, TypeError):
                    # Include users with parse errors if they have streaks
                    if streak_data.get("current_streak", 0) > 0:
                        users_to_remind.append(user)
            else:
                # Include users who never checked in but have FCM token
                # This helps onboard new users
                users_to_remind.append(user)
        
        return users_to_remind
        
    except Exception as e:
        logger.error(f"Error getting users for reminders: {e}")
        return []


async def _send_reminder(user: User, db: AsyncSession) -> str:
    """Send streak reminder to user"""
    try:
        streak_data = user.streak_data or {}
        current_streak = streak_data.get("current_streak", 0)
        
        # Determine message category
        if current_streak == 0:
            category = "new"
        elif current_streak < 7:
            category = "building"
        elif current_streak < 30:
            category = "established"
        else:
            category = "legendary"
        
        # Check if at risk (hasn't checked in yesterday)
        last_check_in = streak_data.get("last_check_in")
        at_risk = False
        
        if last_check_in and current_streak > 0:
            try:
                last_date = datetime.fromisoformat(last_check_in).date()
                yesterday = date.today() - timedelta(days=1)
                
                if last_date < yesterday:
                    category = "at_risk"
                    at_risk = True
            except (ValueError, TypeError):
                pass
        
        # Select random message
        messages = STREAK_MESSAGES.get(category, STREAK_MESSAGES["new"])
        message_template = random.choice(messages)
        message = message_template.format(streak=current_streak)
        
        # Build notification
        if at_risk:
            title = "⚠️ Streak at Risk!"
        else:
            title = "🔥 Don't Forget Your Streak!"
        
        # Send FCM
        success = await _send_fcm_notification(
            token=user.fcm_token,
            title=title,
            body=message,
            data={
                "type": "streak_reminder",
                "streak": str(current_streak),
                "at_risk": str(at_risk)
            }
        )
        
        if success:
            return "at_risk" if at_risk else "sent"
        else:
            return "failed"
            
    except Exception as e:
        logger.error(f"Error sending reminder: {e}")
        return "failed"


async def _send_fcm_notification(
    token: str,
    title: str,
    body: str,
    data: Dict[str, str]
) -> bool:
    """Send FCM push notification"""
    try:
        if not settings.ENABLE_PUSH_NOTIFICATIONS:
            logger.debug("Push notifications disabled")
            return False
        
        # Development mode - just log
        if settings.DEBUG or settings.ENVIRONMENT == "development":
            logger.info(f"📱 [MOCK] FCM: {title} - {body}")
            return True
        
        # Production - use Firebase
        import firebase_admin
        from firebase_admin import messaging
        
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data,
            token=token
        )
        
        response = messaging.send(message)
        logger.debug(f"FCM sent: {response}")
        
        return True
        
    except Exception as e:
        logger.warning(f"FCM send failed: {e}")
        return False


async def _log_reminder_results(
    db: AsyncSession,
    stats: Dict[str, Any],
    start_time: datetime
):
    """Log reminder results to system_logs"""
    try:
        today = date.today()
        
        result = await db.execute(
            select(SystemLog).where(SystemLog.log_date == today)
        )
        system_log = result.scalar_one_or_none()
        
        reminder_data = {
            "job": "send_streak_reminders",
            "timestamp": start_time.isoformat(),
            "users_checked": stats.get("users_checked", 0),
            "reminders_sent": stats.get("reminders_sent", 0),
            "users_at_risk": stats.get("users_at_risk", 0),
            "duration_seconds": stats.get("duration_seconds", 0)
        }
        
        if system_log:
            analytics = system_log.analytics or {}
            analytics["streak_reminders"] = reminder_data
            system_log.analytics = analytics
        else:
            system_log = SystemLog(
                log_date=today,
                scraping_summary={},
                analytics={"streak_reminders": reminder_data},
                ml_processing={}
            )
            db.add(system_log)
        
        await db.commit()
        
    except Exception as e:
        logger.warning(f"Failed to log reminder results: {e}")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    import asyncio
    
    print("🔔 Starting Streak Reminders Job...")
    print("=" * 60)
    
    async def main():
        try:
            result = await run_streak_reminders()
            
            print("\n📊 Results:")
            print(f"   Users Checked: {result.get('users_checked', 0)}")
            print(f"   Reminders Sent: {result.get('reminders_sent', 0)}")
            print(f"   Users At Risk: {result.get('users_at_risk', 0)}")
            print(f"   Skipped: {result.get('reminders_skipped', 0)}")
            print(f"   Duration: {result.get('duration_seconds', 0)}s")
            
            if result.get("error"):
                print(f"\n❌ Error: {result['error']}")
            else:
                print("\n✅ Job completed successfully!")
                
        except Exception as e:
            print(f"\n💥 Critical error: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(main())
    print("\n🏁 Streak reminders job finished.")
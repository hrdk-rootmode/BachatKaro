"""
Streak Reminder Job
Runs at 8 PM IST to remind users to check in

Features:
- Only reminds users who haven't checked in today
- Personalized messages based on streak count
- Warns users at risk of losing streak
- Respects notification preferences
- Tracks reminder effectiveness
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, List
import random

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import User
from jobs.scheduler import update_job_status, JobStatus

logger = logging.getLogger(__name__)

# Personalized messages based on streak
STREAK_MESSAGES = {
    0: [
        "🔥 Start your streak today! Check in now.",
        "💪 Day 1 starts now! Open the app to begin.",
        "🚀 Ready to start your streak journey?"
    ],
    (1, 3): [
        "🔥 You're on a {streak}-day streak! Don't break it!",
        "💪 Keep it going! Day {streak} is almost done.",
        "⏰ Quick check-in to keep your {streak}-day streak!"
    ],
    (4, 7): [
        "🔥 Amazing {streak}-day streak! You're on fire!",
        "🌟 Week warrior! {streak} days and counting!",
        "💪 {streak} days strong! Check in to continue!"
    ],
    (8, 30): [
        "🏆 Incredible {streak}-day streak! You're a legend!",
        "⭐ {streak} days! You're in the top 10% of users!",
        "🔥 {streak} days! Don't lose your momentum!"
    ],
    (31, 100): [
        "👑 {streak}-DAY STREAK! You're unstoppable!",
        "🎖️ Elite status! {streak} days of dedication!",
        "🌟 {streak} days! You're an inspiration!"
    ],
    (101, 999): [
        "🏆 LEGENDARY {streak}-DAY STREAK! 🏆",
        "👑 {streak} DAYS! You're a DealHunt Master!",
        "⭐ {streak} days! We bow to your dedication!"
    ]
}

FREEZE_WARNING = "⚠️ You have {freeze} freeze(s) left! Don't lose your {streak}-day streak!"


async def run_streak_reminders() -> Dict[str, Any]:
    """
    Send streak reminders to users who haven't checked in today
    
    Process:
    1. Find users with active streaks who haven't checked in
    2. Generate personalized messages
    3. Send push notifications
    4. Track reminder stats
    """
    logger.info("🔔 Starting streak reminders...")
    start_time = datetime.utcnow()
    
    update_job_status('streak_reminders', JobStatus.RUNNING)
    
    stats = {
        "users_found": 0,
        "reminders_sent": 0,
        "at_risk_users": 0,
        "errors": [],
        "duration_seconds": 0
    }
    
    try:
        async with async_session_maker() as db:
            # Get users who need reminders
            users_to_remind = await get_users_needing_reminder(db)
            
            stats["users_found"] = len(users_to_remind)
            
            if not users_to_remind:
                logger.info("No users need streak reminders")
                stats["message"] = "No reminders needed"
                update_job_status('streak_reminders', JobStatus.COMPLETED, **stats)
                return stats
            
            # Send reminders
            for user in users_to_remind:
                try:
                    streak_data = user.streak_data or {}
                    current_streak = streak_data.get("current_streak", 0)
                    freeze_count = streak_data.get("freeze_count", 0)
                    
                    # Check if at risk (has streak but no freezes)
                    if current_streak > 0 and freeze_count == 0:
                        stats["at_risk_users"] += 1
                    
                    # Generate and send message
                    success = await send_streak_reminder(user, current_streak, freeze_count)
                    
                    if success:
                        stats["reminders_sent"] += 1
                        
                except Exception as e:
                    stats["errors"].append(f"User {user.id}: {str(e)[:50]}")
                    logger.error(f"Failed to remind user {user.id}: {e}")
            
            stats["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                f"✅ Streak reminders sent | "
                f"Users: {stats['users_found']} | "
                f"Sent: {stats['reminders_sent']} | "
                f"At Risk: {stats['at_risk_users']} | "
                f"Duration: {stats['duration_seconds']:.2f}s"
            )
            
            update_job_status('streak_reminders', JobStatus.COMPLETED, **stats)
            return stats
            
    except Exception as e:
        logger.error(f"❌ Streak reminders failed: {e}")
        stats["error"] = str(e)
        update_job_status('streak_reminders', JobStatus.FAILED, error=str(e))
        raise


async def get_users_needing_reminder(db: AsyncSession) -> List[User]:
    """
    Get users who:
    - Have an active streak OR have streak_reminders enabled
    - Haven't checked in today
    - Have FCM token for push
    - Aren't blocked
    """
    today = date.today().isoformat()
    
    query = (
        select(User)
        .where(
            User.is_blocked == False,
            User.fcm_token.isnot(None),
            User.fcm_token != ""
        )
    )
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    # Filter users who need reminders
    users_to_remind = []
    
    for user in users:
        # Check notification preferences
        prefs = user.notification_preferences or {}
        if not prefs.get("streak_reminders", True):
            continue
        
        streak_data = user.streak_data or {}
        last_check_in = streak_data.get("last_check_in")
        
        # Skip if already checked in today
        if last_check_in and last_check_in.startswith(today):
            continue
        
        # Only remind users with active streaks OR who have checked in before
        current_streak = streak_data.get("current_streak", 0)
        total_check_ins = streak_data.get("total_check_ins", 0)
        
        if current_streak > 0 or total_check_ins > 0:
            users_to_remind.append(user)
    
    return users_to_remind


def get_reminder_message(current_streak: int, freeze_count: int) -> tuple:
    """
    Get personalized reminder message based on streak
    
    Returns:
        (title, body)
    """
    # Find matching message template
    messages = STREAK_MESSAGES.get(0, [])  # Default
    
    for key, msg_list in STREAK_MESSAGES.items():
        if isinstance(key, tuple):
            min_streak, max_streak = key
            if min_streak <= current_streak <= max_streak:
                messages = msg_list
                break
        elif key == current_streak:
            messages = msg_list
            break
    
    # Pick random message
    message_template = random.choice(messages)
    body = message_template.format(streak=current_streak)
    
    # Add freeze warning if applicable
    if current_streak > 0 and freeze_count == 0:
        title = "⚠️ Streak at Risk!"
        body = f"Your {current_streak}-day streak will break at midnight!"
    elif current_streak >= 7:
        title = "🔥 Don't Break Your Streak!"
    else:
        title = "⏰ Daily Check-in Reminder"
    
    return title, body


async def send_streak_reminder(
    user: User,
    current_streak: int,
    freeze_count: int
) -> bool:
    """Send push notification for streak reminder"""
    
    if not user.fcm_token:
        return False
    
    if not settings.ENABLE_PUSH_NOTIFICATIONS:
        logger.debug("Push notifications disabled")
        return False
    
    title, body = get_reminder_message(current_streak, freeze_count)
    
    try:
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
                        "to": user.fcm_token,
                        "notification": {
                            "title": title,
                            "body": body,
                            "click_action": "OPEN_STREAK"
                        },
                        "data": {
                            "type": "streak_reminder",
                            "current_streak": str(current_streak),
                            "freeze_count": str(freeze_count)
                        }
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.debug(f"Streak reminder sent to {user.email}")
                    return True
                else:
                    logger.warning(f"FCM error: {response.status_code}")
                    return False
        else:
            # Log notification (for development)
            logger.info(f"[MOCK PUSH] {title}: {body} -> {user.email}")
            return True
            
    except Exception as e:
        logger.error(f"Streak reminder failed: {e}")
        return False
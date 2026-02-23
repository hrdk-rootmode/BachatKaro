"""
Streak & Gamification API Routes
Daily check-ins, rewards, and milestones
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timedelta, date
from decimal import Decimal
import logging

from app.core.database import get_db
from app.core.redis_client import RedisClient, get_redis
from app.models import User, StreakMilestone
from app.schemas import (
    StreakCheckInResponse,
    StreakMilestoneSchema,
    StreakStatusResponse,
    UseFreezeRequest,
    UseFreezeResponse
)
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# CONSTANTS
# =============================================================================

FREEZE_LIMITS = {
    "free": 2,      # 2 freezes per month
    "pro": 5,       # 5 freezes per month
    "premium": -1   # Unlimited
}

DEFAULT_MILESTONES = [
    {"days": 3, "reward_type": "searches", "reward_value": 5, "badge_emoji": "🔥", "badge_name": "Fire Starter"},
    {"days": 7, "reward_type": "searches", "reward_value": 10, "badge_emoji": "⭐", "badge_name": "Week Warrior"},
    {"days": 14, "reward_type": "watchlist_slots", "reward_value": 2, "badge_emoji": "💪", "badge_name": "Dedicated"},
    {"days": 30, "reward_type": "premium_days", "reward_value": 7, "badge_emoji": "👑", "badge_name": "Monthly Master"},
    {"days": 60, "reward_type": "premium_days", "reward_value": 14, "badge_emoji": "💎", "badge_name": "Diamond Hunter"},
    {"days": 100, "reward_type": "premium_days", "reward_value": 30, "badge_emoji": "🏆", "badge_name": "Century Champion"},
    {"days": 365, "reward_type": "premium_days", "reward_value": 90, "badge_emoji": "🎖️", "badge_name": "Legendary Saver"},
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_freeze_limit(plan: str) -> int:
    """Get freeze limit based on user plan"""
    return FREEZE_LIMITS.get(plan, 2)


def parse_date_safe(date_str: Optional[str]) -> Optional[date]:
    """Safely parse date string"""
    if not date_str:
        return None
    try:
        if isinstance(date_str, datetime):
            return date_str.date()
        return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
    except (ValueError, AttributeError):
        return None


def can_check_in_today(last_check_in: Optional[str]) -> bool:
    """Check if user can check in today"""
    last_date = parse_date_safe(last_check_in)
    if not last_date:
        return True
    return last_date < date.today()


def is_streak_broken(last_check_in: Optional[str]) -> bool:
    """Check if streak is broken (missed yesterday)"""
    last_date = parse_date_safe(last_check_in)
    if not last_date:
        return False  # New user, no broken streak
    
    yesterday = date.today() - timedelta(days=1)
    return last_date < yesterday


def get_next_milestone(current_streak: int, claimed_milestones: List[int]) -> Optional[int]:
    """Get next unclaimed milestone"""
    for milestone in DEFAULT_MILESTONES:
        if milestone["days"] > current_streak and milestone["days"] not in claimed_milestones:
            return milestone["days"]
    return None


async def get_milestones_from_db(db: AsyncSession) -> List[dict]:
    """Get milestones from database or use defaults"""
    result = await db.execute(
        select(StreakMilestone)
        .where(StreakMilestone.is_active == True)
        .order_by(StreakMilestone.streak_days.asc())
    )
    db_milestones = result.scalars().all()
    
    if not db_milestones:
        return DEFAULT_MILESTONES
    
    return [
        {
            "days": m.streak_days,
            "reward_type": m.reward_type,
            "reward_value": m.reward_value,
            "badge_emoji": m.badge_emoji,
            "badge_name": m.badge_name,
            "badge_color": m.badge_color
        }
        for m in db_milestones
    ]


async def apply_milestone_reward(
    user: User,
    milestone: dict,
    db: AsyncSession
) -> str:
    """Apply milestone reward to user"""
    reward_type = milestone["reward_type"]
    reward_value = milestone["reward_value"]
    
    if reward_type == "searches":
        # Add bonus searches
        if user.usage_stats is None:
            user.usage_stats = {}
        user.usage_stats["daily_search_bonus"] = user.usage_stats.get("daily_search_bonus", 0) + reward_value
        return f"+{reward_value} bonus searches"
    
    elif reward_type == "watchlist_slots":
        # Add bonus watchlist slots
        if user.usage_stats is None:
            user.usage_stats = {}
        user.usage_stats["watchlist_bonus"] = user.usage_stats.get("watchlist_bonus", 0) + reward_value
        return f"+{reward_value} watchlist slots"
    
    elif reward_type == "premium_days":
        # Add premium days
        if user.plan == "free":
            user.plan = "pro"
            user.plan_expires_at = datetime.utcnow() + timedelta(days=reward_value)
        elif user.plan_expires_at:
            user.plan_expires_at = user.plan_expires_at + timedelta(days=reward_value)
        else:
            user.plan_expires_at = datetime.utcnow() + timedelta(days=reward_value)
        return f"+{reward_value} days premium"
    
    elif reward_type == "badge":
        # Badge is automatically added via claimed milestones
        return f"Badge: {milestone.get('badge_name', 'New Badge')}"
    
    return "Reward applied"


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/check-in", response_model=StreakCheckInResponse)
async def daily_check_in(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Daily check-in to maintain streak
    
    Features:
    - Increments streak counter
    - Awards milestone rewards automatically
    - Detects broken streaks
    - Updates longest streak record
    """
    # Get current streak data
    streak_data = user.streak_data or {
        "current_streak": 0,
        "longest_streak": 0,
        "last_check_in": None,
        "total_check_ins": 0,
        "streak_rewards_claimed": [],
        "freeze_count": get_freeze_limit(user.plan)
    }
    
    last_check_in = streak_data.get("last_check_in")
    current_streak = streak_data.get("current_streak", 0)
    longest_streak = streak_data.get("longest_streak", 0)
    total_check_ins = streak_data.get("total_check_ins", 0)
    claimed_milestones = streak_data.get("streak_rewards_claimed", [])
    
    # Check if already checked in today
    if not can_check_in_today(last_check_in):
        return StreakCheckInResponse(
            success=False,
            current_streak=current_streak,
            max_streak=longest_streak,
            reward_unlocked=None,
            next_milestone=get_next_milestone(current_streak, claimed_milestones),
            next_milestone_reward=None,
            message="Already checked in today! Come back tomorrow.",
            confetti=False
        )
    
    # Check if streak is broken
    if is_streak_broken(last_check_in):
        # Reset streak
        current_streak = 1
        message = "Welcome back! Your streak has been reset. Let's start fresh!"
    else:
        # Increment streak
        current_streak += 1
        message = f"🔥 Day {current_streak}! Keep it up!"
    
    # Update longest streak
    if current_streak > longest_streak:
        longest_streak = current_streak
    
    # Check for milestone rewards
    reward_unlocked = None
    confetti = False
    milestones = await get_milestones_from_db(db)
    
    for milestone in milestones:
        if milestone["days"] == current_streak and milestone["days"] not in claimed_milestones:
            # Unlock reward!
            reward_description = await apply_milestone_reward(user, milestone, db)
            claimed_milestones.append(milestone["days"])
            
            reward_unlocked = {
                "milestone_days": milestone["days"],
                "reward_type": milestone["reward_type"],
                "reward_value": milestone["reward_value"],
                "badge_emoji": milestone.get("badge_emoji"),
                "badge_name": milestone.get("badge_name"),
                "description": reward_description
            }
            
            message = f"🎉 Milestone reached! {reward_description}"
            confetti = True
            break
    
    # Update streak data
    user.streak_data = {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "last_check_in": datetime.utcnow().isoformat(),
        "total_check_ins": total_check_ins + 1,
        "streak_rewards_claimed": claimed_milestones,
        "freeze_count": streak_data.get("freeze_count", get_freeze_limit(user.plan))
    }
    
    await db.commit()
    
    # Invalidate cache
    await redis.delete(f"streak:{user.id}")
    
    # Track in Redis for analytics
    await redis.increment(f"check_ins:daily:{date.today().isoformat()}")
    
    logger.info(
        f"Check-in successful | User: {user.id} | "
        f"Streak: {current_streak} | Milestone: {reward_unlocked is not None}"
    )
    
    # Get next milestone
    next_milestone = get_next_milestone(current_streak, claimed_milestones)
    next_reward = None
    if next_milestone:
        for m in milestones:
            if m["days"] == next_milestone:
                next_reward = f"{m['reward_value']} {m['reward_type']}"
                break
    
    return StreakCheckInResponse(
        success=True,
        current_streak=current_streak,
        max_streak=longest_streak,
        reward_unlocked=reward_unlocked,
        next_milestone=next_milestone,
        next_milestone_reward=next_reward,
        message=message,
        confetti=confetti
    )


@router.get("/status", response_model=StreakStatusResponse)
async def get_streak_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Get complete streak status and milestones
    
    Returns:
    - Current streak and max streak
    - Whether user can check in today
    - All milestones with unlock status
    - Freeze count remaining
    """
    # Check cache
    cache_key = f"streak:{user.id}"
    cached = await redis.get_json(cache_key)
    
    if cached:
        logger.info(f"Streak cache HIT | User: {user.id}")
        return StreakStatusResponse(**cached)
    
    # Get streak data
    streak_data = user.streak_data or {
        "current_streak": 0,
        "longest_streak": 0,
        "last_check_in": None,
        "total_check_ins": 0,
        "streak_rewards_claimed": [],
        "freeze_count": get_freeze_limit(user.plan)
    }
    
    current_streak = streak_data.get("current_streak", 0)
    longest_streak = streak_data.get("longest_streak", 0)
    total_check_ins = streak_data.get("total_check_ins", 0)
    last_check_in = streak_data.get("last_check_in")
    claimed_milestones = streak_data.get("streak_rewards_claimed", [])
    freeze_count = streak_data.get("freeze_count", get_freeze_limit(user.plan))
    
    # Check if can check in today
    can_check_in = can_check_in_today(last_check_in)
    
    # Check if streak is at risk
    streak_at_risk = is_streak_broken(last_check_in) if not can_check_in else False
    
    # Get milestones
    milestones_config = await get_milestones_from_db(db)
    
    milestones = []
    for m in milestones_config:
        milestones.append(StreakMilestoneSchema(
            days=m["days"],
            reward_type=m["reward_type"],
            reward_value=m["reward_value"],
            badge_emoji=m.get("badge_emoji"),
            badge_name=m.get("badge_name"),
            badge_color=m.get("badge_color"),
            unlocked=current_streak >= m["days"],
            claimed=m["days"] in claimed_milestones
        ))
    
    # Get next milestone
    next_milestone = get_next_milestone(current_streak, claimed_milestones)
    days_until_next = next_milestone - current_streak if next_milestone else None
    
    # Parse last check-in date
    last_check_in_dt = None
    if last_check_in:
        try:
            last_check_in_dt = datetime.fromisoformat(last_check_in.replace('Z', '+00:00'))
        except:
            pass
    
    response = StreakStatusResponse(
        current_streak=current_streak,
        max_streak=longest_streak,
        total_check_ins=total_check_ins,
        freeze_count=freeze_count,
        freeze_limit=get_freeze_limit(user.plan),
        last_check_in=last_check_in_dt,
        can_check_in_today=can_check_in,
        streak_at_risk=streak_at_risk,
        milestones=milestones,
        next_milestone=next_milestone,
        days_until_next_milestone=days_until_next
    )
    
    # Cache for 5 minutes
    await redis.set_json(
        cache_key,
        response.model_dump(mode='json'),
        ttl=300
    )
    
    return response


@router.post("/use-freeze", response_model=UseFreezeResponse)
async def use_streak_freeze(
    request: UseFreezeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Use streak freeze to protect streak when missing a day
    
    Rules:
    - Free: 2 freezes/month
    - Pro: 5 freezes/month
    - Premium: Unlimited
    """
    streak_data = user.streak_data or {}
    current_streak = streak_data.get("current_streak", 0)
    freeze_count = streak_data.get("freeze_count", get_freeze_limit(user.plan))
    freeze_limit = get_freeze_limit(user.plan)
    
    # Check if user has freezes available
    if freeze_limit != -1 and freeze_count <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No freezes remaining this month. Upgrade to Pro or Premium for more freezes."
        )
    
    # Check if streak is actually at risk
    last_check_in = streak_data.get("last_check_in")
    if not is_streak_broken(last_check_in):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your streak is not at risk. You can only use freeze when you've missed a day."
        )
    
    # Apply freeze - update last_check_in to yesterday
    yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
    
    user.streak_data = {
        **streak_data,
        "last_check_in": yesterday,
        "freeze_count": freeze_count - 1 if freeze_limit != -1 else freeze_count
    }
    
    await db.commit()
    
    # Invalidate cache
    await redis.delete(f"streak:{user.id}")
    
    # Calculate protection expiry (until end of today)
    protection_until = datetime.combine(date.today(), datetime.max.time())
    
    logger.info(
        f"Streak freeze used | User: {user.id} | "
        f"Streak: {current_streak} | Freezes remaining: {freeze_count - 1}"
    )
    
    return UseFreezeResponse(
        success=True,
        freeze_count_remaining=freeze_count - 1 if freeze_limit != -1 else -1,
        streak_protected_until=protection_until,
        message=f"🧊 Streak protected! You have {freeze_count - 1 if freeze_limit != -1 else 'unlimited'} freezes remaining."
    )


@router.get("/milestones", response_model=List[StreakMilestoneSchema])
async def get_all_milestones(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all available streak milestones
    
    Returns list of all milestones with unlock/claim status
    """
    streak_data = user.streak_data or {}
    current_streak = streak_data.get("current_streak", 0)
    claimed_milestones = streak_data.get("streak_rewards_claimed", [])
    
    milestones_config = await get_milestones_from_db(db)
    
    milestones = []
    for m in milestones_config:
        milestones.append(StreakMilestoneSchema(
            days=m["days"],
            reward_type=m["reward_type"],
            reward_value=m["reward_value"],
            badge_emoji=m.get("badge_emoji"),
            badge_name=m.get("badge_name"),
            badge_color=m.get("badge_color"),
            unlocked=current_streak >= m["days"],
            claimed=m["days"] in claimed_milestones
        ))
    
    return milestones


@router.get("/leaderboard")
async def get_streak_leaderboard(
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Get streak leaderboard (top streakers)
    
    Returns top N users by current streak
    """
    # Check cache
    cache_key = f"leaderboard:streak:{limit}"
    cached = await redis.get_json(cache_key)
    
    if cached:
        return cached
    
    # Query top users by streak
    # Note: This is simplified - in production you might use a dedicated leaderboard table
    result = await db.execute(
        select(User)
        .where(User.is_blocked == False)
        .order_by(User.streak_data['current_streak'].desc())
        .limit(limit)
    )
    users = result.scalars().all()
    
    leaderboard = []
    for i, u in enumerate(users, 1):
        streak_data = u.streak_data or {}
        leaderboard.append({
            "rank": i,
            "display_name": u.display_name or "Anonymous",
            "current_streak": streak_data.get("current_streak", 0),
            "longest_streak": streak_data.get("longest_streak", 0),
            "is_you": str(u.id) == str(user.id)
        })
    
    # Cache for 15 minutes
    await redis.set_json(cache_key, leaderboard, ttl=900)
    
    return leaderboard
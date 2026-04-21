"""
Streak & Gamification API Routes
Daily check-ins, rewards, and milestones
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Tuple
from datetime import datetime, timedelta, date
from decimal import Decimal
import re
import logging

from app.core.database import get_db
from app.core.config import settings
from app.core.redis_client import RedisClient, get_redis
from app.models import User, StreakMilestone, Notification
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
    # Short-term milestones only (admin can extend later).
    {"days": 5, "reward_type": "searches", "reward_value": 10, "badge_emoji": "🏆", "badge_name": "5-Day Warrior", "description": "+10 extra searches"},
    {"days": 7, "reward_type": "watchlist_slots", "reward_value": 1, "badge_emoji": "⭐", "badge_name": "Week Warrior", "description": "+1 watchlist slot"},
    {"days": 10, "reward_type": "searches", "reward_value": 5, "badge_emoji": "🌟", "badge_name": "10-Day Legend", "description": "+5 extra searches +1 watchlist slot"},
    {"days": 15, "reward_type": "searches", "reward_value": 5, "badge_emoji": "💪", "badge_name": "Dedicated Hunter", "description": "+5 extra searches +2 watchlist slots"},
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


def create_streak_notification(user_id, title: str, message: str, data: Optional[dict] = None) -> Notification:
    return Notification(
        user_id=user_id,
        type="streak_reminder",
        title=title,
        message=message,
        data=data or {},
        is_read=False,
    )


def get_next_milestone(
    current_streak: int,
    claimed_milestones: List[int],
    milestone_days: Optional[List[int]] = None,
) -> Optional[int]:
    """Get next unclaimed milestone"""
    source_days = milestone_days or [int(m["days"]) for m in DEFAULT_MILESTONES]
    for day in sorted({int(d) for d in source_days if int(d) > 0}):
        if day > current_streak and day not in claimed_milestones:
            return day
    return None


async def _seed_default_milestones_if_empty(db: AsyncSession) -> bool:
    """Seed streak_milestones table with defaults when no rows exist."""
    existing_result = await db.execute(select(StreakMilestone.id).limit(1))
    if existing_result.scalar_one_or_none() is not None:
        return False

    for item in DEFAULT_MILESTONES:
        db.add(
            StreakMilestone(
                streak_days=int(item["days"]),
                reward_type=str(item["reward_type"]),
                reward_value=int(item["reward_value"]),
                badge_emoji=item.get("badge_emoji"),
                badge_name=item.get("badge_name"),
                announcement_text=item.get("description"),
                confetti_enabled=True,
                is_active=True,
                sort_order=int(item["days"]),
            )
        )

    await db.commit()
    logger.info("Seeded default streak milestones into DB")
    return True


async def get_milestones_from_db(db: AsyncSession) -> List[dict]:
    """Get milestones from database or use defaults"""
    await _seed_default_milestones_if_empty(db)

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
            "badge_color": m.badge_color,
            "announcement_text": m.announcement_text,
        }
        for m in db_milestones
    ]


def _extract_secondary_reward_counts(announcement_text: Optional[str]) -> tuple[int, int]:
    """Parse optional secondary rewards from announcement text."""
    text = str(announcement_text or "")
    search_matches = [int(m) for m in re.findall(r"\+(\d+)\s*(?:daily\s+)?(?:extra\s+)?search", text, flags=re.IGNORECASE)]
    watchlist_matches = [int(m) for m in re.findall(r"\+(\d+)\s*watchlist", text, flags=re.IGNORECASE)]

    return (max(search_matches) if search_matches else 0, max(watchlist_matches) if watchlist_matches else 0)


def _calculate_milestone_limit_bonus(milestone: dict) -> Tuple[int, int]:
    """Return (search_bonus, watchlist_bonus) represented by a milestone."""
    reward_type = str(milestone.get("reward_type") or "").lower()
    reward_value = int(milestone.get("reward_value") or 0)
    search_bonus = reward_value if reward_type == "searches" else 0
    watchlist_bonus = reward_value if reward_type == "watchlist_slots" else 0

    text_search, text_watchlist = _extract_secondary_reward_counts(milestone.get("announcement_text"))
    search_bonus = max(search_bonus, int(text_search or 0))
    watchlist_bonus = max(watchlist_bonus, int(text_watchlist or 0))

    return search_bonus, watchlist_bonus


def _normalize_claimed_milestones(values: Optional[List]) -> List[int]:
    claimed: List[int] = []
    for item in values or []:
        try:
            claimed.append(int(item))
        except (TypeError, ValueError):
            continue
    return sorted(set(claimed))


async def reconcile_streak_limit_bonuses(
    user: User,
    db: AsyncSession,
    milestones_config: List[dict],
    current_streak: int,
    claimed_milestones: List[int],
) -> List[int]:
    """Ensure streak-derived search/watchlist bonuses are reflected in usage stats."""
    active_milestones = [m for m in milestones_config if int(m.get("days", 0) or 0) > 0]
    eligible_days = {
        int(m["days"]) for m in active_milestones if int(m.get("days", 0) or 0) <= int(current_streak or 0)
    }

    normalized_claimed = set(_normalize_claimed_milestones(claimed_milestones))
    if eligible_days:
        normalized_claimed.update(eligible_days)

    expected_search_bonus = 0
    expected_watchlist_bonus = 0
    for milestone in active_milestones:
        day = int(milestone.get("days", 0) or 0)
        if day in normalized_claimed and day <= int(current_streak or 0):
            search_bonus, watchlist_bonus = _calculate_milestone_limit_bonus(milestone)
            expected_search_bonus += int(search_bonus)
            expected_watchlist_bonus += int(watchlist_bonus)

    usage_stats = dict(user.usage_stats or {})
    current_search_bonus = int(usage_stats.get("bonus_searches", 0) or 0)
    current_daily_search_bonus = int(usage_stats.get("daily_search_bonus", 0) or 0)
    current_watchlist_bonus = int(usage_stats.get("watchlist_bonus", 0) or 0)

    changed = False
    if current_search_bonus < expected_search_bonus:
        usage_stats["bonus_searches"] = expected_search_bonus
        changed = True
    if current_daily_search_bonus < expected_search_bonus:
        usage_stats["daily_search_bonus"] = expected_search_bonus
        changed = True
    if current_watchlist_bonus < expected_watchlist_bonus:
        usage_stats["watchlist_bonus"] = expected_watchlist_bonus
        changed = True

    normalized_list = sorted(normalized_claimed)
    streak_data = dict(user.streak_data or {})
    if _normalize_claimed_milestones(streak_data.get("streak_rewards_claimed", [])) != normalized_list:
        streak_data["streak_rewards_claimed"] = normalized_list
        user.streak_data = streak_data
        changed = True

    if changed:
        user.usage_stats = usage_stats
        await db.commit()

    return normalized_list


async def apply_milestone_reward(
    user: User,
    milestone: dict,
    db: AsyncSession
) -> str:
    """Apply milestone reward to user"""
    reward_type = milestone["reward_type"]
    reward_value = milestone["reward_value"]
    announcement_text = milestone.get("announcement_text")
    search_from_text, watchlist_from_text = _extract_secondary_reward_counts(announcement_text)
    applied_searches = 0
    applied_watchlist = 0
    message_parts: List[str] = []
    
    if reward_type == "searches":
        # Add bonus searches (aligned with auth/stats usage key)
        usage_stats = dict(user.usage_stats or {})
        usage_stats["bonus_searches"] = int(usage_stats.get("bonus_searches", 0) or 0) + reward_value
        usage_stats["daily_search_bonus"] = int(usage_stats.get("daily_search_bonus", 0) or 0) + reward_value
        user.usage_stats = usage_stats
        applied_searches = reward_value
        message_parts.append(f"+{reward_value} extra searches")
    
    elif reward_type == "watchlist_slots":
        # Add bonus watchlist slots
        usage_stats = dict(user.usage_stats or {})
        usage_stats["watchlist_bonus"] = usage_stats.get("watchlist_bonus", 0) + reward_value
        user.usage_stats = usage_stats
        applied_watchlist = reward_value
        message_parts.append(f"+{reward_value} watchlist slot{'s' if reward_value > 1 else ''}")
    
    elif reward_type == "unlimited_search_hours":
        # Add unlimited search hours
        usage_stats = dict(user.usage_stats or {})
        if "unlimited_search_until" not in usage_stats:
            usage_stats["unlimited_search_until"] = None
        
        # Extend existing unlimited search or add new time
        current_until = usage_stats.get("unlimited_search_until")
        start_time = datetime.utcnow()
        
        if current_until and datetime.fromisoformat(current_until.replace('Z', '+00:00')) > start_time:
            # Extend existing unlimited search
            new_until = datetime.fromisoformat(current_until.replace('Z', '+00:00')) + timedelta(hours=reward_value)
        else:
            # Start new unlimited search period
            new_until = start_time + timedelta(hours=reward_value)
        
        usage_stats["unlimited_search_until"] = new_until.isoformat()
        user.usage_stats = usage_stats
        message_parts.append(f"{reward_value} hours unlimited search")
    
    elif reward_type == "premium_days":
        # Add premium days
        if user.plan == "free":
            user.plan = "pro"
            user.plan_expires_at = datetime.utcnow() + timedelta(days=reward_value)
        elif user.plan_expires_at:
            user.plan_expires_at = user.plan_expires_at + timedelta(days=reward_value)
        else:
            user.plan_expires_at = datetime.utcnow() + timedelta(days=reward_value)
        message_parts.append(f"+{reward_value} days premium")
    
    elif reward_type == "free_month":
        # Give free month(s)
        if user.plan == "free":
            user.plan = "pro"
            user.plan_expires_at = datetime.utcnow() + timedelta(days=30 * reward_value)
        elif user.plan_expires_at:
            user.plan_expires_at = user.plan_expires_at + timedelta(days=30 * reward_value)
        else:
            user.plan_expires_at = datetime.utcnow() + timedelta(days=30 * reward_value)
        message_parts.append(f"{reward_value} month{'s' if reward_value > 1 else ''} completely free")
    
    elif reward_type == "badge":
        # Badge is automatically added via claimed milestones
        message_parts.append(f"Badge: {milestone.get('badge_name', 'New Badge')}")

    # Secondary reward support from announcement text (for mixed rewards like +search +watchlist).
    extra_searches = max(0, int(search_from_text) - int(applied_searches))
    if extra_searches > 0:
        usage_stats = dict(user.usage_stats or {})
        usage_stats["bonus_searches"] = int(usage_stats.get("bonus_searches", 0) or 0) + extra_searches
        usage_stats["daily_search_bonus"] = int(usage_stats.get("daily_search_bonus", 0) or 0) + extra_searches
        user.usage_stats = usage_stats
        message_parts.append(f"+{extra_searches} extra searches")

    extra_watchlist = max(0, int(watchlist_from_text) - int(applied_watchlist))
    if extra_watchlist > 0:
        usage_stats = dict(user.usage_stats or {})
        usage_stats["watchlist_bonus"] = int(usage_stats.get("watchlist_bonus", 0) or 0) + extra_watchlist
        user.usage_stats = usage_stats
        message_parts.append(f"+{extra_watchlist} watchlist slot{'s' if extra_watchlist > 1 else ''}")

    if message_parts:
        return " + ".join(message_parts)
    return announcement_text or "Reward applied"


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
    claimed_milestones_raw = streak_data.get("streak_rewards_claimed", [])
    claimed_milestones = _normalize_claimed_milestones(claimed_milestones_raw)
    
    # Check if already checked in today
    if not can_check_in_today(last_check_in):
        milestones = await get_milestones_from_db(db)
        milestone_days = [int(m["days"]) for m in milestones]
        return StreakCheckInResponse(
            success=False,
            current_streak=current_streak,
            max_streak=longest_streak,
            reward_unlocked=None,
            next_milestone=get_next_milestone(current_streak, claimed_milestones, milestone_days),
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
    
    # Check milestones.
    # For existing users, allow catch-up reward when current streak already passed
    # an unclaimed milestone due to earlier inconsistencies.
    for milestone in milestones:
        if milestone["days"] <= current_streak and milestone["days"] not in claimed_milestones:
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

    if reward_unlocked:
        db.add(
            create_streak_notification(
                user_id=user.id,
                title=f"{reward_unlocked['milestone_days']}-day streak milestone unlocked",
                message=reward_unlocked.get("description") or "Your streak reward is ready.",
                data={
                    "milestone_days": reward_unlocked.get("milestone_days"),
                    "reward_type": reward_unlocked.get("reward_type"),
                    "reward_value": reward_unlocked.get("reward_value"),
                },
            )
        )
    
    await db.commit()

    # Final safety sync: keep usage limits consistent with claimed/eligible milestones.
    claimed_milestones = await reconcile_streak_limit_bonuses(
        user=user,
        db=db,
        milestones_config=milestones,
        current_streak=current_streak,
        claimed_milestones=claimed_milestones,
    )
    
    # Invalidate ALL related caches COMPLETELY
    await redis.delete(f"streak:{user.id}")
    await redis.delete(f"watchlist:{user.id}")
    await redis.delete_pattern(f"user:*{user.id}*")
    
    # Track in Redis for analytics
    await redis.increment(f"check_ins:daily:{date.today().isoformat()}")
    
    logger.info(
        f"Check-in successful | User: {user.id} | "
        f"Streak: {current_streak} | Milestone: {reward_unlocked is not None}"
    )
    
    # Get next milestone
    milestone_days = [int(m["days"]) for m in milestones]
    next_milestone = get_next_milestone(current_streak, claimed_milestones, milestone_days)
    next_reward = None
    if next_milestone:
        for m in milestones:
            if m["days"] == next_milestone:
                next_reward = m.get("announcement_text") or f"{m['reward_value']} {m['reward_type']}"
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
    claimed_milestones = _normalize_claimed_milestones(streak_data.get("streak_rewards_claimed", []))
    freeze_count = streak_data.get("freeze_count", get_freeze_limit(user.plan))
    
    # Check if can check in today
    can_check_in = can_check_in_today(last_check_in)
    
    # Check if streak is at risk
    streak_at_risk = is_streak_broken(last_check_in) if not can_check_in else False
    
    # Get milestones
    milestones_config = await get_milestones_from_db(db)

    claimed_milestones = await reconcile_streak_limit_bonuses(
        user=user,
        db=db,
        milestones_config=milestones_config,
        current_streak=current_streak,
        claimed_milestones=claimed_milestones,
    )
    
    milestones = []
    for m in milestones_config:
        milestones.append(StreakMilestoneSchema(
            days=m["days"],
            reward_type=m["reward_type"],
            reward_value=m["reward_value"],
            announcement_text=m.get("announcement_text"),
            badge_emoji=m.get("badge_emoji"),
            badge_name=m.get("badge_name"),
            badge_color=m.get("badge_color"),
            unlocked=current_streak >= m["days"],
            claimed=m["days"] in claimed_milestones
        ))
    
    # Get next milestone
    milestone_days = [int(m["days"]) for m in milestones_config]
    next_milestone = get_next_milestone(current_streak, claimed_milestones, milestone_days)
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
            announcement_text=m.get("announcement_text"),
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


@router.post("/debug/reset")
async def debug_reset_streak(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Development-only helper:
    Fully reset streak progress and streak reward side-effects.
    """
    if settings.ENVIRONMENT.lower() == "production" and not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug streak reset is disabled in production"
        )

    now_iso = datetime.utcnow().isoformat()

    user.streak_data = {
        "current_streak": 0,
        "longest_streak": 0,
        # Keep last_check_in as now so app launch won't auto-check-in immediately.
        "last_check_in": now_iso,
        "total_check_ins": 0,
        "streak_rewards_claimed": [],
        "freeze_count": get_freeze_limit(user.plan),
    }

    usage_stats = dict(user.usage_stats or {})
    usage_stats["watchlist_bonus"] = 0
    usage_stats["bonus_searches"] = 0
    usage_stats["daily_search_bonus"] = 0
    usage_stats.pop("unlimited_search_until", None)
    user.usage_stats = usage_stats

    await db.commit()

    today = datetime.utcnow().date().isoformat()
    await redis.delete(f"streak:{user.id}")
    await redis.delete(f"watchlist:{user.id}")

    return {
        "success": True,
        "message": "Streak and streak rewards fully reset",
        "data": {
            "current_streak": 0,
            "longest_streak": 0,
            "last_check_in": now_iso,
            "watchlist_bonus": 0,
            "bonus_searches": 0,
        },
    }
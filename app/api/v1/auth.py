"""
Authentication & User Management Routes
Handles signup, profile management, and account deletion

✨ AUTO-USER CREATION (Zero-Friction Authentication):
The system now supports automatic user creation from Firebase tokens!

FLOW 1 - AUTO-CREATION (Simplest, Recommended):
  1. User logs in with Firebase in frontend
  2. Frontend gets JWT token
  3. Frontend calls any protected API endpoint with token
  4. If ENABLE_AUTO_USER_CREATION=True:
     - User is automatically created in database
     - User can immediately use all features
  5. No signup endpoint needed!

FLOW 2 - MANUAL SIGNUP (Legacy, Still Supported):
  1. User logs in with Firebase
  2. Frontend calls /signup endpoint with user details
  3. User record created with custom preferences
  4. User can use app

Configuration:
  - ENABLE_AUTO_USER_CREATION: bool (default=True)
  - AUTO_USER_DEFAULT_PLAN: str (default="free")
  - AUTO_USER_PLAN_EXPIRY_DAYS: int (default=365)
  - AUTO_USER_DEFAULT_DISPLAY_NAME: str (default="DealHunt User")

To switch flows:
  - Auto-creation enabled: Just use Firebase auth, no signup needed
  - Auto-creation disabled: Require manual signup endpoint call
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
import string
import logging

from app.core.database import get_db
from app.core.redis_client import RedisClient, get_redis
from app.core.config import settings
from app.models import User, AppConfig
from app.schemas import (
    UserSignupRequest,
    UserResponse,
    UserProfileUpdate,
    UserUsageStats,
    UserPlan
)
from app.api.deps import (
    get_current_user,
    verify_firebase_token,
    check_hardware_id_limit,
    check_ip_signup_limit,
    get_app_config
)
from app.services.plan_catalog import get_plan_catalog, get_plan_limit, normalize_watchlist_limit

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value) -> list:
    return value if isinstance(value, list) else []


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value, default: Optional[str] = None) -> Optional[str]:
    if value is None:
        return default
    try:
        cleaned = str(value).strip()
    except Exception:
        return default
    return cleaned if cleaned else default


def _normalized_user_plan(value) -> str:
    normalized = str(value or UserPlan.FREE.value).lower()
    allowed = {UserPlan.FREE.value, UserPlan.PRO.value, UserPlan.PREMIUM.value}
    return normalized if normalized in allowed else UserPlan.FREE.value


def _extract_iso_date(value) -> Optional[str]:
    """Extract YYYY-MM-DD from ISO datetime/date strings."""
    raw = _safe_str(value, None)
    if not raw:
        return None

    try:
        if "T" in raw:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.date().isoformat()
        parsed = datetime.fromisoformat(raw)
        return parsed.date().isoformat()
    except ValueError:
        return None


def _normalize_daily_search_usage(usage_stats: dict) -> tuple[dict, bool]:
    """Reset today's counters when data still points to a previous date."""
    normalized = dict(usage_stats or {})
    today = datetime.utcnow().date().isoformat()

    last_reset = _safe_str(normalized.get("last_reset"), None)
    last_search_day = _extract_iso_date(normalized.get("last_search_date"))

    if last_reset == today or last_search_day == today:
        return normalized, False

    normalized["daily_searches"] = 0
    normalized["searches_today"] = 0
    normalized["last_reset"] = today
    return normalized, True


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def generate_referral_code(length: int = 6) -> str:
    """
    Generate unique referral code
    Format: 6 character alphanumeric (uppercase)
    """
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


async def get_unique_referral_code(db: AsyncSession) -> str:
    """
    Generate referral code and ensure it's unique
    Max 5 attempts to find unique code
    """
    for attempt in range(5):
        code = generate_referral_code()
        
        # Check if code already exists
        result = await db.execute(
            select(User).where(User.referral_code == code)
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            return code
    
    # Fallback to longer code if collision after 5 attempts
    return generate_referral_code(8)


async def validate_referral_code(
    code: str,
    db: AsyncSession
) -> Optional[User]:
    """
    Validate referral code and return referrer user
    
    Returns:
        User object if valid, None if invalid
    """
    if not code or len(code) < 6:
        return None
    
    result = await db.execute(
        select(User).where(
            User.referral_code == code.upper(),
            User.is_blocked == False
        )
    )
    return result.scalar_one_or_none()


async def process_referral(
    referrer: User,
    new_user: User,
    db: AsyncSession
) -> None:
    """
    Process referral rewards for both users
    
    Rewards:
    - Referrer: +10 bonus searches
    - New user: +5 bonus searches
    """
    # Update referrer stats
    if referrer.usage_stats is None:
        referrer.usage_stats = {}
    
    referrer.usage_stats['bonus_searches'] = \
        referrer.usage_stats.get('bonus_searches', 0) + 10
    referrer.usage_stats['referrals_count'] = \
        referrer.usage_stats.get('referrals_count', 0) + 1
    referrer.usage_stats['last_referral_date'] = datetime.utcnow().isoformat()
    
    # Update new user stats
    if new_user.usage_stats is None:
        new_user.usage_stats = {}
    
    new_user.usage_stats['bonus_searches'] = 5
    new_user.usage_stats['referred_by'] = referrer.referral_code
    
    await db.commit()
    
    logger.info(
        f"Referral processed: {referrer.id} referred {new_user.id}"
    )


# =============================================================================
# ROUTES
# =============================================================================
@router.post("/signup-public", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def public_signup(
    request: Request,
    signup_data: UserSignupRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    config: dict = Depends(get_app_config),
    _check_hardware: None = Depends(check_hardware_id_limit),
    _check_ip: None = Depends(check_ip_signup_limit)
):
    """
    Public Signup - No authentication required
    """
    
    # Check if user already exists
    existing_user = await db.execute(
        select(User).where(
            or_(
                User.firebase_uid == signup_data.firebase_uid,
                User.email == signup_data.email
            )
        )
    )
    existing = existing_user.scalar_one_or_none()
    
    if existing:
        if existing.firebase_uid == signup_data.firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account already exists with this Firebase UID"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )
    
    # Generate unique referral code
    referral_code = await get_unique_referral_code(db)
    
    # Get client IP
    client_ip = request.client.host
    
    # Create new user
    new_user = User(
        firebase_uid=signup_data.firebase_uid,
        email=signup_data.email,
        display_name=signup_data.display_name,
        hardware_id=signup_data.hardware_id,
        fcm_token=signup_data.fcm_token,
        referral_code=referral_code,
        plan=UserPlan.FREE,
        ip_addresses=[client_ip],
        usage_stats={
            'total_searches': 0,
            'searches_this_month': 0,
            'watchlist_slots_used': 0,
            'bonus_searches': 0,
            'signup_ip': client_ip,
            'signup_date': datetime.utcnow().isoformat()
        },
        notification_preferences={
            'price_drop': True,
            'back_in_stock': True,
            'streak_reminder': True,
            'subscription_expiry': True
        },
        last_active=datetime.now(timezone.utc)
    )
    
    db.add(new_user)
    await db.flush()
    await db.commit()
    await db.refresh(new_user)
    
    # Track signup in Redis
    signup_date = datetime.utcnow().date().isoformat()
    await redis_client.increment(f"signups:daily:{signup_date}")
    
    logger.info(f"New user signup: {new_user.id} | Email: {new_user.email}")
    
    return new_user


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: Request,
    signup_data: UserSignupRequest,
    token_data: dict = Depends(verify_firebase_token),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
    config: dict = Depends(get_app_config),
    _check_hardware: None = Depends(check_hardware_id_limit),
    _check_ip: None = Depends(check_ip_signup_limit)
):
    """
    User Signup with Anti-Abuse Protection (Optional - Use if auto-creation is disabled)
    
    ✨ NOTE: If ENABLE_AUTO_USER_CREATION=True, this endpoint is optional!
    - Users are automatically created on first API call with Firebase token
    - This endpoint is only needed if:
      1. Auto-creation is disabled
      2. You want custom user preferences
      3. You want to process referral codes at signup time
    
    Security Checks:
    1. Firebase UID validation
    2. Disposable email blocking
    3. Hardware ID limit (3 accounts per device)
    4. IP signup limit (5 per day)
    5. Referral code validation
    
    Returns:
        Created user object with referral code
    """
    
    # 1. Check if user already exists
    existing_user = await db.execute(
        select(User).where(
            or_(
                User.firebase_uid == signup_data.firebase_uid,
                User.email == signup_data.email
            )
        )
    )
    existing = existing_user.scalar_one_or_none()
    
    if existing:
        if existing.firebase_uid == signup_data.firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account already exists with this Firebase UID"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )
    
    # 2. Validate referral code if provided
    referrer = None
    if signup_data.referral_code:
        referrer = await validate_referral_code(
            signup_data.referral_code,
            db
        )
        if not referrer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid referral code"
            )
    
    # 3. Generate unique referral code for new user
    referral_code = await get_unique_referral_code(db)
    
    # 4. Get client IP
    client_ip = request.client.host
    
    # 5. Create new user
    new_user = User(
        firebase_uid=signup_data.firebase_uid,
        email=signup_data.email,
        display_name=signup_data.display_name,
        hardware_id=signup_data.hardware_id,
        fcm_token=signup_data.fcm_token,
        referral_code=referral_code,
        plan=UserPlan.FREE,
        ip_addresses=[client_ip],
        usage_stats={
            'total_searches': 0,
            'searches_this_month': 0,
            'watchlist_slots_used': 0,
            'bonus_searches': 0,
            'signup_ip': client_ip,
            'signup_date': datetime.utcnow().isoformat()
        },
        notification_preferences={
            'price_drop': True,
            'back_in_stock': True,
            'streak_reminder': True,
            'subscription_expiry': True
        },
        last_active=datetime.now(timezone.utc)
    )
    
    db.add(new_user)
    await db.flush()  # Get user.id before commit
    
    # 6. Process referral if applicable
    if referrer:
        # Prevent self-referral (shouldn't happen but extra safety)
        if referrer.id != new_user.id:
            await process_referral(referrer, new_user, db)
    
    await db.commit()
    await db.refresh(new_user)
    
    # 7. Track signup in Redis (for analytics)
    signup_date = datetime.utcnow().date().isoformat()
    try:
        await redis_client.increment(f"signups:daily:{signup_date}")
    except Exception as e:
        logger.warning(f"Redis signup tracking failed: {e}")
    
    logger.info(
        f"New user signup: {new_user.id} | Email: {new_user.email} | "
        f"Device: {signup_data.hardware_id} | IP: {client_ip}"
    )
    
    return new_user


@router.get("/account-status", response_model=dict)
async def get_account_status(
    user: User = Depends(get_current_user)
):
    """Get current account status including ban information"""
    return {
        "status": "active" if not user.is_blocked else "blocked",
        "is_blocked": user.is_blocked,
        "block_reason": user.block_reason,
        "blocked_at": user.blocked_at.isoformat() if user.blocked_at else None,
        "email": user.email,
        "plan": user.plan,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None
    }


@router.post("/refresh-token")
async def refresh_token(
    token_data: dict = Depends(verify_firebase_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh Firebase ID Token
    
    ✨ NOTE: This endpoint validates the current token
    However, token refresh should happen on FRONTEND with Firebase SDK!
    
    Frontend should call:
      ```javascript
      const newToken = await user.getIdToken(true); // Force refresh
      ```
    
    Backend Usage:
      If frontend sends an old/expiring token, backend will reject with 401
      Frontend then calls user.getIdToken(true) and retries
    
    Returns:
        Token info (this validates token is still valid)
    """
    firebase_uid = token_data.get("uid")
    email = token_data.get("email")
    
    # Update last active
    result = await db.execute(
        select(User).where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()
    
    if user and not user.is_blocked:
        user.last_active = datetime.now(timezone.utc)
        await db.commit()
    
    # Return info
    return {
        "status": "valid",
        "message": "Token is valid. Token refresh should be done on frontend with Firebase SDK.",
        "uid": firebase_uid,
        "email": email,
        "frontend_action": "Call user.getIdToken(true) to get fresh token"
    }


@router.get("/token-status")
async def get_token_status(
    token_data: dict = Depends(verify_firebase_token)
):
    """
    Check Token Status (Frontend Debugging)
    
    Returns information about the current token:
    - Whether it's valid
    - Associated user info
    - Whether frontend needs to refresh
    
    Frontend Usage:
      ```javascript
      const response = await api.get('/auth/token-status');
      if (response.status === 200) {
        console.log('Token is still valid');
      }
      ```
    """
    return {
        "valid": True,
        "uid": token_data.get("uid"),
        "email": token_data.get("email"),
        "email_verified": token_data.get("email_verified", False),
        "message": "Token is currently valid. It will expire in ~1 hour."
    }


@router.post("/logout")
async def logout(
    user: User = Depends(get_current_user),
    redis_client: RedisClient = Depends(get_redis)
):
    """
    Logout User
    
    Frontend should:
    1. Call this endpoint with valid token
    2. Remove token from localStorage
    3. Redirect to login page
    
    Backend:
    - Clears any cached data
    - Logs the logout
    
    Returns: Logout success message
    """
    # Optional: Blacklist token (if you want to prevent reuse)
    # await redis_client.set(f"logout:{user.id}", "true", ttl=3600)
    
    logger.info(f"User logged out: {user.email} (ID: {user.id})")
    
    return {
        "status": "success",
        "message": "Logged out successfully",
        "action": "Remove token from frontend and redirect to login"
    }


@router.get("/ping")
async def auth_ping():
    """
    🔍 PING ENDPOINT - Simple connectivity test (NO AUTH REQUIRED)
    
    Use this to verify the backend is reachable from your device
    
    Returns: {"status": "pong", "timestamp": "2026-03-17T..."}
    """
    return {
        "status": "pong",
        "message": "Backend is reachable!",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/debug/token-check")
async def debug_token_check(request: Request):
    """
    🔍 DEBUG ENDPOINT - Check if Firebase token verification works
    
    No authentication required - for testing purposes only
    
    Usage: curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/v1/auth/debug/token-check
    
    Returns:
    - Authorization header status
    - Token verification result
    - Any error messages
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        return {
            "status": "error",
            "message": "No Authorization header provided",
            "expected": "Authorization: Bearer <firebase_token>"
        }
    
    try:
        # Extract token from "Bearer {token}"
        parts = auth_header.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return {
                "status": "error",
                "message": "Invalid Authorization header format",
                "expected": "Authorization: Bearer <firebase_token>",
                "received": auth_header[:50] + "..." if len(auth_header) > 50 else auth_header
            }
        
        token = parts[1]
        
        # Try to verify Firebase token
        from firebase_admin import auth as firebase_auth
        
        try:
            decoded_token = firebase_auth.verify_id_token(
                token,
                check_revoked=False,
                clock_skew_seconds=max(0, int(getattr(settings, "FIREBASE_CLOCK_SKEW_SECONDS", 5))),
            )
            return {
                "status": "success",
                "message": "Firebase token is valid",
                "firebase_uid": decoded_token.get("uid"),
                "email": decoded_token.get("email"),
                "token_valid": True
            }
        except Exception as e:
            logger.error(f"Token verification failed: {str(e)}")
            return {
                "status": "error",
                "message": f"Firebase token verification failed: {str(e)}",
                "error_type": type(e).__name__,
                "token_valid": False
            }
    
    except Exception as e:
        logger.error(f"Debug endpoint error: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get Current User Profile
    
    Returns complete user data including:
    - Subscription status
    - Usage statistics
    - Notification preferences
    - Streak information
    """
    usage_stats = _safe_dict(user.usage_stats)
    usage_stats, usage_changed = _normalize_daily_search_usage(usage_stats)

    # Keep this value fresh based on real app profile fetches.
    user.last_active = datetime.now(timezone.utc)
    if usage_changed:
        user.usage_stats = usage_stats
    db.add(user)
    await db.commit()

    phone_number = _safe_str(
        usage_stats.get("phone_number", usage_stats.get("phone")),
        None,
    )
    city = _safe_str(
        usage_stats.get("city", usage_stats.get("location")),
        None,
    )
    streak_data = _safe_dict(user.streak_data)
    watchlist = _safe_list(user.watchlist)
    normalized_plan = _normalized_user_plan(user.plan)

    total_searches = _safe_int(usage_stats.get("total_searches"), 0)
    searches_today = _safe_int(
        usage_stats.get("searches_today", usage_stats.get("daily_searches")),
        0,
    )
    current_streak = _safe_int(streak_data.get("current_streak"), 0)
    longest_streak = _safe_int(
        streak_data.get("max_streak", streak_data.get("longest_streak")),
        0,
    )
    freeze_count = _safe_int(streak_data.get("freeze_count"), 0)
    
    return UserResponse(
        id=str(user.id),  # Convert UUID to string
        firebase_uid=user.firebase_uid,
        email=user.email,
        display_name=user.display_name,
        phone_number=phone_number,
        city=city,
        plan=normalized_plan,
        plan_expires_at=user.plan_expires_at,
        usage_stats=usage_stats,
        referral_code=user.referral_code or "",
        total_searches=total_searches,
        searches_today=searches_today,
        watchlist_count=len(watchlist),
        current_streak=current_streak,
        max_streak=longest_streak,
        freeze_count=freeze_count,
        is_blocked=user.is_blocked,
        created_at=user.created_at or datetime.utcnow(),
        last_active=user.last_active
    )


@router.get("/me/stats", response_model=UserUsageStats)
async def get_user_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get Detailed Usage Statistics
    
    Returns:
    - Searches used/remaining today
    - Watchlist slots used/limit
    - Streak information
    - Plan details
    """
    
    plan_catalog = await get_plan_catalog(db)
    usage_stats = _safe_dict(user.usage_stats)
    usage_stats, usage_changed = _normalize_daily_search_usage(usage_stats)
    if usage_changed:
        user.usage_stats = usage_stats
        await db.commit()

    streak_data = _safe_dict(user.streak_data)
    watchlist = _safe_list(user.watchlist)

    current_plan = _normalized_user_plan(user.plan)
    daily_limit = get_plan_limit(plan_catalog, current_plan, "searches_per_day", settings.PLAN_FREE_SEARCHES)

    searches_today = _safe_int(
        usage_stats.get("searches_today", usage_stats.get("daily_searches")),
        0,
    )
    
    # Add bonus searches.
    # Legacy users may still have rewards under daily_search_bonus only.
    bonus_searches = max(
        _safe_int(usage_stats.get('bonus_searches'), 0),
        _safe_int(usage_stats.get('daily_search_bonus'), 0),
    )

    unlimited_until = usage_stats.get("unlimited_search_until")
    if unlimited_until:
        try:
            expires_at = datetime.fromisoformat(str(unlimited_until).replace("Z", "+00:00"))
            now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.utcnow()
            if expires_at > now:
                searches_remaining = -1
            else:
                unlimited_until = None
        except ValueError:
            unlimited_until = None
    
    if daily_limit == -1:
        searches_remaining = -1  # Unlimited
    elif unlimited_until:
        searches_remaining = -1
    else:
        searches_remaining = max(0, daily_limit + bonus_searches - searches_today)

    # Calculate watchlist limit
    watchlist_limit = get_plan_limit(plan_catalog, current_plan, "watchlist_limit", settings.PLAN_FREE_WISHLIST)
    watchlist_limit = normalize_watchlist_limit(watchlist_limit, current_plan)
    watchlist_bonus = _safe_int(usage_stats.get("watchlist_bonus"), 0)
    effective_watchlist_limit = max(0, watchlist_limit + watchlist_bonus)
    
    # Calculate days remaining for subscription
    days_remaining = None
    if user.plan_expires_at:
        now_dt = datetime.now(user.plan_expires_at.tzinfo) if user.plan_expires_at.tzinfo else datetime.utcnow()
        delta = user.plan_expires_at - now_dt
        days_remaining = max(0, delta.days)

    watchlist_count = _safe_int(usage_stats.get("watchlist_slots_used"), len(watchlist))
    total_searches = _safe_int(usage_stats.get("total_searches"), 0)
    current_streak = _safe_int(streak_data.get("current_streak"), 0)
    freeze_count = _safe_int(streak_data.get("freeze_count"), 0)
    
    return UserUsageStats(
        total_searches=total_searches,
        searches_today=searches_today,
        searches_remaining=searches_remaining,
        watchlist_count=watchlist_count,
        watchlist_limit=effective_watchlist_limit,
        current_streak=current_streak,
        freeze_count=freeze_count,
        plan=current_plan,
        plan_expires_at=user.plan_expires_at
    )


@router.post("/me/stats/reset-searches")
async def reset_search_usage_for_debug(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Development-only helper to clear today's search usage counters."""
    if settings.ENVIRONMENT.lower() == "production" and not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug search reset is disabled in production"
        )

    usage_stats = _safe_dict(user.usage_stats)
    usage_stats["daily_searches"] = 0
    usage_stats["searches_today"] = 0
    usage_stats["last_reset"] = datetime.utcnow().date().isoformat()
    usage_stats["last_search_date"] = None
    usage_stats.pop("last_search_query", None)
    usage_stats.pop("last_url_search", None)
    user.usage_stats = usage_stats

    await db.commit()

    return {
        "success": True,
        "message": "Today's search usage has been reset",
        "data": {
            "searches_today": 0,
            "total_searches": _safe_int(usage_stats.get("total_searches"), 0),
        },
    }


@router.put("/me", response_model=UserResponse)
async def update_profile(
    updates: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update User Profile
    
    Allowed updates:
    - display_name
    - fcm_token (for push notifications)
    - notification_preferences
    
    Immutable fields (cannot update):
    - email
    - firebase_uid
    - plan
    - referral_code
    """
    
    # Update only provided fields
    update_data = updates.model_dump(exclude_unset=True)

    incoming_phone = update_data.pop("phone_number", None) if "phone_number" in update_data else None
    incoming_city = update_data.pop("city", None) if "city" in update_data else None
    
    for field, value in update_data.items():
        if hasattr(user, field):
            setattr(user, field, value)

    usage_stats = _safe_dict(user.usage_stats)

    if "phone_number" in updates.model_fields_set:
        clean_phone = _safe_str(incoming_phone, None)
        if clean_phone:
            usage_stats["phone_number"] = clean_phone
        else:
            usage_stats.pop("phone_number", None)

    if "city" in updates.model_fields_set:
        clean_city = _safe_str(incoming_city, None)
        if clean_city:
            usage_stats["city"] = clean_city
        else:
            usage_stats.pop("city", None)

    user.usage_stats = usage_stats
    
    await db.commit()
    await db.refresh(user)
    
    logger.info(f"Profile updated: User {user.id} | Fields: {list(update_data.keys())}")

    usage_stats = _safe_dict(user.usage_stats)
    streak_data = _safe_dict(user.streak_data)
    watchlist = _safe_list(user.watchlist)
    normalized_plan = _normalized_user_plan(user.plan)
    phone_number = _safe_str(
        usage_stats.get("phone_number", usage_stats.get("phone")),
        None,
    )
    city = _safe_str(
        usage_stats.get("city", usage_stats.get("location")),
        None,
    )

    total_searches = _safe_int(usage_stats.get("total_searches"), 0)
    searches_today = _safe_int(
        usage_stats.get("searches_today", usage_stats.get("daily_searches")),
        0,
    )
    current_streak = _safe_int(streak_data.get("current_streak"), 0)
    longest_streak = _safe_int(
        streak_data.get("max_streak", streak_data.get("longest_streak")),
        0,
    )
    freeze_count = _safe_int(streak_data.get("freeze_count"), 0)

    return UserResponse(
        id=str(user.id),
        firebase_uid=user.firebase_uid,
        email=user.email,
        display_name=user.display_name,
        phone_number=phone_number,
        city=city,
        plan=normalized_plan,
        plan_expires_at=user.plan_expires_at,
        usage_stats=usage_stats,
        referral_code=user.referral_code or "",
        total_searches=total_searches,
        searches_today=searches_today,
        watchlist_count=len(watchlist),
        current_streak=current_streak,
        max_streak=longest_streak,
        freeze_count=freeze_count,
        is_blocked=user.is_blocked,
        created_at=user.created_at or datetime.utcnow(),
        last_active=user.last_active,
    )


@router.delete("/me")
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis)
):
    """
    Soft Delete User Account
    
    Process:
    1. Set is_blocked = True (soft delete)
    2. Remove FCM token (stop notifications)
    3. Keep data for 30 days (GDPR compliance)
    4. Schedule permanent deletion after 30 days
    
    Does NOT:
    - Delete user data immediately
    - Refund subscriptions
    - Delete referral history
    """
    
    # Soft delete
    user.is_blocked = True
    user.fcm_token = None
    user.last_active = datetime.now(timezone.utc)
    
    # Add deletion metadata
    if user.usage_stats is None:
        user.usage_stats = {}
    
    user.usage_stats['deletion_requested_at'] = datetime.utcnow().isoformat()
    user.usage_stats['deletion_scheduled_for'] = (
        datetime.utcnow() + timedelta(days=30)
    ).isoformat()
    
    await db.commit()
    
    today = datetime.utcnow().date().isoformat()

    # Track deletion in analytics
    await redis_client.increment(f"deletions:daily:{today}")
    
    logger.warning(
        f"Account deletion requested: User {user.id} | Email: {user.email}"
    )
    
    deletion_date = datetime.utcnow() + timedelta(days=30)
    
    return {
        "message": "Account deactivated successfully",
        "deletion_date": deletion_date.isoformat(),
        "note": "Your data will be permanently deleted after 30 days. "
                "Contact support to cancel this request."
    }


@router.post("/verify-referral-code")
async def verify_referral_code_endpoint(
    referral_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify Referral Code (before signup)
    
    Used by mobile app to validate referral code
    before showing signup form
    """
    
    referrer = await validate_referral_code(referral_code, db)
    
    if not referrer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired referral code"
        )
    
    return {
        "valid": True,
        "referrer_name": referrer.display_name or "Anonymous User",
        "bonus_searches": 5,
        "message": f"You'll get 5 bonus searches when you sign up!"
    }
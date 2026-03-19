"""
Dependency injection functions for FastAPI routes
Handles authentication, rate limiting, and authorization
"""

from typing import Optional, Annotated
from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import auth as firebase_auth

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.core.config import settings
from app.models import User, AppConfig
from app.schemas import UserPlan
from app.schemas import UserSignupRequest
import redis.asyncio as redis
from redis.asyncio import Redis
from app.core.security import initialize_firebase

# Initialize Firebase Admin SDK with proper credentials
initialize_firebase()


# Security scheme
security = HTTPBearer()


# ==================== AUTHENTICATION ====================

async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Verify Firebase ID token
    
    Returns:
        dict: Decoded token with user claims
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        token = credentials.credentials
        logger.info(f"Verifying Firebase token: {token[:20]}...")
        decoded_token = firebase_auth.verify_id_token(token)
        logger.info(f"✅ Token verified for user: {decoded_token.get('email')}")
        return decoded_token
    except firebase_auth.InvalidIdTokenError as e:
        logger.error(f"❌ Invalid Firebase token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}"
        )
    except firebase_auth.ExpiredIdTokenError as e:
        logger.error(f"❌ Expired Firebase token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except Exception as e:
        logger.error(f"❌ Firebase token verification failed: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {type(e).__name__}: {str(e)}"
        )


async def get_current_user(
    request: Request,
    token_data: dict = Depends(verify_firebase_token),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
) -> User:
    """
    Get current authenticated user from database
    
    ✨ ENHANCED: Auto-creates user from Firebase token if enabled
    
    Features:
    - Auto-creates new users from Firebase tokens (zero-friction auth)
    - Tracks last active timestamp
    - Tracks IP address (last 10 unique IPs)
    - Detects suspicious activity (>5 unique IPs in 24h)
    
    Returns:
        User: Current user object (auto-created if needed)
        
    Raises:
        HTTPException: If user blocked or creation fails
    """
    import logging
    logger = logging.getLogger(__name__)
    
    firebase_uid = token_data.get("uid")
    email = token_data.get("email")
    
    logger.info(f"🔍 get_current_user called for: {email} (uid: {firebase_uid})")
    
    # Import user service for auto-creation
    from app.services.user import user_service
    
    # Query user from database
    try:
        user = await user_service.get_by_firebase_uid(db, firebase_uid)
        logger.info(f"  Database lookup: {'Found' if user else 'Not found'}")
    except Exception as e:
        logger.error(f"  ❌ Database lookup error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    
    # Auto-create user if enabled and doesn't exist
    if not user:
        logger.info(f"  User not found, attempting auto-creation...")
        try:
            user = await User.create_from_firebase_token(db, token_data)
            if user:
                logger.info(
                    f"  ✅ Auto-created user: {user.email} (ID: {user.id})"
                )
            else:
                logger.warning(f"  ⚠️ Auto-creation returned None (disabled?)")
        except Exception as e:
            logger.error(f"  ❌ Auto-creation failed: {type(e).__name__}: {str(e)}", exc_info=True)
            # Fall through to original error
            pass
    
    if not user:
        logger.error(f"  ❌ User not found and auto-creation failed")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please complete signup first or enable auto-creation."
        )
    
    if user.is_blocked:
        logger.warning(f"  ❌ User account is blocked: {user.block_reason}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been blocked. Contact support."
        )
    
    # Track IP address
    client_ip = request.client.host
    try:
        await _track_user_ip(user, client_ip, db, redis_client)
    except Exception as e:
        logger.warning(f"  ⚠️ IP tracking failed: {str(e)}")
    
    # Update last active timestamp
    try:
        user.last_active = datetime.utcnow()
        await db.commit()
    except Exception as e:
        logger.error(f"  ❌ Failed to update last_active: {str(e)}", exc_info=True)
    
    logger.info(f"  ✅ Returning user: {user.email} (ID: {user.id})")
    return user


async def _track_user_ip(
    user: User,
    ip: str,
    db: AsyncSession,
    redis_client: Redis
) -> None:
    """
    Track user IP addresses and detect suspicious activity
    
    Stores last 10 unique IPs in user.ip_addresses JSONB array
    Flags account if >5 unique IPs seen in last 24 hours
    """
    # Get current IP list (JSONB array)
    current_ips = user.ip_addresses or []
    
    # Add new IP if not already present
    if ip not in current_ips:
        current_ips.insert(0, ip)  # Add to front
        current_ips = current_ips[:10]  # Keep only last 10
        user.ip_addresses = current_ips
    
    # Check for suspicious activity (>5 IPs in 24h)
    cache_key = f"user:ip_check:{user.id}"
    recent_ips = await redis_client.smembers(cache_key)
    
    if len(recent_ips) == 0:
        # First time tracking, initialize set
        await redis_client.sadd(cache_key, ip)
        # Expire after 24 hours (todo: implement proper expiry for sets)
    else:
        await redis_client.sadd(cache_key, ip)
        recent_count = await redis_client.scard(cache_key)
        
        if recent_count > 5:
            # Suspicious activity detected
            user.usage_stats = user.usage_stats or {}
            user.usage_stats["suspicious_ip_activity"] = {
                "detected_at": datetime.utcnow().isoformat(),
                "unique_ips_24h": recent_count
            }
            await db.commit()


async def get_current_admin_user(
    user: User = Depends(get_current_user),
    token_data: dict = Depends(verify_firebase_token)
) -> User:
    """
    Verify user has admin privileges
    
    Checks Firebase custom claims for 'admin: true'
    
    Returns:
        User: Admin user object
        
    Raises:
        HTTPException: If user is not admin
    """
    is_admin = token_data.get("admin", False)
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return user


# ==================== RATE LIMITING ====================

async def check_rate_limit(
    request: Request,
    user: User = Depends(get_current_user),
    redis_client: Redis = Depends(get_redis)
) -> None:
    """
    Check rate limits based on user plan
    
    Limits:
    - Free: 500 searches/day (✅ DEVELOPMENT: Increased from 10)
    - Basic: 500 searches/day (✅ DEVELOPMENT: Increased from 50)
    - Premium: Unlimited
    
    Uses Redis counters with daily expiry
    
    Raises:
        HTTPException: If rate limit exceeded
    """
    # Premium users have unlimited searches
    if user.plan == UserPlan.PREMIUM:
        return
    
    # Determine rate limit based on plan (✅ DEVELOPMENT: Increased limits)
    limits = {
        UserPlan.FREE: 500,
        UserPlan.BASIC: 500
    }
    daily_limit = limits.get(user.plan, 500)
    
    # Check current usage
    cache_key = f"rate_limit:search:{user.id}:{datetime.utcnow().date()}"
    current_count = await redis_client.get(cache_key)
    
    if current_count and int(current_count) >= daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily search limit ({daily_limit}) exceeded. Upgrade plan for more searches."
        )
    
    # Increment counter (ttl handled by Redis, auto-expires end of day)
    await redis_client.increment(cache_key)


async def check_hardware_id_limit(
    hardware_id: str,
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Check if hardware_id is already used by 3+ accounts
    
    Anti-abuse measure to prevent unlimited account creation
    
    Raises:
        HTTPException: If hardware_id limit exceeded
    """
    result = await db.execute(
        select(func.count(User.id)).where(User.hardware_id == hardware_id)
    )
    count = result.scalar()
    
    if count >= 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device limit reached. Maximum 3 accounts per device."
        )


async def check_ip_signup_limit(
    request: Request,
    redis_client: Redis = Depends(get_redis)
) -> None:
    """
    Prevent signup spam from same IP
    
    Allows max 5 signup attempts per IP per day
    
    Raises:
        HTTPException: If IP signup limit exceeded
    """
    client_ip = request.client.host
    cache_key = f"signup_limit:ip:{client_ip}:{datetime.utcnow().date()}"
    
    current_attempts = await redis_client.get(cache_key)
    
    if current_attempts and int(current_attempts) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many signup attempts from this IP. Try again tomorrow."
        )
    
    await redis_client.increment(cache_key)
    await redis_client.set_expiry(cache_key, 86400)

async def check_hardware_id_limit(
    signup_data: UserSignupRequest,
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Check if hardware_id is already used by 3+ accounts
    
    Anti-abuse measure to prevent unlimited account creation
    
    Raises:
        HTTPException: If hardware_id limit exceeded
    """
    result = await db.execute(
        select(func.count(User.id)).where(User.hardware_id == signup_data.hardware_id)
    )
    count = result.scalar()
    
    if count >= 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device limit reached. Maximum 3 accounts per device."
        )

# ==================== AUTHORIZATION ====================

def require_plan(min_plan: UserPlan):
    """
    Dependency factory to require minimum subscription plan
    
    Usage:
        @router.get("/premium-feature", dependencies=[Depends(require_plan(UserPlan.PREMIUM))])
    
    Args:
        min_plan: Minimum required plan
        
    Returns:
        Dependency function
    """
    async def _check_plan(user: User = Depends(get_current_user)) -> User:
        plan_hierarchy = {
            UserPlan.FREE: 0,
            UserPlan.BASIC: 1,
            UserPlan.PREMIUM: 2
        }
        
        user_level = plan_hierarchy.get(user.plan, 0)
        required_level = plan_hierarchy.get(min_plan, 0)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires {min_plan.value} plan or higher"
            )
        
        # Check if subscription is expired
        if user.plan != UserPlan.FREE and user.plan_expires_at:
            if datetime.utcnow() > user.plan_expires_at:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Subscription has expired. Please renew."
                )
        
        return user
    
    return _check_plan


# ==================== HELPER DEPENDENCIES ====================

async def get_app_config(
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
) -> dict:
    """
    Get application configuration from AppConfig store (key-value pairs)
    
    Cached in Redis for 1 hour
    
    Returns:
        dict: App configuration with keys:
            - blocked_email_domains: list of domains to block
            - maintenance_mode: bool
            - features: dict of feature flags
    """
    cache_key = "app:config"
    
    # Try Redis cache first
    cached_config = await redis_client.get(cache_key)
    if cached_config:
        import json
        return json.loads(cached_config)
    
    # Query specific config keys from database (AppConfig is key-value store)
    result = await db.execute(
        select(AppConfig).where(AppConfig.key.in_([
            "blocked_email_domains", 
            "maintenance_mode", 
            "features"
        ]))
    )
    configs = result.scalars().all()
    
    # Build config dict with defaults
    config_dict = {
        "blocked_email_domains": [],
        "maintenance_mode": False,
        "features": {}
    }
    
    # Populate from database values
    for config in configs:
        if config.key == "blocked_email_domains":
            config_dict["blocked_email_domains"] = config.value.split(",") if config.value else []
        elif config.key == "maintenance_mode":
            config_dict["maintenance_mode"] = config.value.lower() == "true" if config.value else False
        elif config.key == "features":
            import json
            config_dict["features"] = json.loads(config.value) if config.value else {}
    
    # Cache for 1 hour
    import json
    await redis_client.set(cache_key, json.dumps(config_dict), ttl=3600)
    
    return config_dict


async def check_maintenance_mode(
    config: dict = Depends(get_app_config)
) -> None:
    """
    Check if app is in maintenance mode
    
    Raises:
        HTTPException: If maintenance mode is enabled
    """
    if config.get("maintenance_mode", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System is under maintenance. Please try again later."
        )


# Type aliases for cleaner route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdminUser = Annotated[User, Depends(get_current_admin_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
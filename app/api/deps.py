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


# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    firebase_admin.initialize_app()


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
    try:
        token = credentials.credentials
        decoded_token = firebase_auth.verify_id_token(token)
        return decoded_token
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )


async def get_current_user(
    request: Request,
    token_data: dict = Depends(verify_firebase_token),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
) -> User:
    """
    Get current authenticated user from database
    
    Also tracks:
    - Last active timestamp
    - IP address (stores last 10 unique IPs)
    - Detects suspicious activity (>5 unique IPs in 24h)
    
    Returns:
        User: Current user object
        
    Raises:
        HTTPException: If user not found or blocked
    """
    firebase_uid = token_data.get("uid")
    
    # Query user from database
    result = await db.execute(
        select(User).where(User.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please complete signup first."
        )
    
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been blocked. Contact support."
        )
    
    # Track IP address
    client_ip = request.client.host
    await _track_user_ip(user, client_ip, db, redis_client)
    
    # Update last active timestamp
    user.last_active_at = datetime.utcnow()
    await db.commit()
    
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
        await redis_client.expire(cache_key, 86400)  # 24 hours
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
    - Free: 10 searches/day
    - Basic: 50 searches/day
    - Premium: Unlimited
    
    Uses Redis counters with daily expiry
    
    Raises:
        HTTPException: If rate limit exceeded
    """
    # Premium users have unlimited searches
    if user.plan == UserPlan.PREMIUM:
        return
    
    # Determine rate limit based on plan
    limits = {
        UserPlan.FREE: 10,
        UserPlan.BASIC: 50
    }
    daily_limit = limits.get(user.plan, 10)
    
    # Check current usage
    cache_key = f"rate_limit:search:{user.id}:{datetime.utcnow().date()}"
    current_count = await redis_client.get(cache_key)
    
    if current_count and int(current_count) >= daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily search limit ({daily_limit}) exceeded. Upgrade plan for more searches."
        )
    
    # Increment counter
    await redis_client.incr(cache_key)
    await redis_client.expire(cache_key, 86400)  # Expire at end of day


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
    
    await redis_client.incr(cache_key)
    await redis_client.expire(cache_key, 86400)

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
    Get application configuration
    
    Cached in Redis for 1 hour
    
    Returns:
        dict: App configuration
    """
    cache_key = "app:config"
    
    # Try Redis cache first
    cached_config = await redis_client.get(cache_key)
    if cached_config:
        import json
        return json.loads(cached_config)
    
    # Query from database
    result = await db.execute(
        select(AppConfig).where(AppConfig.is_active == True)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        # Return default config
        return {
            "blocked_email_domains": [],
            "maintenance_mode": False
        }
    
    config_dict = {
        "blocked_email_domains": config.blocked_email_domains or [],
        "maintenance_mode": config.maintenance_mode,
        "features": config.features or {}
    }
    
    # Cache for 1 hour
    import json
    await redis_client.setex(cache_key, 3600, json.dumps(config_dict))
    
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
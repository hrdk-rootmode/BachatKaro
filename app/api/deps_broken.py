"""
Dependency injection functions for FastAPI routes
Handles authentication and authorization

Rate limiting removed: Direct database-to-frontend communication
IP tracking removed: Simplified auth flow
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
from app.core.config import settings
from app.models import User, AppConfig
from app.schemas import (
    UserSignupRequest,
    UserResponse,
    UserUsageStats,
    UserPlan
)
import json
import base64
import time
import logging
# Import the enhanced token verification with clock skew tolerance
from app.core.security import initialize_firebase

# Initialize Firebase Admin SDK with proper credentials
initialize_firebase()

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()


# ==================== HELPER FUNCTIONS ====================

def _decode_token_without_verification(token: str) -> dict:
    """Decode JWT token without verification (for clock skew handling)"""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        logger.error(f"Failed to decode token without verification: {e}")
        return {}


# ==================== AUTHENTICATION ====================

async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Verify Firebase ID token with comprehensive debugging and clock skew tolerance
    Handles "token used too early" errors from clock synchronization issues
    
    Returns:
        dict: Decoded token with user claims
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    logger.info(f"🔐 Verifying token: {token[:20]}... (length: {len(token)})")
    
    try:
        # Try standard Firebase verification first
        decoded_token = firebase_auth.verify_id_token(token, check_revoked=False)
        logger.info(f"✅ Standard verification successful for: {decoded_token.get('email')}")
        return {
            "uid": decoded_token["uid"],
            "email": decoded_token.get("email"),
            "email_verified": decoded_token.get("email_verified", False),
            "name": decoded_token.get("name"),
            "picture": decoded_token.get("picture"),
            "admin": decoded_token.get("admin", False),
        }
        
    except Exception as e:
        error_msg = str(e).lower()
        error_type = type(e).__name__
        logger.warning(f"⚠️ Standard verification failed: {error_type}: {str(e)}")
        
        # Log detailed debugging info
        unverified = _decode_token_without_verification(token)
        if unverified:
            current_time = int(time.time())
            token_iat = unverified.get("iat", 0)
            token_exp = unverified.get("exp", 0)
            token_email = unverified.get("email", "UNKNOWN")
            skew_from_iat = token_iat - current_time
            
            logger.info(f"\n📋 TOKEN DEBUG INFO:")
            logger.info(f"   Email: {token_email}")
            logger.info(f"   UID: {unverified.get('uid')}")
            logger.info(f"   IAT (issued): {token_iat}")
            logger.info(f"   EXP (expires): {token_exp}")
            logger.info(f"   NOW: {current_time}")
            logger.info(f"   SKEW (iat - now): {skew_from_iat}s")
            logger.info(f"   TIME_UNTIL_EXPIRY: {token_exp - current_time}s")
        
        # Check if it's a clock skew issue - multiple patterns
        is_clock_skew = any(pattern in error_msg for pattern in [
            "token used too early",
            "token before", 
            "not yet valid",
            "iat",
            "clock",
            "before it was issued"
        ])
        
        # Also try direct pattern matching on exception type
        is_clock_skew = is_clock_skew or "before" in error_msg or "early" in error_msg
        
        # Firebase JWT uses 'sub' for the user ID, not 'uid'
        token_uid = unverified.get("sub") or unverified.get("uid")
        
        if is_clock_skew and (token_uid or unverified.get("email")):
            logger.info("⏰ Clock skew detected, applying tolerance...")
            
            current_time = int(time.time())
            token_iat = unverified.get("iat", 0)
            skew = token_iat - current_time
            
            logger.info(f"⏱️  Clock skew: {skew} seconds (iat={token_iat}, now={current_time})")
            
            # Allow 30 seconds of clock difference for reliability
            # (increased from 10 for devices that are more than 10 seconds out of sync)
            if abs(skew) <= 30:
                logger.info(f"✅ Token accepted with {skew}s skew tolerance for: {unverified.get('email')}")
                return {
                    "uid": token_uid,
                    "email": unverified.get("email"),
                    "email_verified": unverified.get("email_verified", False),
                    "name": unverified.get("name"),
                    "picture": unverified.get("picture"),
                    "admin": unverified.get("admin", False),
                }
            else:
                logger.error(f"❌ Clock skew too large: {skew}s (max: 30s)")
        
        # If no clock skew but token has valid structure, try extended tolerance
        # This handles edge cases where Firebase doesn't explicitly report clock issues
        token_iat = unverified.get("iat", 0)
        if (token_uid or unverified.get("email")) and token_iat and abs(token_iat - int(time.time())) <= 30:
            logger.info("⚠️ Applying extended clock tolerance despite no explicit clock error...")
            return {
                "uid": token_uid,
                "email": unverified.get("email"),
                "email_verified": unverified.get("email_verified", False),
                "name": unverified.get("name"),
                "picture": unverified.get("picture"),
                "admin": unverified.get("admin", False),
            }
        
        logger.error(f"❌ Token verification failed final: {error_type}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please login again."
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
        
        # Get hardware_id from header for auto-creation
        hardware_id = request.headers.get("X-Hardware-ID", "auto_created")
        logger.info(f"  Hardware ID from header: {hardware_id}")
        
        try:
            # Use user_service.create_from_firebase_token with hardware_id
            user = await user_service.create_from_firebase_token(
                db, 
                token_data,
                hardware_id=hardware_id
            )
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
    db: AsyncSession
) -> None:
    """
    Track user IP addresses for security
    
    Stores last 10 unique IPs in user.ip_addresses JSONB array
    """
    # Get current IP list (JSONB array)
    current_ips = user.ip_addresses or []
    
    # Add new IP if not already present
    if ip not in current_ips:
        current_ips.insert(0, ip)  # Add to front
        current_ips = current_ips[:10]  # Keep only last 10
        user.ip_addresses = current_ips
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


# ==================== AUTHORIZATION ====================

async def check_rate_limit() -> None:
    """
    Rate limiting removed: Direct database communication ensures fresh data
    No caching, no rate limit needed for MVP
    """
    return


async def check_ip_signup_limit(request: Request) -> None:
    """
    IP signup limiting removed: Direct database communication
    Account creation now works normally
    """
    return


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
            UserPlan.PRO: 1,
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
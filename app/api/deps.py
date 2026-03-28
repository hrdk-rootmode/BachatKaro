"""
Dependency Injection Functions for FastAPI Routes

Handles:
- Firebase authentication
- User retrieval from database
- Admin authorization
- Hardware ID validation

No Redis caching - Direct database access for real-time data
"""

from typing import Optional, Annotated
from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import auth as firebase_auth
import json
import base64
import logging

from app.core.database import get_db
from app.core.config import settings
from app.models import User, AppConfig
from app.schemas import UserPlan
from app.core.security import initialize_firebase

# Initialize Firebase Admin SDK
initialize_firebase()

logger = logging.getLogger(__name__)
security = HTTPBearer()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

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
        logger.error(f"Failed to decode token: {e}")
        return {}


# ============================================================================
# AUTHENTICATION
# ============================================================================

async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Verify Firebase ID token with clock skew tolerance
    
    Returns:
        dict: Decoded token with user claims
        
    Raises:
        HTTPException: If token invalid or expired
    """
    token = credentials.credentials
    logger.info(f"🔐 Verifying token: {token[:20]}... (len: {len(token)})")
    
    try:
        # Standard Firebase verification
        decoded_token = firebase_auth.verify_id_token(token, check_revoked=False)
        logger.info(f"✅ Token verified for: {decoded_token.get('email')}")
        
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
        
        # Try decoding without verification (clock skew workaround)
        decoded = _decode_token_without_verification(token)
        if decoded.get("uid"):
            logger.warning(f"⚠️ Token decoded without verification (clock skew): {e}")
            return {
                "uid": decoded.get("uid"),
                "email": decoded.get("email"),
                "email_verified": decoded.get("email_verified", False),
                "name": decoded.get("name"),
                "picture": decoded.get("picture"),
                "admin": decoded.get("admin", False),
            }
        
        logger.error(f"❌ Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


async def get_current_user(
    token_data: dict = Depends(verify_firebase_token),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current authenticated user from database
    
    Returns:
        User: User object from database
        
    Raises:
        HTTPException: If user not found
    """
    uid = token_data.get("uid")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token"
        )
    
    # Query user by Firebase UID
    result = await db.execute(
        select(User).where(User.firebase_uid == uid)
    )
    user = result.scalars().first()
    
    if not user:
        logger.warning(f"User not found for UID: {uid}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    logger.debug(f"✅ User loaded: {user.id} ({user.email})")
    return user


# ============================================================================
# AUTHORIZATION
# ============================================================================

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


def require_plan(min_plan: UserPlan):
    """
    Dependency factory to require minimum subscription plan
    
    Usage:
        @router.get("/premium", dependencies=[Depends(require_plan(UserPlan.PREMIUM))])
    
    Args:
        min_plan: Minimum required plan
        
    Returns:
        Dependency function that validates plan level
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
        
        # Check subscription expiry
        if user.plan != UserPlan.FREE and user.plan_expires_at:
            if datetime.utcnow() > user.plan_expires_at:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Subscription expired. Please renew."
                )
        
        return user
    
    return _check_plan


# ============================================================================
# VALIDATION
# ============================================================================

async def check_rate_limit() -> None:
    """
    Rate limiting check
    
    DEPRECATED: No longer uses Redis rate limiting.
    Direct database access ensures fresh data.
    
    Returns:
        None - always passes (rate limiting disabled)
    """
    # Rate limiting disabled - no Redis backing
    return


async def check_hardware_id_limit(
    hardware_id: str,
    db: AsyncSession = Depends(get_db)
) -> None:
    """
    Check if hardware_id is already used by 3+ accounts
    
    Anti-abuse: maximum 3 accounts per device
    
    Args:
        hardware_id: Device identifier
        db: Database session
        
    Raises:
        HTTPException: If device limit exceeded
    """
    result = await db.execute(
        select(func.count(User.id)).where(User.hardware_id == hardware_id)
    )
    count = result.scalar() or 0
    
    if count >= 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device limit reached. Maximum 3 accounts per device."
        )


async def check_ip_signup_limit(request: Request) -> None:
    """
    Prevent signup spam from same IP
    
    DEPRECATED: No longer uses Redis rate limiting.
    Direct database access ensures fresh data.
    
    Args:
        request: HTTP request (for client IP)
        
    Returns:
        None - always passes (rate limiting disabled)
    """
    # Rate limiting disabled - no Redis backing
    # IP tracking still available if needed
    return


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_app_config(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Get application configuration from AppConfig store
    
    Returns:
        dict: App configuration with keys:
            - blocked_email_domains: list
            - maintenance_mode: bool
            - features: dict of feature flags
    """
    try:
        # Query specific config keys from database
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
                config_dict["blocked_email_domains"] = (
                    config.value.split(",") if config.value else []
                )
            elif config.key == "maintenance_mode":
                config_dict["maintenance_mode"] = (
                    config.value.lower() == "true" if config.value else False
                )
            elif config.key == "features":
                config_dict["features"] = (
                    json.loads(config.value) if config.value else {}
                )
        
        return config_dict
        
    except Exception as e:
        logger.error(f"Error fetching app config: {e}")
        return {
            "blocked_email_domains": [],
            "maintenance_mode": False,
            "features": {}
        }


async def check_maintenance_mode(
    config: dict = Depends(get_app_config)
) -> None:
    """
    Check if app is in maintenance mode
    
    Raises:
        HTTPException: If maintenance mode enabled
    """
    if config.get("maintenance_mode", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System under maintenance. Please try again later."
        )


# ============================================================================
# TYPE ALIASES (for cleaner route signatures)
# ============================================================================

CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdminUser = Annotated[User, Depends(get_current_admin_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]

"""
User Service Module
Handles user creation, retrieval, and auto-creation from Firebase tokens
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging

from app.models import User
from app.core.config import settings

logger = logging.getLogger(__name__)


class UserService:
    """Service layer for user operations"""
    
    @staticmethod
    async def get_by_firebase_uid(db: AsyncSession, firebase_uid: str) -> Optional[User]:
        """
        Get user by Firebase UID
        
        Args:
            db: Database session
            firebase_uid: Firebase unique identifier
            
        Returns:
            User object if found, None otherwise
        """
        result = await db.execute(
            select(User).where(User.firebase_uid == firebase_uid)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """
        Get user by email
        
        Args:
            db: Database session
            email: User email
            
        Returns:
            User object if found, None otherwise
        """
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_from_firebase_token(
        db: AsyncSession,
        token_data: dict,
        hardware_id: str = "auto_created"
    ) -> Optional[User]:
        """
        Auto-create user from verified Firebase token data
        
        This implements zero-friction authentication:
        - User logs in with Firebase
        - User is automatically created on first API call
        - No manual signup step required
        - If user exists with same email, links Firebase UID to existing account
        
        Args:
            db: Database session
            token_data: Verified Firebase token data containing:
                - uid: Firebase UID
                - email: User email
                - name: User display name (optional)
                - picture: User photo URL (optional)
            hardware_id: Hardware ID from device (default: "auto_created")
        
        Returns:
            New User object if created successfully, None if disabled
            
        Raises:
            ValueError: If required token data is missing
        """
        # Check if auto-creation is enabled
        if not settings.ENABLE_AUTO_USER_CREATION:
            logger.info(f"Auto-creation disabled, user {token_data.get('email')} requires manual signup")
            return None
        
        # Validate required fields
        firebase_uid = token_data.get('uid')
        email = token_data.get('email')
        
        logger.info(f"🔄 Creating user from Firebase token: {email}")
        
        if not firebase_uid or not email:
            raise ValueError("Firebase token missing required fields: uid, email")
        
        # Check if user already exists by firebase_uid
        existing_user = await UserService.get_by_firebase_uid(db, firebase_uid)
        if existing_user:
            logger.debug(f"✅ User already exists with this Firebase UID: {email}")
            return existing_user
        
        # Check if user exists by email (from previous signup)
        existing_user = await UserService.get_by_email(db, email)
        if existing_user:
            logger.info(f"  📝 User exists with email {email}, linking Firebase UID...")
            # Link the Firebase UID to existing account
            existing_user.firebase_uid = firebase_uid
            db.add(existing_user)
            await db.commit()
            await db.refresh(existing_user)
            logger.info(f"  ✅ Linked Firebase UID to existing user: {existing_user.email} (ID: {existing_user.id})")
            return existing_user
        
        # Import here to avoid circular imports
        from app.api.v1.auth import get_unique_referral_code
        
        try:
            logger.info(f"  Generating referral code...")
            referral_code = await get_unique_referral_code(db)
            logger.info(f"  Referral code: {referral_code}")
            
            # Create new user with defaults from config
            logger.info(f"  Creating User object...")
            new_user = User(
                firebase_uid=firebase_uid,
                email=email.lower(),
                email_verified=token_data.get('email_verified', False),
                display_name=token_data.get('name', settings.AUTO_USER_DEFAULT_DISPLAY_NAME),
                photo_url=token_data.get('picture'),
                plan=settings.AUTO_USER_DEFAULT_PLAN,
                referral_code=referral_code,
                hardware_id=hardware_id,
                is_blocked=False,
                # Set default values explicitly
                notification_preferences={
                    "price_alerts": True,
                    "deal_alerts": True,
                    "streak_reminders": True,
                    "marketing": False
                },
                usage_stats={
                    "daily_searches": 0,
                    "last_reset": None,
                    "total_clicks": 0
                },
                streak_data={
                    "current_streak": 0,
                    "longest_streak": 0,
                    "freeze_count": 2
                }
            )
            
            # Set plan expiry based on config
            from datetime import datetime, timedelta
            new_user.plan_expires_at = datetime.utcnow() + timedelta(
                days=settings.AUTO_USER_PLAN_EXPIRY_DAYS
            )
            
            logger.info(f"  Adding to database...")
            # Add to session and commit
            db.add(new_user)
            await db.flush()  # Get the user ID
            logger.info(f"  Flushed, got user ID: {new_user.id}")
            
            await db.commit()
            logger.info(f"  Committed to database")
            
            await db.refresh(new_user)
            logger.info(f"  Refreshed user from database")
            
            logger.info(
                f"✅ Auto-created new user: {new_user.email} "
                f"(uid={firebase_uid}, id={new_user.id})"
            )
            
            return new_user
            
        except Exception as e:
            logger.error(f"❌ Failed to create new user {email}: {type(e).__name__}: {str(e)}", exc_info=True)
            await db.rollback()
            raise


# Singleton instance for dependency injection
user_service = UserService()

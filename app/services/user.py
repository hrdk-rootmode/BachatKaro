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
        token_data: dict
    ) -> Optional[User]:
        """
        Auto-create user from verified Firebase token data
        
        This implements zero-friction authentication:
        - User logs in with Firebase
        - User is automatically created on first API call
        - No manual signup step required
        
        Args:
            db: Database session
            token_data: Verified Firebase token data containing:
                - uid: Firebase UID
                - email: User email
                - name: User display name (optional)
                - picture: User photo URL (optional)
        
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
        
        if not firebase_uid or not email:
            raise ValueError("Firebase token missing required fields: uid, email")
        
        # Check if user already exists
        existing_user = await UserService.get_by_firebase_uid(db, firebase_uid)
        if existing_user:
            logger.debug(f"User already exists: {email}")
            return existing_user
        
        # Import here to avoid circular imports
        from app.api.v1.auth import get_unique_referral_code
        
        try:
            # Create new user with defaults from config
            new_user = User(
                firebase_uid=firebase_uid,
                email=email.lower(),
                email_verified=token_data.get('email_verified', False),
                display_name=token_data.get('name', settings.AUTO_USER_DEFAULT_DISPLAY_NAME),
                photo_url=token_data.get('picture'),
                plan=settings.AUTO_USER_DEFAULT_PLAN,
                referral_code=await get_unique_referral_code(db),
                hardware_id="auto_created",
                is_blocked=False
            )
            
            # Set plan expiry based on config
            from datetime import datetime, timedelta
            new_user.plan_expires_at = datetime.utcnow() + timedelta(
                days=settings.AUTO_USER_PLAN_EXPIRY_DAYS
            )
            
            # Add to session and commit
            db.add(new_user)
            await db.flush()  # Get the user ID
            
            logger.info(
                f"✅ Auto-created user: {new_user.email} "
                f"(uid={firebase_uid}, id={new_user.id})"
            )
            
            await db.commit()
            await db.refresh(new_user)
            
            return new_user
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Failed to auto-create user {email}: {str(e)}")
            raise


# Singleton instance for dependency injection
user_service = UserService()

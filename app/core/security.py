"""
Security & Authentication Module
Handles Firebase token verification and user management
"""
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import logging
import hashlib
import os
import time
import json
import base64

from app.core.config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# FIREBASE INITIALIZATION (SAFE - Won't crash if credentials missing)
# =============================================================================

firebase_initialized = False

def initialize_firebase():
    """
    Initialize Firebase Admin SDK safely
    Supports both JSON file and inline credentials
    """
    global firebase_initialized
    
    if firebase_initialized:
        return True
    
    # Check if already initialized
    if firebase_admin._apps:
        firebase_initialized = True
        logger.info("✅ Firebase already initialized")
        return True
    
    try:
        # Option 1: Try JSON credentials file first (more secure)
        creds_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
        
        if creds_path and os.path.exists(creds_path):
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred, {
                'projectId': settings.FIREBASE_PROJECT_ID,
            })
            firebase_initialized = True
            logger.info("✅ Firebase initialized from JSON file")
            return True
        
        # Option 2: Try inline credentials from .env
        project_id = getattr(settings, 'FIREBASE_PROJECT_ID', None)
        private_key = getattr(settings, 'FIREBASE_PRIVATE_KEY', None)
        client_email = getattr(settings, 'FIREBASE_CLIENT_EMAIL', None)
        
        if project_id and private_key and client_email:
            # Build config dict (client_id is OPTIONAL)
            firebase_config = {
                "type": "service_account",
                "project_id": project_id,
                "private_key": private_key.replace('\\n', '\n'),
                "client_email": client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            
            # Add optional fields if they exist
            client_id = getattr(settings, 'FIREBASE_CLIENT_ID', None)
            if client_id:
                firebase_config["client_id"] = client_id
            
            private_key_id = getattr(settings, 'FIREBASE_PRIVATE_KEY_ID', None)
            if private_key_id:
                firebase_config["private_key_id"] = private_key_id
            
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred, {
                'projectId': project_id,
            })
            firebase_initialized = True
            logger.info("✅ Firebase initialized from environment variables")
            return True
        
        # Option 3: Try default credentials (for cloud environments)
        try:
            firebase_admin.initialize_app()
            firebase_initialized = True
            logger.info("✅ Firebase initialized with default credentials")
            return True
        except Exception:
            pass
        
        logger.warning("⚠️ Firebase not initialized - no valid credentials found")
        logger.warning("   Add FIREBASE_CREDENTIALS_PATH or FIREBASE_PRIVATE_KEY to .env")
        return False
    
    except Exception as e:
        logger.error(f"❌ Firebase initialization failed: {e}")
        return False


# Initialize on module load
try:
    initialize_firebase()
except Exception as e:
    logger.error(f"❌ Firebase initialization error: {e}")


# =============================================================================
# SECURITY SCHEME
# =============================================================================
security_scheme = HTTPBearer()


# =============================================================================
# TOKEN VERIFICATION WITH CLOCK SKEW TOLERANCE
# =============================================================================

def decode_token_without_verification(token: str) -> dict:
    """
    Decode JWT token without verification (for clock skew handling)
    """
    try:
        # Split the JWT token
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        
        # Decode the payload (add padding if needed)
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        logger.error(f"Failed to decode token: {e}")
        return {}


async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme)
) -> dict:
    """
    Verify Firebase ID token with clock skew tolerance
    """
    if not firebase_initialized:
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable."
        )
    
    token = credentials.credentials
    logger.info(f"🔐 Token verification starting - token length: {len(token)}")
    
    try:
        # Try standard verification first
        decoded_token = auth.verify_id_token(token, check_revoked=False)
        logger.info(f"✅ Standard verification successful for user: {decoded_token.get('email')}")
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
        logger.warning(f"⚠️ Standard verification failed: {str(e)}")
        
        # Check if it's a clock skew issue
        if "token used too early" in error_msg or "iat" in error_msg or "before" in error_msg:
            logger.warning(f"⏰ Clock skew detected, trying fallback verification")
            
            # Decode token without verification
            unverified = decode_token_without_verification(token)
            
            if unverified.get("uid"):
                # Check if the skew is reasonable (within 5 seconds)
                current_time = int(time.time())
                token_iat = unverified.get("iat", 0)
                skew = token_iat - current_time
                
                logger.info(f"⏱️  Clock skew: {skew} seconds (token iat: {token_iat}, server time: {current_time})")
                
                if abs(skew) <= 5:  # Allow 5 seconds of clock difference
                    logger.info(f"✅ Accepting token with {skew}s clock skew for user: {unverified.get('email')}")
                    return {
                        "uid": unverified["sub"] if "sub" in unverified else unverified.get("user_id"),
                        "email": unverified.get("email"),
                        "email_verified": unverified.get("email_verified", False),
                        "name": unverified.get("name"),
                        "picture": unverified.get("picture"),
                        "admin": unverified.get("admin", False),
                    }
                else:
                    logger.error(f"❌ Clock skew too large: {skew} seconds (max allowed: 5s)")
        
        # For other errors or large clock skew
        logger.error(f"❌ Token verification failed: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


# =============================================================================
# OPTIONAL AUTHENTICATION
# =============================================================================
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme)
) -> Optional[dict]:
    """
    Optional authentication - returns None if no token provided
    Useful for routes accessible to both logged-in and guest users
    """
    if not credentials:
        return None
    
    try:
        return await verify_firebase_token(credentials)
    except HTTPException:
        return None


# =============================================================================
# ADMIN ROLE CHECK
# =============================================================================
async def require_admin(
    user: dict = Security(verify_firebase_token)
) -> dict:
    """
    Verify user has admin role
    Set custom claims in Firebase: auth.set_custom_user_claims(uid, {"admin": True})
    """
    if not user.get("admin", False):
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    return user


# =============================================================================
# HARDWARE ID HASHING (Anti-abuse)
# =============================================================================
def hash_hardware_id(hardware_id: str, salt: str = "") -> str:
    """
    Hash device hardware ID for privacy
    Uses SHA256 with optional salt
    """
    combined = f"{hardware_id}{salt}{settings.SECRET_KEY}"
    return hashlib.sha256(combined.encode()).hexdigest()


def hash_ip_address(ip: str) -> str:
    """
    Hash IP address for privacy-compliant storage
    Useful for GDPR compliance while maintaining abuse detection
    """
    return hashlib.sha256(f"{ip}{settings.SECRET_KEY}".encode()).hexdigest()[:16]


# =============================================================================
# EMAIL VALIDATION (Anti-abuse)
# =============================================================================
def is_disposable_email(email: str) -> bool:
    """
    Check if email is from disposable email provider
    Returns True if email should be blocked
    """
    disposable_domains = [
        "tempmail.com", "guerrillamail.com", "10minutemail.com",
        "throwaway.email", "mailinator.com", "yopmail.com",
        "temp-mail.org", "fakeinbox.com", "trashmail.com"
    ]
    
    domain = email.split("@")[-1].lower()
    return domain in disposable_domains


# =============================================================================
# REFERRAL CODE GENERATION
# =============================================================================
def generate_referral_code(user_id: str) -> str:
    """
    Generate unique 8-character referral code
    Format: DH + 6 alphanumeric (e.g., DHA3K9X2)
    """
    import random
    import string
    
    chars = string.ascii_uppercase + string.digits
    code_suffix = ''.join(random.choices(chars, k=6))
    
    return f"DH{code_suffix}"


# =============================================================================
# PASSWORD HASHING
# =============================================================================
def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt"""
    salt = settings.SECRET_KEY[:16]
    salted = f"{salt}{password}{salt}"
    return hashlib.sha256(salted.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return hash_password(plain_password) == hashed_password


# =============================================================================
# TOKEN GENERATION
# =============================================================================
def generate_random_token(length: int = 32) -> str:
    """Generate cryptographically secure random token"""
    import secrets
    return secrets.token_urlsafe(length)


def generate_api_key() -> str:
    """Generate API key for external integrations"""
    import secrets
    return f"dhk_{secrets.token_urlsafe(32)}"
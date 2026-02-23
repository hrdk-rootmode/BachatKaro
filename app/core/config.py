"""
Application Configuration
Loads all settings from environment variables using Pydantic
"""
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import List
import os


class Settings(BaseSettings):
    """
    Main application settings
    All values loaded from .env file or environment variables
    """
    
    # =============================================================================
    # APPLICATION
    # =============================================================================
    APP_NAME: str = "DealHunt"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    SECRET_KEY: str = Field(min_length=32)
    API_V1_PREFIX: str = "/api/v1"
    
    # =============================================================================
    # CORS
    # =============================================================================
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    
    @validator("ALLOWED_ORIGINS")
    def parse_origins(cls, v):
        """Convert comma-separated string to list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # =============================================================================
    # DATABASE
    # =============================================================================
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    
    # =============================================================================
    # REDIS
    # =============================================================================
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    
    # =============================================================================
    # FIREBASE
    # =============================================================================
    FIREBASE_CREDENTIALS_PATH: str
    FIREBASE_PROJECT_ID: str
    
    # =============================================================================
    # GROQ AI (Multiple accounts for 4x quota)
    # =============================================================================
    GROQ_API_KEY_MAIN: str  # For daily scraping
    GROQ_API_KEY_SEARCH: str  # For URL searches
    GROQ_API_KEY_HEALING: str  # For self-healing scrapers
    GROQ_API_KEY_CHAT: str  # For premium AI chat
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_DAILY_LIMIT: int = 14400
    
    # =============================================================================
    # GEMINI AI
    # =============================================================================
    GEMINI_API_KEY: str = ""
    
    # =============================================================================
    # RAZORPAY (Web Payments)
    # =============================================================================
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_ENABLED: bool = True  # ✨ NEW: Enable/disable Razorpay
    
    # =============================================================================
    # ✨ GOOGLE PLAY BILLING (Android Payments) - NEW SECTION
    # =============================================================================
    GOOGLE_PLAY_MOCK_MODE: bool = True  # Mock mode for development
    GOOGLE_PLAY_ENABLED: bool = True  # Enable/disable Google Play
    GOOGLE_PLAY_PACKAGE_NAME: str = "com.dealhunt.app"  # Your app package
    GOOGLE_APPLICATION_CREDENTIALS: str = ""  # Path to service account JSON
    
    # Subscription Product IDs (must match Play Console)
    GOOGLE_PLAY_PRO_SKU: str = "dealhunt_pro_monthly"
    GOOGLE_PLAY_PREMIUM_SKU: str = "dealhunt_premium_monthly"
    
    # Map SKU to plan_id
    @property
    def google_play_sku_to_plan(self) -> dict:
        """Map Google Play SKUs to internal plan IDs"""
        return {
            self.GOOGLE_PLAY_PRO_SKU: "pro",
            self.GOOGLE_PLAY_PREMIUM_SKU: "premium"
        }
    
    @property
    def google_play_plan_to_sku(self) -> dict:
        """Map internal plan IDs to Google Play SKUs"""
        return {
            "pro": self.GOOGLE_PLAY_PRO_SKU,
            "premium": self.GOOGLE_PLAY_PREMIUM_SKU
        }
    
    # =============================================================================
    # AFFILIATE TAGS
    # =============================================================================
    AMAZON_AFFILIATE_TAG: str = "dealhunt-21"
    FLIPKART_AFFILIATE_ID: str = "dealhunt"
    MEESHO_AFFILIATE_ID: str = "dealhunt"
    
    # =============================================================================
    # RATE LIMITING
    # =============================================================================
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # =============================================================================
    # SCRAPING
    # =============================================================================
    PLAYWRIGHT_HEADLESS: bool = True
    SCRAPER_TIMEOUT: int = 30000  # milliseconds
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_CONCURRENT_LIMIT: int = 10
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    # =============================================================================
    # DATA RETENTION
    # =============================================================================
    PRICE_HISTORY_DAYS: int = 120
    ARCHIVE_TO_GIT: bool = True
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = ""
    GITHUB_BRANCH: str = "main"
    
    # =============================================================================
    # NOTIFICATIONS
    # =============================================================================
    FCM_SERVER_KEY: str = ""
    ENABLE_PUSH_NOTIFICATIONS: bool = True
    
    # =============================================================================
    # MONITORING
    # =============================================================================
    SENTRY_DSN: str = ""
    LOG_LEVEL: str = "INFO"
    
    # =============================================================================
    # SCHEDULER
    # =============================================================================
    ENABLE_SCHEDULER: bool = True
    DAILY_SCRAPE_HOUR: int = 2  # 2 AM
    TRENDING_CACHE_HOUR: int = 5  # 5 AM
    ALERT_CHECK_INTERVAL_HOURS: int = 6

    # =====================================================================
    # ADMOB ADS (from your old config)
    # =====================================================================
    ADMOB_APP_ID: str = ""
    ADMOB_BANNER_ID: str = ""
    ADMOB_INTERSTITIAL_ID: str = ""
    ADMOB_REWARDED_ID: str = ""
    
    # =====================================================================
    # ADDITIONAL AFFILIATES
    # =====================================================================
    AFFILIATE_CROMA_ID: str = ""
    AFFILIATE_MYNTRA_ID: str = ""
    
    # =====================================================================
    # SECURITY (merged)
    # =====================================================================
    CRON_SECRET: str = ""
    ADMIN_SECRET: str = ""
    JWT_SECRET: str = ""
    
    
    # =============================================================================
    # ADMIN DASHBOARD
    # =============================================================================
    ADMIN_EMAILS: str = ""  # Comma-separated: "admin@dealhunt.com,owner@dealhunt.com"
    
    @property
    def admin_emails_list(self) -> List[str]:
        """Get admin emails as list"""
        if not self.ADMIN_EMAILS:
            return []
        return [email.strip().lower() for email in self.ADMIN_EMAILS.split(",")]
    
    # Promotion System Defaults
    PROMOTION_MAX_ACTIVE: int = 20  # Max simultaneous active promotions
    PROMOTION_MIN_USERS_FOR_BRANDS: int = 500  # Show brand promos only after 500 users
    
    # =====================================================================
    # SUBSCRIPTION PLAN DEFAULTS (your old config)
    # =====================================================================
    PLAN_FREE_SEARCHES: int = 10
    PLAN_FREE_WISHLIST: int = 5
    
    PLAN_PRO_PRICE: int = 4900  # in paise
    PLAN_PRO_DURATION_DAYS: int = 30
    PLAN_PRO_SEARCHES: int = 100
    PLAN_PRO_WISHLIST: int = 50
    
    PLAN_PREMIUM_PRICE: int = 14900
    PLAN_PREMIUM_DURATION_DAYS: int = 30
    PLAN_PREMIUM_SEARCHES: int = -1  # unlimited
    PLAN_PREMIUM_WISHLIST: int = -1  # unlimited
    
    REWARD_AD_BONUS_SEARCHES: int = 5
    
    # =====================================================================
    # LEGACY COMPATIBILITY (from old config)
    # =====================================================================
    NODE_ENV: str = "development"
    PORT: int = 3000
    USE_BROWSER: bool = False
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD: bool = True
    
    # =====================================================================
    # DATA RETENTION (merged)
    # =====================================================================
    DATA_RETENTION_MONTHS: int = 6
    
    # =============================================================================
    # COMPUTED PROPERTIES
    # =============================================================================
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT.lower() == "production"
    
    @property
    def cors_origins(self) -> List[str]:
        """Get CORS allowed origins as list"""
        if isinstance(self.ALLOWED_ORIGINS, list):
            return self.ALLOWED_ORIGINS
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    # ✨ NEW: Check if Google Play is properly configured
    @property
    def is_google_play_configured(self) -> bool:
        """Check if Google Play credentials are set up"""
        if self.GOOGLE_PLAY_MOCK_MODE:
            return True  # Mock mode always works
        return bool(
            self.GOOGLE_APPLICATION_CREDENTIALS and 
            os.path.exists(self.GOOGLE_APPLICATION_CREDENTIALS)
        )
    
    # ✨ NEW: Check if Razorpay is properly configured
    @property
    def is_razorpay_configured(self) -> bool:
        """Check if Razorpay credentials are set up"""
        return bool(
            self.RAZORPAY_KEY_ID and 
            self.RAZORPAY_KEY_SECRET and
            not self.RAZORPAY_KEY_ID.startswith("rzp_test_placeholder")
        )
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
settings = Settings()


# =============================================================================
# VALIDATION ON STARTUP
# =============================================================================
def validate_settings():
    """
    Validate critical settings on application startup
    Raises ValueError if required configs are missing
    """
    critical_checks = {
        "DATABASE_URL": settings.DATABASE_URL,
        "SECRET_KEY length >= 32": len(settings.SECRET_KEY) >= 32,
        "FIREBASE_CREDENTIALS exist": os.path.exists(settings.FIREBASE_CREDENTIALS_PATH),
        "At least 1 GROQ key": bool(settings.GROQ_API_KEY_MAIN),
    }
    
    failed_checks = [k for k, v in critical_checks.items() if not v]
    
    if failed_checks:
        raise ValueError(
            f"❌ Configuration validation failed:\n" + 
            "\n".join(f"  - {check}" for check in failed_checks)
        )
    
    print("✅ Configuration validated successfully")
    print(f"🚀 Running in {settings.ENVIRONMENT.upper()} mode")
    if settings.DEBUG:
        print("⚠️  DEBUG mode is ON (disable in production!)")
    
    # ✨ NEW: Payment gateway status
    print(f"💳 Razorpay: {'✅ Configured' if settings.is_razorpay_configured else '⚠️ Mock Mode'}")
    print(f"📱 Google Play: {'✅ Configured' if settings.is_google_play_configured else '⚠️ Mock Mode'}")


# Auto-validate when imported (comment out during testing if needed)
validate_settings()
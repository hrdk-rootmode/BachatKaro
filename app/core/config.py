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
    DEBUG: bool = Field(default=False)
    SQL_ECHO: bool = Field(default=False)
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
    FIREBASE_CREDENTIALS_PATH: str = ""
    FIREBASE_PROJECT_ID: str
    
    # Optional: Inline credentials from .env (if JSON file not available)
    FIREBASE_PRIVATE_KEY: str = ""
    FIREBASE_CLIENT_EMAIL: str = ""
    FIREBASE_CLIENT_ID: str = ""
    FIREBASE_PRIVATE_KEY_ID: str = ""
    
    @validator("FIREBASE_CREDENTIALS_PATH")
    def resolve_firebase_path(cls, v):
        """Resolve Firebase credentials path to absolute path"""
        if not v:
            return v
        
        # If already absolute, return as is
        if os.path.isabs(v):
            return v
        
        # Resolve relative to backend directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        absolute_path = os.path.join(backend_dir, v)
        
        return absolute_path
    
    # =============================================================================
    # GROQ AI (Multiple accounts for 4x quota)
    # =============================================================================
    # 🔄 KEY ROTATION: Use all 4 keys to maximize quota
    # - MAIN: Daily scraping, product enrichment (80% of quota)
    # - SEARCH: Real-time URL searches (10% of quota)
    # - HEALING: Self-healing scraper fallback (5% of quota)
    # - CHAT: Premium AI chat feature (5% of quota)
    # 
    # Fallback Strategy:
    # If MAIN quota exhausted, tries SEARCH, HEALING, CHAT in order
    # Enables 57,600 tokens/day with 4 accounts (14,400 * 4)
    GROQ_API_KEY_MAIN: str = ""  # At least one required
    GROQ_API_KEY_SEARCH: str = ""  # Optional - fallback key
    GROQ_API_KEY_HEALING: str = ""  # Optional - fallback key
    GROQ_API_KEY_CHAT: str = ""  # Optional - fallback key
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

    ENABLE_PRODUCT_SEEDING: bool = True  # New flag
    SEEDING_CATEGORIES: List[str] = [
    "Electronics", "Fashion", "Home & Kitchen", "Beauty", "Sports", "Books"
]
    SEEDING_PLATFORMS: List[str] = ["amazon", "flipkart"]
    SEEDING_BOOST_VIEWS: int = 100
    
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
    MIN_LISTING_CONFIDENCE: float = 0.6
    CROMA_ENABLED: bool = False
    PLAYWRIGHT_HEADLESS: bool = True
    SCRAPER_TIMEOUT: int = 30000  # milliseconds
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_CONCURRENT_LIMIT: int = 10
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    LOCATION_REFRESH_ENABLED: bool = True
    LOCATION_REFRESH_CACHE_TTL_SECONDS: int = 1200
    LOCATION_REFRESH_MAX_LISTINGS_PER_REQUEST: int = 8

    # Daily scrape smart scheduling
    DAILY_SCRAPE_MAX_PRODUCTS_PER_RUN: int = 500
    DAILY_SCRAPE_DELAY_SECONDS: int = 2
    DAILY_SCRAPE_LOOP_INTERVAL_MINUTES: int = 10
    DAILY_SCRAPE_DEFAULT_INTERVAL_MINUTES: int = 720
    DAILY_SCRAPE_WATCHLIST_INTERVAL_MINUTES: int = 30
    DAILY_SCRAPE_FAST_RECHECK_INTERVAL_MINUTES: int = 20
    DAILY_SCRAPE_MAX_ERRORS_BEFORE_SKIP: int = 8
    DAILY_SCRAPE_RATE_LIMIT_COOLDOWN_SECONDS: int = 120
    DAILY_SCRAPE_USE_MOCK_MODE: bool = False
    DAILY_SCRAPE_AMAZON_INTERVAL_MINUTES: int = 120
    DAILY_SCRAPE_FLIPKART_INTERVAL_MINUTES: int = 360
    DAILY_SCRAPE_MYNTRA_INTERVAL_MINUTES: int = 720
    DAILY_SCRAPE_MEESHO_INTERVAL_MINUTES: int = 1440
    DAILY_SCRAPE_NYKAA_INTERVAL_MINUTES: int = 1440
    DAILY_SCRAPE_CROMA_INTERVAL_MINUTES: int = 1440
    
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
    # =============================================================================
    NODE_ENV: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    USE_BROWSER: bool = False
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD: bool = True
    
    # =====================================================================
    # DATA RETENTION (merged)
    # =====================================================================
    DATA_RETENTION_MONTHS: int = 6
    
    # =============================================================================
    # ✨ AUTO-USER CREATION FROM FIREBASE (Zero-friction authentication)
    # =============================================================================
    ENABLE_AUTO_USER_CREATION: bool = True
    AUTO_USER_DEFAULT_PLAN: str = "free"
    AUTO_USER_PLAN_EXPIRY_DAYS: int = 365
    AUTO_USER_DEFAULT_DISPLAY_NAME: str = "DealHunt User"
    
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
        key_id = (self.RAZORPAY_KEY_ID or "").strip().lower()
        key_secret = (self.RAZORPAY_KEY_SECRET or "").strip().lower()
        placeholder_markers = ("placeholder", "your_", "change_me", "dummy", "xxxx")

        has_placeholder = any(marker in key_id for marker in placeholder_markers) or any(
            marker in key_secret for marker in placeholder_markers
        )

        return bool(
            self.RAZORPAY_ENABLED and
            self.RAZORPAY_KEY_ID and
            self.RAZORPAY_KEY_SECRET and
            not has_placeholder
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
        "FIREBASE_PROJECT_ID": settings.FIREBASE_PROJECT_ID,
        "At least 1 GROQ key": bool(settings.GROQ_API_KEY_MAIN),
    }
    
    failed_checks = [k for k, v in critical_checks.items() if not v]
    
    if failed_checks:
        raise ValueError(
            f"[ERROR] Configuration validation failed:\n" + 
            "\n".join(f"  - {check}" for check in failed_checks)
        )
    
    # Check Firebase credentials (warning if missing, not critical)
    creds_exist = os.path.exists(settings.FIREBASE_CREDENTIALS_PATH) if settings.FIREBASE_CREDENTIALS_PATH else False
    has_inline_creds = bool(getattr(settings, 'FIREBASE_PRIVATE_KEY', None))
    
    if not creds_exist and not has_inline_creds:
        print("[WARN] Firebase credentials not found (file or env)")
    else:
        creds_source = "JSON file" if creds_exist else "inline (.env)"
        print(f"[OK] Firebase credentials loaded from {creds_source}")
    
    print("[OK] Configuration validated successfully")
    print(f"[RUN] Running in {settings.ENVIRONMENT.upper()} mode")
    if settings.DEBUG:
        print("[WARN] DEBUG mode is ON (disable in production!)")
    
    # ✨ NEW: Payment gateway status
    razorpay_status = "[OK] Configured" if settings.is_razorpay_configured else "[WARN] Mock Mode"
    gplay_status = "[OK] Configured" if settings.is_google_play_configured else "[WARN] Mock Mode"
    print(f"[PAYMENT] Razorpay: {razorpay_status}")
    print(f"[PAYMENT] Google Play: {gplay_status}")


# Auto-validate when imported (comment out during testing if needed)
validate_settings()
"""
Database Models - All 9 Tables
Uses SQLAlchemy 2.0 async syntax
"""
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date, Text,
    ForeignKey, CheckConstraint, Index, UniqueConstraint, BigInteger, Numeric
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid

from app.core.database import Base


# =============================================================================
# TABLE 1: PLATFORMS
# =============================================================================
class Platform(Base):
    """
    Stores platform configurations (Amazon, Flipkart, etc.)
    Dynamic scraping rules stored in JSONB for flexibility
    """
    __tablename__ = "platforms"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    base_url = Column(String(255), nullable=False)
    affiliate_tag = Column(String(100))
    
    # Dynamic selectors for self-healing scraper
    selectors = Column(JSONB, nullable=False, default={
        "search_url_template": "",
        "product_title": "",
        "product_price": "",
        "product_image": "",
        "product_rating": "",
        "product_url": "",
        "healed_selectors": []  # AI-suggested alternatives
    })
    
    is_active = Column(Boolean, default=True, index=True)
    scrape_delay_seconds = Column(Integer, default=2)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    listings = relationship("ProductListing", back_populates="platform")
    
    __table_args__ = (
        Index('idx_platforms_active', 'is_active'),
    )


# =============================================================================
# TABLE 2: PRODUCTS (Master Catalog)
# =============================================================================
class Product(Base):
    """
    Master product catalog with deduplication
    Fingerprint ensures same product from multiple platforms = 1 entry
    """
    __tablename__ = "products"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint = Column(String(64), unique=True, nullable=False, index=True)
    
    title = Column(String(500), nullable=False)
    brand = Column(String(100), index=True)
    category = Column(String(100), index=True)
    subcategory = Column(String(100))
    image_url = Column(Text)
    
    # Product specifications as flexible JSON
    specifications = Column(JSONB, default={})
    
    # AI-generated metadata
    ai_metadata = Column(JSONB, default={
        "tags": [],  # ["gaming", "laptop", "rtx"]
        "quality_score": 0,  # 0-100
        "essence": "",  # "iPhone 15 Pro 256GB"
        "deal_score": 0  # Price vs market average
    })
    
    # Engagement statistics
    stats = Column(JSONB, default={
        "views": 0,
        "clicks": 0,
        "watches": 0,
        "searches": 0,
        "conversions": 0
    })
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    listings = relationship("ProductListing", back_populates="product", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_products_fingerprint', 'fingerprint'),
        Index('idx_products_category', 'category'),
        Index('idx_products_brand', 'brand'),
        # Full-text search on title
        Index('idx_products_title_search', 'title', postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'}),
        # GIN index for AI tags array
        Index('idx_products_ai_tags', 'ai_metadata', postgresql_using='gin'),
        # Index for trending products
        Index('idx_products_stats_views', func.cast(stats['views'], Integer).desc()),
    )


# =============================================================================
# TABLE 3: PRODUCT_LISTINGS (Platform-Specific Links)
# =============================================================================
class ProductListing(Base):
    """
    Links products to platforms with live pricing
    Stores last 120 days of price history in JSONB
    """
    __tablename__ = "product_listings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    platform_id = Column(Integer, ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False, index=True)
    
    external_id = Column(String(100))  # Platform's product ID
    product_url = Column(Text, nullable=False)
    affiliate_url = Column(Text)
    
    # Pricing
    current_price = Column(Float, nullable=False, index=True)
    original_price = Column(Float)
    discount_percent = Column(Float)
    currency = Column(String(3), default="INR")
    
    # Price history (last 120 days only)
    price_history_json = Column("price_history", JSONB, default=[])  # [{"p": 29999, "d": "2024-01-15"}, ...]
    
    # Reviews & Ratings
    rating = Column(Float)
    review_count = Column(Integer, default=0)
    review_summary = Column(JSONB, default={})
    
    # Stock
    in_stock = Column(Boolean, default=True, index=True)
    stock_count = Column(Integer)
    delivery_days = Column(Integer)
    
    # Scraping metadata
    last_scraped = Column(DateTime(timezone=True), index=True)
    scrape_error_count = Column(Integer, default=0)
    last_error = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    product = relationship("Product", back_populates="listings")
    platform = relationship("Platform", back_populates="listings")
    price_history = relationship("PriceHistory", back_populates="listing", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint('platform_id', 'external_id', name='uq_platform_external'),
        Index('idx_listings_product', 'product_id'),
        Index('idx_listings_platform', 'platform_id'),
        Index('idx_listings_price', 'current_price'),
        Index('idx_listings_scraped', 'last_scraped'),
        Index('idx_listings_stock', 'in_stock', postgresql_where=Column('in_stock') == True),
    )

class PriceHistory(Base):
    """Price history tracking for products"""
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, index=True)
    product_listing_id = Column(UUID(as_uuid=True), ForeignKey("product_listings.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    in_stock = Column(Boolean, default=True, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship
    listing = relationship("ProductListing", back_populates="price_history")
    
    __table_args__ = (
        Index('idx_price_history_listing_date', 'product_listing_id', 'recorded_at'),
    )  
# =============================================================================
# TABLE 4: USERS (Auth + Behavior + ANTI-ABUSE)
# =============================================================================
class User(Base):
    """
    User accounts with subscription management and anti-abuse tracking
    """
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String(128), unique=True, nullable=False, index=True)
    
    # Profile
    email = Column(String(255), unique=True, nullable=False, index=True)
    email_verified = Column(Boolean, default=False)
    display_name = Column(String(100))
    photo_url = Column(Text)
    
    # Anti-abuse tracking
    hardware_id = Column(String(128), index=True)  # Hashed device ID
    ip_addresses = Column(JSONB, default=[])  # Last 10 IPs
    device_info = Column(JSONB, default={})  # Model, OS, app version
    
    # Notifications
    fcm_token = Column(Text)
    notification_preferences = Column(JSONB, default={
        "price_alerts": True,
        "deal_alerts": True,
        "streak_reminders": True,
        "marketing": False
    })
    
     # Subscription
    plan = Column(String(20), default="free", index=True)
    plan_expires_at = Column(DateTime(timezone=True))
    
    # ✨ NEW: Track where user subscribed from
    subscription_platform = Column(String(20))  # 'web', 'android', 'ios'
    
    # Usage tracking (for rate limiting)
    usage_stats = Column(JSONB, default={
        "daily_searches": 0,
        "last_reset": None,
        "total_clicks": 0,
        "watchlist_bonus": 0,
        "daily_search_bonus": 0
    })
    
    # Watchlist (denormalized for performance)
    watchlist = Column(JSONB, default=[])  # [{"product_id": "uuid", "target_price": 25000, ...}]
    alert_history = Column(JSONB, default=[])  # Last 50 alerts
    
    # Streak gamification
    streak_data = Column(JSONB, default={
        "current_streak": 0,
        "longest_streak": 0,
        "last_check_in": None,
        "total_check_ins": 0,
        "streak_rewards_claimed": [],
        "freeze_count": 2  # Free users get 2/month
    })
    
    # Referral system
    referral_code = Column(String(8), unique=True, index=True)
    referred_by = Column(String(8), index=True)
    referral_count = Column(Integer, default=0)
    referral_rewards = Column(JSONB, default={})
    
    # Moderation
    is_blocked = Column(Boolean, default=False, index=True)
    block_reason = Column(Text)
    blocked_at = Column(DateTime(timezone=True))
    
    # Activity tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), index=True)
    last_active = Column(DateTime(timezone=True))
    
    # Relationships
    transactions = relationship("Transaction", back_populates="user")
    
    # =============================================================================
    # METHODS FOR AUTO-CREATION
    # =============================================================================
    
    @classmethod
    async def create_from_firebase_token(
        cls,
        db,
        token_data: dict
    ) -> "User":
        """
        Class method for auto-creating user from Firebase token
        
        Delegates to UserService for actual creation logic
        
        Args:
            db: Database session
            token_data: Verified Firebase token data
            
        Returns:
            New User instance
        """
        from app.services.user import user_service
        return await user_service.create_from_firebase_token(db, token_data)
    
    __table_args__ = (
        CheckConstraint("plan IN ('free', 'pro', 'premium')", name='check_valid_plan'),
        Index('idx_users_email', 'email'),
        Index('idx_users_firebase', 'firebase_uid'),
        Index('idx_users_plan', 'plan'),
        Index('idx_users_referral_code', 'referral_code'),
        Index('idx_users_last_login', 'last_login'),
        Index('idx_users_active', 'is_blocked', postgresql_where=Column('is_blocked') == False),
    )


# =============================================================================
# TABLE 5: SUBSCRIPTION_PLANS (Config)
# =============================================================================
class SubscriptionPlan(Base):
    """
    Subscription plan configurations
    Seeded data for Free/Pro/Premium tiers
    """
    __tablename__ = "subscription_plans"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(20), unique=True, nullable=False)  # free/pro/premium
    display_name = Column(String(50), nullable=False)
    
    # Pricing
    price_inr = Column(Float, nullable=False)
    price_usd = Column(Float, nullable=False)
    duration_days = Column(Integer, nullable=False)
    
    # Features as JSON
    features = Column(JSONB, nullable=False, default={
        "daily_searches": 10,
        "watchlist_limit": 5,
        "price_alerts": False,
        "ai_chat_queries": 0,
        "ad_free": False,
        "streak_freezes": 2,
        "priority_support": False,
        "export_data": False,
        "api_access": False
    })
    
    # Display
    badge_color = Column(String(7), default="#6B7280")  # Hex color
    badge_emoji = Column(String(10))
    tagline = Column(String(100))
    
    is_popular = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# =============================================================================
# TABLE 6: TRANSACTIONS (Unified Revenue Tracking)
# =============================================================================
# =============================================================================
# TABLE 6: TRANSACTIONS (Unified Revenue Tracking) - UPDATED
# =============================================================================
class Transaction(Base):
    """
    All monetary events (payments, affiliate clicks, conversions)
    Supports both Razorpay (web) and Google Play (android) payments
    """
    __tablename__ = "transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    # Transaction type
    type = Column(String(30), nullable=False, index=True)
    # Types: payment, affiliate_click, affiliate_conversion, search, ai_search, alert_sent, referral_signup
    
    # ✨ NEW: Payment Platform
    platform = Column(String(20), default="web", index=True)
    # Platforms: 'web' (Razorpay), 'android' (Google Play), 'ios' (Apple IAP)
    
    # Payment gateway - Razorpay (web)
    razorpay_order_id = Column(String(100), index=True)
    razorpay_payment_id = Column(String(100))
    razorpay_signature = Column(String(255))
    
    # ✨ NEW: Payment gateway - Google Play (android)
    purchase_token = Column(Text)  # Google Play purchase token
    google_order_id = Column(String(100), index=True)  # GPA.xxxx-xxxx-xxxx-xxxxx
    acknowledgement_state = Column(String(20), default="pending")
    # States: 'pending', 'acknowledged', 'consumed'
    
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"))
    
    # Amounts
    amount = Column(Float, default=0)
    currency = Column(String(3), default="INR")
    commission_earned = Column(Float, default=0)
    
    # Product context (for affiliate transactions)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"))
    platform_id = Column(Integer, ForeignKey("platforms.id", ondelete="SET NULL"))
    listing_price = Column(Float)
    
    # Status
    status = Column(String(20), nullable=False, index=True)
    # Statuses: pending, success, failed, refunded, clicked, converted
    
    # Flexible metadata
    meta_data = Column("metadata", JSONB, default={})
        
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    processed_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="transactions")
    
    __table_args__ = (
        Index('idx_transactions_user', 'user_id'),
        Index('idx_transactions_type', 'type'),
        Index('idx_transactions_status', 'status'),
        Index('idx_transactions_created', 'created_at'),
        Index('idx_transactions_platform', 'platform'),  # ✨ NEW
        Index('idx_transactions_purchase_token', 'purchase_token',  # ✨ NEW
              postgresql_where=Column('purchase_token').isnot(None)),
        Index('idx_transactions_google_order', 'google_order_id',  # ✨ NEW
              postgresql_where=Column('google_order_id').isnot(None)),
        Index('idx_transactions_revenue', 'type', 'status', 
              postgresql_where=(Column('type').in_(['payment', 'affiliate_conversion']) & (Column('status') == 'success'))),
    )

# =============================================================================
# TABLE 7: SYSTEM_LOGS (Daily Operations)
# =============================================================================
class SystemLog(Base):
    """
    Daily operational logs for monitoring and analytics
    """
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    log_date = Column(Date, unique=True, nullable=False, index=True)
    
    # Scraping summary
    scraping_summary = Column(JSONB, default={
        "sessions": [],  # [{"platform": "amazon", "products_scraped": 150, "errors": 2, "duration": 45}]
        "products_scraped": 0,
        "products_updated": 0,
        "errors": 0,
        "duration_seconds": 0
    })
    
    # Analytics
    analytics = Column(JSONB, default={
        "active_users": 0,
        "new_signups": 0,
        "searches_performed": 0,
        "affiliate_clicks": 0,
        "alerts_sent": 0,
        "revenue_inr": 0
    })
    
    # ML processing
    ml_processing = Column(JSONB, default={
        "products_analyzed": 0,
        "groq_requests": 0,
        "groq_quota_used": 0,
        "predictions_generated": 0
    })
    
    # Git archival
    archived_to_git = Column(Boolean, default=False)
    archive_path = Column(String(255))
    archive_size_mb = Column(Float)
    github_commit_hash = Column(String(40))
    github_committed_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_system_logs_date', 'log_date'),
    )


# =============================================================================
# TABLE 8: APP_CONFIG (Feature Flags)
# =============================================================================
class AppConfig(Base):
    """
    Application configuration key-value store
    Allows runtime config changes without deployment
    """
    __tablename__ = "app_config"
    
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), nullable=False)  # string, number, boolean, json
    
    description = Column(Text)
    category = Column(String(50))  # features, limits, maintenance, ai, etc.
    is_public = Column(Boolean, default=False)  # Can be exposed to frontend
    
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100))  # Admin email or system


# =============================================================================
# TABLE 9: STREAK_MILESTONES (Gamification Config)
# =============================================================================
class StreakMilestone(Base):
    """
    Gamification reward configuration
    Defines rewards for streak achievements
    """
    __tablename__ = "streak_milestones"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    streak_days = Column(Integer, unique=True, nullable=False, index=True)
    
    # Reward configuration
    reward_type = Column(String(30), nullable=False)  # searches, premium_days, watchlist_slots, badge
    reward_value = Column(Integer, nullable=False)
    
    # Badge display
    badge_emoji = Column(String(10))
    badge_name = Column(String(50))
    badge_color = Column(String(7))  # Hex color
    
    # Announcement
    announcement_text = Column(String(200))
    confetti_enabled = Column(Boolean, default=True)
    
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    __table_args__ = (
        Index('idx_streak_days', 'streak_days'),
    )
    # ─── Add this at the bottom of your existing models.py ───

class UserWatchlist(Base):
    __tablename__ = "user_watchlist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    target_price = Column(Float, nullable=True)
    notify = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="watchlist_items")
    product = relationship("Product")

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_user_product_watchlist"),
        Index("ix_watchlist_user", "user_id"),
    )

# =============================================================================
# TABLE 10: PROMOTIONS (Brand Campaigns)
# =============================================================================
class Promotion(Base):
    """
    Brand promotion campaigns - managed from admin dashboard
    Enables monetization through sponsored products, banners, push notifications
    """
    __tablename__ = "promotions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Campaign Details
    title = Column(String(200), nullable=False)
    description = Column(Text)
    campaign_type = Column(String(50), nullable=False, index=True)
    # Types: 'featured_product', 'banner', 'sponsored_search', 'push_notification', 'takeover'
    
    # Targeting Rules
    target_platforms = Column(JSONB, default=[])  # ["amazon", "flipkart"] or [] (all)
    target_categories = Column(JSONB, default=[])  # ["electronics"] or [] (all)
    target_user_plan = Column(JSONB, default=["free", "pro"])  # Don't show to premium users
    target_min_users = Column(Integer, default=0)  # Only show if >= X active users
    target_max_users = Column(Integer)  # Stop showing after X active users
    
    # Content
    image_url = Column(Text)
    cta_text = Column(String(100))  # "Shop Now", "Get 50% Off"
    destination_url = Column(Text, nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"))
    
    # Display Rules
    position = Column(Integer, default=1)  # 1 = top slot, 2 = second slot
    priority = Column(Integer, default=5)  # Higher = shown first
    max_impressions = Column(Integer)  # Stop after X views
    max_clicks = Column(Integer)  # Stop after X clicks
    max_budget_inr = Column(Float)  # Stop after spending X rupees
    
    # Scheduling
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    is_approved = Column(Boolean, default=True)  # For future brand self-service
    
    # Analytics (Updated in real-time)
    stats = Column(JSONB, default={
        "impressions": 0,
        "clicks": 0,
        "conversions": 0,  # Tracked via affiliate
        "revenue_earned": 0
    })
    
    # Pricing
    pricing_model = Column(String(20), nullable=False)  # 'cpm', 'cpc', 'flat'
    rate_inr = Column(Float, nullable=False)  # ₹10 per click, ₹1000 flat fee
    
    # Auto-adjust pricing based on traffic
    pricing_tiers = Column(JSONB, default=[])
    # [{"min_users": 500, "rate": 10}, {"min_users": 1000, "rate": 15}]
    
    # Brand Information
    brand_name = Column(String(100), index=True)
    brand_contact_email = Column(String(255))
    payment_status = Column(String(20), default="pending", index=True)
    # Statuses: 'pending', 'paid', 'refunded', 'cancelled'
    
    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(255))  # Admin email who created this
    
    __table_args__ = (
        Index('idx_promotions_active', 'is_active', 'start_date', 'end_date'),
        Index('idx_promotions_type', 'campaign_type'),
        Index('idx_promotions_brand', 'brand_name'),
        Index('idx_promotions_dates', 'start_date', 'end_date'),
        CheckConstraint("campaign_type IN ('featured_product', 'banner', 'sponsored_search', 'push_notification', 'takeover')", 
                       name='check_valid_campaign_type'),
        CheckConstraint("pricing_model IN ('cpm', 'cpc', 'flat')", 
                       name='check_valid_pricing_model'),
        CheckConstraint("payment_status IN ('pending', 'paid', 'refunded', 'cancelled')", 
                       name='check_valid_payment_status'),
    )
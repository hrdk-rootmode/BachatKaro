"""
Pydantic schemas for request/response validation
All models use Pydantic v2 with proper type hints
"""

from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from enum import Enum
from typing import Optional, List, Dict, Any, Union

# ==================== ENUMS ====================
ProductId = Union[str, int] 

class UserPlan(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"


class Platform(str, Enum):
    AMAZON = "amazon"
    FLIPKART = "flipkart"
    MEESHO = "meesho"
    MYNTRA = "myntra"


class NotificationType(str, Enum):
    PRICE_DROP = "price_drop"
    BACK_IN_STOCK = "back_in_stock"
    STREAK_REMINDER = "streak_reminder"
    SUBSCRIPTION_EXPIRY = "subscription_expiry"


# ==================== USER SCHEMAS ====================

class UserSignupRequest(BaseModel):
    """Request schema for user registration"""
    firebase_uid: str = Field(..., min_length=10, max_length=128)
    email: EmailStr
    display_name: Optional[str] = Field(None, max_length=100)
    hardware_id: str = Field(..., min_length=16, max_length=64, description="Unique device identifier")
    fcm_token: Optional[str] = Field(None, max_length=512)
    referral_code: Optional[str] = Field(None, min_length=6, max_length=10)
    
    @field_validator('email')
    @classmethod
    def validate_email_domain(cls, v: str) -> str:
        """Block disposable email domains"""
        disposable_domains = [
            'tempmail.com', 'guerrillamail.com', '10minutemail.com',
            'throwaway.email', 'mailinator.com', 'trashmail.com'
        ]
        domain = v.split('@')[1].lower()
        if domain in disposable_domains:
            raise ValueError(f"Disposable email domain '{domain}' not allowed")
        return v


class UserResponse(BaseModel):
    """Response schema for user data"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    firebase_uid: str
    email: str
    display_name: Optional[str]
    plan: UserPlan
    plan_expires_at: Optional[datetime]
    referral_code: str
    total_searches: int
    searches_today: int
    watchlist_count: int
    current_streak: int
    max_streak: int
    freeze_count: int
    is_blocked: bool
    created_at: datetime
    last_active_at: Optional[datetime]


class UserProfileUpdate(BaseModel):
    """Request schema for profile updates"""
    display_name: Optional[str] = Field(None, max_length=100)
    fcm_token: Optional[str] = Field(None, max_length=512)
    notification_preferences: Optional[Dict[str, bool]] = None


class UserUsageStats(BaseModel):
    """User usage statistics"""
    total_searches: int
    searches_today: int
    searches_remaining: int
    watchlist_count: int
    watchlist_limit: int
    current_streak: int
    freeze_count: int
    plan: UserPlan
    plan_expires_at: Optional[datetime]


# ==================== SEARCH SCHEMAS ====================

class SearchRequest(BaseModel):
    """Request schema for product search"""
    query: str = Field(..., min_length=2, max_length=200)
    platforms: Optional[List[Platform]] = Field(default=None, description="If None, search all platforms")
    min_price: Optional[Decimal] = Field(default=None, ge=0)
    max_price: Optional[Decimal] = Field(default=None, ge=0)
    sort_by: Optional[str] = Field(default="relevance", pattern="^(relevance|price_low|price_high|rating)$")
    page: int = Field(default=1, ge=1, le=10)
    
    @field_validator('max_price')
    @classmethod
    def validate_price_range(cls, v, info):
        """Ensure max_price > min_price"""
        if v and info.data.get('min_price') and v < info.data['min_price']:
            raise ValueError("max_price must be greater than min_price")
        return v


class SearchByURLRequest(BaseModel):
    """Request schema for URL-based search"""
    url: str = Field(..., max_length=2048, pattern="^https?://")


class ProductListingResponse(BaseModel):
    """Single product listing from a platform"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    platform: Platform
    platform_product_id: str
    url: str
    title: str
    current_price: Decimal
    original_price: Optional[Decimal]
    discount_percentage: Optional[int]
    rating: Optional[Decimal]
    reviews_count: Optional[int]
    image_url: Optional[str]
    in_stock: bool
    last_scraped_at: datetime


class ProductResponse(BaseModel):
    """Complete product information with all listings"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    fingerprint: str
    best_price: Decimal
    best_platform: Platform
    avg_price: Optional[Decimal]
    price_trend: Optional[str]  # "up", "down", "stable"
    ai_generated_essence: str
    ai_extracted_specs: Dict[str, Any]
    ai_tags: List[str]
    created_at: datetime
    listings: List[ProductListingResponse]


class SearchResponse(BaseModel):
    """Search results with metadata"""
    query: str
    total_results: int
    page: int
    products: List[ProductResponse]
    cache_hit: bool
    search_time_ms: int


class TrendingProductResponse(BaseModel):
    """Trending product summary"""
    model_config = ConfigDict(from_attributes=True)
    
    product_id: UUID
    title: str
    best_price: Decimal
    best_platform: Platform
    discount_percentage: Optional[int]
    image_url: Optional[str]
    search_count: int
    rank: int


# ==================== PRICE HISTORY SCHEMAS ====================

class PriceHistoryPoint(BaseModel):
    """Single price history data point"""
    date: datetime
    price: Decimal
    platform: Platform


class PriceHistoryResponse(BaseModel):
    """Price history for a product"""
    product_id: int
    platform: Platform
    history: List[PriceHistoryPoint]
    lowest_price: Decimal
    highest_price: Decimal
    average_price: Decimal
    price_drop_percentage: Optional[Decimal]

# ==================== WATCHLIST SCHEMAS (UPDATED) ====================

class WatchlistAddRequest(BaseModel):
    """Request to add product to watchlist"""
    product_id: str = Field(..., description="Product UUID")
    target_price: Optional[Decimal] = Field(default=None, ge=0)
    notify_any_drop: bool = Field(default=True)


class WatchlistUpdateRequest(BaseModel):
    """Request to update watchlist item"""
    target_price: Optional[Decimal] = Field(default=None, ge=0)
    notify_any_drop: Optional[bool] = None


class WatchlistItemResponse(BaseModel):
    """Watchlist item with denormalized product data"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # UUID
    product_id: str  # UUID
    target_price: Optional[Decimal]
    notify_any_drop: bool
    created_at: datetime
    
    # Denormalized product data
    product_title: str
    current_price: Decimal
    original_price: Optional[Decimal]
    platform: str
    image_url: Optional[str]
    product_url: str
    in_stock: bool
    price_change_percentage: Optional[Decimal]
    is_target_reached: bool = False


class WatchlistResponse(BaseModel):
    """User's complete watchlist"""
    items: List[WatchlistItemResponse]
    total_count: int
    limit: int
    limit_reached: bool


# ==================== STREAK SCHEMAS (UPDATED) ====================

class StreakCheckInResponse(BaseModel):
    """Response after daily check-in"""
    success: bool
    current_streak: int
    max_streak: int
    reward_unlocked: Optional[Dict[str, Any]] = None
    next_milestone: Optional[int]
    next_milestone_reward: Optional[str]
    message: str
    confetti: bool = False


class StreakMilestoneSchema(BaseModel):
    """Streak milestone reward"""
    days: int
    reward_type: str
    reward_value: int
    badge_emoji: Optional[str]
    badge_name: Optional[str]
    badge_color: Optional[str]
    unlocked: bool
    claimed: bool


class StreakStatusResponse(BaseModel):
    """User's streak status"""
    current_streak: int
    max_streak: int
    total_check_ins: int
    freeze_count: int
    freeze_limit: int
    last_check_in: Optional[datetime]
    can_check_in_today: bool
    streak_at_risk: bool  # True if user hasn't checked in today
    milestones: List[StreakMilestoneSchema]
    next_milestone: Optional[int]
    days_until_next_milestone: Optional[int]


class UseFreezeResponse(BaseModel):
    """Response after using streak freeze"""
    success: bool
    freeze_count_remaining: int
    streak_protected_until: datetime
    message: str


class UseFreezeRequest(BaseModel):
    """Request to use streak freeze"""
    freeze_days: int = Field(default=1, ge=1, le=3)


# ==================== SUBSCRIPTION SCHEMAS ====================

class SubscriptionPlanResponse(BaseModel):
    """Subscription plan details"""
    plan_id: str
    name: str
    price: Decimal
    duration_days: int
    features: Dict[str, Any]
    limits: Dict[str, int]  # searches_per_day, watchlist_limit, etc.
    popular: bool = False


class CreateOrderRequest(BaseModel):
    """Request to create Razorpay order"""
    plan_id: str = Field(..., pattern="^(basic|premium)$")


class CreateOrderResponse(BaseModel):
    """Razorpay order details"""
    order_id: str
    amount: int  # in paise
    currency: str
    razorpay_key: str


class VerifyPaymentRequest(BaseModel):
    """Request to verify Razorpay payment"""
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    """Payment verification result"""
    success: bool
    plan: UserPlan
    expires_at: datetime
    transaction_id: str
    message: str

class SubscriptionStatusResponse(BaseModel):
    """Current subscription status"""
    plan: UserPlan
    expires_at: Optional[datetime]
    days_remaining: Optional[int]
    auto_renew: bool
    next_billing_date: Optional[datetime]


# ==================== ADMIN SCHEMAS ====================

class AdminDashboardResponse(BaseModel):
    """Admin dashboard overview"""
    total_users: int
    active_users_today: int
    total_revenue_mtd: Decimal
    total_products_tracked: int
    total_searches_today: int
    affiliate_clicks_today: int
    conversion_rate: Decimal
    churn_rate: Decimal


class AdminUserSegment(BaseModel):
    """User segmentation data"""
    plan: UserPlan
    count: int
    percentage: Decimal
    avg_ltv: Decimal
    avg_searches_per_day: Decimal


class AdminRevenueBreakdown(BaseModel):
    """Daily revenue breakdown"""
    date: datetime
    subscription_revenue: Decimal
    affiliate_revenue: Decimal
    total_revenue: Decimal
    new_subscriptions: int
    churned_users: int


class AdminScraperStatus(BaseModel):
    """Scraper health metrics"""
    platform: Platform
    success_rate: Decimal
    failed_products_count: int
    avg_scrape_time_ms: int
    last_successful_scrape: datetime
    selector_health: str  # "healthy", "degraded", "failing"


class BlockUserRequest(BaseModel):
    """Request to block user"""
    user_id: int = Field(..., gt=0)
    reason: str = Field(..., min_length=10, max_length=500)
    permanent: bool = Field(default=False)


# ==================== NOTIFICATION SCHEMAS ====================

class NotificationResponse(BaseModel):
    """User notification"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    type: NotificationType
    title: str
    message: str
    data: Dict[str, Any]
    is_read: bool
    created_at: datetime


# ==================== HEALTH CHECK SCHEMA ====================

class HealthCheckResponse(BaseModel):
    """System health status"""
    status: str  # "healthy", "degraded", "unhealthy"
    database: str
    redis: str
    timestamp: datetime
    version: str

# ==================== ADMIN: USER MANAGEMENT SCHEMAS ====================

class AdminUserSummary(BaseModel):
    """User summary for admin list view"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    email: str
    display_name: Optional[str]
    plan: UserPlan
    plan_expires_at: Optional[datetime]
    
    # Activity
    created_at: datetime
    last_active: Optional[datetime]
    total_searches: int
    watchlist_count: int
    current_streak: int
    
    # Anti-abuse flags
    hardware_id: Optional[str]
    accounts_on_device: int = 0
    unique_ips_count: int = 0
    is_blocked: bool
    
    # Revenue
    lifetime_value_inr: float = 0
    total_spent_inr: float = 0


class AdminUserDetail(BaseModel):
    """Detailed user profile for admin"""
    model_config = ConfigDict(from_attributes=True)
    
    user: UserResponse
    
    activity: Dict[str, Any] = {
        "total_searches": 0,
        "searches_today": 0,
        "affiliate_clicks": 0,
        "affiliate_conversions": 0,
        "ai_chat_queries": 0
    }
    
    ip_history: List[str] = []
    device_info: Dict[str, Any] = {}
    
    transactions: List[Dict[str, Any]] = []
    watchlist: List[Dict[str, Any]] = []
    
    flags: List[str] = []  # ["suspicious_ips", "max_devices", "high_refunds"]


class BanUserRequest(BaseModel):
    """Request to ban user"""
    reason: str = Field(..., min_length=10, max_length=500)
    permanent: bool = Field(default=False)


class BulkUserBonus(BaseModel):
    """Grant bonuses to multiple users"""
    target: str = Field(..., pattern="^(all_free_users|all_pro_users|all_premium_users|specific_users)$")
    user_ids: Optional[List[str]] = None  # Required if target = specific_users
    reason: str = Field(..., max_length=200)
    bonuses: Dict[str, int] = {
        "daily_searches": 0,
        "watchlist_slots": 0,
        "streak_freeze": 0,
        "premium_days": 0
    }
    duration_days: int = Field(default=7, ge=1, le=365)


# ==================== ADMIN: REVENUE ANALYTICS SCHEMAS ====================

class RevenueOverview(BaseModel):
    """Admin revenue dashboard overview"""
    total_revenue_inr: float
    
    today: Dict[str, float] = {
        "subscriptions": 0,
        "affiliate_conversions": 0,
        "promotions": 0,
        "total": 0
    }
    
    this_month: Dict[str, Any] = {
        "total": 0,
        "mrr": 0,  # Monthly Recurring Revenue
        "affiliate": 0,
        "promotions": 0,
        "growth_vs_last_month": 0
    }
    
    breakdown: Dict[str, Any] = {
        "free_users": 0,
        "pro_users": 0,
        "premium_users": 0,
        "churn_rate": 0,
        "conversion_rate": 0
    }
    
    projections: Dict[str, Any] = {
        "next_month_mrr": 0,
        "breakeven_users": 0,
        "months_to_loan_payoff": 0  # Based on ₹8L target
    }


class TransactionListItem(BaseModel):
    """Transaction summary for admin list"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    user_email: str
    type: str
    amount: float
    currency: str
    status: str
    created_at: datetime
    
    # Context
    plan_name: Optional[str]
    product_title: Optional[str]
    platform_name: Optional[str]


class PlanRevenueBreakdown(BaseModel):
    """Revenue breakdown by subscription plan"""
    plan: UserPlan
    active_users: int
    monthly_revenue: float
    churn_count: int
    new_subscriptions: int
    avg_lifetime_value: float


class AffiliatePerformer(BaseModel):
    """Top affiliate product/platform performance"""
    product_id: Optional[str]
    product_title: str
    platform: str
    clicks: int
    conversions: int
    conversion_rate: float
    revenue_earned: float


# ==================== ADMIN: PROMOTION MANAGEMENT SCHEMAS ====================

class PromotionCreate(BaseModel):
    """Request to create brand promotion"""
    title: str = Field(..., min_length=5, max_length=200)
    description: Optional[str] = None
    campaign_type: str = Field(..., pattern="^(featured_product|banner|sponsored_search|push_notification|takeover)$")
    
    # Targeting
    target_platforms: List[str] = []  # Empty = all platforms
    target_categories: List[str] = []  # Empty = all categories
    target_user_plan: List[UserPlan] = [UserPlan.FREE, UserPlan.BASIC]
    target_min_users: int = Field(default=0, ge=0)
    target_max_users: Optional[int] = None
    
    # Content
    image_url: Optional[str] = None
    cta_text: str = Field(default="Learn More", max_length=100)
    destination_url: str = Field(..., pattern="^https?://")
    product_id: Optional[str] = None
    
    # Display
    position: int = Field(default=1, ge=1, le=10)
    priority: int = Field(default=5, ge=1, le=10)
    max_impressions: Optional[int] = None
    max_clicks: Optional[int] = None
    max_budget_inr: Optional[float] = None
    
    # Schedule
    start_date: datetime
    end_date: datetime
    
    # Pricing
    pricing_model: str = Field(..., pattern="^(cpm|cpc|flat)$")
    rate_inr: float = Field(..., gt=0)
    pricing_tiers: List[Dict[str, Any]] = []
    
    # Brand
    brand_name: str = Field(..., min_length=2, max_length=100)
    brand_contact_email: EmailStr


class PromotionUpdate(BaseModel):
    """Update existing promotion"""
    title: Optional[str] = None
    is_active: Optional[bool] = None
    end_date: Optional[datetime] = None
    max_clicks: Optional[int] = None
    max_budget_inr: Optional[float] = None
    payment_status: Optional[str] = None


class PromotionResponse(BaseModel):
    """Promotion details response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    title: str
    campaign_type: str
    brand_name: str
    
    is_active: bool
    start_date: datetime
    end_date: datetime
    
    stats: Dict[str, Any]
    pricing_model: str
    rate_inr: float
    
    status: str  # 'scheduled', 'active', 'paused', 'completed', 'budget_exhausted'
    created_at: datetime


class PromotionAnalytics(BaseModel):
    """Detailed promotion performance"""
    promotion: PromotionResponse
    
    performance: Dict[str, Any] = {
        "impressions": 0,
        "clicks": 0,
        "conversions": 0,
        "ctr": 0,  # Click-through rate
        "revenue_earned": 0
    }
    
    remaining: Dict[str, Any] = {
        "impressions": 0,
        "clicks": 0,
        "budget": 0,
        "days": 0
    }
    
    daily_stats: List[Dict[str, Any]] = []  # Last 30 days breakdown


class BrandRevenueReport(BaseModel):
    """Invoice-ready report for brand"""
    brand_name: str
    period_start: datetime
    period_end: datetime
    
    campaigns: List[Dict[str, Any]]
    
    total_impressions: int
    total_clicks: int
    total_conversions: int
    
    amount_due_inr: float
    payment_status: str
    
    invoice_url: Optional[str] = None


class PushCampaignCreate(BaseModel):
    """Create push notification campaign"""
    title: str = Field(..., min_length=5, max_length=100)
    message: str = Field(..., min_length=10, max_length=200)
    destination_url: str
    
    target_user_plan: List[UserPlan] = [UserPlan.FREE]
    schedule_time: Optional[datetime] = None  # If None, send immediately
    
    pricing_model: str = "cpm"
    rate_inr: float = Field(default=100, gt=0)  # ₹100 per 1000 users
    
    brand_name: str
    brand_contact_email: EmailStr


# ==================== ADMIN: SYSTEM MONITORING SCHEMAS ====================

class SystemHealthResponse(BaseModel):
    """System health status"""
    database: Dict[str, Any] = {
        "status": "healthy",
        "connections": 0,
        "size_mb": 0,
        "query_time_avg_ms": 0
    }
    
    redis: Dict[str, Any] = {
        "status": "healthy",
        "memory_used_mb": 0,
        "cache_hit_rate": 0,
        "keys": 0
    }
    
    scrapers: Dict[str, Any] = {}  # Platform-wise health
    
    groq_ai: Dict[str, Any] = {
        "quota_used_today": 0,
        "quota_remaining": 0,
        "avg_response_time_ms": 0
    }
    
    disk: Dict[str, Any] = {
        "total_gb": 0,
        "used_gb": 0,
        "free_gb": 0,
        "percent_used": 0
    }


class SystemStatsResponse(BaseModel):
    """System-wide statistics"""
    traffic: Dict[str, int] = {
        "requests_today": 0,
        "searches_today": 0,
        "unique_users_today": 0,
        "avg_response_time_ms": 0
    }
    
    engagement: Dict[str, Any] = {
        "daily_active_users": 0,
        "weekly_active_users": 0,
        "monthly_active_users": 0,
        "streak_participants": 0,
        "avg_session_duration_min": 0
    }
    
    products: Dict[str, Any] = {
        "total_tracked": 0,
        "scraped_today": 0,
        "trending_today": []
    }
    
    conversions: Dict[str, Any] = {
        "affiliate_clicks_today": 0,
        "affiliate_conversions_today": 0,
        "conversion_rate": 0,
        "revenue_today": 0
    }


class ForceScrapeRequest(BaseModel):
    """Manually trigger scraper"""
    platform: str = Field(..., pattern="^(amazon|flipkart|meesho|myntra|all)$")
    async_mode: bool = Field(default=False)
    category: Optional[str] = None  # Scrape specific category only


class ForceScrapeResponse(BaseModel):
    """Scraper execution result"""
    job_id: Optional[str] = None  # If async
    status: str  # 'completed', 'in_progress', 'failed', 'timeout'
    
    products_scraped: Optional[int] = 0
    products_updated: Optional[int] = 0
    errors: Optional[int] = 0
    duration_seconds: Optional[int] = 0
    
    error_details: Optional[List[str]] = None


class AppConfigUpdateRequest(BaseModel):
    """Update app configuration"""
    key: str = Field(..., max_length=100)
    value: str
    value_type: str = Field(..., pattern="^(string|number|boolean|json)$")
    description: Optional[str] = None
    category: Optional[str] = None


class MaintenanceModeRequest(BaseModel):
    """Enable/disable maintenance mode"""
    enabled: bool
    message: Optional[str] = Field(default="We're upgrading! Back soon.", max_length=200)
    estimated_duration_minutes: Optional[int] = None

# ==================== PAYMENT PLATFORM ENUM (NEW) ====================

class PaymentPlatform(str, Enum):
    """Payment platform types"""
    WEB = "web"          # Razorpay (web browser)
    ANDROID = "android"  # Google Play Billing
    IOS = "ios"          # Apple IAP (future)


# ==================== GOOGLE PLAY BILLING SCHEMAS (NEW) ====================

class GooglePlayPurchaseRequest(BaseModel):
    """Request to verify Google Play purchase"""
    purchase_token: str = Field(..., min_length=10, description="Purchase token from Google Play")
    product_id: str = Field(..., description="SKU/Product ID from Play Console")
    package_name: Optional[str] = Field(default=None, description="App package name")
    
    @field_validator('product_id')
    @classmethod
    def validate_product_id(cls, v: str) -> str:
        """Validate product ID format"""
        valid_prefixes = ['dealhunt_', 'com.dealhunt.']
        if not any(v.startswith(prefix) for prefix in valid_prefixes):
            # Allow any format in mock mode
            pass
        return v


class GooglePlayPurchaseResponse(BaseModel):
    """Response after Google Play purchase verification"""
    success: bool
    plan: UserPlan
    expires_at: datetime
    transaction_id: str
    order_id: Optional[str] = None  # Google Play order ID
    acknowledged: bool = False
    message: str
    mock_mode: bool = False


class GooglePlayAcknowledgeRequest(BaseModel):
    """Request to acknowledge Google Play purchase"""
    purchase_token: str = Field(..., min_length=10)
    product_id: str


class GooglePlayAcknowledgeResponse(BaseModel):
    """Response after acknowledging purchase"""
    success: bool
    message: str


class GooglePlaySubscriptionStatus(BaseModel):
    """Google Play subscription status from API"""
    kind: str = "androidpublisher#subscriptionPurchase"
    start_time_millis: Optional[int] = None
    expiry_time_millis: Optional[int] = None
    auto_renewing: bool = False
    price_currency_code: str = "INR"
    price_amount_micros: Optional[int] = None
    country_code: str = "IN"
    payment_state: Optional[int] = None  # 0=pending, 1=received, 2=free_trial, 3=deferred
    cancel_reason: Optional[int] = None  # 0=user, 1=system, 2=replaced, 3=developer
    user_cancellation_time_millis: Optional[int] = None
    order_id: Optional[str] = None
    acknowledgement_state: int = 0  # 0=not_ack, 1=ack


class GooglePlayNotification(BaseModel):
    """
    Google Play Real-time Developer Notification (RTDN)
    Sent via Cloud Pub/Sub webhook
    """
    version: str = "1.0"
    package_name: str
    event_time_millis: int
    subscription_notification: Optional[Dict[str, Any]] = None
    one_time_product_notification: Optional[Dict[str, Any]] = None
    test_notification: Optional[Dict[str, Any]] = None


class GooglePlayWebhookPayload(BaseModel):
    """Webhook payload from Google Cloud Pub/Sub"""
    message: Dict[str, Any]
    subscription: str


# ==================== UPDATED CREATE ORDER REQUEST ====================

class CreateOrderRequestV2(BaseModel):
    """
    Request to create payment order (supports both platforms)
    
    For web: Creates Razorpay order
    For android: Returns product SKU for Google Play
    """
    plan_id: str = Field(..., pattern="^(pro|premium)$")
    platform: PaymentPlatform = Field(default=PaymentPlatform.WEB)


class CreateOrderResponseV2(BaseModel):
    """
    Response for create order (platform-aware)
    """
    platform: PaymentPlatform
    plan_id: str
    
    # Razorpay fields (web only)
    order_id: Optional[str] = None
    razorpay_key: Optional[str] = None
    
    # Google Play fields (android only)
    product_sku: Optional[str] = None
    
    # Common fields
    amount: int  # in paise
    currency: str = "INR"
    
    # Status
    mock_mode: bool = False


# ==================== PAYMENT STATUS SCHEMAS ====================

class PaymentMethodStatus(BaseModel):
    """Status of a payment method"""
    enabled: bool
    configured: bool
    mock_mode: bool
    message: str


class PaymentMethodsResponse(BaseModel):
    """Available payment methods"""
    razorpay: PaymentMethodStatus
    google_play: PaymentMethodStatus
    apple_iap: PaymentMethodStatus  # Future
    
    recommended: PaymentPlatform  # Based on request headers


# ==================== UPDATED SUBSCRIPTION STATUS ====================

class SubscriptionStatusResponseV2(BaseModel):
    """Current subscription status (with platform info)"""
    plan: UserPlan
    expires_at: Optional[datetime]
    days_remaining: Optional[int]
    auto_renew: bool
    next_billing_date: Optional[datetime]
    
    # ✨ NEW: Platform info
    subscription_platform: Optional[PaymentPlatform] = None
    google_order_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None
    
    # Status flags
    is_active: bool = True
    is_trial: bool = False
    is_grace_period: bool = False  # Payment failed but still active
    will_renew: bool = False
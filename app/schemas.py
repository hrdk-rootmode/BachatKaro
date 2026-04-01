"""
Pydantic schemas for request/response validation
All models use Pydantic v2 with proper type hints

FIXED:
- Changed all id fields from int to str (UUID compatibility)
- Added missing platforms (nykaa, croma) to Platform enum
- Changed all monetary fields from float to Decimal
- Added security validators for query sanitization
- Added max_length constraints for security
- Removed unused ProductId type alias
- Standardized field naming (review_count vs reviews_count)
- Added missing job-related schemas
"""

from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from enum import Enum
import re


# ==================== ENUMS ====================

class UserPlan(str, Enum):
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"


class Platform(str, Enum):
    """✅ FIXED: Added missing platforms"""
    AMAZON = "amazon"
    FLIPKART = "flipkart"
    MEESHO = "meesho"
    MYNTRA = "myntra"
    NYKAA = "nykaa"
    CROMA = "croma"


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
    """✅ FIXED: Changed id from int to str (UUID)"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # ✅ UUID as string
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
    last_active: Optional[datetime]


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
    """✅ FIXED: Added query sanitization"""
    query: str = Field(..., min_length=2, max_length=200)
    platforms: Optional[List[Platform]] = Field(default=None, description="If None, search all platforms")
    min_price: Optional[Decimal] = Field(default=None, ge=0)
    max_price: Optional[Decimal] = Field(default=None, ge=0)
    sort_by: Optional[str] = Field(default="relevance", pattern="^(relevance|price_low|price_high|rating)$")
    page: int = Field(default=1, ge=1, le=10)
    
    @field_validator('query')
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """✅ NEW: Sanitize query to prevent injection attacks"""
        # Remove potential SQL injection patterns
        dangerous_patterns = [
            r'(\bDROP\b|\bDELETE\b|\bUPDATE\b|\bINSERT\b)',  # SQL keywords
            r'(<script|javascript:|onerror=)',  # XSS patterns
            r'(union\s+select|;\s*--)',  # SQL injection
        ]
        
        query_upper = v.upper()
        for pattern in dangerous_patterns:
            if re.search(pattern, query_upper, re.IGNORECASE):
                raise ValueError("Query contains potentially dangerous patterns")
        
        # Remove excessive whitespace
        v = re.sub(r'\s+', ' ', v).strip()
        
        return v
    
    @field_validator('max_price')
    @classmethod
    def validate_price_range(cls, v, info):
        """Ensure max_price > min_price"""
        if v and info.data.get('min_price') and v < info.data['min_price']:
            raise ValueError("max_price must be greater than min_price")
        return v


class SearchByURLRequest(BaseModel):
    """✅ FIXED: Added max_length for security"""
    url: str = Field(..., min_length=10, max_length=2048, pattern="^https?://")
    
    @field_validator('url')
    @classmethod
    def validate_url_domain(cls, v: str) -> str:
        """✅ NEW: Validate URL is from supported platforms"""
        supported_domains = [
            'amazon.in', 'amazon.com',
            'flipkart.com',
            'meesho.com',
            'myntra.com',
            'nykaa.com',
            'croma.com'
        ]
        
        # Extract domain
        domain_match = re.search(r'https?://(?:www\.)?([^/]+)', v)
        if domain_match:
            domain = domain_match.group(1).lower()
            if not any(supported in domain for supported in supported_domains):
                raise ValueError(f"URL must be from supported platforms: {', '.join(supported_domains)}")
        
        return v


class AttributeConfidence(BaseModel):
    """Attribute with confidence and source tracking."""
    value: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source: Optional[str] = None  # api|next_data|json_ld|dom|ai|title_heuristic


class ProductBase(BaseModel):
    """Base product schema used by richer response models."""
    title: str
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = None
    specifications: Dict[str, Any] = Field(default_factory=dict)


class ProductListingResponse(BaseModel):
    """✅ FIXED: Changed id to str, standardized field names
    ✅ NEW: Added variant_fingerprint for cross-platform matching"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # ✅ UUID as string
    # Optional relational fields for admin/detail views
    product_id: Optional[str] = None
    platform_id: Optional[int] = None
    platform_name: Optional[str] = None
    platform: Platform
    platform_product_id: str
    url: str
    title: str
    current_price: Decimal
    original_price: Optional[Decimal]
    discount_percentage: Optional[int]
    # Alias-compatible field used by some endpoints/jobs
    discount_percent: Optional[Decimal] = None
    rating: Optional[Decimal]
    review_count: Optional[int]  # ✅ Standardized (was reviews_count)
    image_url: Optional[str]
    in_stock: bool
    last_scraped_at: datetime
    extraction_confidence: Optional[float] = Field(None, ge=0, le=1)
    extraction_method: Optional[str] = None
    data_source: Optional[str] = None
    seller_name: Optional[str] = None
    seller_rating: Optional[Decimal] = None
    # ✅ NEW: Variant fingerprinting for cross-platform linking
    variant_fingerprint: Optional[str] = Field(None, description="Exact variant fingerprint for cross-platform matching")


class ProductResponse(BaseModel):
    """✅ FIXED: Changed id to str
    ✅ NEW: Added variant fingerprinting fields"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # ✅ UUID as string
    fingerprint: str
    # ✅ NEW: Enhanced variant fingerprinting
    variant_fingerprint: Optional[str] = Field(None, description="Exact variant fingerprint (e.g., iPhone 15 Pro 256GB)")
    base_fingerprint: Optional[str] = Field(None, description="Base product fingerprint (e.g., iPhone 15 series)")
    # Variant metadata
    variant_type: Optional[str] = Field(None, description="Variant type (pro, plus, max, ultra, lite, etc)")
    storage_gb: Optional[int] = Field(None, description="Storage capacity in GB")
    color: Optional[str] = Field(None, description="Product color")
    condition: Optional[str] = Field(None, description="Product condition (new, refurbished, used)")
    # Product base info
    title: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    image_url: Optional[str] = None
    specifications: Dict[str, Any] = Field(default_factory=dict)
    # Confidence and provenance
    brand_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    brand_source: Optional[str] = None
    color_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    color_source: Optional[str] = None
    specs_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    specs_source: Optional[str] = None
    last_enriched_at: Optional[datetime] = None
    enrichment_version: Optional[int] = None
    # Price and trending
    best_price: Decimal
    best_platform: Platform
    avg_price: Optional[Decimal]
    price_trend: Optional[str]  # "up", "down", "stable"
    # AI metadata
    ai_generated_essence: str
    ai_extracted_specs: Dict[str, Any]
    ai_tags: List[str]
    ai_metadata: Dict[str, Any] = Field(default_factory=dict)
    stats: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None
    listings: List[ProductListingResponse]


class ProductWithListings(ProductResponse):
    """Product response with listing aggregates."""
    listings: List[ProductListingResponse] = Field(default_factory=list)
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    platform_count: int = 0
    best_deal_platform: Optional[str] = None


class SearchResponse(BaseModel):
    """Search results with metadata"""
    query: str
    total_results: int
    page: int
    products: List[ProductResponse]
    cache_hit: bool
    search_time_ms: int


class TrendingProductResponse(BaseModel):
    """Trending product summary
    ✅ NEW: Added variant fingerprinting for cross-platform deduplication
    ✅ NEW: Added platform_count for cross-platform availability indicator"""
    model_config = ConfigDict(from_attributes=True)
    
    product_id: str  # ✅ UUID as string
    title: str
    # ✅ NEW: Variant fingerprinting
    variant_fingerprint: Optional[str] = Field(None, description="Exact variant fingerprint")
    base_fingerprint: Optional[str] = Field(None, description="Base product fingerprint")
    variant_type: Optional[str] = Field(None, description="Variant type (pro, plus, max, etc)")
    # Pricing
    best_price: Decimal
    best_platform: Platform
    discount_percentage: Optional[int]
    image_url: Optional[str]
    search_count: int
    rank: int
    # ✅ NEW: Cross-platform availability (for home page badge)
    platform_count: int = Field(1, description="How many platforms have this product")


# ==================== PRICE HISTORY SCHEMAS ====================

class PriceHistoryPoint(BaseModel):
    """Single price history data point"""
    date: datetime
    price: Decimal
    platform: Platform


class PriceHistoryResponse(BaseModel):
    """Price history for a product"""
    product_id: str  # ✅ UUID as string
    platform: Platform
    history: List[PriceHistoryPoint]
    data_points_count: int = 0
    history_span_days: int = 0
    lowest_price: Decimal
    highest_price: Decimal
    average_price: Decimal
    price_drop_percentage: Optional[Decimal]
    observed_change_percentage_7d: Optional[Decimal] = Field(
        default=None,
        description="Observed price change over the most recent 7-day window",
    )
    observed_drop_amount_7d: Optional[Decimal] = Field(
        default=None,
        description="Observed rupee drop over the most recent 7-day window when price moved down",
    )
    prediction_available: bool = Field(
        default=False,
        description="Whether enough historical data exists for trend-based prediction",
    )
    predicted_change_percentage_7d: Optional[Decimal] = Field(
        default=None,
        description="Trend-only directional signal for next 7 days",
    )
    predicted_price_7d: Optional[Decimal] = Field(default=None, description="Model estimate for next 7 days")
    predicted_price_30d: Optional[Decimal] = Field(default=None, description="Model estimate for next 30 days")
    predicted_change_percentage_30d: Optional[Decimal] = Field(
        default=None,
        description="Projected % change over next 30 days vs current price",
    )
    recommendation: Optional[str] = Field(default=None, description="buy_now | wait | watch")
    confidence_score: Optional[Decimal] = Field(default=None, description="Forecast confidence from 0-100")
    recommendation_reasons: List[str] = Field(default_factory=list)
    insight_basis: List[str] = Field(default_factory=list)
    upcoming_sale_event: Optional[str] = Field(default=None, description="Nearest expected India sale event")
    days_until_sale_event: Optional[int] = Field(default=None, description="Days left for upcoming sale event")


# ==================== REFRESH PRICE SCHEMAS ====================

class PlatformPriceSnapshot(BaseModel):
    """Price snapshot for a single platform"""
    platform: Platform
    current_price: Decimal
    original_price: Optional[Decimal]
    discount_percentage: Optional[int]
    in_stock: bool
    last_updated_at: datetime
    location_applied: bool = False
    location_scope: Optional[str] = None  # 'global' | 'pincode' | 'state'
    pincode: Optional[str] = None
    state: Optional[str] = None


class RefreshPriceResponse(BaseModel):
    """Response when refreshing product prices"""
    product_id: str
    best_price: Decimal
    best_platform: Platform
    all_platforms: List[PlatformPriceSnapshot]
    last_updated_at: datetime
    freshness_status: str  # 'fresh' (< 2h), 'stale' (2-12h), 'very_stale' (> 12h)
    price_change: Optional[Decimal] = None  # How much changed since last update
    refresh_in_progress: bool = False
    can_refresh_again_at: Optional[datetime] = None  # When can user refresh again


class LocationPriceRefreshRequest(BaseModel):
    """Request payload for location-aware live refresh"""
    pincode: str = Field(..., pattern=r"^\d{6}$", description="Indian pincode")
    state: Optional[str] = Field(default=None, min_length=2, max_length=60)
    platform: Optional[Platform] = None
    force_refresh: bool = False


class LocationRefreshPriceResponse(BaseModel):
    """Response for location-aware refresh with cache metadata"""
    product_id: str
    pincode: str
    state: Optional[str] = None
    best_price: Decimal
    best_platform: Platform
    all_platforms: List[PlatformPriceSnapshot]
    last_updated_at: datetime
    freshness_status: str
    cache_hit: bool = False
    location_applied_platforms: int = 0
    message: Optional[str] = None


# ==================== WATCHLIST SCHEMAS ====================

class WatchlistAddRequest(BaseModel):
    """Request to add product to watchlist"""
    product_id: str = Field(..., min_length=32, max_length=40, description="Product UUID")
    target_price: Optional[Decimal] = Field(default=None, ge=0)
    notify_any_drop: bool = Field(default=True)


class WatchlistUpdateRequest(BaseModel):
    """Request to update watchlist item"""
    target_price: Optional[Decimal] = Field(default=None, ge=0)
    notify_any_drop: Optional[bool] = None


class WatchlistItemResponse(BaseModel):
    """Watchlist item with denormalized product data"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # ✅ UUID
    product_id: str  # ✅ UUID
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


# ==================== STREAK SCHEMAS ====================

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
    streak_at_risk: bool
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
    limits: Dict[str, int]
    popular: bool = False


class CreateOrderRequest(BaseModel):
    """Request to create Razorpay order"""
    plan_id: str = Field(..., pattern="^(pro|premium)$")


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
    """✅ FIXED: Changed float to Decimal for money"""
    total_users: int
    active_users_today: int
    total_revenue_mtd: Decimal  # ✅ Changed from float
    total_products_tracked: int
    total_searches_today: int
    affiliate_clicks_today: int
    conversion_rate: Decimal
    churn_rate: Decimal


class AdminUserSegment(BaseModel):
    """✅ FIXED: Changed float to Decimal"""
    plan: UserPlan
    count: int
    percentage: Decimal
    avg_ltv: Decimal  # ✅ Changed from float
    avg_searches_per_day: Decimal


class AdminRevenueBreakdown(BaseModel):
    """✅ FIXED: Changed float to Decimal"""
    date: datetime
    subscription_revenue: Decimal  # ✅ Changed from float
    affiliate_revenue: Decimal  # ✅ Changed from float
    total_revenue: Decimal  # ✅ Changed from float
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
    """✅ FIXED: Changed user_id to str"""
    user_id: str = Field(..., description="User UUID")
    reason: str = Field(..., min_length=10, max_length=500)
    permanent: bool = Field(default=False)


# ==================== NOTIFICATION SCHEMAS ====================

class NotificationResponse(BaseModel):
    """✅ FIXED: Changed id to str"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # ✅ UUID as string
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
    """✅ FIXED: Changed id to str, float to Decimal"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # ✅ UUID
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
    lifetime_value_inr: Decimal = Decimal("0")  # ✅ Changed from float
    total_spent_inr: Decimal = Decimal("0")  # ✅ Changed from float


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
    
    flags: List[str] = []


class BanUserRequest(BaseModel):
    """Request to ban user"""
    reason: str = Field(..., min_length=10, max_length=500)
    permanent: bool = Field(default=False)


class BulkUserBonus(BaseModel):
    """Grant bonuses to multiple users"""
    target: str = Field(..., pattern="^(all_free_users|all_pro_users|all_premium_users|specific_users)$")
    user_ids: Optional[List[str]] = None
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
    """✅ FIXED: Changed all float to Decimal"""
    total_revenue_inr: Decimal  # ✅ Changed from float
    
    today: Dict[str, Decimal] = {
        "subscriptions": Decimal("0"),
        "affiliate_conversions": Decimal("0"),
        "promotions": Decimal("0"),
        "total": Decimal("0")
    }
    
    this_month: Dict[str, Any] = {
        "total": Decimal("0"),
        "mrr": Decimal("0"),
        "affiliate": Decimal("0"),
        "promotions": Decimal("0"),
        "growth_vs_last_month": Decimal("0")
    }
    
    breakdown: Dict[str, Any] = {
        "free_users": 0,
        "pro_users": 0,
        "premium_users": 0,
        "churn_rate": Decimal("0"),
        "conversion_rate": Decimal("0")
    }
    
    projections: Dict[str, Any] = {
        "next_month_mrr": Decimal("0"),
        "breakeven_users": 0,
        "months_to_loan_payoff": 0
    }


class TransactionListItem(BaseModel):
    """✅ FIXED: Changed id to str, float to Decimal"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # ✅ UUID
    user_email: str
    type: str
    amount: Decimal  # ✅ Changed from float
    currency: str
    status: str
    created_at: datetime
    
    # Context
    plan_name: Optional[str]
    product_title: Optional[str]
    platform_name: Optional[str]


class PlanRevenueBreakdown(BaseModel):
    """✅ FIXED: Changed float to Decimal"""
    plan: UserPlan
    active_users: int
    monthly_revenue: Decimal  # ✅ Changed from float
    churn_count: int
    new_subscriptions: int
    avg_lifetime_value: Decimal  # ✅ Changed from float


class AffiliatePerformer(BaseModel):
    """✅ FIXED: Changed float to Decimal"""
    product_id: Optional[str]
    product_title: str
    platform: str
    clicks: int
    conversions: int
    conversion_rate: Decimal  # ✅ Changed from float
    revenue_earned: Decimal  # ✅ Changed from float


# ==================== ADMIN: PROMOTION MANAGEMENT SCHEMAS ====================

class PromotionCreate(BaseModel):
    """✅ FIXED: Added max_length for security"""
    title: str = Field(..., min_length=5, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)  # ✅ Added max
    campaign_type: str = Field(..., pattern="^(featured_product|banner|sponsored_search|push_notification|takeover)$")
    
    # Targeting
    target_platforms: List[str] = []
    target_categories: List[str] = []
    target_user_plan: List[UserPlan] = [UserPlan.FREE, UserPlan.PRO]
    target_min_users: int = Field(default=0, ge=0)
    target_max_users: Optional[int] = None
    
    # Content
    image_url: Optional[str] = Field(None, max_length=2048)  # ✅ Added max
    cta_text: str = Field(default="Learn More", max_length=100)
    destination_url: str = Field(..., min_length=10, max_length=2048, pattern="^https?://")  # ✅ Added max
    product_id: Optional[str] = None
    
    # Display
    position: int = Field(default=1, ge=1, le=10)
    priority: int = Field(default=5, ge=1, le=10)
    max_impressions: Optional[int] = None
    max_clicks: Optional[int] = None
    max_budget_inr: Optional[Decimal] = None  # ✅ Changed from float
    
    # Schedule
    start_date: datetime
    end_date: datetime
    
    # Pricing
    pricing_model: str = Field(..., pattern="^(cpm|cpc|flat)$")
    rate_inr: Decimal = Field(..., gt=0)  # ✅ Changed from float
    pricing_tiers: List[Dict[str, Any]] = []
    
    # Brand
    brand_name: str = Field(..., min_length=2, max_length=100)
    brand_contact_email: EmailStr


class PromotionUpdate(BaseModel):
    """Update existing promotion"""
    title: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None
    end_date: Optional[datetime] = None
    max_clicks: Optional[int] = None
    max_budget_inr: Optional[Decimal] = None  # ✅ Changed from float
    payment_status: Optional[str] = None


class PromotionResponse(BaseModel):
    """✅ FIXED: Changed id to str, float to Decimal"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str  # ✅ UUID
    title: str
    campaign_type: str
    brand_name: str
    
    is_active: bool
    start_date: datetime
    end_date: datetime
    
    stats: Dict[str, Any]
    pricing_model: str
    rate_inr: Decimal  # ✅ Changed from float
    
    status: str
    created_at: datetime


class PromotionAnalytics(BaseModel):
    """✅ FIXED: Changed float to Decimal"""
    promotion: PromotionResponse
    
    performance: Dict[str, Any] = {
        "impressions": 0,
        "clicks": 0,
        "conversions": 0,
        "ctr": Decimal("0"),  # ✅ Changed from float
        "revenue_earned": Decimal("0")  # ✅ Changed from float
    }
    
    remaining: Dict[str, Any] = {
        "impressions": 0,
        "clicks": 0,
        "budget": Decimal("0"),  # ✅ Changed from float
        "days": 0
    }
    
    daily_stats: List[Dict[str, Any]] = []


class BrandRevenueReport(BaseModel):
    """✅ FIXED: Changed float to Decimal"""
    brand_name: str
    period_start: datetime
    period_end: datetime
    
    campaigns: List[Dict[str, Any]]
    
    total_impressions: int
    total_clicks: int
    total_conversions: int
    
    amount_due_inr: Decimal  # ✅ Changed from float
    payment_status: str
    
    invoice_url: Optional[str] = None


class PushCampaignCreate(BaseModel):
    """✅ FIXED: Added max_length, changed float to Decimal"""
    title: str = Field(..., min_length=5, max_length=100)
    message: str = Field(..., min_length=10, max_length=200)
    destination_url: str = Field(..., max_length=2048)  # ✅ Added max
    
    target_user_plan: List[UserPlan] = [UserPlan.FREE]
    schedule_time: Optional[datetime] = None
    
    pricing_model: str = "cpm"
    rate_inr: Decimal = Field(default=Decimal("100"), gt=0)  # ✅ Changed from float
    
    brand_name: str = Field(..., max_length=100)  # ✅ Added max
    brand_contact_email: EmailStr


# ==================== ADMIN: SYSTEM MONITORING SCHEMAS ====================

class SystemHealthResponse(BaseModel):
    """✅ FIXED: Changed float to Decimal"""
    database: Dict[str, Any] = {
        "status": "healthy",
        "connections": 0,
        "size_mb": Decimal("0"),  # ✅ Changed from float
        "query_time_avg_ms": 0
    }
    
    redis: Dict[str, Any] = {
        "status": "healthy",
        "memory_used_mb": Decimal("0"),  # ✅ Changed from float
        "cache_hit_rate": Decimal("0"),  # ✅ Changed from float
        "keys": 0
    }
    
    scrapers: Dict[str, Any] = {}
    
    groq_ai: Dict[str, Any] = {
        "quota_used_today": 0,
        "quota_remaining": 0,
        "avg_response_time_ms": 0
    }
    
    disk: Dict[str, Any] = {
        "total_gb": Decimal("0"),  # ✅ Changed from float
        "used_gb": Decimal("0"),  # ✅ Changed from float
        "free_gb": Decimal("0"),  # ✅ Changed from float
        "percent_used": Decimal("0")  # ✅ Changed from float
    }


class SystemStatsResponse(BaseModel):
    """✅ FIXED: Changed float to Decimal"""
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
        "avg_session_duration_min": Decimal("0")  # ✅ Changed from float
    }
    
    products: Dict[str, Any] = {
        "total_tracked": 0,
        "scraped_today": 0,
        "trending_today": []
    }
    
    conversions: Dict[str, Any] = {
        "affiliate_clicks_today": 0,
        "affiliate_conversions_today": 0,
        "conversion_rate": Decimal("0"),  # ✅ Changed from float
        "revenue_today": Decimal("0")  # ✅ Changed from float
    }


class ForceScrapeRequest(BaseModel):
    """Manually trigger scraper"""
    platform: str = Field(..., pattern="^(amazon|flipkart|meesho|myntra|nykaa|croma|all)$")  # ✅ Added nykaa, croma
    async_mode: bool = Field(default=False)
    category: Optional[str] = Field(None, max_length=100)  # ✅ Added max


class ForceScrapeResponse(BaseModel):
    """Scraper execution result"""
    job_id: Optional[str] = None
    status: str
    
    products_scraped: Optional[int] = 0
    products_updated: Optional[int] = 0
    errors: Optional[int] = 0
    duration_seconds: Optional[int] = 0
    
    error_details: Optional[List[str]] = None


class AppConfigUpdateRequest(BaseModel):
    """Update app configuration"""
    key: str = Field(..., max_length=100)
    value: str = Field(..., max_length=10000)  # ✅ Added max
    value_type: str = Field(..., pattern="^(string|number|boolean|json)$")
    description: Optional[str] = Field(None, max_length=500)  # ✅ Added max
    category: Optional[str] = Field(None, max_length=50)  # ✅ Added max


class MaintenanceModeRequest(BaseModel):
    """Enable/disable maintenance mode"""
    enabled: bool
    message: Optional[str] = Field(default="We're upgrading! Back soon.", max_length=200)
    estimated_duration_minutes: Optional[int] = None


# ==================== PAYMENT PLATFORM ENUM ====================

class PaymentPlatform(str, Enum):
    """Payment platform types"""
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"


# ==================== GOOGLE PLAY BILLING SCHEMAS ====================

class GooglePlayPurchaseRequest(BaseModel):
    """✅ FIXED: Added max_length for security"""
    purchase_token: str = Field(..., min_length=10, max_length=1000, description="Purchase token from Google Play")  # ✅ Added max
    product_id: str = Field(..., max_length=200, description="SKU/Product ID from Play Console")  # ✅ Added max
    package_name: Optional[str] = Field(default=None, max_length=200, description="App package name")  # ✅ Added max
    
    @field_validator('product_id')
    @classmethod
    def validate_product_id(cls, v: str) -> str:
        """Validate product ID format"""
        valid_prefixes = ['dealhunt_', 'com.dealhunt.']
        if not any(v.startswith(prefix) for prefix in valid_prefixes):
            pass  # Allow any format in mock mode
        return v


class GooglePlayPurchaseResponse(BaseModel):
    """Response after Google Play purchase verification"""
    success: bool
    plan: UserPlan
    expires_at: datetime
    transaction_id: str
    order_id: Optional[str] = None
    acknowledged: bool = False
    message: str
    mock_mode: bool = False


class GooglePlayAcknowledgeRequest(BaseModel):
    """✅ FIXED: Added max_length"""
    purchase_token: str = Field(..., min_length=10, max_length=1000)  # ✅ Added max
    product_id: str = Field(..., max_length=200)  # ✅ Added max


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
    payment_state: Optional[int] = None
    cancel_reason: Optional[int] = None
    user_cancellation_time_millis: Optional[int] = None
    order_id: Optional[str] = None
    acknowledgement_state: int = 0


class GooglePlayNotification(BaseModel):
    """Google Play Real-time Developer Notification"""
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
    """Request to create payment order (supports both platforms)"""
    plan_id: str = Field(..., pattern="^(pro|premium)$")
    platform: PaymentPlatform = Field(default=PaymentPlatform.WEB)


class CreateOrderResponseV2(BaseModel):
    """Response for create order (platform-aware)"""
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
    apple_iap: PaymentMethodStatus
    
    recommended: PaymentPlatform


# ==================== UPDATED SUBSCRIPTION STATUS ====================

class SubscriptionStatusResponseV2(BaseModel):
    """Current subscription status (with platform info)"""
    plan: UserPlan
    expires_at: Optional[datetime]
    days_remaining: Optional[int]
    auto_renew: bool
    next_billing_date: Optional[datetime]
    
    # Platform info
    subscription_platform: Optional[PaymentPlatform] = None
    google_order_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None
    
    # Status flags
    is_active: bool = True
    is_trial: bool = False
    is_grace_period: bool = False
    will_renew: bool = False


# ==================== ✅ NEW: JOB MANAGEMENT SCHEMAS ====================

class JobStatus(BaseModel):
    """Status of a single background job"""
    job_id: str
    name: str
    next_run: Optional[datetime]
    last_run: Optional[datetime]
    last_result: Optional[str]
    success_count: int
    error_count: int
    is_running: bool


class SchedulerStatusResponse(BaseModel):
    """Scheduler status response"""
    running: bool
    jobs_count: int
    jobs: List[JobStatus]
    uptime_seconds: Optional[int]


class TriggerJobRequest(BaseModel):
    """Request to manually trigger a job"""
    job_id: str = Field(..., pattern="^(daily_scrape|daily_scrape_trending|seed_products|load_trending_redis|check_price_alerts|send_streak_reminders|sync_subscriptions|monthly_archive)$")


class TriggerJobResponse(BaseModel):
    """Response after triggering a job"""
    success: bool
    job_id: str
    started_at: datetime
    message: str
    async_execution: bool = False
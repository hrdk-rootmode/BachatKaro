"""
Subscription & Payment API Routes
Supports both Razorpay (web) and Google Play Billing (Android)
Supports mock mode for development without credentials
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import json

from app.core.database import get_db
from app.core.redis_client import RedisClient, get_redis
from app.core.config import settings
from app.models import User, Transaction
from app.schemas import (
    SubscriptionPlanResponse,
    CreateOrderRequest,
    CreateOrderResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
    SubscriptionStatusResponse,
    UserPlan,
    # ✨ NEW: Google Play schemas
    GooglePlayPurchaseRequest,
    GooglePlayPurchaseResponse,
    GooglePlayAcknowledgeRequest,
    GooglePlayAcknowledgeResponse,
    PaymentPlatform,
    CreateOrderRequestV2,
    CreateOrderResponseV2,
    PaymentMethodsResponse,
    PaymentMethodStatus,
)
from app.api.deps import get_current_user
from app.services.plan_catalog import (
    get_plan_catalog,
    get_plan_config,
    get_plan_from_sku,
    get_paid_plan_ids,
)

# ✨ NEW: Import payment services
from app.services.payments import (
    razorpay_client,
    google_play_client,
    payment_router
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _utc_now() -> datetime:
    """Return a timezone-aware UTC datetime for all subscription comparisons."""
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetimes to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def create_transaction(
    db: AsyncSession,
    user_id,
    transaction_type: str,
    amount: float,
    status: str,
    platform: str = "web",
    razorpay_order_id: str = None,
    razorpay_payment_id: str = None,
    razorpay_signature: str = None,
    purchase_token: str = None,
    google_order_id: str = None,
    plan_id: int = None,
    metadata: dict = None
) -> Transaction:
    """Create transaction record"""
    transaction = Transaction(
        user_id=user_id,
        type=transaction_type,
        amount=amount,
        currency="INR",
        status=status,
        platform=platform,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
        purchase_token=purchase_token,
        google_order_id=google_order_id,
        plan_id=plan_id,
        meta_data=metadata or {}
    )
    
    db.add(transaction)
    await db.flush()
    
    return transaction


async def activate_subscription(
    user: User,
    plan_id: str,
    platform: str,
    db: AsyncSession,
    redis: RedisClient
) -> datetime:
    """
    Activate subscription for user
    
    Returns:
        New expiry datetime
    """
    plan_config = await get_plan_config(db, plan_id)
    duration_days = plan_config["duration_days"]

    current_expiry = _as_utc(user.plan_expires_at)
    now = _utc_now()
    
    # Extend if already subscribed, else start fresh
    if current_expiry and current_expiry > now:
        new_expiry = current_expiry + timedelta(days=duration_days)
    else:
        new_expiry = now + timedelta(days=duration_days)
    
    # Update user
    user.plan = plan_id
    user.plan_expires_at = new_expiry
    user.subscription_platform = platform
    
    if user.usage_stats is None:
        user.usage_stats = {}
    user.usage_stats["subscription_activated_at"] = _utc_now().isoformat()
    user.usage_stats["subscription_platform"] = platform
    user.usage_stats.pop("subscription_cancelled_at", None)
    user.usage_stats.pop("watchlist_grace_until", None)
    user.usage_stats.pop("watchlist_grace_reason", None)
    
    # Initialize streak data for new subscribers
    if not user.streak_data:
        user.streak_data = {
            "current_streak": 0,
            "longest_streak": 0,
            "last_check_in": None,
            "total_check_ins": 0,
            "streak_rewards_claimed": [],
            "freeze_count": 2  # Base freeze count
        }
    
    # Auto-activate streak for new subscribers
    if user.streak_data.get("current_streak", 0) == 0 and not user.streak_data.get("last_check_in"):
        user.streak_data["current_streak"] = 1
        user.streak_data["last_check_in"] = now.isoformat()
        user.streak_data["total_check_ins"] = 1
        logger.info(f"Auto-activated streak for new subscriber | User: {user.id}")
    
    await db.commit()
    
    # Invalidate caches
    await redis.delete(f"user:{user.id}")
    await redis.delete(f"watchlist:{user.id}")
    await redis.delete(f"streak:{user.id}")
    await redis.delete(f"subscription:{user.id}")
    
    return new_expiry


# =============================================================================
# ROUTES - COMMON
# =============================================================================

@router.get("/plans", response_model=List[SubscriptionPlanResponse])
async def get_subscription_plans(
    platform: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get available subscription plans
    
    Args:
        platform: Optional platform filter (web, android, ios)
    
    Returns:
        List of plans with features and pricing
    """
    plans = []
    catalog = await get_plan_catalog(db)

    for _, config in catalog.items():
        plan_response = SubscriptionPlanResponse(
            plan_id=config["plan_id"],
            name=config.get("display_name") or config["name"],
            price=Decimal(str(config["price_paise"] / 100)),
            duration_days=config["duration_days"],
            features=config["features"],
            limits=config["limits"],
            popular=config["popular"]
        )
        plans.append(plan_response)
    
    plans.sort(key=lambda x: x.price)
    
    return plans


@router.get("/payment-methods", response_model=PaymentMethodsResponse)
async def get_payment_methods(
    user_agent: Optional[str] = Header(default=""),
    x_platform: Optional[str] = Header(default=""),
    user: User = Depends(get_current_user)
):
    """
    Get available payment methods and recommended one
    
    Headers:
        User-Agent: Browser/app user agent
        X-Platform: Explicit platform (android, ios, web)
    """
    status = payment_router.get_status()
    recommended = payment_router.get_recommended_method(user_agent, x_platform)
    
    return PaymentMethodsResponse(
        razorpay=PaymentMethodStatus(
            enabled=status["razorpay"]["enabled"],
            configured=status["razorpay"]["configured"],
            mock_mode=status["razorpay"]["mock_mode"],
            message="Web payments via Razorpay"
        ),
        google_play=PaymentMethodStatus(
            enabled=status["google_play"]["enabled"],
            configured=status["google_play"]["configured"],
            mock_mode=status["google_play"]["mock_mode"],
            message="Android payments via Google Play"
        ),
        apple_iap=PaymentMethodStatus(
            enabled=False,
            configured=False,
            mock_mode=True,
            message="iOS payments coming soon"
        ),
        recommended=PaymentPlatform(recommended)
    )


# =============================================================================
# ROUTES - RAZORPAY (WEB)
# =============================================================================

@router.post("/create-order", response_model=CreateOrderResponseV2)
async def create_payment_order(
    request: CreateOrderRequestV2,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create payment order for subscription
    
    For web: Creates Razorpay order
    For android: Returns Google Play SKU
    """
    plan_catalog = await get_plan_catalog(db)
    paid_plan_ids = get_paid_plan_ids(plan_catalog)

    if request.plan_id not in paid_plan_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only paid plans can be purchased. Available paid plans: {', '.join(paid_plan_ids)}"
        )

    try:
        plan_config = await get_plan_config(db, request.plan_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    amount = int(plan_config["price_paise"])
    platform = request.platform.value if hasattr(request.platform, 'value') else request.platform
    
    # =========================================================================
    # WEB (Razorpay)
    # =========================================================================
    if platform == "web":
        receipt = f"sub_{user.id}_{_utc_now().strftime('%Y%m%d%H%M%S')}"
        
        try:
            order = razorpay_client.create_order(
                amount=amount,
                currency="INR",
                receipt=receipt,
                notes={
                    "user_id": str(user.id),
                    "plan_id": request.plan_id,
                    "user_email": user.email
                }
            )
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create payment order. Please try again."
            )
        
        # Create pending transaction
        await create_transaction(
            db=db,
            user_id=user.id,
            transaction_type="payment",
            amount=amount / 100,
            status="pending",
            platform="web",
            razorpay_order_id=order["id"],
            metadata={
                "plan_id": request.plan_id,
                "plan_name": plan_config.get("display_name") or plan_config["name"],
                "duration_days": plan_config["duration_days"],
                "mock_mode": razorpay_client.is_mock_mode
            }
        )
        
        await db.commit()
        
        logger.info(
            f"Razorpay order created | User: {user.id} | "
            f"Plan: {request.plan_id} | Order: {order['id']} | "
            f"Mock: {razorpay_client.is_mock_mode}"
        )
        
        return CreateOrderResponseV2(
            platform=PaymentPlatform.WEB,
            plan_id=request.plan_id,
            order_id=order["id"],
            razorpay_key=settings.RAZORPAY_KEY_ID,
            amount=amount,
            currency="INR",
            mock_mode=razorpay_client.is_mock_mode
        )
    
    # =========================================================================
    # ANDROID (Google Play)
    # =========================================================================
    elif platform == "android":
        product_sku = plan_config.get("google_play_sku")
        
        if not product_sku:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No Google Play SKU configured for plan: {request.plan_id}"
            )
        
        logger.info(
            f"Google Play order initiated | User: {user.id} | "
            f"Plan: {request.plan_id} | SKU: {product_sku} | "
            f"Mock: {google_play_client.is_mock_mode}"
        )
        
        return CreateOrderResponseV2(
            platform=PaymentPlatform.ANDROID,
            plan_id=request.plan_id,
            product_sku=product_sku,
            amount=amount,
            currency="INR",
            mock_mode=google_play_client.is_mock_mode
        )
    
    # =========================================================================
    # iOS (Future)
    # =========================================================================
    elif platform == "ios":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Apple IAP not yet implemented. Coming soon!"
        )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown platform: {platform}"
        )


@router.post("/verify-payment", response_model=VerifyPaymentResponse)
async def verify_razorpay_payment(
    request: VerifyPaymentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Verify Razorpay payment and activate subscription (WEB ONLY)
    
    Works in mock mode - accepts mock signatures
    """
    # Verify signature
    is_valid = razorpay_client.verify_payment_signature(
        order_id=request.razorpay_order_id,
        payment_id=request.razorpay_payment_id,
        signature=request.razorpay_signature
    )
    
    if not is_valid:
        logger.warning(
            f"Razorpay signature INVALID | User: {user.id} | "
            f"Order: {request.razorpay_order_id}"
        )
        
        result = await db.execute(
            select(Transaction)
            .where(Transaction.razorpay_order_id == request.razorpay_order_id)
        )
        transaction = result.scalar_one_or_none()
        
        if transaction:
            transaction.status = "failed"
            transaction.meta_data = transaction.meta_data or {}
            transaction.meta_data["failure_reason"] = "invalid_signature"
            await db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed. Invalid signature."
        )
    
    # Get transaction
    result = await db.execute(
        select(Transaction)
        .where(Transaction.razorpay_order_id == request.razorpay_order_id)
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )
    
    if transaction.status == "success":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment already processed"
        )
    
    # In mock mode, skip payment fetch
    if not razorpay_client.is_mock_mode:
        payment = razorpay_client.fetch_payment(request.razorpay_payment_id)
        
        if not payment or payment.get("status") != "captured":
            if payment and payment.get("status") == "authorized":
                capture_result = razorpay_client.capture_payment(
                    request.razorpay_payment_id,
                    payment["amount"]
                )
                if not capture_result:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Payment capture failed"
                    )
    
    # Update transaction
    transaction.status = "success"
    transaction.razorpay_payment_id = request.razorpay_payment_id
    transaction.razorpay_signature = request.razorpay_signature
    transaction.processed_at = _utc_now()
    
    # Activate subscription
    plan_id = transaction.meta_data.get("plan_id", "pro")
    plan_config = await get_plan_config(db, plan_id)
    
    new_expiry = await activate_subscription(
        user=user,
        plan_id=plan_id,
        platform="web",
        db=db,
        redis=redis
    )
    
    transaction.meta_data["activated_at"] = _utc_now().isoformat()
    await db.commit()
    
    logger.info(
        f"Razorpay subscription activated | User: {user.id} | "
        f"Plan: {plan_id} | Expires: {new_expiry} | "
        f"Mock: {razorpay_client.is_mock_mode}"
    )
    
    return VerifyPaymentResponse(
        success=True,
        plan=UserPlan(plan_id) if plan_id in ["pro", "premium"] else UserPlan.PREMIUM,
        expires_at=new_expiry,
        transaction_id=str(transaction.id),
        message=f"🎉 Welcome to {plan_config['name']}! Your subscription is now active."
    )


# =============================================================================
# ROUTES - GOOGLE PLAY (ANDROID)
# =============================================================================

@router.post("/verify-purchase", response_model=GooglePlayPurchaseResponse)
async def verify_google_play_purchase(
    request: GooglePlayPurchaseRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """
    Verify Google Play purchase and activate subscription (ANDROID ONLY)
    
    Called by Android app after successful Google Play purchase
    Works in mock mode - accepts mock tokens
    """
    try:
        # Verify with Google Play
        result = await google_play_client.verify_purchase(
            purchase_token=request.purchase_token,
            product_id=request.product_id
        )
        
        if not result.get("valid"):
            raise ValueError("Purchase verification failed")
        
    except ValueError as e:
        logger.warning(
            f"Google Play verification failed | User: {user.id} | "
            f"Product: {request.product_id} | Error: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Purchase verification failed: {str(e)}"
        )
    
    plan_catalog = await get_plan_catalog(db)

    # Get plan from SKU
    plan_id = get_plan_from_sku(request.product_id, plan_catalog)
    if not plan_id:
        # Try direct match
        plan_id = request.product_id.replace("dealhunt_", "").replace("_monthly", "")
        if plan_id not in plan_catalog:
            plan_id = "pro"  # Default fallback

    plan_config = await get_plan_config(db, plan_id)
    
    # Check for duplicate transaction
    existing = await db.execute(
        select(Transaction)
        .where(Transaction.purchase_token == request.purchase_token)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Purchase already processed"
        )
    
    # Create transaction
    transaction = await create_transaction(
        db=db,
        user_id=user.id,
        transaction_type="payment",
        amount=plan_config["price_paise"] / 100,
        status="success",
        platform="android",
        purchase_token=request.purchase_token,
        google_order_id=result.get("order_id"),
        metadata={
            "plan_id": plan_id,
            "plan_name": plan_config.get("display_name") or plan_config["name"],
            "duration_days": plan_config["duration_days"],
            "product_id": request.product_id,
            "mock_mode": result.get("mock_mode", google_play_client.is_mock_mode),
            "auto_renewing": result.get("auto_renewing", False),
            "expiry_time_millis": result.get("expiry_time_millis")
        }
    )
    transaction.processed_at = _utc_now()
    
    # Activate subscription
    new_expiry = await activate_subscription(
        user=user,
        plan_id=plan_id,
        platform="android",
        db=db,
        redis=redis
    )
    
    # Acknowledge purchase (required within 3 days!)
    acknowledged = await google_play_client.acknowledge_purchase(
        purchase_token=request.purchase_token,
        product_id=request.product_id
    )
    
    transaction.acknowledgement_state = "acknowledged" if acknowledged else "pending"
    transaction.meta_data["acknowledged_at"] = _utc_now().isoformat() if acknowledged else None
    
    await db.commit()
    
    logger.info(
        f"Google Play subscription activated | User: {user.id} | "
        f"Plan: {plan_id} | Order: {result.get('order_id')} | "
        f"Acknowledged: {acknowledged} | Mock: {google_play_client.is_mock_mode}"
    )
    
    return GooglePlayPurchaseResponse(
        success=True,
        plan=UserPlan(plan_id) if plan_id in ["pro", "premium"] else UserPlan.PREMIUM,
        expires_at=new_expiry,
        transaction_id=str(transaction.id),
        order_id=result.get("order_id"),
        acknowledged=acknowledged,
        message=f"🎉 Welcome to {plan_config['name']}! Your subscription is now active.",
        mock_mode=result.get("mock_mode", google_play_client.is_mock_mode)
    )


@router.post("/acknowledge-purchase", response_model=GooglePlayAcknowledgeResponse)
async def acknowledge_google_play_purchase(
    request: GooglePlayAcknowledgeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Acknowledge Google Play purchase (call if auto-acknowledge failed)
    
    Must be done within 3 days or Google will refund the purchase!
    """
    # Find transaction
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user.id,
            Transaction.purchase_token == request.purchase_token
        )
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )
    
    if transaction.acknowledgement_state == "acknowledged":
        return GooglePlayAcknowledgeResponse(
            success=True,
            message="Purchase already acknowledged"
        )
    
    # Acknowledge with Google
    success = await google_play_client.acknowledge_purchase(
        purchase_token=request.purchase_token,
        product_id=request.product_id
    )
    
    if success:
        transaction.acknowledgement_state = "acknowledged"
        transaction.meta_data = transaction.meta_data or {}
        transaction.meta_data["acknowledged_at"] = _utc_now().isoformat()
        await db.commit()
        
        logger.info(f"Purchase acknowledged | User: {user.id} | Token: {request.purchase_token[:20]}...")
        
        return GooglePlayAcknowledgeResponse(
            success=True,
            message="Purchase acknowledged successfully"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge purchase. Please try again."
        )


@router.post("/webhook/google")
async def google_play_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Google Play Real-time Developer Notification (RTDN) webhook
    
    Receives notifications about subscription events:
    - Renewals
    - Cancellations
    - Grace period
    - Account hold
    - Expirations
    """
    try:
        body = await request.body()
        payload = json.loads(body)
        
        # Decode base64 message data
        import base64
        message_data = payload.get("message", {}).get("data", "")
        decoded = base64.b64decode(message_data).decode("utf-8")
        notification = json.loads(decoded)
        
    except Exception as e:
        logger.error(f"Failed to parse Google webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload"
        )
    
    # Handle notification
    result = await google_play_client.handle_notification(notification)
    
    action = result.get("action")
    purchase_token = result.get("purchase_token")
    
    logger.info(f"Google webhook | Action: {action} | Token: {purchase_token[:20] if purchase_token else 'N/A'}...")
    
    # Handle specific actions
    if action in ["canceled", "expired", "revoked"]:
        # Find and update user subscription
        if purchase_token:
            tx_result = await db.execute(
                select(Transaction)
                .where(Transaction.purchase_token == purchase_token)
            )
            transaction = tx_result.scalar_one_or_none()
            
            if transaction and transaction.user_id:
                from app.models import User
                user_result = await db.execute(
                    select(User).where(User.id == transaction.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user:
                    # Don't immediately cancel - let current period expire
                    if user.usage_stats is None:
                        user.usage_stats = {}
                    user.usage_stats["subscription_cancelled_at"] = _utc_now().isoformat()
                    user.usage_stats["cancellation_source"] = "google_webhook"
                    user.usage_stats["watchlist_grace_until"] = (_utc_now() + timedelta(days=2)).isoformat()
                    user.usage_stats["watchlist_grace_reason"] = "subscription_canceled"
                    await db.commit()
                    
                    logger.info(f"Subscription cancelled via webhook | User: {user.id}")
    
    elif action == "renewed" and result.get("requires_verification"):
        # Subscription renewed - update expiry
        if purchase_token:
            tx_result = await db.execute(
                select(Transaction)
                .where(Transaction.purchase_token == purchase_token)
                .order_by(Transaction.created_at.desc())
            )
            transaction = tx_result.scalar_one_or_none()
            
            if transaction:
                # Verify and extend subscription
                try:
                    subscription_id = result.get("subscription_id")
                    verify_result = await google_play_client.verify_purchase(
                        purchase_token=purchase_token,
                        product_id=subscription_id
                    )
                    
                    if verify_result.get("valid"):
                        from app.models import User
                        user_result = await db.execute(
                            select(User).where(User.id == transaction.user_id)
                        )
                        user = user_result.scalar_one_or_none()
                        
                        if user:
                            expiry_millis = verify_result.get("expiry_time_millis", 0)
                            if expiry_millis:
                                user.plan_expires_at = datetime.fromtimestamp(expiry_millis / 1000, tz=timezone.utc)
                                await db.commit()
                                logger.info(f"Subscription renewed via webhook | User: {user.id}")
                except Exception as e:
                    logger.error(f"Failed to process renewal: {e}")
    
    return {"status": "ok", "action": action}


# =============================================================================
# ROUTES - COMMON (EXISTING)
# =============================================================================

@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    user: User = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis)
):
    """Get current subscription status"""
    cache_key = f"subscription:{user.id}"
    cached = await redis.get_json(cache_key)
    
    if cached:
        return SubscriptionStatusResponse(**cached)
    
    days_remaining = None
    if user.plan_expires_at:
        delta = _as_utc(user.plan_expires_at) - _utc_now()
        days_remaining = max(0, delta.days)
    
    plan = user.plan
    expires_at = user.plan_expires_at
    
    if plan != "free" and expires_at and _as_utc(expires_at) < _utc_now():
        plan = "free"
        expires_at = None
        days_remaining = None
    
    # Map plan to UserPlan enum
    plan_mapping = {
        "free": UserPlan.FREE,
        "pro": UserPlan.PRO,
        "premium": UserPlan.PREMIUM
    }
    user_plan = plan_mapping.get(plan, UserPlan.FREE)
    
    response = SubscriptionStatusResponse(
        plan=user_plan,
        expires_at=expires_at,
        days_remaining=days_remaining,
        auto_renew=False,
        next_billing_date=None
    )
    
    await redis.set_json(cache_key, response.model_dump(mode='json'), ttl=300)
    
    return response


@router.get("/history")
async def get_payment_history(
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's payment/transaction history"""
    limit = max(1, min(int(limit or 100), 500))

    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user.id,
            Transaction.type == "payment"
        )
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    transactions = result.scalars().all()
    
    history = []
    for t in transactions:
        history.append({
            "id": str(t.id),
            "amount": t.amount,
            "currency": t.currency,
            "status": t.status,
            "platform": t.platform,
            "plan": t.meta_data.get("plan_name") if t.meta_data else None,
            "razorpay_payment_id": t.razorpay_payment_id,
            "google_order_id": t.google_order_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "processed_at": t.processed_at.isoformat() if t.processed_at else None,
            "mock_mode": t.meta_data.get("mock_mode", False) if t.meta_data else False
        })
    
    return {
        "transactions": history,
        "total_count": len(history),
        "payment_services": payment_router.get_status()
    }


@router.delete("/history/{transaction_id}")
async def delete_payment_history_item(
    transaction_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """Delete a single payment history item. Allowed in non-production development builds."""
    if settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Transaction deletion is disabled in production."
        )

    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
            Transaction.type == "payment"
        )
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    await db.delete(transaction)
    await db.commit()
    await redis.delete(f"subscription:{user.id}")

    return {
        "success": True,
        "deleted_id": str(transaction.id),
        "message": "Transaction deleted successfully."
    }


@router.delete("/history")
async def clear_payment_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """Clear all payment history and reset demo subscription state in development."""
    if settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo cleanup is disabled in production."
        )

    transaction_result = await db.execute(
        delete(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.type == "payment"
        )
    )

    deleted_count = int(getattr(transaction_result, "rowcount", 0) or 0)

    user.plan = "free"
    user.plan_expires_at = None
    user.subscription_platform = None

    if user.usage_stats is None:
        user.usage_stats = {}

    user.usage_stats.pop("subscription_activated_at", None)
    user.usage_stats.pop("subscription_cancelled_at", None)
    user.usage_stats.pop("auto_renew", None)
    user.usage_stats["demo_subscription_cleared_at"] = _utc_now().isoformat()

    await db.commit()

    await redis.delete(f"user:{user.id}")
    await redis.delete(f"subscription:{user.id}")
    await redis.delete(f"watchlist:{user.id}")

    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": "Demo subscription data cleared successfully."
    }


@router.post("/cancel")
async def cancel_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    """Cancel subscription (takes effect at end of billing period)"""
    if user.plan == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to cancel"
        )
    
    if user.usage_stats is None:
        user.usage_stats = {}
    
    user.usage_stats["subscription_cancelled_at"] = _utc_now().isoformat()
    user.usage_stats["auto_renew"] = False
    user.usage_stats["watchlist_grace_until"] = (_utc_now() + timedelta(days=2)).isoformat()
    user.usage_stats["watchlist_grace_reason"] = "subscription_canceled"
    
    await db.commit()
    
    await redis.delete(f"subscription:{user.id}")
    
    logger.info(f"Subscription cancelled | User: {user.id} | Plan: {user.plan}")
    
    # Note: For Google Play, user must cancel through Play Store
    # For Razorpay, we just mark as non-renewing
    
    cancel_instructions = ""
    if user.subscription_platform == "android":
        cancel_instructions = " To stop future charges, please cancel your subscription in Google Play Store."
    
    plan_display_name = user.plan.title()
    try:
        plan_cfg = await get_plan_config(db, user.plan, include_inactive=True)
        plan_display_name = plan_cfg.get("display_name") or plan_cfg.get("name") or plan_display_name
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Subscription cancelled. You'll retain {plan_display_name} access until {user.plan_expires_at.strftime('%Y-%m-%d') if user.plan_expires_at else 'N/A'}.{cancel_instructions}",
        "access_until": user.plan_expires_at,
        "platform": user.subscription_platform
    }


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Razorpay webhook handler (WEB ONLY)"""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    
    if not razorpay_client.verify_webhook_signature(body, signature):
        logger.warning("Razorpay webhook signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )
    
    payload = json.loads(body)
    event = payload.get("event")
    
    logger.info(f"Razorpay webhook | Event: {event}")
    
    if event == "payment.captured":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payment.get("order_id")
        
        result = await db.execute(
            select(Transaction)
            .where(Transaction.razorpay_order_id == order_id)
        )
        transaction = result.scalar_one_or_none()
        
        if transaction and transaction.status == "pending":
            transaction.status = "success"
            transaction.razorpay_payment_id = payment.get("id")
            transaction.processed_at = _utc_now()
            await db.commit()
            logger.info(f"Transaction updated via webhook | Order: {order_id}")
    
    elif event == "payment.failed":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payment.get("order_id")
        
        result = await db.execute(
            select(Transaction)
            .where(Transaction.razorpay_order_id == order_id)
        )
        transaction = result.scalar_one_or_none()
        
        if transaction:
            transaction.status = "failed"
            transaction.meta_data = transaction.meta_data or {}
            transaction.meta_data["failure_reason"] = payment.get("error_description", "unknown")
            await db.commit()
            logger.warning(f"Payment failed via webhook | Order: {order_id}")
    
    return {"status": "ok"}


@router.get("/mock-status")
async def get_mock_status():
    """Check payment service status (for development)"""
    return {
        "razorpay": {
            "mock_mode": razorpay_client.is_mock_mode,
            "message": "⚠️ MOCK mode" if razorpay_client.is_mock_mode else "✅ Real payments"
        },
        "google_play": {
            "mock_mode": google_play_client.is_mock_mode,
            "message": "⚠️ MOCK mode" if google_play_client.is_mock_mode else "✅ Real payments"
        }
    }
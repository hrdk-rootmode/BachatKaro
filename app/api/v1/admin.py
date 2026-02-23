"""
Admin Dashboard API Endpoints
Complete control center for managing DealHunt

Features:
- User Management (list, view, ban, delete, bonus)
- Revenue Analytics (overview, transactions, plans, affiliates)
- Promotion Management (create, update, delete, analytics)
- System Monitoring (health, stats, logs, config)
- Live Config Management (no-code changes)

Security:
- Firebase custom claims (admin: true)
- Email whitelist verification
- All actions logged for audit
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional, List
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.core.config import settings
from app.api.deps import get_current_admin_user, verify_firebase_token
from app.models import (
    User, Transaction, SubscriptionPlan, Product, ProductListing,
    Platform, SystemLog, AppConfig, Promotion, UserWatchlist, StreakMilestone
)
from app.schemas import (
    # User Management
    AdminUserSummary, AdminUserDetail, BanUserRequest, BulkUserBonus,
    # Revenue
    RevenueOverview, TransactionListItem, PlanRevenueBreakdown, AffiliatePerformer,
    # Promotions
    PromotionCreate, PromotionUpdate, PromotionResponse, PromotionAnalytics,
    BrandRevenueReport, PushCampaignCreate,
    # System
    SystemHealthResponse, SystemStatsResponse, ForceScrapeRequest, 
    ForceScrapeResponse, AppConfigUpdateRequest, MaintenanceModeRequest,
    # Common
    UserPlan
)
from app.services.analytics import analytics_service

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def verify_admin_email(user: User) -> None:
    """Double verification: Firebase claims + email whitelist"""
    admin_emails = settings.admin_emails_list
    
    # If whitelist is configured, check it
    if admin_emails and user.email.lower() not in admin_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not in admin whitelist"
        )


async def log_action(
    db: AsyncSession,
    admin_email: str,
    action: str,
    target: str = None,
    details: dict = None,
    request: Request = None
) -> None:
    """Log admin action for audit trail"""
    ip = request.client.host if request else None
    await analytics_service.log_admin_action(
        db=db,
        admin_email=admin_email,
        action=action,
        target=target,
        details=details,
        ip_address=ip
    )


# =============================================================================
# USER MANAGEMENT ENDPOINTS (5)
# =============================================================================

@router.get("/users", response_model=dict)
async def list_users(
    request: Request,
    plan: Optional[str] = Query(None, pattern="^(free|pro|premium)$"),
    is_blocked: Optional[bool] = Query(None),
    suspicious: Optional[bool] = Query(False),
    search: Optional[str] = Query(None, max_length=100),
    sort_by: Optional[str] = Query("created_at", pattern="^(created_at|last_active|plan)$"),
    order: Optional[str] = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List users with filters
    
    Filters:
    - plan: Filter by subscription plan
    - is_blocked: Filter blocked/unblocked users
    - suspicious: Show only users with fraud flags
    - search: Search by email or display name
    """
    await verify_admin_email(user)
    
    # Build query
    query = select(User)
    
    if plan:
        query = query.where(User.plan == plan)
    
    if is_blocked is not None:
        query = query.where(User.is_blocked == is_blocked)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                User.email.ilike(search_pattern),
                User.display_name.ilike(search_pattern)
            )
        )
    
    # Sorting
    sort_column = getattr(User, sort_by, User.created_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    # Execute
    result = await db.execute(query)
    users = result.scalars().all()
    
    # Get total count
    count_query = select(func.count(User.id))
    if plan:
        count_query = count_query.where(User.plan == plan)
    if is_blocked is not None:
        count_query = count_query.where(User.is_blocked == is_blocked)
    
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    # Format response
    user_list = []
    for u in users:
        # Get account count on same device
        accounts_on_device = 0
        if u.hardware_id:
            hw_result = await db.execute(
                select(func.count(User.id)).where(User.hardware_id == u.hardware_id)
            )
            accounts_on_device = hw_result.scalar() or 0
        
        # Get lifetime value
        ltv = await analytics_service.get_user_lifetime_value(db, u.id)
        
        usage = u.usage_stats or {}
        streak = u.streak_data or {}
        
        user_list.append({
            "id": str(u.id),
            "email": u.email,
            "display_name": u.display_name,
            "plan": u.plan,
            "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_active": u.last_active.isoformat() if u.last_active else None,
            "total_searches": usage.get("daily_searches", 0),
            "watchlist_count": len(u.watchlist or []),
            "current_streak": streak.get("current_streak", 0),
            "hardware_id": u.hardware_id[:8] + "..." if u.hardware_id else None,
            "accounts_on_device": accounts_on_device,
            "unique_ips_count": len(u.ip_addresses or []),
            "is_blocked": u.is_blocked,
            "lifetime_value_inr": ltv,
            "total_spent_inr": ltv
        })
    
    # If suspicious filter, get suspicious users
    if suspicious:
        suspicious_users = await analytics_service.get_suspicious_users(db, limit=limit)
        return {
            "users": suspicious_users,
            "total": len(suspicious_users),
            "page": 1,
            "limit": limit,
            "filter": "suspicious_only"
        }
    
    return {
        "users": user_list,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


@router.get("/users/{user_id}", response_model=dict)
async def get_user_detail(
    user_id: str,
    request: Request,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed user profile with activity history"""
    await verify_admin_email(user)
    
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    target_user = await db.get(User, uid)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get transactions
    tx_result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == uid)
        .order_by(Transaction.created_at.desc())
        .limit(50)
    )
    transactions = tx_result.scalars().all()
    
    # Get watchlist
    watchlist_result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == uid)
        .options(selectinload(UserWatchlist.product))
    )
    watchlist_items = watchlist_result.scalars().all()
    
    # Calculate activity stats
    usage = target_user.usage_stats or {}
    streak = target_user.streak_data or {}
    
    # Get accounts on same device
    accounts_on_device = 0
    if target_user.hardware_id:
        hw_result = await db.execute(
            select(func.count(User.id))
            .where(User.hardware_id == target_user.hardware_id)
        )
        accounts_on_device = hw_result.scalar() or 0
    
    # Build flags
    flags = []
    if accounts_on_device >= 3:
        flags.append("max_devices_reached")
    if len(target_user.ip_addresses or []) > 5:
        flags.append("multiple_ips")
    if usage.get("suspicious_ip_activity"):
        flags.append("ip_fraud_detected")
    if target_user.is_blocked:
        flags.append("blocked")
    
    ltv = await analytics_service.get_user_lifetime_value(db, uid)
    
    await log_action(db, user.email, "viewed_user", str(uid), request=request)
    
    return {
        "user": {
            "id": str(target_user.id),
            "firebase_uid": target_user.firebase_uid,
            "email": target_user.email,
            "display_name": target_user.display_name,
            "photo_url": target_user.photo_url,
            "plan": target_user.plan,
            "plan_expires_at": target_user.plan_expires_at.isoformat() if target_user.plan_expires_at else None,
            "referral_code": target_user.referral_code,
            "referred_by": target_user.referred_by,
            "referral_count": target_user.referral_count,
            "is_blocked": target_user.is_blocked,
            "block_reason": target_user.block_reason,
            "created_at": target_user.created_at.isoformat() if target_user.created_at else None,
            "last_login": target_user.last_login.isoformat() if target_user.last_login else None,
            "last_active": target_user.last_active.isoformat() if target_user.last_active else None
        },
        "activity": {
            "total_searches": usage.get("daily_searches", 0),
            "total_clicks": usage.get("total_clicks", 0),
            "current_streak": streak.get("current_streak", 0),
            "longest_streak": streak.get("longest_streak", 0),
            "total_check_ins": streak.get("total_check_ins", 0)
        },
        "ip_history": target_user.ip_addresses or [],
        "device_info": target_user.device_info or {},
        "accounts_on_device": accounts_on_device,
        "transactions": [
            {
                "id": str(tx.id),
                "type": tx.type,
                "amount": tx.amount,
                "status": tx.status,
                "created_at": tx.created_at.isoformat() if tx.created_at else None
            }
            for tx in transactions
        ],
        "watchlist": [
            {
                "id": str(w.id),
                "product_id": str(w.product_id),
                "product_title": w.product.title if w.product else "Unknown",
                "target_price": w.target_price,
                "created_at": w.created_at.isoformat() if w.created_at else None
            }
            for w in watchlist_items
        ],
        "flags": flags,
        "lifetime_value_inr": ltv
    }


@router.put("/users/{user_id}/ban", response_model=dict)
async def ban_user(
    user_id: str,
    request: Request,
    ban_request: BanUserRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Ban or unban a user"""
    await verify_admin_email(user)
    
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    target_user = await db.get(User, uid)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Don't allow banning yourself
    if target_user.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot ban yourself")
    
    # Toggle ban status
    target_user.is_blocked = True
    target_user.block_reason = ban_request.reason
    target_user.blocked_at = datetime.utcnow()
    
    await db.commit()
    
    await log_action(
        db, user.email, "banned_user", str(uid),
        details={"reason": ban_request.reason, "permanent": ban_request.permanent},
        request=request
    )
    
    logger.info(f"Admin {user.email} banned user {target_user.email}: {ban_request.reason}")
    
    return {
        "success": True,
        "user_id": str(uid),
        "is_blocked": True,
        "reason": ban_request.reason,
        "message": f"User {target_user.email} has been banned"
    }


@router.put("/users/{user_id}/unban", response_model=dict)
async def unban_user(
    user_id: str,
    request: Request,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Unban a previously banned user"""
    await verify_admin_email(user)
    
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    target_user = await db.get(User, uid)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    target_user.is_blocked = False
    target_user.block_reason = None
    target_user.blocked_at = None
    
    await db.commit()
    
    await log_action(db, user.email, "unbanned_user", str(uid), request=request)
    
    return {
        "success": True,
        "user_id": str(uid),
        "is_blocked": False,
        "message": f"User {target_user.email} has been unbanned"
    }


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: str,
    request: Request,
    hard_delete: bool = Query(False),
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a user (soft or hard delete)"""
    await verify_admin_email(user)
    
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    target_user = await db.get(User, uid)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Don't allow deleting yourself
    if target_user.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    email = target_user.email
    
    if hard_delete:
        # Hard delete - remove from database
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()
        action = "hard_deleted_user"
    else:
        # Soft delete - just block
        target_user.is_blocked = True
        target_user.block_reason = "Account deleted by admin"
        target_user.blocked_at = datetime.utcnow()
        await db.commit()
        action = "soft_deleted_user"
    
    await log_action(
        db, user.email, action, str(uid),
        details={"email": email, "hard_delete": hard_delete},
        request=request
    )
    
    return {
        "success": True,
        "user_id": str(uid),
        "action": "hard_delete" if hard_delete else "soft_delete",
        "message": f"User {email} has been deleted"
    }


@router.post("/users/bulk-bonus", response_model=dict)
async def grant_bulk_bonus(
    request: Request,
    bonus_request: BulkUserBonus,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Grant bonuses to multiple users (for promotions, apologies, etc.)"""
    await verify_admin_email(user)
    
    # Build query based on target
    query = select(User).where(User.is_blocked == False)
    
    if bonus_request.target == "all_free_users":
        query = query.where(User.plan == "free")
    elif bonus_request.target == "all_pro_users":
        query = query.where(User.plan == "pro")
    elif bonus_request.target == "all_premium_users":
        query = query.where(User.plan == "premium")
    elif bonus_request.target == "specific_users":
        if not bonus_request.user_ids:
            raise HTTPException(status_code=400, detail="user_ids required for specific_users target")
        uuids = [UUID(uid) for uid in bonus_request.user_ids]
        query = query.where(User.id.in_(uuids))
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    if not users:
        raise HTTPException(status_code=404, detail="No users match the criteria")
    
    updated_count = 0
    bonuses = bonus_request.bonuses
    
    for u in users:
        usage = u.usage_stats or {}
        
        # Apply bonuses
        if bonuses.get("daily_searches", 0) > 0:
            usage["daily_search_bonus"] = usage.get("daily_search_bonus", 0) + bonuses["daily_searches"]
        
        if bonuses.get("watchlist_slots", 0) > 0:
            usage["watchlist_bonus"] = usage.get("watchlist_bonus", 0) + bonuses["watchlist_slots"]
        
        if bonuses.get("streak_freeze", 0) > 0:
            streak = u.streak_data or {}
            streak["freeze_count"] = streak.get("freeze_count", 0) + bonuses["streak_freeze"]
            u.streak_data = streak
        
        if bonuses.get("premium_days", 0) > 0:
            if u.plan_expires_at:
                u.plan_expires_at = u.plan_expires_at + timedelta(days=bonuses["premium_days"])
            else:
                u.plan_expires_at = datetime.utcnow() + timedelta(days=bonuses["premium_days"])
            if u.plan == "free":
                u.plan = "pro"
        
        u.usage_stats = usage
        updated_count += 1
    
    await db.commit()
    
    await log_action(
        db, user.email, "granted_bulk_bonus",
        details={
            "target": bonus_request.target,
            "bonuses": bonuses,
            "users_affected": updated_count,
            "reason": bonus_request.reason
        },
        request=request
    )
    
    return {
        "success": True,
        "users_affected": updated_count,
        "bonuses_granted": bonuses,
        "reason": bonus_request.reason,
        "message": f"Bonuses granted to {updated_count} users"
    }


# =============================================================================
# REVENUE ANALYTICS ENDPOINTS (4)
# =============================================================================

@router.get("/revenue/overview", response_model=dict)
async def get_revenue_overview(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Complete revenue dashboard
    
    Shows:
    - Today's revenue breakdown
    - Monthly totals with MRR
    - User breakdown by plan
    - Projections including loan payoff date
    """
    await verify_admin_email(user)
    
    overview = await analytics_service.get_revenue_overview(db)
    return overview


@router.get("/revenue/transactions", response_model=dict)
async def list_transactions(
    type: Optional[str] = Query(None, pattern="^(payment|affiliate_click|affiliate_conversion|refund)$"),
    status: Optional[str] = Query(None, pattern="^(pending|success|failed|refunded)$"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List transactions with filters"""
    await verify_admin_email(user)
    
    query = select(Transaction).options(selectinload(Transaction.user))
    
    if type:
        query = query.where(Transaction.type == type)
    if status:
        query = query.where(Transaction.status == status)
    if start_date:
        query = query.where(Transaction.created_at >= start_date)
    if end_date:
        query = query.where(Transaction.created_at <= end_date)
    
    query = query.order_by(Transaction.created_at.desc())
    
    # Pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    # Get total count
    count_query = select(func.count(Transaction.id))
    if type:
        count_query = count_query.where(Transaction.type == type)
    if status:
        count_query = count_query.where(Transaction.status == status)
    
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    return {
        "transactions": [
            {
                "id": str(tx.id),
                "user_email": tx.user.email if tx.user else "Unknown",
                "type": tx.type,
                "amount": tx.amount,
                "currency": tx.currency,
                "status": tx.status,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "razorpay_payment_id": tx.razorpay_payment_id,
                "commission_earned": tx.commission_earned
            }
            for tx in transactions
        ],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


@router.get("/revenue/plans", response_model=dict)
async def get_plan_breakdown(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get revenue breakdown by subscription plan"""
    await verify_admin_email(user)
    
    user_breakdown = await analytics_service.get_user_breakdown(db)
    mrr = await analytics_service.calculate_mrr(db)
    
    pro_price = settings.PLAN_PRO_PRICE / 100
    premium_price = settings.PLAN_PREMIUM_PRICE / 100
    
    return {
        "plans": [
            {
                "plan": "free",
                "active_users": user_breakdown.get("free", 0),
                "monthly_revenue": 0,
                "avg_lifetime_value": 0
            },
            {
                "plan": "pro",
                "active_users": user_breakdown.get("pro", 0),
                "monthly_revenue": user_breakdown.get("pro", 0) * pro_price,
                "price_per_user": pro_price,
                "avg_lifetime_value": pro_price * 6  # Assume 6 months avg
            },
            {
                "plan": "premium",
                "active_users": user_breakdown.get("premium", 0),
                "monthly_revenue": user_breakdown.get("premium", 0) * premium_price,
                "price_per_user": premium_price,
                "avg_lifetime_value": premium_price * 12  # Assume 12 months avg
            }
        ],
        "total_mrr": mrr,
        "total_users": sum(user_breakdown.values())
    }


@router.get("/revenue/affiliates", response_model=dict)
async def get_affiliate_performance(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get top affiliate performers"""
    await verify_admin_email(user)
    
    performers = await analytics_service.get_affiliate_performance(db, days, limit)
    clicks_today = await analytics_service.get_affiliate_clicks_today(db)
    
    return {
        "top_products": performers,
        "clicks_today": clicks_today,
        "period_days": days
    }


# =============================================================================
# PROMOTION MANAGEMENT ENDPOINTS (8)
# =============================================================================

@router.post("/promotions", response_model=dict)
async def create_promotion(
    request: Request,
    promo_data: PromotionCreate,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new brand promotion campaign"""
    await verify_admin_email(user)
    
    # Validate dates
    if promo_data.end_date <= promo_data.start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
    # Create promotion
    promotion = Promotion(
        title=promo_data.title,
        description=promo_data.description,
        campaign_type=promo_data.campaign_type,
        target_platforms=promo_data.target_platforms,
        target_categories=promo_data.target_categories,
        target_user_plan=[p.value for p in promo_data.target_user_plan],
        target_min_users=promo_data.target_min_users,
        target_max_users=promo_data.target_max_users,
        image_url=promo_data.image_url,
        cta_text=promo_data.cta_text,
        destination_url=promo_data.destination_url,
        product_id=UUID(promo_data.product_id) if promo_data.product_id else None,
        position=promo_data.position,
        priority=promo_data.priority,
        max_impressions=promo_data.max_impressions,
        max_clicks=promo_data.max_clicks,
        max_budget_inr=promo_data.max_budget_inr,
        start_date=promo_data.start_date,
        end_date=promo_data.end_date,
        pricing_model=promo_data.pricing_model,
        rate_inr=promo_data.rate_inr,
        pricing_tiers=promo_data.pricing_tiers,
        brand_name=promo_data.brand_name,
        brand_contact_email=promo_data.brand_contact_email,
        created_by=user.email,
        is_active=True,
        is_approved=True,
        stats={
            "impressions": 0,
            "clicks": 0,
            "conversions": 0,
            "revenue_earned": 0
        }
    )
    
    db.add(promotion)
    await db.commit()
    await db.refresh(promotion)
    
    await log_action(
        db, user.email, "created_promotion",
        str(promotion.id),
        details={"title": promo_data.title, "brand": promo_data.brand_name},
        request=request
    )
    
    return {
        "success": True,
        "promotion_id": str(promotion.id),
        "title": promotion.title,
        "status": "scheduled" if promotion.start_date > datetime.utcnow() else "active",
        "message": f"Promotion '{promo_data.title}' created successfully"
    }


@router.get("/promotions", response_model=dict)
async def list_promotions(
    status: Optional[str] = Query(None, pattern="^(active|scheduled|completed|paused)$"),
    campaign_type: Optional[str] = None,
    brand_name: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List promotions with filters"""
    await verify_admin_email(user)
    
    now = datetime.utcnow()
    query = select(Promotion)
    
    if campaign_type:
        query = query.where(Promotion.campaign_type == campaign_type)
    if brand_name:
        query = query.where(Promotion.brand_name.ilike(f"%{brand_name}%"))
    
    if status == "active":
        query = query.where(
            and_(
                Promotion.is_active == True,
                Promotion.start_date <= now,
                Promotion.end_date >= now
            )
        )
    elif status == "scheduled":
        query = query.where(
            and_(
                Promotion.is_active == True,
                Promotion.start_date > now
            )
        )
    elif status == "completed":
        query = query.where(Promotion.end_date < now)
    elif status == "paused":
        query = query.where(Promotion.is_active == False)
    
    query = query.order_by(Promotion.created_at.desc())
    
    # Pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    promotions = result.scalars().all()
    
    # Get total
    count_result = await db.execute(select(func.count(Promotion.id)))
    total = count_result.scalar() or 0
    
    promo_list = []
    for p in promotions:
        # Determine current status
        if not p.is_active:
            promo_status = "paused"
        elif p.end_date < now:
            promo_status = "completed"
        elif p.start_date > now:
            promo_status = "scheduled"
        else:
            promo_status = "active"
        
        stats = p.stats or {}
        
        promo_list.append({
            "id": str(p.id),
            "title": p.title,
            "campaign_type": p.campaign_type,
            "brand_name": p.brand_name,
            "is_active": p.is_active,
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat(),
            "stats": stats,
            "pricing_model": p.pricing_model,
            "rate_inr": p.rate_inr,
            "status": promo_status,
            "created_at": p.created_at.isoformat() if p.created_at else None
        })
    
    return {
        "promotions": promo_list,
        "total": total,
        "page": page,
        "limit": limit
    }


@router.get("/promotions/{promotion_id}", response_model=dict)
async def get_promotion_detail(
    promotion_id: str,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed promotion analytics"""
    await verify_admin_email(user)
    
    try:
        pid = UUID(promotion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid promotion ID")
    
    promotion = await db.get(Promotion, pid)
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")
    
    now = datetime.utcnow()
    stats = promotion.stats or {}
    
    # Calculate remaining
    remaining_impressions = (promotion.max_impressions or 999999) - stats.get("impressions", 0)
    remaining_clicks = (promotion.max_clicks or 999999) - stats.get("clicks", 0)
    remaining_days = (promotion.end_date - now).days if promotion.end_date > now else 0
    remaining_budget = (promotion.max_budget_inr or 999999) - stats.get("revenue_earned", 0)
    
    # Calculate CTR
    impressions = stats.get("impressions", 0)
    clicks = stats.get("clicks", 0)
    ctr = (clicks / impressions * 100) if impressions > 0 else 0
    
    return {
        "promotion": {
            "id": str(promotion.id),
            "title": promotion.title,
            "description": promotion.description,
            "campaign_type": promotion.campaign_type,
            "brand_name": promotion.brand_name,
            "brand_contact_email": promotion.brand_contact_email,
            "image_url": promotion.image_url,
            "cta_text": promotion.cta_text,
            "destination_url": promotion.destination_url,
            "target_platforms": promotion.target_platforms,
            "target_categories": promotion.target_categories,
            "target_user_plan": promotion.target_user_plan,
            "target_min_users": promotion.target_min_users,
            "position": promotion.position,
            "priority": promotion.priority,
            "start_date": promotion.start_date.isoformat(),
            "end_date": promotion.end_date.isoformat(),
            "is_active": promotion.is_active,
            "pricing_model": promotion.pricing_model,
            "rate_inr": promotion.rate_inr,
            "payment_status": promotion.payment_status,
            "created_by": promotion.created_by,
            "created_at": promotion.created_at.isoformat() if promotion.created_at else None
        },
        "performance": {
            "impressions": stats.get("impressions", 0),
            "clicks": clicks,
            "conversions": stats.get("conversions", 0),
            "ctr": round(ctr, 2),
            "revenue_earned": stats.get("revenue_earned", 0)
        },
        "remaining": {
            "impressions": max(0, remaining_impressions),
            "clicks": max(0, remaining_clicks),
            "budget": max(0, remaining_budget),
            "days": max(0, remaining_days)
        },
        "limits": {
            "max_impressions": promotion.max_impressions,
            "max_clicks": promotion.max_clicks,
            "max_budget_inr": promotion.max_budget_inr
        }
    }


@router.put("/promotions/{promotion_id}", response_model=dict)
async def update_promotion(
    promotion_id: str,
    request: Request,
    update_data: PromotionUpdate,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update promotion settings"""
    await verify_admin_email(user)
    
    try:
        pid = UUID(promotion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid promotion ID")
    
    promotion = await db.get(Promotion, pid)
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")
    
    # Update fields
    if update_data.title is not None:
        promotion.title = update_data.title
    if update_data.is_active is not None:
        promotion.is_active = update_data.is_active
    if update_data.end_date is not None:
        promotion.end_date = update_data.end_date
    if update_data.max_clicks is not None:
        promotion.max_clicks = update_data.max_clicks
    if update_data.max_budget_inr is not None:
        promotion.max_budget_inr = update_data.max_budget_inr
    if update_data.payment_status is not None:
        promotion.payment_status = update_data.payment_status
    
    await db.commit()
    
    await log_action(
        db, user.email, "updated_promotion",
        str(pid),
        details=update_data.model_dump(exclude_none=True),
        request=request
    )
    
    return {
        "success": True,
        "promotion_id": str(pid),
        "message": "Promotion updated successfully"
    }


@router.delete("/promotions/{promotion_id}", response_model=dict)
async def delete_promotion(
    promotion_id: str,
    request: Request,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a promotion"""
    await verify_admin_email(user)
    
    try:
        pid = UUID(promotion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid promotion ID")
    
    promotion = await db.get(Promotion, pid)
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")
    
    title = promotion.title
    
    await db.execute(delete(Promotion).where(Promotion.id == pid))
    await db.commit()
    
    await log_action(
        db, user.email, "deleted_promotion",
        str(pid),
        details={"title": title},
        request=request
    )
    
    return {
        "success": True,
        "promotion_id": str(pid),
        "message": f"Promotion '{title}' deleted successfully"
    }


@router.get("/promotions/revenue/report", response_model=dict)
async def get_promotion_revenue_report(
    brand_name: Optional[str] = None,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),  # YYYY-MM
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get promotion revenue report (for invoicing brands)"""
    await verify_admin_email(user)
    
    query = select(Promotion)
    
    if brand_name:
        query = query.where(Promotion.brand_name.ilike(f"%{brand_name}%"))
    
    if month:
        year, mon = month.split("-")
        start_date = datetime(int(year), int(mon), 1)
        if int(mon) == 12:
            end_date = datetime(int(year) + 1, 1, 1)
        else:
            end_date = datetime(int(year), int(mon) + 1, 1)
        
        query = query.where(
            and_(
                Promotion.start_date >= start_date,
                Promotion.start_date < end_date
            )
        )
    
    result = await db.execute(query)
    promotions = result.scalars().all()
    
    # Group by brand
    brands = {}
    for p in promotions:
        brand = p.brand_name
        if brand not in brands:
            brands[brand] = {
                "brand_name": brand,
                "contact_email": p.brand_contact_email,
                "campaigns": [],
                "total_impressions": 0,
                "total_clicks": 0,
                "total_conversions": 0,
                "total_due": 0
            }
        
        stats = p.stats or {}
        revenue = stats.get("revenue_earned", 0)
        
        brands[brand]["campaigns"].append({
            "title": p.title,
            "campaign_type": p.campaign_type,
            "impressions": stats.get("impressions", 0),
            "clicks": stats.get("clicks", 0),
            "conversions": stats.get("conversions", 0),
            "pricing_model": p.pricing_model,
            "rate": p.rate_inr,
            "revenue": revenue,
            "payment_status": p.payment_status
        })
        
        brands[brand]["total_impressions"] += stats.get("impressions", 0)
        brands[brand]["total_clicks"] += stats.get("clicks", 0)
        brands[brand]["total_conversions"] += stats.get("conversions", 0)
        brands[brand]["total_due"] += revenue
    
    return {
        "period": month or "all_time",
        "brands": list(brands.values()),
        "grand_total": sum(b["total_due"] for b in brands.values())
    }


# =============================================================================
# SYSTEM MONITORING ENDPOINTS (6)
# =============================================================================

@router.get("/system/health", response_model=dict)
async def get_system_health(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Get complete system health status"""
    await verify_admin_email(user)
    
    health = {
        "database": {"status": "healthy"},
        "redis": {"status": "healthy"},
        "scrapers": {},
        "groq_ai": {},
        "overall": "healthy"
    }
    
    # Check database
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        
        # Get connection count (approximate)
        pool_result = await db.execute(text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
        ))
        conn_count = pool_result.scalar() or 0
        
        # Get database size
        size_result = await db.execute(text(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        ))
        db_size = size_result.scalar() or "Unknown"
        
        health["database"] = {
            "status": "healthy",
            "connections": conn_count,
            "size": db_size
        }
    except Exception as e:
        health["database"] = {"status": "unhealthy", "error": str(e)}
        health["overall"] = "degraded"
    
    # Check Redis
    try:
        await redis_client.ping()
        
        info = await redis_client.info("memory")
        memory_used = info.get("used_memory_human", "Unknown")
        
        keys_count = await redis_client.dbsize()
        
        health["redis"] = {
            "status": "healthy",
            "memory_used": memory_used,
            "keys": keys_count
        }
    except Exception as e:
        health["redis"] = {"status": "unhealthy", "error": str(e)}
        health["overall"] = "degraded"
    
    # Check scrapers
    try:
        scraper_health = await analytics_service.get_scraper_health(db)
        health["scrapers"] = scraper_health
        
        # Check if any scraper is failing
        for platform, data in scraper_health.items():
            if data.get("status") == "failing":
                health["overall"] = "degraded"
    except Exception as e:
        health["scrapers"] = {"error": str(e)}
    
    # Check Groq quota (from Redis if tracked)
    try:
        today = date.today().isoformat()
        quota_key = f"groq:usage:{today}"
        quota_used = await redis_client.get(quota_key)
        
        health["groq_ai"] = {
            "quota_used_today": int(quota_used or 0),
            "quota_limit": settings.GROQ_DAILY_LIMIT,
            "quota_remaining": settings.GROQ_DAILY_LIMIT - int(quota_used or 0)
        }
    except Exception:
        health["groq_ai"] = {"status": "unknown"}
    
    return health


@router.get("/system/stats", response_model=dict)
async def get_system_stats(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Get system-wide statistics"""
    await verify_admin_email(user)
    
    # Active users
    dau = await analytics_service.get_active_users_count(db, "daily")
    wau = await analytics_service.get_active_users_count(db, "weekly")
    mau = await analytics_service.get_active_users_count(db, "monthly")
    
    # Product stats
    product_stats = await analytics_service.get_product_stats(db)
    
    # Searches today
    searches_today = await analytics_service.get_searches_today(db)
    
    # Affiliate clicks
    affiliate_clicks = await analytics_service.get_affiliate_clicks_today(db)
    
    # Cache stats from Redis
    cache_hit_rate = 0
    try:
        info = await redis_client.info("stats")
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        if hits + misses > 0:
            cache_hit_rate = round((hits / (hits + misses)) * 100, 1)
    except Exception:
        pass
    
    return {
        "traffic": {
            "searches_today": searches_today,
            "unique_users_today": dau,
            "cache_hit_rate": cache_hit_rate
        },
        "engagement": {
            "daily_active_users": dau,
            "weekly_active_users": wau,
            "monthly_active_users": mau
        },
        "products": product_stats,
        "conversions": {
            "affiliate_clicks_today": affiliate_clicks
        }
    }


@router.get("/system/logs", response_model=dict)
async def get_system_logs(
    log_date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    days: int = Query(7, ge=1, le=30),
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get system logs"""
    await verify_admin_email(user)
    
    if log_date:
        # Get specific date
        target_date = datetime.strptime(log_date, "%Y-%m-%d").date()
        result = await db.execute(
            select(SystemLog).where(SystemLog.log_date == target_date)
        )
        log = result.scalar_one_or_none()
        
        if not log:
            return {"logs": [], "message": f"No logs for {log_date}"}
        
        return {
            "logs": [{
                "date": log.log_date.isoformat(),
                "scraping_summary": log.scraping_summary,
                "analytics": log.analytics,
                "ml_processing": log.ml_processing,
                "archived_to_git": log.archived_to_git
            }]
        }
    
    # Get last N days
    since_date = date.today() - timedelta(days=days)
    result = await db.execute(
        select(SystemLog)
        .where(SystemLog.log_date >= since_date)
        .order_by(SystemLog.log_date.desc())
    )
    logs = result.scalars().all()
    
    return {
        "logs": [
            {
                "date": log.log_date.isoformat(),
                "scraping_summary": log.scraping_summary,
                "analytics": log.analytics,
                "ml_processing": log.ml_processing,
                "archived_to_git": log.archived_to_git
            }
            for log in logs
        ],
        "period_days": days
    }


@router.post("/system/force-scrape", response_model=dict)
async def force_scrape(
    request: Request,
    scrape_request: ForceScrapeRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger scraper"""
    await verify_admin_email(user)
    
    # For now, return a placeholder response
    # Actual implementation will come in Part 9 (Scrapers)
    
    await log_action(
        db, user.email, "triggered_scrape",
        details={
            "platform": scrape_request.platform,
            "async": scrape_request.async_mode,
            "category": scrape_request.category
        },
        request=request
    )
    
    if scrape_request.async_mode:
        # Would queue background job
        import uuid
        job_id = str(uuid.uuid4())
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": f"Scraping job queued for {scrape_request.platform}",
            "note": "Background job system will be implemented in Part 10"
        }
    else:
        # Synchronous - would wait for completion
        return {
            "status": "placeholder",
            "message": f"Scraper for {scrape_request.platform} would run here",
            "note": "Scraper implementation coming in Part 9",
            "products_scraped": 0,
            "duration_seconds": 0
        }


@router.put("/system/config", response_model=dict)
async def update_app_config(
    request: Request,
    config_update: AppConfigUpdateRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Update application configuration"""
    await verify_admin_email(user)
    
    # Get or create config entry
    result = await db.execute(
        select(AppConfig).where(AppConfig.key == config_update.key)
    )
    config = result.scalar_one_or_none()
    
    if config:
        config.value = config_update.value
        config.value_type = config_update.value_type
        if config_update.description:
            config.description = config_update.description
        if config_update.category:
            config.category = config_update.category
        config.updated_by = user.email
    else:
        config = AppConfig(
            key=config_update.key,
            value=config_update.value,
            value_type=config_update.value_type,
            description=config_update.description,
            category=config_update.category,
            is_public=False,
            updated_by=user.email
        )
        db.add(config)
    
    await db.commit()
    
    # Invalidate config cache
    await redis_client.delete("app:config")
    
    await log_action(
        db, user.email, "updated_config",
        config_update.key,
        details={"new_value": config_update.value, "type": config_update.value_type},
        request=request
    )
    
    return {
        "success": True,
        "key": config_update.key,
        "value": config_update.value,
        "message": f"Config '{config_update.key}' updated successfully"
    }


@router.get("/system/config", response_model=dict)
async def get_all_config(
    category: Optional[str] = None,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all app configuration"""
    await verify_admin_email(user)
    
    query = select(AppConfig)
    if category:
        query = query.where(AppConfig.category == category)
    
    result = await db.execute(query)
    configs = result.scalars().all()
    
    return {
        "configs": [
            {
                "key": c.key,
                "value": c.value,
                "value_type": c.value_type,
                "description": c.description,
                "category": c.category,
                "is_public": c.is_public,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "updated_by": c.updated_by
            }
            for c in configs
        ]
    }


@router.post("/system/maintenance", response_model=dict)
async def toggle_maintenance_mode(
    request: Request,
    maintenance_request: MaintenanceModeRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Enable/disable maintenance mode"""
    await verify_admin_email(user)
    
    # Update maintenance_mode config
    result = await db.execute(
        select(AppConfig).where(AppConfig.key == "maintenance_mode")
    )
    config = result.scalar_one_or_none()
    
    if config:
        config.value = str(maintenance_request.enabled).lower()
        config.updated_by = user.email
    else:
        config = AppConfig(
            key="maintenance_mode",
            value=str(maintenance_request.enabled).lower(),
            value_type="boolean",
            description="Application maintenance mode",
            category="system",
            is_public=True,
            updated_by=user.email
        )
        db.add(config)
    
    # Store maintenance message if enabled
    if maintenance_request.enabled and maintenance_request.message:
        msg_result = await db.execute(
            select(AppConfig).where(AppConfig.key == "maintenance_message")
        )
        msg_config = msg_result.scalar_one_or_none()
        
        if msg_config:
            msg_config.value = maintenance_request.message
        else:
            msg_config = AppConfig(
                key="maintenance_message",
                value=maintenance_request.message,
                value_type="string",
                category="system",
                is_public=True,
                updated_by=user.email
            )
            db.add(msg_config)
    
    await db.commit()
    
    # Invalidate cache
    await redis_client.delete("app:config")
    
    await log_action(
        db, user.email,
        "enabled_maintenance" if maintenance_request.enabled else "disabled_maintenance",
        details={
            "message": maintenance_request.message,
            "duration_minutes": maintenance_request.estimated_duration_minutes
        },
        request=request
    )
    
    return {
        "success": True,
        "maintenance_mode": maintenance_request.enabled,
        "message": maintenance_request.message if maintenance_request.enabled else "Maintenance mode disabled",
        "estimated_duration_minutes": maintenance_request.estimated_duration_minutes
    }
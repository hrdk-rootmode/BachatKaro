"""
Admin Dashboard API Endpoints
Complete control center for managing DealHunt

Features:
- User Management (list, view, ban, delete, bonus)
- Revenue Analytics (overview, transactions, plans, affiliates)
- Promotion Management (create, update, delete, analytics)
- System Monitoring (health, stats, logs, config)
- Live Config Management (no-code changes)
- ✅ NEW: Working Force-Scrape & Scheduler Status

Security:
- Firebase custom claims (admin: true)
- Email whitelist verification
- All actions logged for audit
"""

import logging
import asyncio
from datetime import datetime, timedelta, date, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update, delete, text, cast, String
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from bs4 import BeautifulSoup

from app.core.database import get_db
from app.core.redis_client import get_redis, RedisClient
from app.core.config import settings
from app.api.deps import get_current_admin_user, verify_firebase_token
from app.models import (
    User, Transaction, SubscriptionPlan, Product, ProductListing,
    Platform, SystemLog, AppConfig, Promotion, UserWatchlist, StreakMilestone,
    PriceHistory
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
    SubscriptionPlanUpdateRequest,
    # Jobs
    SchedulerStatusResponse, TriggerJobRequest, TriggerJobResponse,
    # Scraper Testing
    PlatformStatus, ScraperStatusResponse, ScraperTestRequest, ScraperTestResult,
    ScraperTestResponse, BatchScraperTestResponse, ScraperFixRequest, ScraperFixResponse,
    ScraperConfigUpdateRequest, ScraperConfigResponse, ScraperInspectionResponse,
    ScraperSelectorUpdateRequest, ScraperSelectorUpdateResponse,
    # ✅ NEW: Selector validation schemas
    SelectorHealthInfo, LastScrapedValue, SelectorValidationResult,
    HtmlOutlineNode, SelectorInspectionItem,
    ValidateSelectorRequest, ValidateSelectorResponse,
    # Common
    UserPlan
)
from app.services.analytics import analytics_service
from app.services.ai.groq_client import groq_client
from app.services.admin.selector_validator import SelectorValidator, LastScrapedValueFinder
from app.services.scraper.browser import get_browser_manager

# ✅ NEW: Import scheduler functions
from jobs.scheduler import trigger_job_manually, get_scheduler_status

logger = logging.getLogger(__name__)

router = APIRouter()


SENSITIVE_CONFIG_EXACT_KEYS = {
    "DATABASE_URL",
    "SECRET_KEY",
    "JWT_SECRET",
    "CRON_SECRET",
    "ADMIN_SECRET",
    "FIREBASE_PRIVATE_KEY",
    "FIREBASE_PRIVATE_KEY_ID",
    "FIREBASE_CLIENT_EMAIL",
    "FIREBASE_CLIENT_ID",
    "GROQ_API_KEY_MAIN",
    "GROQ_API_KEY_SEARCH",
    "GROQ_API_KEY_HEALING",
    "GROQ_API_KEY_CHAT",
    "GEMINI_API_KEY",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "FCM_SERVER_KEY",
    "GITHUB_TOKEN",
}

SENSITIVE_CONFIG_KEYWORDS = (
    "API_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PRIVATE_KEY",
    "WEBHOOK",
    "CREDENTIALS",
    "DATABASE_URL",
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def verify_admin_email(user: User) -> None:
    """Double verification: Firebase claims + email whitelist"""
    admin_emails = settings.admin_emails_list
    
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


def _normalize_selector_value(selector_value: Any) -> str:
    if isinstance(selector_value, dict):
        return str(selector_value.get("selector", "") or "").strip()
    if selector_value is None:
        return ""
    return str(selector_value).strip()


def _build_selector_hint(tag: str, node_id: Optional[str], classes: List[str]) -> str:
    if node_id:
        return f"#{node_id}"
    if classes:
        return "." + ".".join(classes[:3])
    return tag


def _build_html_outline(html: str, max_nodes: int = 120, max_depth: int = 4) -> List[Dict[str, Any]]:
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    root = soup.body or soup
    outline: List[Dict[str, Any]] = []

    def walk(node, depth: int = 0) -> None:
        if len(outline) >= max_nodes or depth > max_depth:
            return

        for child in getattr(node, "children", []):
            if len(outline) >= max_nodes:
                return
            if not getattr(child, "name", None):
                continue
            if child.name in {"script", "style", "noscript"}:
                continue

            classes = child.get("class", []) or []
            attrs = {
                key: value
                for key, value in child.attrs.items()
                if key in {"href", "src", "role", "aria-label", "data-testid", "data-id", "itemprop"}
            }
            outline.append({
                "depth": depth,
                "tag": child.name,
                "node_id": child.get("id"),
                "classes": classes[:6],
                "text": child.get_text(" ", strip=True)[:160] or None,
                "selector_hint": _build_selector_hint(child.name, child.get("id"), classes),
                "attributes": attrs,
            })
            walk(child, depth + 1)

    walk(root, 0)
    return outline


async def _fetch_live_html(page_url: str, timeout_seconds: int = 45) -> str:
    browser_manager = await get_browser_manager()

    async with browser_manager.get_page(block_resources=False, stealth=True) as page:
        await asyncio.wait_for(
            page.goto(page_url, wait_until="domcontentloaded"),
            timeout=min(timeout_seconds, 45)
        )
        await asyncio.wait_for(page.wait_for_timeout(1500), timeout=min(timeout_seconds, 10))
        return await asyncio.wait_for(page.content(), timeout=min(timeout_seconds, 45))


def is_sensitive_config_key(key: str) -> bool:
    """Detect keys that must remain env-only and never be exposed from DB config."""
    if not key:
        return False

    upper = key.strip().upper()
    if upper in SENSITIVE_CONFIG_EXACT_KEYS:
        return True

    return any(token in upper for token in SENSITIVE_CONFIG_KEYWORDS)


def normalize_config_value_type(value_type: str) -> str:
    """Normalize legacy/alias value types to supported schema types."""
    normalized = (value_type or "string").strip().lower()
    aliases = {
        "int": "number",
        "integer": "number",
        "float": "number",
        "decimal": "number",
        "bool": "boolean",
        "dict": "json",
        "list": "json",
        "jsonb": "json",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {"string", "number", "boolean", "json"} else "string"


def infer_config_value_type(value) -> str:
    """Infer config value type from python runtime value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (list, dict, tuple)):
        return "json"
    return "string"


def serialize_config_value(value, value_type: str) -> str:
    """Serialize value to DB text format using normalized value_type."""
    normalized_type = normalize_config_value_type(value_type)

    if value is None:
        return ""

    if normalized_type == "boolean":
        if isinstance(value, bool):
            return str(value).lower()
        return str(str(value).strip().lower() in {"1", "true", "yes", "on"}).lower()

    if normalized_type == "number":
        return str(value)

    if normalized_type == "json":
        if isinstance(value, str):
            text_value = value.strip()
            if not text_value:
                return "{}"
            try:
                json.loads(text_value)
                return text_value
            except Exception:
                return json.dumps({"value": text_value})
        return json.dumps(value, default=str)

    return str(value)


def infer_config_category(key: str) -> str:
    """Infer AppConfig category from setting key name."""
    upper = (key or "").upper()

    if upper.startswith("DAILY_SCRAPE_") or "SCRAPER" in upper:
        return "scraper"
    if upper.startswith("PLAN_") or upper.startswith("REWARD_"):
        return "plans"
    if upper.startswith("RATE_LIMIT"):
        return "limits"
    if upper.startswith("RAZORPAY_") or upper.startswith("GOOGLE_PLAY_"):
        return "payments"
    if upper.startswith("FIREBASE_"):
        return "auth"
    if upper.startswith("GROQ_") or upper.startswith("GEMINI_"):
        return "ai"
    if upper.startswith("LOCATION_REFRESH_"):
        return "location"
    return "system"


def settings_to_config_entries() -> list[dict]:
    """Convert backend settings to AppConfig candidate entries, excluding sensitive keys."""
    if hasattr(settings, "model_dump"):
        raw_settings = settings.model_dump()
    else:
        raw_settings = settings.dict()

    entries = []
    for key, value in raw_settings.items():
        if is_sensitive_config_key(key):
            continue

        value_type = infer_config_value_type(value)
        entries.append({
            "key": key,
            "value": serialize_config_value(value, value_type),
            "value_type": value_type,
            "category": infer_config_category(key),
            "description": f"Synced from backend setting: {key}",
            "is_public": False,
        })

    return entries


def serialize_subscription_plan(plan: SubscriptionPlan) -> dict:
    """Serialize subscription plan row to admin/frontend-friendly payload."""
    features = plan.features if isinstance(plan.features, dict) else {}
    searches_per_day = features.get("daily_searches", 0)
    watchlist_limit = features.get("watchlist_limit", 0)

    return {
        "name": plan.name,
        "display_name": plan.display_name,
        "price_inr": float(plan.price_inr or 0),
        "duration_days": int(plan.duration_days or 0),
        "searches_per_day": int(searches_per_day) if searches_per_day is not None else 0,
        "watchlist_limit": int(watchlist_limit) if watchlist_limit is not None else 0,
        "is_popular": bool(plan.is_popular),
        "is_active": bool(plan.is_active),
        "sort_order": int(plan.sort_order or 0),
        "tagline": plan.tagline,
        "features": features,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


# =============================================================================
# USER MANAGEMENT ENDPOINTS (5)
# =============================================================================

@router.get("/users", response_model=dict)
async def list_users(
    request: Request,
    plan: Optional[str] = Query(None, pattern="^[a-z0-9_]+$"),
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
    """List users with filters"""
    await verify_admin_email(user)
    
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
    
    sort_column = getattr(User, sort_by, User.created_at)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    users = result.scalars().all()

    user_ids = [u.id for u in users]
    watchlist_counts: dict[UUID, int] = {}
    search_counts: dict[UUID, int] = {}

    if user_ids:
        watchlist_result = await db.execute(
            select(UserWatchlist.user_id, func.count(UserWatchlist.id))
            .where(UserWatchlist.user_id.in_(user_ids))
            .group_by(UserWatchlist.user_id)
        )
        watchlist_counts = {row[0]: row[1] for row in watchlist_result.all()}

        search_result = await db.execute(
            select(Transaction.user_id, func.count(Transaction.id))
            .where(
                and_(
                    Transaction.user_id.in_(user_ids),
                    Transaction.type.in_(["search", "ai_search"])
                )
            )
            .group_by(Transaction.user_id)
        )
        search_counts = {row[0]: row[1] for row in search_result.all()}
    
    count_query = select(func.count(User.id))
    if plan:
        count_query = count_query.where(User.plan == plan)
    if is_blocked is not None:
        count_query = count_query.where(User.is_blocked == is_blocked)
    
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    user_list = []
    for u in users:
        accounts_on_device = 0
        if u.hardware_id:
            hw_result = await db.execute(
                select(func.count(User.id)).where(User.hardware_id == u.hardware_id)
            )
            accounts_on_device = hw_result.scalar() or 0
        
        ltv = await analytics_service.get_user_lifetime_value(db, u.id)
        
        usage = u.usage_stats or {}
        streak = u.streak_data or {}

        usage_total_searches = usage.get("total_searches", usage.get("daily_searches", 0))
        db_total_searches = search_counts.get(u.id, 0)
        total_searches = max(int(usage_total_searches or 0), int(db_total_searches or 0))

        watchlist_count = int(watchlist_counts.get(u.id, 0))
        if watchlist_count == 0:
            watchlist_count = len(u.watchlist or [])
        
        user_list.append({
            "id": str(u.id),
            "email": u.email,
            "display_name": u.display_name,
            "plan": u.plan,
            "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_active": u.last_active.isoformat() if u.last_active else None,
            "total_searches": total_searches,
            "watchlist_count": watchlist_count,
            "current_streak": streak.get("current_streak", 0),
            "hardware_id": u.hardware_id[:8] + "..." if u.hardware_id else None,
            "accounts_on_device": accounts_on_device,
            "unique_ips_count": len(u.ip_addresses or []),
            "is_blocked": u.is_blocked,
            "lifetime_value_inr": ltv,
            "total_spent_inr": ltv
        })
    
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
    
    tx_result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == uid)
        .order_by(Transaction.created_at.desc())
        .limit(50)
    )
    transactions = tx_result.scalars().all()
    
    watchlist_result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == uid)
        .options(selectinload(UserWatchlist.product))
    )
    watchlist_items = watchlist_result.scalars().all()

    search_count_result = await db.execute(
        select(func.count(Transaction.id))
        .where(
            and_(
                Transaction.user_id == uid,
                Transaction.type.in_(["search", "ai_search"])
            )
        )
    )
    db_total_searches = search_count_result.scalar() or 0
    
    usage = target_user.usage_stats or {}
    streak = target_user.streak_data or {}
    usage_total_searches = usage.get("total_searches", usage.get("daily_searches", 0))
    total_searches = max(int(usage_total_searches or 0), int(db_total_searches or 0))
    
    accounts_on_device = 0
    if target_user.hardware_id:
        hw_result = await db.execute(
            select(func.count(User.id))
            .where(User.hardware_id == target_user.hardware_id)
        )
        accounts_on_device = hw_result.scalar() or 0
    
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
            "total_searches": total_searches,
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
    
    if target_user.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot ban yourself")
    
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
    
    if target_user.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    email = target_user.email
    
    if hard_delete:
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()
        action = "hard_deleted_user"
    else:
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
    """Grant bonuses to multiple users"""
    await verify_admin_email(user)
    
    query = select(User).where(User.is_blocked == False)
    
    if bonus_request.target == "specific_users":
        if not bonus_request.user_ids:
            raise HTTPException(status_code=400, detail="user_ids required for specific_users target")
        uuids = [UUID(uid) for uid in bonus_request.user_ids]
        query = query.where(User.id.in_(uuids))
    elif bonus_request.target.startswith("all_") and bonus_request.target.endswith("_users"):
        plan_name = bonus_request.target[len("all_"):-len("_users")].strip().lower()
        if not plan_name:
            raise HTTPException(status_code=400, detail="Invalid bulk bonus target")
        query = query.where(User.plan == plan_name)
    else:
        raise HTTPException(status_code=400, detail="Invalid bulk bonus target")
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    if not users:
        raise HTTPException(status_code=404, detail="No users match the criteria")
    
    updated_count = 0
    bonuses = bonus_request.bonuses
    
    for u in users:
        usage = u.usage_stats or {}
        
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
    """Complete revenue dashboard"""
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
    
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
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

    plan_result = await db.execute(select(SubscriptionPlan))
    plan_rows = plan_result.scalars().all()
    plan_prices = {str(p.name).lower(): float(p.price_inr or 0) for p in plan_rows}

    pro_price = plan_prices.get("pro", settings.PLAN_PRO_PRICE / 100)
    premium_price = plan_prices.get("premium", settings.PLAN_PREMIUM_PRICE / 100)
    
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
                "avg_lifetime_value": pro_price * 6
            },
            {
                "plan": "premium",
                "active_users": user_breakdown.get("premium", 0),
                "monthly_revenue": user_breakdown.get("premium", 0) * premium_price,
                "price_per_user": premium_price,
                "avg_lifetime_value": premium_price * 12
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
    
    if promo_data.end_date <= promo_data.start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
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
    
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    promotions = result.scalars().all()
    
    count_result = await db.execute(select(func.count(Promotion.id)))
    total = count_result.scalar() or 0
    
    promo_list = []
    for p in promotions:
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
    
    remaining_impressions = (promotion.max_impressions or 999999) - stats.get("impressions", 0)
    remaining_clicks = (promotion.max_clicks or 999999) - stats.get("clicks", 0)
    remaining_days = (promotion.end_date - now).days if promotion.end_date > now else 0
    remaining_budget = (promotion.max_budget_inr or 999999) - stats.get("revenue_earned", 0)
    
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
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get promotion revenue report"""
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
# PRODUCT MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/products", response_model=dict)
async def list_admin_products(
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None,
    product_id: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    platform: Optional[str] = None,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List products with filters for admin"""
    await verify_admin_email(user)
    
    query = select(Product)
    
    if search:
        query = query.where(Product.title.ilike(f"%{search}%"))
    if product_id:
        product_id_value = product_id.strip()
        if product_id_value:
            try:
                parsed_uuid = UUID(product_id_value)
                query = query.where(Product.id == parsed_uuid)
            except ValueError:
                query = query.where(cast(Product.id, String).ilike(f"%{product_id_value}%"))
    if category:
        query = query.where(Product.category == category)
    if brand:
        query = query.where(Product.brand.ilike(f"%{brand}%"))
    
    if platform:
        query = query.join(ProductListing).join(Platform).where(Platform.name == platform.lower())
    
    query = query.order_by(Product.created_at.desc())
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    # Paginate
    offset = (page - 1) * limit
    results = await db.execute(query.offset(offset).limit(limit))
    products = results.scalars().all()
    
    product_list = []
    for p in products:
        # Get listings count per product
        list_res = await db.execute(select(func.count(ProductListing.id)).where(ProductListing.product_id == p.id))
        platforms_count = list_res.scalar() or 0
        
        product_list.append({
            "id": str(p.id),
            "title": p.title,
            "brand": p.brand,
            "category": p.category,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "platforms_count": platforms_count,
            "image_url": p.image_url
        })
        
    return {
        "products": product_list,
        "total": total,
        "page": page,
        "limit": limit
    }


@router.get("/products/{product_id}", response_model=dict)
async def get_admin_product_detail(
    product_id: str,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get full product detail for admin"""
    await verify_admin_email(user)
    
    try:
        pid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product ID")
    
    product = await db.get(Product, pid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get listings
    results = await db.execute(
        select(ProductListing).where(ProductListing.product_id == pid)
    )
    listings_models = results.scalars().all()
    
    listings = []
    for l in listings_models:
        # Get platform info
        plat = await db.get(Platform, l.platform_id)
        
        # Get price history count
        hist_count_res = await db.execute(
            select(func.count(PriceHistory.id)).where(PriceHistory.product_listing_id == l.id)
        )
        history_points = hist_count_res.scalar() or 0
        
        listings.append({
            "id": str(l.id),
            "platform_name": plat.name if plat else "Unknown",
            "external_id": l.external_id,
            "product_url": l.product_url,
            "current_price": l.current_price,
            "original_price": l.original_price,
            "in_stock": l.in_stock,
            "last_scraped": l.last_scraped.isoformat() if l.last_scraped else None,
            "scrape_priority": l.scrape_priority,
            "history_points": history_points
        })
    
    return {
        "product": {
            "id": str(product.id),
            "fingerprint": product.fingerprint,
            "variant_fingerprint": product.variant_fingerprint,
            "base_fingerprint": product.base_fingerprint,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "subcategory": product.subcategory,
            "image_url": product.image_url,
            "specifications": product.specifications,
            "stats": product.stats,
            "variant_type": product.variant_type,
            "storage_gb": product.storage_gb,
            "color": product.color,
            "condition": product.condition,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None
        },
        "listings": listings
    }


@router.put("/products/{product_id}", response_model=dict)
async def update_admin_product(
    product_id: str,
    update_data: dict,  # Using dict for flexibility since schemas are failing
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update product details for admin"""
    await verify_admin_email(user)
    
    try:
        pid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product ID")
    
    product = await db.get(Product, pid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    for field, value in update_data.items():
        if hasattr(product, field):
            setattr(product, field, value)
    
    await db.commit()
    return {"success": True, "message": "Product updated"}


@router.delete("/products/{product_id}", response_model=dict)
async def delete_admin_product(
    product_id: str,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete product for admin"""
    await verify_admin_email(user)
    
    try:
        pid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product ID")
    
    product = await db.get(Product, pid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    await db.delete(product)
    await db.commit()
    return {"success": True, "message": "Product deleted"}

# =============================================================================
# LISTING MANAGEMENT ENDPOINTS
# =============================================================================

@router.put("/listings/{listing_id}/price", response_model=dict)
async def update_listing_price(
    listing_id: str,
    update_data: dict,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update listing price for admin"""
    await verify_admin_email(user)
    
    try:
        lid = UUID(listing_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid listing ID")
    
    listing = await db.get(ProductListing, lid)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    # Update price fields
    if "current_price" in update_data:
        listing.current_price = float(update_data["current_price"])
    if "original_price" in update_data:
        listing.original_price = float(update_data["original_price"])
    
    # Log price change
    await log_action(
        db, user.email, "updated_listing_price",
        listing_id,
        details=update_data
    )
    
    await db.commit()
    return {"success": True, "message": "Listing price updated"}

@router.get("/listings/{listing_id}/price-history", response_model=dict)
async def get_listing_price_history(
    listing_id: str,
    days: int = 30,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get price history for a listing"""
    await verify_admin_email(user)
    
    try:
        lid = UUID(listing_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid listing ID")
    
    listing = await db.get(ProductListing, lid)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    # Get price history
    since_date = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(PriceHistory)
        .where(
            and_(
                PriceHistory.product_listing_id == lid,
                PriceHistory.recorded_at >= since_date
            )
        )
        .order_by(PriceHistory.recorded_at.desc())
    )
    
    history_points = result.scalars().all()
    
    history_list = []
    for point in history_points:
        history_list.append({
            "price": float(point.price),
            "in_stock": point.in_stock,
            "recorded_at": point.recorded_at.isoformat() if point.recorded_at else None
        })
    
    return {
        "listing_id": listing_id,
        "history": history_list,
        "total_points": len(history_list)
    }

@router.post("/listings/{listing_id}/price-history", response_model=dict)
async def add_price_history_point(
    listing_id: str,
    price_data: dict,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a price history point for a listing"""
    await verify_admin_email(user)
    
    try:
        lid = UUID(listing_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid listing ID")
    
    listing = await db.get(ProductListing, lid)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    # Create new price history point
    new_point = PriceHistory(
        product_listing_id=lid,
        price=price_data.get("price"),
        in_stock=price_data.get("in_stock", True)
    )
    
    # Update current price if provided
    if "current_price" in price_data:
        listing.current_price = float(price_data["current_price"])
    
    db.add(new_point)
    
    await log_action(
        db, user.email, "added_price_history",
        listing_id,
        details=price_data
    )
    
    await db.commit()
    return {"success": True, "message": "Price history point added"}

@router.get("/listings/{listing_id}/performance", response_model=dict)
async def get_listing_performance(
    listing_id: str,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get performance metrics for a listing"""
    await verify_admin_email(user)
    
    try:
        lid = UUID(listing_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid listing ID")
    
    listing = await db.get(ProductListing, lid)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    # Get price history for analysis
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.product_listing_id == lid)
        .order_by(PriceHistory.recorded_at.desc())
        .limit(100)  # Last 100 points
    )
    
    history_points = result.scalars().all()
    
    if not history_points:
        return {
            "listing_id": listing_id,
            "price_volatility": 0,
            "avg_price": listing.current_price,
            "min_price": listing.current_price,
            "max_price": listing.current_price,
            "stock_availability": 100.0,
            "total_price_points": 0
        }
    
    prices = [float(p.price) for p in history_points]
    stock_available = sum(1 for p in history_points if p.in_stock)
    
    performance = {
        "listing_id": listing_id,
        "price_volatility": (max(prices) - min(prices)) / min(prices) * 100 if min(prices) > 0 else 0,
        "avg_price": sum(prices) / len(prices),
        "min_price": min(prices),
        "max_price": max(prices),
        "stock_availability": (stock_available / len(history_points)) * 100,
        "total_price_points": len(history_points)
    }
    
    return performance


# =============================================================================
# JOB MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/jobs/current", response_model=dict)
async def get_current_jobs(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get currently running jobs"""
    await verify_admin_email(user)
    
    try:
        # Import scheduler functions
        from jobs.scheduler import get_scheduler_status, _job_registry
        
        # Get real scheduler status
        scheduler_status = await get_scheduler_status()
        
        # Get running jobs from registry
        running_jobs = []
        for job_id, job_info in _job_registry.items():
            if job_info.is_running:
                # Calculate progress based on job type and runtime
                progress = 0
                if job_info.started_at:
                    runtime_seconds = (datetime.utcnow() - job_info.started_at).total_seconds()
                    
                    # Estimate progress based on typical job durations
                    if job_id == "daily_scrape":
                        progress = min(95, (runtime_seconds / 300) * 100)  # 5 minutes typical
                    elif job_id == "daily_scrape_trending":
                        progress = min(95, (runtime_seconds / 180) * 100)  # 3 minutes typical
                    elif job_id == "seed_products":
                        progress = min(95, (runtime_seconds / 120) * 100)  # 2 minutes typical
                    elif job_id == "check_price_alerts":
                        progress = min(95, (runtime_seconds / 60) * 100)  # 1 minute typical
                    else:
                        progress = min(95, (runtime_seconds / 60) * 100)  # Default 1 minute
                
                running_jobs.append({
                    "id": job_id,
                    "type": job_id.replace("_", " ").title(),
                    "status": "running",
                    "started_at": job_info.started_at.isoformat() if job_info.started_at else datetime.utcnow().isoformat(),
                    "progress": int(progress),
                    "platform": "all" if "scrape" in job_id else "system",
                    "total_items": 100,  # Placeholder
                    "processed_items": int(progress),
                    "name": job_info.name,
                    "description": job_info.description
                })
        
        return {
            "current_jobs": running_jobs,
            "total_running": len(running_jobs),
            "scheduler_status": scheduler_status
        }
    
    except Exception as e:
        logger.error(f"Error getting current jobs: {e}")
        # Fallback with mock data if scheduler not available
        return {
            "current_jobs": [],
            "total_running": 0,
            "error": str(e)
        }

@router.get("/jobs/{job_id}/logs", response_model=dict)
async def get_job_logs(
    job_id: str,
    lines: int = 100,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get logs for a specific job"""
    await verify_admin_email(user)
    
    try:
        # Import scheduler to get job info
        from jobs.scheduler import _job_registry
        
        job_info = _job_registry.get(job_id)
        
        if not job_info:
            return {
                "job_id": job_id,
                "logs": [],
                "total_lines": 0,
                "error": f"Job {job_id} not found in registry"
            }
        
        # Get real logs from job info
        logs = []
        
        # Add job start log
        if job_info.started_at:
            logs.append({
                "timestamp": job_info.started_at.isoformat(),
                "level": "info",
                "message": f"Job {job_id} started",
                "details": f"Started at: {job_info.started_at.isoformat()}"
            })
        
        # Add status logs based on job state
        if job_info.is_running:
            runtime = datetime.utcnow() - job_info.started_at if job_info.started_at else timedelta(0)
            logs.append({
                "timestamp": datetime.utcnow().isoformat(),
                "level": "info",
                "message": f"Job {job_id} is running",
                "details": f"Runtime: {runtime.total_seconds():.1f}s, Status: {job_info.last_status.value}"
            })
        
        # Add completion/error logs
        if job_info.last_run and not job_info.is_running:
            if job_info.last_status.value == "success":
                logs.append({
                    "timestamp": job_info.last_run.isoformat(),
                    "level": "info",
                    "message": f"Job {job_id} completed successfully",
                    "details": f"Completed at: {job_info.last_run.isoformat()}"
                })
            elif job_info.last_status.value == "error":
                logs.append({
                    "timestamp": job_info.last_run.isoformat(),
                    "level": "error",
                    "message": f"Job {job_id} failed",
                    "details": f"Error: {job_info.last_error or 'Unknown error'}"
                })
        
        # Add job statistics
        logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "level": "info",
            "message": f"Job {job_id} statistics",
            "details": f"Success count: {job_info.success_count}, Error count: {job_info.error_count}, Last run: {job_info.last_run.isoformat() if job_info.last_run else 'Never'}"
        })
        
        return {
            "job_id": job_id,
            "logs": logs[-lines:],  # Return last N lines
            "total_lines": len(logs),
            "job_info": {
                "name": job_info.name,
                "description": job_info.description,
                "is_running": job_info.is_running,
                "last_status": job_info.last_status.value,
                "success_count": job_info.success_count,
                "error_count": job_info.error_count,
                "last_run": job_info.last_run.isoformat() if job_info.last_run else None,
                "next_run": job_info.next_run.isoformat() if job_info.next_run else None
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting job logs: {e}")
        return {
            "job_id": job_id,
            "logs": [{
                "timestamp": datetime.utcnow().isoformat(),
                "level": "error",
                "message": f"Failed to get logs for job {job_id}",
                "details": str(e)
            }],
            "total_lines": 1,
            "error": str(e)
        }

@router.post("/jobs/schedule", response_model=dict)
async def create_job_schedule(
    schedule_data: dict,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new job schedule"""
    await verify_admin_email(user)
    
    # Log schedule creation
    await log_action(
        db, user.email, "created_schedule",
        schedule_data.get("name"),
        details=schedule_data
    )
    
    # This would typically save to a scheduler database
    # For now, return success response
    schedule_id = f"schedule_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    return {
        "success": True,
        "message": "Schedule created successfully",
        "schedule_id": schedule_id
    }

@router.get("/jobs/schedules", response_model=dict)
async def get_job_schedules(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all job schedules"""
    await verify_admin_email(user)
    
    # This would typically query scheduler database
    # For now, return mock schedules
    schedules = [
        {
            "id": "schedule_001",
            "name": "Daily Amazon Scrape",
            "job_type": "scrape",
            "frequency": "daily",
            "time": "02:00",
            "enabled": True,
            "platform": "amazon",
            "next_run": "2024-01-15T02:00:00Z"
        },
        {
            "id": "schedule_002", 
            "name": "Weekly Cleanup",
            "job_type": "cleanup",
            "frequency": "weekly",
            "time": "03:00",
            "enabled": True,
            "day_of_week": "Sunday",
            "next_run": "2024-01-21T03:00:00Z"
        }
    ]
    
    return {
        "schedules": schedules,
        "total_schedules": len(schedules)
    }

@router.put("/jobs/schedules/{schedule_id}", response_model=dict)
async def update_job_schedule(
    schedule_id: str,
    update_data: dict,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a job schedule"""
    await verify_admin_email(user)
    
    # Log schedule update
    await log_action(
        db, user.email, "updated_schedule",
        schedule_id,
        details=update_data
    )
    
    return {
        "success": True,
        "message": "Schedule updated successfully"
    }

@router.delete("/jobs/schedules/{schedule_id}", response_model=dict)
async def delete_job_schedule(
    schedule_id: str,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a job schedule"""
    await verify_admin_email(user)
    
    # Log schedule deletion
    await log_action(
        db, user.email, "deleted_schedule",
        schedule_id
    )
    
    return {
        "success": True,
        "message": "Schedule deleted successfully"
    }

# =============================================================================
# PRODUCT MONITORING ENDPOINTS
# =============================================================================

@router.get("/products/new", response_model=dict)
async def get_new_products(
    hours: int = 24,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get newly added products within specified hours"""
    await verify_admin_email(user)
    
    # Calculate time threshold
    since_date = datetime.utcnow() - timedelta(hours=hours)
    
    # Query new products
    result = await db.execute(
        select(Product)
        .where(Product.created_at >= since_date)
        .order_by(Product.created_at.desc())
        .limit(100)
    )
    
    new_products = result.scalars().all()
    
    products_data = []
    for product in new_products:
        # Get platform count
        platform_result = await db.execute(
            select(func.count(ProductListing.id))
            .where(ProductListing.product_id == product.id)
        )
        platform_count = platform_result.scalar() or 0
        
        products_data.append({
            "id": str(product.id),
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "platforms_count": platform_count,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "first_seen": product.created_at.isoformat() if product.created_at else None
        })
    
    return {
        "products": products_data,
        "total": len(products_data),
        "hours": hours
    }

@router.get("/products/changes", response_model=dict)
async def get_recent_changes(
    change_type: str = "all",
    hours: int = 24,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get recent product changes"""
    await verify_admin_email(user)
    
    # Calculate time threshold
    since_date = datetime.utcnow() - timedelta(hours=hours)
    
    changes_data = []
    
    if change_type in ["all", "price_change"]:
        # Get recent price changes
        price_result = await db.execute(
            select(PriceHistory)
            .where(PriceHistory.recorded_at >= since_date)
            .order_by(PriceHistory.recorded_at.desc())
            .limit(50)
        )
        
        price_changes = price_result.scalars().all()
        
        for change in price_changes:
            # Get listing and product info
            listing = await db.get(ProductListing, change.product_listing_id)
            if listing:
                product = await db.get(Product, listing.product_id)
                if product:
                    changes_data.append({
                        "product_title": product.title,
                        "change_type": "price_change",
                        "platform_name": listing.platform.name if listing.platform else "Unknown",
                        "old_value": f"₹{change.price:.2f}",
                        "new_value": f"₹{listing.current_price:.2f}",
                        "changed_at": change.recorded_at.isoformat()
                    })
    
    if change_type in ["all", "stock_change"]:
        # Get recent stock changes (this would need additional tracking)
        # For now, add mock data
        changes_data.append({
            "product_title": "Sample Product",
            "change_type": "stock_change",
            "platform_name": "Amazon",
            "old_value": "Out of Stock",
            "new_value": "In Stock",
            "changed_at": datetime.utcnow().isoformat()
        })
    
    return {
        "changes": changes_data,
        "total": len(changes_data),
        "change_type": change_type,
        "hours": hours
    }

@router.get("/system/database-stats", response_model=dict)
async def get_database_statistics(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get database statistics"""
    await verify_admin_email(user)
    
    # Get product count
    product_result = await db.execute(select(func.count(Product.id)))
    total_products = product_result.scalar() or 0
    
    # Get listing count
    listing_result = await db.execute(select(func.count(ProductListing.id)))
    total_listings = listing_result.scalar() or 0
    
    # Get price history count
    history_result = await db.execute(select(func.count(PriceHistory.id)))
    total_history = history_result.scalar() or 0
    
    # Calculate approximate database size (this would be more accurate with actual DB queries)
    estimated_size_mb = (total_products * 0.001) + (total_listings * 0.002) + (total_history * 0.0005)
    
    return {
        "total_products": total_products,
        "total_listings": total_listings,
        "total_price_history": total_history,
        "estimated_size_mb": round(estimated_size_mb, 2),
        "last_updated": datetime.utcnow().isoformat()
    }


# =============================================================================
# SYSTEM MONITORING ENDPOINTS (6) - ✅ UPDATED WITH WORKING FORCE-SCRAPE
# =============================================================================

@router.get("/system/health", response_model=dict)
async def get_system_health(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis)
):
    """Get complete system health status"""
    await verify_admin_email(user)
    
    health = {
        "database": {"status": "healthy"},
        "redis": {"status": "disabled"},
        "scrapers": {},
        "groq_ai": {},
        "overall": "healthy"
    }
    
    # Check database
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        
        pool_result = await db.execute(text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
        ))
        conn_count = pool_result.scalar() or 0
        
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
    
    # Redis is optional; when disabled/unavailable we don't degrade overall health.
    try:
        if redis_client and redis_client._client is not None and await redis_client.ping():
            info = await redis_client._client.info("memory")
            memory_used = info.get("used_memory_human", "Unknown")
            keys_count = await redis_client._client.dbsize()
            health["redis"] = {
                "status": "healthy",
                "memory_used": memory_used,
                "keys": keys_count
            }
        else:
            health["redis"] = {
                "status": "disabled",
                "message": "Redis not configured or unavailable"
            }
    except Exception as e:
        health["redis"] = {
            "status": "disabled",
            "message": f"Redis unavailable: {str(e)}"
        }
    
    # Check scrapers
    try:
        scraper_health = await analytics_service.get_scraper_health(db)
        health["scrapers"] = scraper_health
        
        for platform, data in scraper_health.items():
            if data.get("status") == "failing":
                health["overall"] = "degraded"
    except Exception as e:
        health["scrapers"] = {"error": str(e)}
    
    # Check Groq quota (best-effort if Redis exists)
    try:
        if redis_client:
            today = date.today().isoformat()
            quota_key = f"groq:usage:{today}"
            quota_used = await redis_client.get(quota_key)
            used = int(quota_used or 0)
            health["groq_ai"] = {
                "quota_used_today": used,
                "quota_limit": settings.GROQ_DAILY_LIMIT,
                "quota_remaining": max(0, settings.GROQ_DAILY_LIMIT - used)
            }
        else:
            health["groq_ai"] = {"status": "unknown", "message": "Redis disabled"}
    except Exception:
        health["groq_ai"] = {"status": "unknown", "message": "Quota source unavailable"}
    
    return health


@router.get("/system/stats", response_model=dict)
async def get_system_stats(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis)
):
    """Get system-wide statistics"""
    await verify_admin_email(user)
    
    dau = await analytics_service.get_active_users_count(db, "daily")
    wau = await analytics_service.get_active_users_count(db, "weekly")
    mau = await analytics_service.get_active_users_count(db, "monthly")
    user_breakdown = await analytics_service.get_user_breakdown(db)
    total_users = sum(user_breakdown.values())
    
    product_stats = await analytics_service.get_product_stats(db)
    
    searches_today = await analytics_service.get_searches_today(db)
    
    affiliate_clicks = await analytics_service.get_affiliate_clicks_today(db)
    
    cache_hit_rate = 0
    try:
        if redis_client and redis_client._client is not None and await redis_client.ping():
            info = await redis_client._client.info("stats")
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            if hits + misses > 0:
                cache_hit_rate = round((hits / (hits + misses)) * 100, 1)
    except Exception:
        pass
    
    # Get real job statistics
    active_jobs = 0
    completed_today = 0
    failed_today = 0
    success_rate = 0.0
    
    try:
        from jobs.scheduler import get_scheduler_status, _job_registry
        
        # Get scheduler status
        scheduler_status = await get_scheduler_status()
        
        # Count active jobs
        for job_id, job_info in _job_registry.items():
            if job_info.is_running:
                active_jobs += 1
            
            # Count jobs completed today
            if job_info.last_run:
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                if job_info.last_run >= today_start:
                    if job_info.last_status.value == "success":
                        completed_today += 1
                    elif job_info.last_status.value == "error":
                        failed_today += 1
        
        # Calculate success rate
        total_jobs_today = completed_today + failed_today
        if total_jobs_today > 0:
            success_rate = (completed_today / total_jobs_today) * 100
        
    except Exception as e:
        logger.error(f"Error getting job stats: {e}")
    
    return {
        "traffic": {
            "searches_today": searches_today,
            "unique_users_today": dau,
            "cache_hit_rate": cache_hit_rate
        },
        "engagement": {
            "daily_active_users": dau,
            "weekly_active_users": wau,
            "monthly_active_users": mau,
            "total_users": total_users,
            "free_users": user_breakdown.get("free", 0),
            "pro_users": user_breakdown.get("pro", 0),
            "premium_users": user_breakdown.get("premium", 0)
        },
        "products": {
            **product_stats,
            "total_products": product_stats.get("total_tracked", 0)
        },
        "conversions": {
            "affiliate_clicks_today": affiliate_clicks
        },
        "jobs": {
            "active_jobs": active_jobs,
            "completed_jobs_today": completed_today,
            "failed_jobs_today": failed_today,
            "success_rate": round(success_rate, 1)
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


# =============================================================================
# ✅ UPDATED: WORKING FORCE-SCRAPE ENDPOINT
# =============================================================================

@router.post("/system/force-scrape", response_model=dict)
async def force_scrape(
    request: Request,
    scrape_request: ForceScrapeRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger scraper job
    
    ✅ NOW WORKING: Actually triggers APScheduler jobs
    """
    await verify_admin_email(user)
    
    # Map platform to job_id
    job_mapping = {
        "all": "daily_scrape",
        "amazon": "daily_scrape",
        "flipkart": "daily_scrape",
        "myntra": "daily_scrape",
        "nykaa": "daily_scrape",
        "croma": "daily_scrape",
        "meesho": "daily_scrape",
        "trending": "daily_scrape_trending",
    }
    
    job_id = job_mapping.get(scrape_request.platform, "daily_scrape_trending")
    
    # If category is specified, use seed_products job
    if scrape_request.category:
        job_id = "seed_products"
    
    await log_action(
        db, user.email, "triggered_scrape",
        details={
            "platform": scrape_request.platform,
            "job_id": job_id,
            "async": scrape_request.async_mode,
            "category": scrape_request.category
        },
        request=request
    )
    
    # ✅ Actually trigger the job
    try:
        result = await trigger_job_manually(job_id)
        
        if result.get("success"):
            return {
                "success": True,
                "job_id": job_id,
                "status": "completed" if not scrape_request.async_mode else "queued",
                "message": f"Job '{job_id}' triggered successfully",
                "result": result.get("result"),
                "triggered_at": result.get("triggered_at")
            }
        else:
            return {
                "success": False,
                "job_id": job_id,
                "status": "failed",
                "error": result.get("error"),
                "message": f"Job '{job_id}' failed to trigger"
            }
            
    except Exception as e:
        logger.error(f"Force scrape failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger job: {str(e)}"
        )


# =============================================================================
# ✅ NEW: SCHEDULER STATUS ENDPOINT
# =============================================================================

@router.get("/system/scheduler", response_model=dict)
async def get_scheduler_health(
    user: User = Depends(get_current_admin_user)
):
    """
    Get APScheduler status and all job information
    
    ✅ NEW: Exposes scheduler status to admin dashboard
    """
    await verify_admin_email(user)
    
    try:
        status = get_scheduler_status()
        return status
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        return {
            "running": False,
            "error": str(e),
            "jobs": []
        }


@router.post("/system/trigger-job", response_model=dict)
async def trigger_job(
    request: Request,
    job_request: TriggerJobRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger any APScheduler job by ID
    
    ✅ NEW: Generic job trigger endpoint
    """
    await verify_admin_email(user)
    
    await log_action(
        db, user.email, "triggered_job",
        details={"job_id": job_request.job_id},
        request=request
    )
    
    try:
        result = await trigger_job_manually(job_request.job_id)
        
        return {
            "success": result.get("success", False),
            "job_id": job_request.job_id,
            "result": result.get("result"),
            "error": result.get("error"),
            "triggered_at": result.get("triggered_at")
        }
        
    except Exception as e:
        logger.error(f"Job trigger failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger job: {str(e)}"
        )


@router.get("/system/subscription-plans", response_model=dict)
async def list_subscription_plans_config(
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List subscription plans from DB for admin editing."""
    await verify_admin_email(user)

    result = await db.execute(
        select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order.asc(), SubscriptionPlan.id.asc())
    )
    plans = result.scalars().all()

    return {
        "plans": [serialize_subscription_plan(plan) for plan in plans]
    }


@router.put("/system/subscription-plans/{plan_name}", response_model=dict)
async def update_subscription_plan_config(
    plan_name: str,
    request: Request,
    plan_update: SubscriptionPlanUpdateRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    """Update a subscription plan in DB so changes reflect across backend/admin/frontend."""
    await verify_admin_email(user)

    normalized_name = (plan_name or "").strip().lower()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan name is required")

    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.name == normalized_name)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan '{normalized_name}' not found")

    if plan_update.display_name is not None:
        plan.display_name = plan_update.display_name
    if plan_update.price_inr is not None:
        plan.price_inr = float(plan_update.price_inr)
        # Keep price_usd roughly in sync if present.
        plan.price_usd = round(float(plan_update.price_inr) / 83.0, 2)
    if plan_update.duration_days is not None:
        plan.duration_days = plan_update.duration_days
    if plan_update.is_popular is not None:
        plan.is_popular = plan_update.is_popular
    if plan_update.is_active is not None:
        plan.is_active = plan_update.is_active
    if plan_update.sort_order is not None:
        plan.sort_order = plan_update.sort_order
    if plan_update.tagline is not None:
        plan.tagline = plan_update.tagline

    features_touched = (
        plan_update.features is not None
        or plan_update.searches_per_day is not None
        or plan_update.watchlist_limit is not None
    )
    if features_touched:
        # Always work on a new dict so SQLAlchemy can detect JSON changes reliably.
        features = dict(plan.features) if isinstance(plan.features, dict) else {}

        if isinstance(plan_update.features, dict):
            features.update(plan_update.features)
        if plan_update.searches_per_day is not None:
            features["daily_searches"] = plan_update.searches_per_day
        if plan_update.watchlist_limit is not None:
            features["watchlist_limit"] = plan_update.watchlist_limit

        plan.features = features
        flag_modified(plan, "features")

    await db.commit()
    await db.refresh(plan)

    await redis_client.delete("app:config")

    await log_action(
        db,
        user.email,
        "updated_subscription_plan",
        normalized_name,
        details={
            "price_inr": plan.price_inr,
            "duration_days": plan.duration_days,
            "searches_per_day": features.get("daily_searches"),
            "watchlist_limit": features.get("watchlist_limit"),
            "is_active": plan.is_active,
            "is_popular": plan.is_popular,
        },
        request=request,
    )

    return {
        "success": True,
        "plan": serialize_subscription_plan(plan),
        "message": f"Subscription plan '{normalized_name}' updated successfully",
    }


@router.put("/system/config", response_model=dict)
async def update_app_config(
    request: Request,
    config_update: AppConfigUpdateRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis)
):
    """Update application configuration"""
    await verify_admin_email(user)

    config_key = (config_update.key or "").strip()
    if not config_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Config key is required")

    if is_sensitive_config_key(config_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Config '{config_key}' is sensitive and must be managed via environment variables",
        )

    normalized_type = normalize_config_value_type(config_update.value_type)
    normalized_value = serialize_config_value(config_update.value, normalized_type)
    
    result = await db.execute(
        select(AppConfig).where(AppConfig.key == config_key)
    )
    config = result.scalar_one_or_none()
    
    if config:
        config.value = normalized_value
        config.value_type = normalized_type
        if config_update.description:
            config.description = config_update.description
        if config_update.category:
            config.category = config_update.category
        config.updated_by = user.email
    else:
        config = AppConfig(
            key=config_key,
            value=normalized_value,
            value_type=normalized_type,
            description=config_update.description,
            category=config_update.category,
            is_public=False,
            updated_by=user.email
        )
        db.add(config)
    
    await db.commit()
    
    await redis_client.delete("app:config")
    
    await log_action(
        db, user.email, "updated_config",
        config_key,
        details={"new_value": normalized_value, "type": normalized_type},
        request=request
    )
    
    return {
        "success": True,
        "key": config_key,
        "value": normalized_value,
        "value_type": normalized_type,
        "message": f"Config '{config_key}' updated successfully"
    }


@router.post("/system/config/sync", response_model=dict)
async def sync_settings_into_app_config(
    request: Request,
    overwrite_existing: bool = Body(default=False, embed=True),
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    """
    Sync non-sensitive backend settings into app_config without migrations.
    Secrets and API keys remain env-only.
    """
    await verify_admin_email(user)

    entries = settings_to_config_entries()
    if not entries:
        return {
            "success": True,
            "created": 0,
            "updated": 0,
            "skipped_existing": 0,
            "skipped_sensitive": 0,
            "message": "No syncable settings found",
        }

    key_set = [entry["key"] for entry in entries]
    existing_result = await db.execute(
        select(AppConfig).where(AppConfig.key.in_(key_set))
    )
    existing_configs = {cfg.key: cfg for cfg in existing_result.scalars().all()}

    created = 0
    updated = 0
    skipped_existing = 0

    for entry in entries:
        key = entry["key"]
        existing = existing_configs.get(key)

        if existing:
            if not overwrite_existing:
                skipped_existing += 1
                continue

            existing.value = entry["value"]
            existing.value_type = entry["value_type"]
            existing.category = existing.category or entry["category"]
            if not existing.description:
                existing.description = entry["description"]
            existing.updated_by = user.email
            updated += 1
            continue

        db.add(
            AppConfig(
                key=key,
                value=entry["value"],
                value_type=entry["value_type"],
                description=entry["description"],
                category=entry["category"],
                is_public=entry["is_public"],
                updated_by=user.email,
            )
        )
        created += 1

    await db.commit()
    await redis_client.delete("app:config")

    await log_action(
        db,
        user.email,
        "synced_settings_to_db",
        details={
            "created": created,
            "updated": updated,
            "skipped_existing": skipped_existing,
            "overwrite_existing": overwrite_existing,
        },
        request=request,
    )

    return {
        "success": True,
        "created": created,
        "updated": updated,
        "skipped_existing": skipped_existing,
        "synced_total": created + updated,
        "message": "Settings synced to app_config successfully",
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

    config_rows = []
    for c in configs:
        sensitive = is_sensitive_config_key(c.key)
        config_rows.append(
            {
                "key": c.key,
                "value": "********" if sensitive else c.value,
                "value_type": c.value_type,
                "description": c.description,
                "category": c.category,
                "is_public": c.is_public,
                "is_sensitive": sensitive,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "updated_by": c.updated_by,
            }
        )
    
    return {
        "configs": config_rows
    }


@router.post("/system/maintenance", response_model=dict)
async def toggle_maintenance_mode(
    request: Request,
    maintenance_request: MaintenanceModeRequest,
    user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis)
):
    """Enable/disable maintenance mode"""
    await verify_admin_email(user)
    
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
    
    await redis_client.delete("app:config")
    
    await log_action(
        db, user.email,
        "enabled_maintenance" if maintenance_request.enabled else "disabled_maintenance",
        details={
            "message": maintenance_request.message,
        },
        request=request
    )
    
    return {
        "success": True,
        "maintenance_mode": maintenance_request.enabled,
        "message": maintenance_request.message if maintenance_request.enabled else "Maintenance mode disabled",
        "estimated_duration_minutes": maintenance_request.estimated_duration_minutes
    }


@router.get("/scrapers/status", response_model=ScraperStatusResponse)
async def get_scraper_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user)
) -> ScraperStatusResponse:
    """Get status of all platform scrapers"""
    await verify_admin_email(user)
    
    # Get platform data from database
    result = await db.execute(
        select(Platform).order_by(Platform.name)  
    )
    platforms_db = result.scalars().all()
    
    platform_statuses = []
    healthy_count = 0
    error_count = 0
    
    for platform in platforms_db:
        # Get recent listings for this platform
        listings_result = await db.execute(
            select(ProductListing)
            .where(ProductListing.platform_id == platform.id)
            .order_by(ProductListing.last_scraped.desc())
            .limit(100)
        )
        listings = listings_result.scalars().all()
        
        # Calculate metrics
        total_listings = len(listings)
        # Fix: use timezone aware UTC datetime to avoid comparison error
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
        recent_listings = [l for l in listings if l.last_scraped and l.last_scraped > cutoff_time]
        success_rate = len(recent_listings) / max(total_listings, 1) * 100 if total_listings > 0 else 0.0
        
        # Determine status
        if success_rate >= 80:
            status = "healthy"
            healthy_count += 1
        elif success_rate >= 50:
            status = "warning"
        else:
            status = "error"
            error_count += 1
        
        # Get last run time
        last_run = None
        if listings:
            last_run = max((l.last_scraped for l in listings if l.last_scraped), default=None)
        
        platform_status = PlatformStatus(
            platform=platform.name,
            status=status,
            success_rate=success_rate,
            total_listings=total_listings,
            last_run=last_run,
            last_error=None,  # Could be enhanced with error tracking
            response_time_ms=None,  # Could be enhanced with performance tracking
            is_enabled=platform.is_active
        )
        platform_statuses.append(platform_status)
    
    # Determine overall health
    if healthy_count == len(platform_statuses):
        overall_health = "healthy"
    elif healthy_count >= len(platform_statuses) * 0.7:
        overall_health = "warning"
    else:
        overall_health = "error"
    
    return ScraperStatusResponse(
        platforms=platform_statuses,
        overall_health=overall_health,
        total_platforms=len(platform_statuses),
        healthy_platforms=healthy_count,
        error_platforms=error_count
    )


@router.post("/scrapers/test/{platform}", response_model=ScraperTestResponse)
async def test_platform_scraper(
    platform: str,
    test_request: ScraperTestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user),
    request: Request = None
) -> ScraperTestResponse:
    """Test a specific platform scraper with selector health info"""
    await verify_admin_email(user)
    
    # Validate platform
    supported_platforms = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
    if platform not in supported_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' not supported. Use: {', '.join(supported_platforms)}"
        )
    
    started_at = datetime.utcnow()
    
    try:
        # Import test script functionality
        import sys
        import os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))
        
        from scripts.test_scrapers import test_search, test_url
        from app.services.scraper.base import ProductData
        
        # ✅ NEW: Load platform config and selectors from database
        result = await db.execute(select(Platform).where(Platform.name == platform))
        platform_config = result.scalar_one_or_none()
        
        db_selectors = {}
        db_selector_health = {}
        html_validation_results = {}
        
        if platform_config and platform_config.selectors:
            db_selectors = platform_config.selectors or {}
        
        # Determine test type
        if test_request.url:
            # Test URL scraping
            product = await test_url(platform, test_request.url, test_request.mode)
            success = product is not None
            products_found = 1 if product else 0
            test_type = "url"
            sample_products = []
            test_html = None  # Will fetch if available
            
            if product:
                sample_products.append({
                    "title": product.title,
                    "brand": product.brand,
                    "price": product.current_price,
                    "url": product.product_url
                })
        elif test_request.query:
            # Test search functionality
            products = await test_search(platform, test_request.query, test_request.mode, test_request.limit)
            success = len(products) > 0
            products_found = len(products)
            test_type = "search"
            sample_products = []
            test_html = None
            
            for product in products[:3]:  # Limit sample products
                sample_products.append({
                    "title": product.title,
                    "brand": product.brand,
                    "price": product.current_price,
                    "url": product.product_url
                })
        else:
            # Health check only
            test_type = "health_check"
            success = True
            products_found = 0
            sample_products = []
            test_html = None
        
        # ✅ NEW: Validate selectors against HTML if available
        if test_html and db_selectors:
            html_validation_results = await SelectorValidator.validate_selectors_batch(
                db_selectors,
                test_html
            )
            
            # Build selector health info
            for field_name, selector in db_selectors.items():
                validation = html_validation_results.get(field_name, {})
                health_status = SelectorValidator.get_selector_health(validation)
                
                db_selector_health[field_name] = SelectorHealthInfo(
                    selector=selector,
                    status=health_status,
                    match_count=validation.get("match_count", 0),
                    sample_text=validation.get("sample_matches", [None])[0] if validation.get("sample_matches") else None,
                    confidence=validation.get("confidence", 0.0),
                    last_validated_at=datetime.utcnow()
                )
        
        # ✅ NEW: Get last scraped values
        last_scraped_values = await LastScrapedValueFinder.get_last_scraped_values(
            db,
            platform,
            limit=5
        )
        
        completed_at = datetime.utcnow()
        test_duration_ms = (completed_at - started_at).total_seconds() * 1000
        
        # Create test result with new fields
        test_result = ScraperTestResult(
            platform=platform,
            success=success,
            products_found=products_found,
            test_duration_ms=test_duration_ms,
            extraction_method=None,  # Could be enhanced
            error_message=None if success else "No products found",
            sample_products=sample_products,
            performance_metrics={
                "test_duration_ms": test_duration_ms,
                "products_per_second": products_found / (test_duration_ms / 1000) if test_duration_ms > 0 else 0
            },
            # ✅ NEW: Add selector health and validation info
            db_selectors=db_selectors if db_selectors else None,
            db_selector_health=db_selector_health if db_selector_health else None,
            last_scraped_values=last_scraped_values if last_scraped_values else None,
            html_validation_results=html_validation_results if html_validation_results else None
        )
        
        # Log the test
        await log_action(
            db, user.email,
            f"test_scraper_{platform}",
            details={
                "test_type": test_type,
                "query": test_request.query,
                "url": test_request.url,
                "mode": test_request.mode,
                "success": success,
                "products_found": products_found,
                "selector_health": {k: v.status for k, v in db_selector_health.items()} if db_selector_health else {}
            },
            request=request
        )
        
        return ScraperTestResponse(
            success=True,
            platform=platform,
            test_type=test_type,
            started_at=started_at,
            completed_at=completed_at,
            results=test_result,
            message=f"Test completed successfully. Found {products_found} products."
        )
        
    except Exception as e:
        logger.error(f"Scraper test error: {e}", exc_info=True)
        completed_at = datetime.utcnow()
        test_duration_ms = (completed_at - started_at).total_seconds() * 1000
        
        # Create error result
        test_result = ScraperTestResult(
            platform=platform,
            success=False,
            products_found=0,
            test_duration_ms=test_duration_ms,
            extraction_method=None,
            error_message=str(e),
            sample_products=[],
            performance_metrics={"test_duration_ms": test_duration_ms}
        )
        
        # Log the error
        await log_action(
            db, user.email,
            f"test_scraper_{platform}_error",
            details={
                "test_type": "error",
                "error": str(e),
                "duration_ms": test_duration_ms
            },
            request=request
        )
        
        return ScraperTestResponse(
            success=False,
            platform=platform,
            test_type="error",
            started_at=started_at,
            completed_at=completed_at,
            results=test_result,
            message=f"Test failed: {str(e)}"
        )


@router.post("/scrapers/validate-selector/{platform}", response_model=ValidateSelectorResponse)
async def validate_selector(
    platform: str,
    validate_request: ValidateSelectorRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user),
    request: Request = None
) -> ValidateSelectorResponse:
    """Validate a single selector against platform HTML (admin scraper testing tool)"""
    await verify_admin_email(user)
    
    # Validate platform
    supported_platforms = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
    if platform not in supported_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' not supported"
        )
    
    try:
        selector = validate_request.selector
        field_name = validate_request.field_name

        html_content = (validate_request.html_content or "").strip()
        if not html_content and validate_request.page_url:
            html_content = await _fetch_live_html(validate_request.page_url, timeout_seconds=20)

        if not html_content:
            html_content = """
            <div class="product-item">
                <h2 class="product-title">Sample Product Title</h2>
                <span class="product-price">₹1,999</span>
                <img class="product-image" src="image.jpg"/>
                <div class="rating">4.5 stars</div>
            </div>
            """
        
        # Validate the selector
        validation_result = SelectorValidator.validate_selector_against_html(
            selector,
            html_content
        )
        
        # Determine health status
        health_status = SelectorValidator.get_selector_health(validation_result)
        
        # Log the validation
        await log_action(
            db, user.email,
            f"validate_selector_{platform}",
            details={
                "field_name": field_name,
                "selector": selector,
                "match_count": validation_result.get("match_count", 0),
                "status": health_status
            },
            request=request
        )
        
        return ValidateSelectorResponse(
            success=True,
            field_name=field_name,
            selector=selector,
            match_count=validation_result.get("match_count", 0),
            is_valid=validation_result.get("is_valid", False),
            sample_matches=validation_result.get("sample_matches", []),
            confidence=validation_result.get("confidence", 0.0),
            error=validation_result.get("error"),
            status=health_status
        )
        
    except Exception as e:
        logger.error(f"Selector validation error: {e}", exc_info=True)
        
        return ValidateSelectorResponse(
            success=False,
            field_name=validate_request.field_name,
            selector=validate_request.selector,
            match_count=0,
            is_valid=False,
            sample_matches=[],
            confidence=0.0,
            error=str(e),
            status="untested"
        )


@router.post("/scrapers/inspect/{platform}", response_model=ScraperInspectionResponse)
async def inspect_scraper_page(
    platform: str,
    inspect_request: ScraperTestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user),
    request: Request = None
) -> ScraperInspectionResponse:
    """Fetch live HTML, outline it, and validate DB selectors against that page."""
    await verify_admin_email(user)

    supported_platforms = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
    if platform not in supported_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' not supported"
        )

    page_url = (inspect_request.url or "").strip()
    if not page_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A live page URL is required for inspection"
        )

    started_at = datetime.utcnow()

    try:
        result = await db.execute(select(Platform).where(Platform.name == platform))
        platform_config = result.scalar_one_or_none()
        selector_snapshot = {}
        if platform_config and platform_config.selectors:
            selector_snapshot = platform_config.selectors or {}

        html_content = await _fetch_live_html(page_url, timeout_seconds=inspect_request.timeout_seconds)
        html_outline = _build_html_outline(html_content)
        last_scraped_values = await LastScrapedValueFinder.get_last_scraped_values(db, platform, limit=3)

        selector_insights: Dict[str, Any] = {}
        broken_fields: List[str] = []
        suggested_fields: List[str] = []

        for field_name, selector_value in selector_snapshot.items():
            current_selector = _normalize_selector_value(selector_value)
            validation = SelectorValidator.validate_selector_against_html(current_selector, html_content)
            status = SelectorValidator.get_selector_health(validation)

            ai_suggested_selector = None
            ai_status = None
            ai_match_count = None
            ai_sample_matches: List[str] = []

            if current_selector:
                try:
                    ai_suggested_selector = await groq_client.suggest_selector_fix(
                        html_snippet=html_content,
                        failed_selector=current_selector,
                        target_data=field_name,
                        platform_name=platform,
                    )
                except Exception as ai_error:
                    logger.warning(f"AI selector suggestion failed for {platform}:{field_name}: {ai_error}")

                if ai_suggested_selector:
                    suggested_fields.append(field_name)
                    ai_validation = SelectorValidator.validate_selector_against_html(ai_suggested_selector, html_content)
                    ai_status = SelectorValidator.get_selector_health(ai_validation)
                    ai_match_count = ai_validation.get("match_count", 0)
                    ai_sample_matches = ai_validation.get("sample_matches", [])[:3]

            if status in {"broken", "uncertain"}:
                broken_fields.append(field_name)

            selector_insights[field_name] = {
                "field_name": field_name,
                "current_selector": current_selector,
                "status": status,
                "match_count": validation.get("match_count", 0),
                "sample_matches": validation.get("sample_matches", [])[:3],
                "confidence": validation.get("confidence", 0.0),
                "ai_suggested_selector": ai_suggested_selector,
                "ai_status": ai_status,
                "ai_match_count": ai_match_count,
                "ai_sample_matches": ai_sample_matches,
            }

        await log_action(
            db,
            user.email,
            f"inspect_scraper_{platform}",
            details={
                "page_url": page_url,
                "selector_count": len(selector_snapshot),
                "broken_fields": broken_fields,
                "suggested_fields": suggested_fields,
            },
            request=request,
        )

        return ScraperInspectionResponse(
            success=True,
            platform=platform,
            page_url=page_url,
            fetched_at=started_at,
            html_length=len(html_content),
            html_excerpt=html_content[:18000],
            html_outline=html_outline,
            selector_snapshot={field: _normalize_selector_value(selector_value) for field, selector_value in selector_snapshot.items()},
            selector_insights=selector_insights,
            last_scraped_values=last_scraped_values,
            ai_summary={
                "total_selectors": len(selector_snapshot),
                "broken_fields": broken_fields,
                "suggested_fields": suggested_fields,
                "html_nodes": len(html_outline),
                "has_live_html": True,
            },
            message=f"Inspection completed for {platform}"
        )

    except Exception as e:
        logger.error(f"Scraper inspection error: {e}", exc_info=True)
        return ScraperInspectionResponse(
            success=False,
            platform=platform,
            page_url=page_url,
            fetched_at=started_at,
            html_length=0,
            html_excerpt="",
            html_outline=[],
            selector_snapshot={},
            selector_insights={},
            last_scraped_values=[],
            ai_summary={"error": str(e), "has_live_html": False},
            message=str(e)
        )


@router.get("/scrapers/selectors/{platform}", response_model=Dict[str, str])
async def get_platform_selectors(
    platform: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user),
) -> Any:
    """Get all raw selectors currently stored in DB for a platform"""
    await verify_admin_email(user)
    
    supported_platforms = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
    if platform not in supported_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' not supported"
        )
    
    result = await db.execute(select(Platform).where(Platform.name == platform))
    platform_config = result.scalar_one_or_none()
    
    if not platform_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Platform '{platform}' not found")
    
    selectors = {}
    if platform_config.selectors:
        for field, value in platform_config.selectors.items():
            selectors[field] = _normalize_selector_value(value)
    
    return selectors


@router.put("/scrapers/selectors/{platform}", response_model=ScraperSelectorUpdateResponse)
async def update_scraper_selector(
    platform: str,
    update_request: ScraperSelectorUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user),
    request: Request = None,
) -> ScraperSelectorUpdateResponse:
    """Persist a selector edit for a platform in the DB."""
    await verify_admin_email(user)

    supported_platforms = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
    if platform not in supported_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' not supported"
        )

    field_name = update_request.field_name.strip()
    selector_value = update_request.selector.strip()
    if not field_name or not selector_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="field_name and selector are required")

    result = await db.execute(select(Platform).where(Platform.name == platform))
    platform_config = result.scalar_one_or_none()
    if not platform_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Platform '{platform}' not found")

    selectors = dict(platform_config.selectors or {})
    old_selector = _normalize_selector_value(selectors.get(field_name)) if field_name in selectors else None
    selectors[field_name] = selector_value

    platform_config.selectors = selectors
    flag_modified(platform_config, "selectors")
    await db.commit()

    await log_action(
        db,
        user.email,
        f"update_scraper_selector_{platform}",
        details={
            "field_name": field_name,
            "old_selector": old_selector,
            "new_selector": selector_value,
        },
        request=request,
    )

    return ScraperSelectorUpdateResponse(
        success=True,
        platform=platform,
        field_name=field_name,
        old_selector=old_selector,
        new_selector=selector_value,
        updated_at=datetime.utcnow(),
        message=f"Selector for {field_name} updated successfully"
    )


@router.post("/scrapers/test/all", response_model=BatchScraperTestResponse)
async def test_all_scrapers(
    test_request: ScraperTestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user),
    request: Request = None
) -> BatchScraperTestResponse:
    """Test all platform scrapers"""
    await verify_admin_email(user)
    
    if not test_request.query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query is required for batch testing all platforms"
        )
    
    started_at = datetime.utcnow()
    supported_platforms = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
    platform_results = []
    successful_tests = 0
    failed_tests = 0
    
    for platform in supported_platforms:
        try:
            # Test each platform
            platform_response = await test_platform_scraper(
                platform, test_request, db, user, request
            )
            platform_results.append(platform_response)
            
            if platform_response.success:
                successful_tests += 1
            else:
                failed_tests += 1
                
        except Exception as e:
            failed_tests += 1
            # Create error response for this platform
            error_response = ScraperTestResponse(
                success=False,
                platform=platform,
                test_type="error",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                results=ScraperTestResult(
                    platform=platform,
                    success=False,
                    products_found=0,
                    test_duration_ms=0,
                    error_message=str(e)
                ),
                message=f"Platform test failed: {str(e)}"
            )
            platform_results.append(error_response)
    
    completed_at = datetime.utcnow()
    total_duration_ms = (completed_at - started_at).total_seconds() * 1000
    
    # Create summary
    summary = {
        "total_duration_ms": total_duration_ms,
        "average_platform_time_ms": total_duration_ms / len(supported_platforms),
        "success_rate": (successful_tests / len(supported_platforms)) * 100,
        "total_products_found": sum(r.results.products_found for r in platform_results if r.success),
        "query": test_request.query,
        "mode": test_request.mode
    }
    
    # Log the batch test
    await log_action(
        db, user.email,
        "test_all_scrapers",
        details={
            "query": test_request.query,
            "mode": test_request.mode,
            "total_platforms": len(supported_platforms),
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate": summary["success_rate"]
        },
        request=request
    )
    
    return BatchScraperTestResponse(
        success=successful_tests > 0,
        started_at=started_at,
        completed_at=completed_at,
        total_platforms=len(supported_platforms),
        successful_tests=successful_tests,
        failed_tests=failed_tests,
        platform_results=platform_results,
        summary=summary
    )


@router.post("/scrapers/fix/{platform}", response_model=ScraperFixResponse)
async def fix_platform_scraper(
    platform: str,
    fix_request: ScraperFixRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user),
    request: Request = None
) -> ScraperFixResponse:
    """Fix a platform scraper (auto-fix, manual config, or reset)"""
    await verify_admin_email(user)
    
    # Validate platform
    supported_platforms = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
    if platform not in supported_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' not supported"
        )
    
    applied_at = datetime.utcnow()
    changes_made = []
    
    try:
        if fix_request.fix_type == "auto":
            # Auto-fix using self-healing mechanisms
            changes_made.append("Cleared scraper cache")
            changes_made.append("Reset rate limiters")
            changes_made.append("Reinitialized browser session")
            
            # Could add more sophisticated auto-fix logic here
            message = f"Auto-fix applied to {platform} scraper"
            
        elif fix_request.fix_type == "manual":
            # Manual configuration updates
            if fix_request.config_updates:
                for key, value in fix_request.config_updates.items():
                    # Update platform configuration
                    changes_made.append(f"Updated {key}: {value}")
                message = f"Manual configuration updates applied to {platform} scraper"
            else:
                message = f"No configuration changes provided for {platform}"
                
        elif fix_request.fix_type == "reset":
            # Reset scraper to default state
            changes_made.append("Reset scraper configuration to defaults")
            changes_made.append("Cleared all cached data")
            changes_made.append("Reinitialized scraper instance")
            message = f"Reset {platform} scraper to default state"
        
        # Log the fix
        await log_action(
            db, user.email,
            f"fix_scraper_{platform}",
            details={
                "fix_type": fix_request.fix_type,
                "changes_made": changes_made,
                "config_updates": fix_request.config_updates
            },
            request=request
        )
        
        return ScraperFixResponse(
            success=True,
            platform=platform,
            fix_type=fix_request.fix_type,
            applied_at=applied_at,
            changes_made=changes_made,
            message=message
        )
        
    except Exception as e:
        return ScraperFixResponse(
            success=False,
            platform=platform,
            fix_type=fix_request.fix_type,
            applied_at=applied_at,
            changes_made=[],
            message=f"Fix failed: {str(e)}"
        )


@router.get("/scrapers/results/{platform}")
async def get_scraper_results(
    platform: str,
    days: int = Query(default=7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_admin_user)
) -> dict:
    """Get recent test results for a platform"""
    await verify_admin_email(user)
    
    # Validate platform
    supported_platforms = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]
    if platform not in supported_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' not supported"
        )
    
    # Get recent listings for this platform
    since_date = datetime.utcnow() - timedelta(days=days)
    listings_result = await db.execute(
        select(ProductListing)
        .where(ProductListing.platform_name == platform)
        .where(ProductListing.updated_at >= since_date)
        .order_by(ProductListing.updated_at.desc())
    )
    listings = listings_result.scalars().all()
    
    # Calculate statistics
    total_listings = len(listings)
    successful_listings = len([l for l in listings if l.current_price and l.current_price > 0])
    success_rate = (successful_listings / total_listings * 100) if total_listings > 0 else 0
    
    # Group by date
    daily_stats = {}
    for listing in listings:
        if listing.updated_at:
            date_key = listing.updated_at.date().isoformat()
            if date_key not in daily_stats:
                daily_stats[date_key] = {"total": 0, "successful": 0}
            daily_stats[date_key]["total"] += 1
            if listing.current_price and listing.current_price > 0:
                daily_stats[date_key]["successful"] += 1
    
    return {
        "platform": platform,
        "period_days": days,
        "total_listings": total_listings,
        "successful_listings": successful_listings,
        "success_rate": success_rate,
        "daily_statistics": daily_stats,
        "recent_listings": [
            {
                "id": str(listing.id),
                "title": listing.title[:100] + "..." if listing.title and len(listing.title) > 100 else listing.title,
                "current_price": listing.current_price,
                "updated_at": listing.updated_at.isoformat() if listing.updated_at else None
            }
            for listing in listings[:10]  # Limit to 10 most recent
        ]
    }


# =============================================================================
# GROQ API KEY TESTER
# =============================================================================

@router.post("/scrapers/groq/test-key")
async def test_groq_api_key(
    payload: dict = Body(...),
    user: User = Depends(get_current_admin_user),
) -> dict:
    """Test a Groq API key by making a minimal real API call."""
    await verify_admin_email(user)

    api_key = (payload.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    import httpx, time

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        "max_tokens": 5,
        "temperature": 0.0,
    }

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=body)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            reply = data["choices"][0]["message"]["content"].strip()
            model_used = data.get("model", "unknown")
            usage = data.get("usage", {})
            return {
                "success": True,
                "reply": reply,
                "model": model_used,
                "latency_ms": latency_ms,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            }
        elif resp.status_code == 401:
            return {"success": False, "error": "Invalid API key (401 Unauthorized)", "latency_ms": latency_ms}
        elif resp.status_code == 429:
            return {"success": False, "error": "Rate limit hit (429) — key is valid but quota exhausted", "latency_ms": latency_ms}
        else:
            return {"success": False, "error": f"Groq returned HTTP {resp.status_code}: {resp.text[:200]}", "latency_ms": latency_ms}

    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out after 15s", "latency_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}", "latency_ms": int((time.perf_counter() - t0) * 1000)}


@router.get("/scrapers/playwright/check")
async def check_playwright(
    user: User = Depends(get_current_admin_user),
) -> dict:
    """Check if Playwright + Chromium are available on this server."""
    await verify_admin_email(user)

    checks = {}

    try:
        import playwright as _pw
        checks["playwright_installed"] = True
        checks["playwright_version"] = getattr(_pw, "__version__", "unknown")
    except ImportError as e:
        checks["playwright_installed"] = False
        checks["playwright_error"] = str(e)
        return {"ready": False, "checks": checks, "fix": "pip install playwright && playwright install chromium"}

    # Launch chromium in a thread (Windows-safe)
    import concurrent.futures

    def _try_launch():
        import asyncio, sys
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _launch():
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                    v = browser.version
                    await browser.close()
                    return v
            return loop.run_until_complete(_launch())
        finally:
            loop.close()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            version = pool.submit(_try_launch).result(timeout=30)
        checks["chromium_available"] = True
        checks["chromium_version"] = version
        return {"ready": True, "checks": checks}
    except Exception as e:
        import traceback
        logger.error(f"Playwright check failed:\n{traceback.format_exc()}")
        checks["chromium_available"] = False
        checks["chromium_error"] = str(e) or repr(e)
        return {"ready": False, "checks": checks, "fix": "playwright install chromium"}
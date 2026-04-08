"""
Subscription plan catalog utilities.

Single source of truth for plan configuration with DB-first lookup and
safe fallback to environment defaults.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import SubscriptionPlan

logger = logging.getLogger(__name__)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _default_plan_catalog() -> Dict[str, Dict[str, Any]]:
    """Build default plan catalog from environment settings."""
    return {
        "free": {
            "plan_id": "free",
            "name": "Free",
            "display_name": "Free",
            "price_paise": 0,
            "duration_days": 36500,
            "features": {
                "daily_searches": settings.PLAN_FREE_SEARCHES,
                "watchlist_limit": settings.PLAN_FREE_WISHLIST,
                "price_alerts": False,
                "ad_free": False,
                "streak_freezes": 2,
                "priority_support": False,
            },
            "limits": {
                "searches_per_day": settings.PLAN_FREE_SEARCHES,
                "watchlist_limit": settings.PLAN_FREE_WISHLIST,
            },
            "popular": False,
            "google_play_sku": None,
            "sort_order": 0,
            "is_active": True,
        },
        "pro": {
            "plan_id": "pro",
            "name": "Pro",
            "display_name": "Pro",
            "price_paise": settings.PLAN_PRO_PRICE,
            "duration_days": settings.PLAN_PRO_DURATION_DAYS,
            "features": {
                "daily_searches": settings.PLAN_PRO_SEARCHES,
                "watchlist_limit": settings.PLAN_PRO_WISHLIST,
                "price_alerts": True,
                "ad_free": False,
                "streak_freezes": 5,
                "priority_support": False,
            },
            "limits": {
                "searches_per_day": settings.PLAN_PRO_SEARCHES,
                "watchlist_limit": settings.PLAN_PRO_WISHLIST,
            },
            "popular": True,
            "google_play_sku": settings.GOOGLE_PLAY_PRO_SKU,
            "sort_order": 1,
            "is_active": True,
        },
        "premium": {
            "plan_id": "premium",
            "name": "Premium",
            "display_name": "Premium",
            "price_paise": settings.PLAN_PREMIUM_PRICE,
            "duration_days": settings.PLAN_PREMIUM_DURATION_DAYS,
            "features": {
                "daily_searches": settings.PLAN_PREMIUM_SEARCHES,
                "watchlist_limit": settings.PLAN_PREMIUM_WISHLIST,
                "price_alerts": True,
                "ad_free": True,
                "streak_freezes": -1,
                "priority_support": True,
                "ai_chat": True,
                "export_data": True,
            },
            "limits": {
                "searches_per_day": settings.PLAN_PREMIUM_SEARCHES,
                "watchlist_limit": settings.PLAN_PREMIUM_WISHLIST,
            },
            "popular": False,
            "google_play_sku": settings.GOOGLE_PLAY_PREMIUM_SKU,
            "sort_order": 2,
            "is_active": True,
        },
    }


async def get_plan_catalog(
    db: AsyncSession,
    include_inactive: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Load plan catalog from DB with fallback to defaults.

    Returns dict keyed by plan_id (lowercase), sorted by sort_order then price.
    """
    catalog = deepcopy(_default_plan_catalog())

    try:
        result = await db.execute(
            select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order.asc(), SubscriptionPlan.id.asc())
        )
        db_plans = result.scalars().all()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to load subscription_plans from DB, using defaults: %s", exc)
        db_plans = []

    for db_plan in db_plans:
        plan_id = (db_plan.name or "").strip().lower()
        if not plan_id:
            continue

        is_active = bool(db_plan.is_active)
        if not include_inactive and not is_active and plan_id != "free":
            continue

        base = catalog.get(
            plan_id,
            {
                "plan_id": plan_id,
                "name": plan_id.title(),
                "display_name": plan_id.title(),
                "price_paise": 0,
                "duration_days": 30,
                "features": {},
                "limits": {
                    "searches_per_day": settings.PLAN_FREE_SEARCHES,
                    "watchlist_limit": settings.PLAN_FREE_WISHLIST,
                },
                "popular": False,
                "google_play_sku": settings.google_play_plan_to_sku.get(plan_id),
                "sort_order": 99,
                "is_active": is_active,
            },
        )

        features = db_plan.features if isinstance(db_plan.features, dict) else {}

        default_limits = base.get("limits", {})
        searches_per_day = _safe_int(
            features.get("daily_searches", default_limits.get("searches_per_day", settings.PLAN_FREE_SEARCHES)),
            settings.PLAN_FREE_SEARCHES,
        )
        watchlist_limit = _safe_int(
            features.get("watchlist_limit", default_limits.get("watchlist_limit", settings.PLAN_FREE_WISHLIST)),
            settings.PLAN_FREE_WISHLIST,
        )

        price_paise = _safe_int(round(float(db_plan.price_inr or 0) * 100), base.get("price_paise", 0))
        duration_days = _safe_int(db_plan.duration_days, base.get("duration_days", 30))

        catalog[plan_id] = {
            "plan_id": plan_id,
            "name": db_plan.display_name or base.get("name") or plan_id.title(),
            "display_name": db_plan.display_name or base.get("display_name") or plan_id.title(),
            "price_paise": price_paise,
            "duration_days": duration_days,
            "features": features or base.get("features", {}),
            "limits": {
                "searches_per_day": searches_per_day,
                "watchlist_limit": watchlist_limit,
            },
            "popular": bool(db_plan.is_popular),
            "google_play_sku": settings.google_play_plan_to_sku.get(plan_id, base.get("google_play_sku")),
            "sort_order": _safe_int(db_plan.sort_order, base.get("sort_order", 99)),
            "is_active": is_active,
        }

    if "free" not in catalog:
        defaults = _default_plan_catalog()
        catalog["free"] = defaults["free"]

    sorted_plan_ids = sorted(
        catalog.keys(),
        key=lambda pid: (
            _safe_int(catalog[pid].get("sort_order"), 99),
            _safe_int(catalog[pid].get("price_paise"), 0),
            pid,
        ),
    )

    return {pid: catalog[pid] for pid in sorted_plan_ids}


async def get_plan_config(
    db: AsyncSession,
    plan_id: str,
    include_inactive: bool = False,
) -> Dict[str, Any]:
    """Return one plan config from catalog or raise ValueError."""
    normalized = (plan_id or "").strip().lower()
    catalog = await get_plan_catalog(db, include_inactive=include_inactive)
    if normalized not in catalog:
        raise ValueError(f"Invalid plan: {plan_id}")
    return catalog[normalized]


def get_plan_from_sku(
    sku: str,
    plan_catalog: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[str]:
    """Map Google Play SKU to internal plan id."""
    if not sku:
        return None

    # Prefer explicit environment mapping.
    mapped = settings.google_play_sku_to_plan.get(sku)
    if mapped:
        return mapped

    if plan_catalog:
        for plan_id, config in plan_catalog.items():
            if config.get("google_play_sku") == sku:
                return plan_id

    return None


def get_plan_limit(
    plan_catalog: Dict[str, Dict[str, Any]],
    plan_id: str,
    limit_key: str,
    default_value: int,
) -> int:
    """Read a numeric limit (searches_per_day/watchlist_limit) for a plan."""
    normalized = (plan_id or "").strip().lower()
    plan_cfg = plan_catalog.get(normalized) or plan_catalog.get("free") or {}
    limits = plan_cfg.get("limits", {})
    return _safe_int(limits.get(limit_key), default_value)


def get_paid_plan_ids(plan_catalog: Dict[str, Dict[str, Any]]) -> list[str]:
    """Return active paid plan ids sorted by catalog order."""
    paid = []
    for plan_id, config in plan_catalog.items():
        price_paise = _safe_int(config.get("price_paise"), 0)
        is_active = bool(config.get("is_active", True))
        if price_paise > 0 and is_active:
            paid.append(plan_id)
    return paid

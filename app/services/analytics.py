"""
Analytics Service
Revenue calculations, user metrics, and projection engine
This is your financial tracking powerhouse
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, text, distinct, Numeric
from sqlalchemy.sql import extract

from app.models import (
    User, Transaction, SubscriptionPlan, Product, ProductListing,
    Platform, SystemLog, Promotion, UserWatchlist
)
from app.schemas import UserPlan
from app.core.config import settings

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Comprehensive analytics for admin dashboard
    
    Features:
    - Real-time revenue tracking
    - User segmentation
    - Subscription metrics (MRR, churn, LTV)
    - Affiliate performance
    - Growth projections
    - Loan payoff calculator (your ₹8L goal!)
    """
    
    # =============================================================================
    # REVENUE ANALYTICS
    # =============================================================================
    
    async def get_revenue_overview(
        self, 
        db: AsyncSession,
        target_loan_amount: float = 800000  # Your ₹8L goal
    ) -> Dict[str, Any]:
        """
        Complete revenue dashboard data
        
        Returns everything you need to see:
        - Today's earnings
        - Monthly totals
        - User breakdown
        - Projections including loan payoff date
        """
        today = date.today()
        first_day_of_month = today.replace(day=1)
        last_month_start = (first_day_of_month - timedelta(days=1)).replace(day=1)
        
        # Today's revenue
        today_revenue = await self._get_revenue_for_period(
            db, 
            datetime.combine(today, datetime.min.time()),
            datetime.combine(today, datetime.max.time())
        )
        
        # This month's revenue
        month_revenue = await self._get_revenue_for_period(
            db,
            datetime.combine(first_day_of_month, datetime.min.time()),
            datetime.now()
        )
        
        # Last month's revenue (for comparison)
        last_month_revenue = await self._get_revenue_for_period(
            db,
            datetime.combine(last_month_start, datetime.min.time()),
            datetime.combine(first_day_of_month - timedelta(days=1), datetime.max.time())
        )
        
        # MRR calculation
        mrr = await self.calculate_mrr(db)
        
        # User breakdown
        user_stats = await self.get_user_breakdown(db)
        
        # Churn and conversion rates
        churn_rate = await self.calculate_churn_rate(db)
        conversion_rate = await self.calculate_conversion_rate(db)
        
        # Total lifetime revenue
        total_revenue = await self._get_total_revenue(db)

        # Recent successful payments for dashboard table
        recent_transactions = await self._get_recent_transactions(db, limit=10)
        
        # Calculate growth
        growth_percent = 0
        if last_month_revenue["total"] > 0:
            growth_percent = ((month_revenue["total"] - last_month_revenue["total"]) / 
                            last_month_revenue["total"]) * 100
        
        # Projections
        avg_monthly_revenue = mrr + (month_revenue.get("affiliate", 0) * 0.8)  # Conservative
        months_to_loan_payoff = 0
        if avg_monthly_revenue > 0:
            months_to_loan_payoff = int(target_loan_amount / avg_monthly_revenue) + 1
        
        # Breakeven users (assuming ₹10/user/month average)
        monthly_costs = 5000  # Server, API costs estimate
        breakeven_users = int(monthly_costs / 10) if monthly_costs > 0 else 0
        
        return {
            "total_revenue_inr": round(total_revenue, 2),
            "monthly_recurring_revenue": round(mrr, 2),
            "conversion_rate": round(conversion_rate, 2),
            "recent_transactions": recent_transactions,
            "today": {
                "subscriptions": round(today_revenue.get("subscriptions", 0), 2),
                "affiliate_conversions": round(today_revenue.get("affiliate", 0), 2),
                "promotions": round(today_revenue.get("promotions", 0), 2),
                "total": round(today_revenue.get("total", 0), 2)
            },
            "this_month": {
                "total": round(month_revenue.get("total", 0), 2),
                "mrr": round(mrr, 2),
                "affiliate": round(month_revenue.get("affiliate", 0), 2),
                "promotions": round(month_revenue.get("promotions", 0), 2),
                "growth_vs_last_month": round(growth_percent, 1)
            },
            "breakdown": {
                "free_users": user_stats.get("free", 0),
                "pro_users": user_stats.get("pro", 0),
                "premium_users": user_stats.get("premium", 0),
                "churn_rate": round(churn_rate, 2),
                "conversion_rate": round(conversion_rate, 2)
            },
            "projections": {
                "next_month_mrr": round(mrr * 1.1, 2),  # 10% growth assumption
                "breakeven_users": breakeven_users,
                "months_to_loan_payoff": months_to_loan_payoff,
                "loan_payoff_date": (datetime.now() + timedelta(days=30 * months_to_loan_payoff)).strftime("%Y-%m-%d") if months_to_loan_payoff > 0 else "N/A"
            }
        }
    
    async def _get_revenue_for_period(
        self, 
        db: AsyncSession, 
        start: datetime, 
        end: datetime
    ) -> Dict[str, float]:
        """Get revenue breakdown for a specific period"""
        
        # Subscription revenue
        sub_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.type == "payment",
                    Transaction.status == "success",
                    Transaction.created_at >= start,
                    Transaction.created_at <= end
                )
            )
        )
        subscription_revenue = float(sub_result.scalar() or 0)
        
        # Affiliate revenue
        aff_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.commission_earned), 0))
            .where(
                and_(
                    Transaction.type == "affiliate_conversion",
                    Transaction.status == "success",
                    Transaction.created_at >= start,
                    Transaction.created_at <= end
                )
            )
        )
        affiliate_revenue = float(aff_result.scalar() or 0)
        
        # Promotion revenue
        promo_result = await db.execute(
            select(func.coalesce(
                func.sum(
                    func.cast(Promotion.stats['revenue_earned'].astext, Numeric)
                ), 0
            ))
            .where(
                and_(
                    Promotion.start_date >= start,
                    Promotion.end_date <= end,
                    Promotion.payment_status == "paid"
                )
            )
        )
        promotion_revenue = float(promo_result.scalar() or 0)
        
        total = subscription_revenue + affiliate_revenue + promotion_revenue
        
        return {
            "subscriptions": subscription_revenue,
            "affiliate": affiliate_revenue,
            "promotions": promotion_revenue,
            "total": total
        }
    
    async def _get_total_revenue(self, db: AsyncSession) -> float:
        """Get all-time total revenue"""
        result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.type == "payment",
                    Transaction.status == "success"
                )
            )
        )
        return float(result.scalar() or 0)

    async def _get_recent_transactions(self, db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
        """Get latest successful payment transactions for admin dashboard."""
        result = await db.execute(
            select(Transaction)
            .where(
                and_(
                    Transaction.type == "payment",
                    Transaction.status == "success"
                )
            )
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()

        return [
            {
                "id": str(tx.id),
                "type": tx.type,
                "amount": float(tx.amount or 0),
                "status": tx.status,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
            for tx in rows
        ]
    
    async def calculate_mrr(self, db: AsyncSession) -> float:
        """
        Calculate Monthly Recurring Revenue
        
        MRR = (Pro users × ₹49) + (Premium users × ₹149)
        Only counts non-expired subscriptions
        """
        now = datetime.utcnow()
        
        # Count active Pro users
        pro_result = await db.execute(
            select(func.count(User.id))
            .where(
                and_(
                    User.plan == "pro",
                    User.is_blocked == False,
                    or_(
                        User.plan_expires_at == None,
                        User.plan_expires_at > now
                    )
                )
            )
        )
        pro_count = pro_result.scalar() or 0
        
        # Count active Premium users
        premium_result = await db.execute(
            select(func.count(User.id))
            .where(
                and_(
                    User.plan == "premium",
                    User.is_blocked == False,
                    or_(
                        User.plan_expires_at == None,
                        User.plan_expires_at > now
                    )
                )
            )
        )
        premium_count = premium_result.scalar() or 0
        
        # Calculate MRR (prices in INR)
        pro_price = settings.PLAN_PRO_PRICE / 100  # Convert paise to rupees
        premium_price = settings.PLAN_PREMIUM_PRICE / 100
        
        mrr = (pro_count * pro_price) + (premium_count * premium_price)
        
        return mrr
    
    async def calculate_churn_rate(self, db: AsyncSession, days: int = 30) -> float:
        """
        Calculate subscription churn rate
        
        Churn = (Users who cancelled in last 30 days / Active paid users at start) × 100
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Users who were paid but are now free or expired
        churned_result = await db.execute(
            select(func.count(distinct(Transaction.user_id)))
            .where(
                and_(
                    Transaction.type == "payment",
                    Transaction.status == "success",
                    Transaction.created_at < start_date
                )
            )
        )
        total_ever_paid = churned_result.scalar() or 0
        
        # Currently active paid users
        active_result = await db.execute(
            select(func.count(User.id))
            .where(
                and_(
                    User.plan.in_(["pro", "premium"]),
                    User.is_blocked == False,
                    or_(
                        User.plan_expires_at == None,
                        User.plan_expires_at > datetime.utcnow()
                    )
                )
            )
        )
        active_paid = active_result.scalar() or 0
        
        if total_ever_paid == 0:
            return 0.0
        
        churned = total_ever_paid - active_paid
        churn_rate = (churned / total_ever_paid) * 100
        
        return max(0, churn_rate)  # Don't return negative
    
    async def calculate_conversion_rate(self, db: AsyncSession) -> float:
        """
        Calculate free → paid conversion rate
        
        Conversion = (Users who ever paid / Total users) × 100
        """
        # Total users
        total_result = await db.execute(
            select(func.count(User.id))
            .where(User.is_blocked == False)
        )
        total_users = total_result.scalar() or 0
        
        if total_users == 0:
            return 0.0
        
        # Users who ever paid
        paid_result = await db.execute(
            select(func.count(distinct(Transaction.user_id)))
            .where(
                and_(
                    Transaction.type == "payment",
                    Transaction.status == "success"
                )
            )
        )
        paid_users = paid_result.scalar() or 0
        
        return (paid_users / total_users) * 100
    
    async def get_user_breakdown(self, db: AsyncSession) -> Dict[str, int]:
        """Get user count by plan"""
        result = await db.execute(
            select(User.plan, func.count(User.id))
            .where(User.is_blocked == False)
            .group_by(User.plan)
        )
        rows = result.all()
        
        breakdown = {"free": 0, "pro": 0, "premium": 0}
        for row in rows:
            if row[0] in breakdown:
                breakdown[row[0]] = row[1]
        
        return breakdown
    
    # =============================================================================
    # USER ANALYTICS
    # =============================================================================
    
    async def get_active_users_count(
        self, 
        db: AsyncSession, 
        period: str = "daily"
    ) -> int:
        """Get active users count for period (daily/weekly/monthly)"""
        now = datetime.utcnow()
        
        if period == "daily":
            since = now - timedelta(days=1)
        elif period == "weekly":
            since = now - timedelta(days=7)
        elif period == "monthly":
            since = now - timedelta(days=30)
        else:
            since = now - timedelta(days=1)
        
        result = await db.execute(
            select(func.count(User.id))
            .where(
                and_(
                    User.is_blocked == False,
                    User.last_active >= since
                )
            )
        )
        return result.scalar() or 0
    
    async def get_suspicious_users(
        self, 
        db: AsyncSession, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get users with suspicious activity patterns"""
        result = await db.execute(
            select(User)
            .where(User.is_blocked == False)
            .order_by(User.created_at.desc())
            .limit(500)  # Check recent 500 users
        )
        users = result.scalars().all()
        
        suspicious = []
        for user in users:
            flags = []
            
            # Check multiple IPs (>5 in stored list)
            ips = user.ip_addresses or []
            if len(ips) > 5:
                flags.append("multiple_ips")
            
            # Check if hardware_id has many accounts
            if user.hardware_id:
                hw_result = await db.execute(
                    select(func.count(User.id))
                    .where(User.hardware_id == user.hardware_id)
                )
                hw_count = hw_result.scalar() or 0
                if hw_count >= 3:
                    flags.append("max_devices_reached")
            
            # Check for suspicious usage patterns
            usage = user.usage_stats or {}
            if usage.get("suspicious_ip_activity"):
                flags.append("ip_fraud_detected")
            
            if flags:
                suspicious.append({
                    "id": str(user.id),
                    "email": user.email,
                    "plan": user.plan,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "flags": flags,
                    "hardware_id": user.hardware_id[:8] + "..." if user.hardware_id else None,
                    "ip_count": len(ips)
                })
        
        return suspicious[:limit]
    
    async def get_user_lifetime_value(
        self, 
        db: AsyncSession, 
        user_id: UUID
    ) -> float:
        """Calculate lifetime value of a user"""
        result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.type == "payment",
                    Transaction.status == "success"
                )
            )
        )
        return float(result.scalar() or 0)
    
    # =============================================================================
    # AFFILIATE ANALYTICS
    # =============================================================================
    
    async def get_affiliate_performance(
        self, 
        db: AsyncSession, 
        days: int = 30,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get top performing products/platforms for affiliate revenue"""
        since = datetime.utcnow() - timedelta(days=days)
        
        # Top products by affiliate conversions
        result = await db.execute(
            select(
                Transaction.product_id,
                func.count(Transaction.id).label("conversions"),
                func.sum(Transaction.commission_earned).label("revenue")
            )
            .where(
                and_(
                    Transaction.type == "affiliate_conversion",
                    Transaction.status == "success",
                    Transaction.created_at >= since,
                    Transaction.product_id != None
                )
            )
            .group_by(Transaction.product_id)
            .order_by(func.sum(Transaction.commission_earned).desc())
            .limit(limit)
        )
        rows = result.all()
        
        performers = []
        for row in rows:
            # Get product details
            product = await db.get(Product, row.product_id)
            if product:
                performers.append({
                    "product_id": str(row.product_id),
                    "product_title": product.title[:50] if product.title else "Unknown",
                    "conversions": row.conversions,
                    "revenue_earned": float(row.revenue or 0)
                })
        
        return performers
    
    async def get_affiliate_clicks_today(self, db: AsyncSession) -> int:
        """Get affiliate clicks for today"""
        today_start = datetime.combine(date.today(), datetime.min.time())
        
        result = await db.execute(
            select(func.count(Transaction.id))
            .where(
                and_(
                    Transaction.type == "affiliate_click",
                    Transaction.created_at >= today_start
                )
            )
        )
        return result.scalar() or 0
    
    # =============================================================================
    # PRODUCT & SEARCH ANALYTICS
    # =============================================================================
    
    async def get_product_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """Get product catalog statistics"""
        # Total products
        total_result = await db.execute(select(func.count(Product.id)))
        total = total_result.scalar() or 0
        
        # Products with active listings
        active_result = await db.execute(
            select(func.count(distinct(ProductListing.product_id)))
            .where(ProductListing.in_stock == True)
        )
        active = active_result.scalar() or 0
        
        # Products scraped today
        today_start = datetime.combine(date.today(), datetime.min.time())
        scraped_result = await db.execute(
            select(func.count(distinct(ProductListing.product_id)))
            .where(ProductListing.last_scraped >= today_start)
        )
        scraped_today = scraped_result.scalar() or 0
        
        return {
            "total_tracked": total,
            "with_active_listings": active,
            "scraped_today": scraped_today,
            "by_category": await self.get_products_by_category(db)
        }
    
    async def get_searches_today(self, db: AsyncSession) -> int:
        """Get search count for today"""
        today_start = datetime.combine(date.today(), datetime.min.time())
        
        result = await db.execute(
            select(func.count(Transaction.id))
            .where(
                and_(
                    Transaction.type.in_(["search", "ai_search"]),
                    Transaction.created_at >= today_start
                )
            )
        )
        return result.scalar() or 0
    
    # =============================================================================
    # PROMOTION ANALYTICS
    # =============================================================================
    
    async def get_promotion_revenue(
        self, 
        db: AsyncSession,
        promotion_id: Optional[UUID] = None,
        brand_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get promotion revenue statistics"""
        query = select(Promotion)
        
        if promotion_id:
            query = query.where(Promotion.id == promotion_id)
        if brand_name:
            query = query.where(Promotion.brand_name == brand_name)
        
        result = await db.execute(query)
        promotions = result.scalars().all()
        
        total_impressions = 0
        total_clicks = 0
        total_revenue = 0
        
        for promo in promotions:
            stats = promo.stats or {}
            total_impressions += stats.get("impressions", 0)
            total_clicks += stats.get("clicks", 0)
            total_revenue += stats.get("revenue_earned", 0)
        
        return {
            "total_promotions": len(promotions),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_revenue": total_revenue,
            "avg_ctr": (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        }
    
    # =============================================================================
    # SYSTEM STATS
    # =============================================================================
    
    async def get_scraper_health(self, db: AsyncSession) -> Dict[str, Any]:
        """Get scraper health metrics per platform"""
        result = await db.execute(select(Platform).where(Platform.is_active == True))
        platforms = result.scalars().all()
        
        health = {}
        
        for platform in platforms:
            # Get latest scraping stats
            listing_result = await db.execute(
                select(
                    func.count(ProductListing.id).label("total"),
                    func.count(ProductListing.id).filter(
                        ProductListing.scrape_error_count == 0
                    ).label("success"),
                    func.max(ProductListing.last_scraped).label("last_run")
                )
                .where(ProductListing.platform_id == platform.id)
            )
            row = listing_result.one()
            
            success_rate = (row.success / row.total * 100) if row.total > 0 else 100
            
            # Check selector health
            selectors = platform.selectors or {}
            healed_count = len(selectors.get("healed_selectors", []))
            
            if healed_count == 0:
                selector_status = "healthy"
            elif healed_count < 3:
                selector_status = "healed"
            else:
                selector_status = "degraded"
            
            health[platform.name] = {
                "status": "healthy" if success_rate > 90 else "degraded" if success_rate > 70 else "failing",
                "success_rate": round(success_rate, 1),
                "total_listings": row.total,
                "last_run": row.last_run.isoformat() if row.last_run else None,
                "selector_health": selector_status,
                "healed_selectors_count": healed_count
            }
        
        return health
    
    async def log_admin_action(
        self,
        db: AsyncSession,
        admin_email: str,
        action: str,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """Log admin action for audit trail"""
        today = date.today()
        
        # Get or create today's log entry
        result = await db.execute(
            select(SystemLog).where(SystemLog.log_date == today)
        )
        log = result.scalar_one_or_none()
        
        if not log:
            log = SystemLog(log_date=today)
            db.add(log)
        
        # Add admin action to analytics
        analytics = log.analytics or {}
        admin_actions = analytics.get("admin_actions", [])
        
        admin_actions.append({
            "admin_email": admin_email,
            "action": action,
            "target": target,
            "details": details,
            "ip_address": ip_address,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep only last 100 actions per day
        admin_actions = admin_actions[-100:]
        analytics["admin_actions"] = admin_actions
        log.analytics = analytics
        
        await db.commit()

    async def get_products_by_category(self, db: AsyncSession) -> Dict[str, int]:
        """Get product count by category"""
        result = await db.execute(
            select(Product.category, func.count(Product.id))
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
        )
        rows = result.all()
        return {row[0]: row[1] for row in rows}


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
analytics_service = AnalyticsService()
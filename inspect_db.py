"""
Quick Database Inspector
Shows counts + small samples for current schema.

Run:
  python inspect_db.py
"""

import asyncio
from sqlalchemy import func, select

from app.core.database import async_session_maker
from app.models import (
    AppConfig,
    Platform,
    PriceHistory,
    Product,
    ProductListing,
    Promotion,
    StreakMilestone,
    SubscriptionPlan,
    SystemLog,
    Transaction,
    User,
    UserWatchlist,
)


async def count_rows(session, model):
    return int((await session.scalar(select(func.count(model.id)))) or 0)


async def inspect_database() -> None:
    print("\n" + "=" * 80)
    print("DATABASE INSPECTION - DealHunt")
    print("=" * 80 + "\n")

    async with async_session_maker() as session:
        tables = [
            ("platforms", Platform),
            ("products", Product),
            ("product_listings", ProductListing),
            ("price_history", PriceHistory),
            ("users", User),
            ("user_watchlist", UserWatchlist),
            ("subscription_plans", SubscriptionPlan),
            ("transactions", Transaction),
            ("promotions", Promotion),
            ("system_logs", SystemLog),
            ("streak_milestones", StreakMilestone),
        ]

        print("TABLE COUNTS")
        print("-" * 80)
        for name, model in tables:
            count = await count_rows(session, model)
            print(f"  {name:<20} {count:>8}")

        app_config_count = int((await session.scalar(select(func.count(AppConfig.key)))) or 0)
        print(f"  {'app_config':<20} {app_config_count:>8}")

        print("\nSAMPLES")
        print("-" * 80)

        products = (await session.execute(select(Product).limit(3))).scalars().all()
        if products:
            print("  Products:")
            for p in products:
                print(f"    - {str(p.id)} | {p.title[:80]}")

        listings = (
            await session.execute(
                select(ProductListing)
                .order_by(ProductListing.last_scraped.desc().nullslast())
                .limit(3)
            )
        ).scalars().all()
        if listings:
            print("  Listings:")
            for l in listings:
                print(
                    f"    - {str(l.id)} | product={str(l.product_id)} | "
                    f"price={l.current_price} | in_stock={l.in_stock}"
                )

        watchlist_items = (await session.execute(select(UserWatchlist).limit(3))).scalars().all()
        if watchlist_items:
            print("  Watchlist:")
            for w in watchlist_items:
                print(
                    f"    - user={str(w.user_id)} | product={str(w.product_id)} | "
                    f"target={w.target_price} | notify={w.notify}"
                )

        latest_log = (
            await session.execute(select(SystemLog).order_by(SystemLog.log_date.desc()).limit(1))
        ).scalar_one_or_none()
        if latest_log:
            analytics = latest_log.analytics or {}
            print("  Latest system log:")
            print(
                f"    - date={latest_log.log_date} | alerts_sent={analytics.get('alerts_sent', 0)} | "
                f"archive_path={latest_log.archive_path}"
            )

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(inspect_database())

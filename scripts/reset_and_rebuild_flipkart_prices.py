#!/usr/bin/env python3
"""
Reset and rebuild Flipkart prices.

Flow:
1. Reset all flipkart listing price fields.
2. Delete flipkart price_history rows.
3. Re-scrape each flipkart listing URL and store normalized prices.
4. Rebuild price_history baseline from fresh scraped price.

Usage:
  python scripts/reset_and_rebuild_flipkart_prices.py
"""

import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, Tuple

from sqlalchemy import func, select, text, update

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import async_session_maker
from app.models import Platform, PriceHistory, ProductListing
from app.services.scraper.factory import get_platform_handler
from app.services.scraper.rate_limiter import RateLimitExceeded


def _to_positive_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _normalize_snapshot(
    current_raw: Any,
    original_raw: Any,
    discount_raw: Any,
    fallback_original: Any = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    current_price = _to_positive_float(current_raw)
    if current_price is None:
        return None, None, None

    original_price = _to_positive_float(original_raw)
    if original_price is None:
        original_price = _to_positive_float(fallback_original)

    if original_price is not None and original_price <= current_price:
        low = min(current_price, original_price)
        high = max(current_price, original_price)
        current_price = low
        original_price = high if high > low else None

    discount_percent = None
    if original_price is not None and original_price > current_price:
        discount_percent = round(((original_price - current_price) / original_price) * 100, 1)
    else:
        original_price = None
        try:
            hint = float(discount_raw) if discount_raw is not None else None
            if hint is not None and 0 < hint <= 95:
                discount_percent = round(hint, 1)
        except (TypeError, ValueError):
            discount_percent = None

    return current_price, original_price, discount_percent


async def main() -> None:
    async with async_session_maker() as db:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        platform_id = await db.scalar(
            select(Platform.id).where(func.lower(Platform.name) == "flipkart")
        )
        if not platform_id:
            print("flipkart_platform_not_found=1")
            return

        listings = (
            await db.execute(
                select(ProductListing)
                .where(ProductListing.platform_id == platform_id)
                .order_by(ProductListing.created_at.asc())
            )
        ).scalars().all()

        total_listings = len(listings)
        if total_listings == 0:
            print("flipkart_listings_found=0")
            return

        await db.execute(
            update(ProductListing)
            .where(ProductListing.platform_id == platform_id)
            .values(
                current_price=0.0,
                original_price=None,
                discount_percent=None,
                last_scraped=None,
                scrape_error_count=0,
                last_error=f"flipkart_price_reset_{ts}",
            )
        )

        await db.execute(
            text(
                """
                DELETE FROM price_history ph
                USING product_listings pl
                WHERE ph.product_listing_id = pl.id
                  AND pl.platform_id = :platform_id
                """
            ),
            {"platform_id": platform_id},
        )

        await db.commit()

        print("--- reset completed ---")
        print("backup_tables_created=0")
        print(f"total_listings={total_listings}")

        handler = await get_platform_handler("flipkart", db=db)
        if not handler:
            print("flipkart_handler_unavailable=1")
            return

        # One-time rebuild tuning to avoid aggressive burst cooldown loops.
        config = handler.rate_limiter.get_config("flipkart")
        config.burst_size = max(config.burst_size, 12)
        config.min_delay_seconds = max(config.min_delay_seconds, 4.0)
        config.max_delay_seconds = max(config.max_delay_seconds, 8.0)

        refreshed = 0
        failed = 0
        missing_url = 0
        invalid_live_snapshot = 0
        rate_limit_hits = 0
        history_inserted = 0

        for idx, listing in enumerate(listings, 1):
            url = listing.product_url
            if not url:
                missing_url += 1
                failed += 1
                continue

            product_data = None
            attempts = 0
            while attempts < 3:
                attempts += 1
                try:
                    product_data = await handler.get_product(url)
                    break
                except RateLimitExceeded as e:
                    rate_limit_hits += 1
                    wait_seconds = max(20, int(getattr(e, "retry_after", 60) or 60))
                    print(f"rate_limited idx={idx} wait={wait_seconds}s")
                    await asyncio.sleep(wait_seconds)
                except Exception as exc:
                    if attempts >= 3:
                        listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                        listing.last_error = str(exc)[:500]
                    else:
                        await asyncio.sleep(10)

            if not product_data or getattr(product_data, "current_price", None) is None:
                listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                listing.last_error = "No valid live product data"
                failed += 1
            else:
                current_price, original_price, discount_percent = _normalize_snapshot(
                    current_raw=getattr(product_data, "current_price", None),
                    original_raw=getattr(product_data, "original_price", None),
                    discount_raw=getattr(product_data, "discount_percent", None),
                    fallback_original=None,
                )

                if current_price is None:
                    listing.scrape_error_count = (listing.scrape_error_count or 0) + 1
                    listing.last_error = "Invalid live price snapshot"
                    invalid_live_snapshot += 1
                    failed += 1
                else:
                    now = datetime.utcnow()
                    listing.current_price = current_price
                    listing.original_price = original_price
                    listing.discount_percent = discount_percent
                    listing.last_scraped = now
                    listing.last_price_change_at = now
                    listing.scrape_error_count = 0
                    listing.last_error = None
                    if getattr(product_data, "in_stock", None) is not None:
                        listing.in_stock = bool(product_data.in_stock)
                    if getattr(product_data, "rating", None) is not None:
                        listing.rating = float(product_data.rating)
                    if getattr(product_data, "review_count", None) is not None:
                        listing.review_count = int(product_data.review_count)

                    db.add(
                        PriceHistory(
                            product_listing_id=listing.id,
                            price=Decimal(str(current_price)),
                            in_stock=listing.in_stock if listing.in_stock is not None else True,
                            recorded_at=now,
                        )
                    )
                    history_inserted += 1
                    refreshed += 1

            if idx % 20 == 0:
                await db.commit()
                print(
                    f"progress {idx}/{total_listings} refreshed={refreshed} failed={failed} "
                    f"rate_limits={rate_limit_hits}"
                )

            # Extra throttle to reduce hard block risk in long rebuild.
            await asyncio.sleep(2.5)

        await db.commit()

        filled_count = await db.scalar(
            select(func.count(ProductListing.id)).where(
                ProductListing.platform_id == platform_id,
                ProductListing.current_price > 0,
            )
        )

        history_count = await db.scalar(
            text(
                """
                SELECT COUNT(*)
                FROM price_history ph
                JOIN product_listings pl ON pl.id = ph.product_listing_id
                WHERE pl.platform_id = :platform_id
                """
            ),
            {"platform_id": platform_id},
        )

        print("--- rebuild summary ---")
        print(f"total_listings={total_listings}")
        print(f"refreshed={refreshed}")
        print(f"failed={failed}")
        print(f"missing_url={missing_url}")
        print(f"invalid_live_snapshot={invalid_live_snapshot}")
        print(f"rate_limit_hits={rate_limit_hits}")
        print(f"history_inserted={history_inserted}")
        print(f"listings_with_price_after={int(filled_count or 0)}")
        print(f"history_rows_after={int(history_count or 0)}")


if __name__ == "__main__":
    asyncio.run(main())

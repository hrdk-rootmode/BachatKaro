#!/usr/bin/env python3
"""
Normalize listing prices safely in product_listings.

What it fixes:
- current_price <= 0 with valid original_price
- swapped/reversed prices (original_price <= current_price)
- inconsistent or missing discount_percent when original_price > current_price
- invalid discount_percent when original_price is missing

Safety features:
- Dry-run mode by default
- Optional history recording when current_price changes

Usage examples:
  python scripts/normalize_listing_prices.py --platform flipkart --dry-run
    python scripts/normalize_listing_prices.py --platform flipkart --apply
  python scripts/normalize_listing_prices.py --platform amazon --apply --no-history
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import func, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import async_session_maker
from app.models import Platform, PriceHistory, ProductListing


def _to_float(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _round_discount(current: float, original: float) -> Optional[float]:
    if original <= 0 or current <= 0 or original <= current:
        return None
    return round(((original - current) / original) * 100, 1)


def _normalize_prices(
    current_price: Optional[float],
    original_price: Optional[float],
    discount_percent: Optional[float],
) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    reason_parts = []
    current = _to_float(current_price)
    original = _to_float(original_price)

    if current is None and original is not None:
        current = original
        original = None
        reason_parts.append("promote_original_to_current")

    if current is None:
        return None, None, None, "unfixable_missing_current"

    if original is not None and original <= current:
        low = min(current, original)
        high = max(current, original)
        current = low
        if high > low:
            original = high
            reason_parts.append("swap_or_reorder_prices")
        else:
            original = None
            reason_parts.append("drop_equal_original")

    if original is not None and original > current:
        expected_discount = _round_discount(current, original)
        if expected_discount is None:
            original = None
            normalized_discount = None
            reason_parts.append("drop_invalid_original")
        else:
            normalized_discount = expected_discount
            if discount_percent is None:
                reason_parts.append("fill_missing_discount")
            else:
                try:
                    if abs(float(discount_percent) - expected_discount) > 0.15:
                        reason_parts.append("recompute_discount")
                except (TypeError, ValueError):
                    reason_parts.append("recompute_discount")
    else:
        normalized_discount = None
        if discount_percent is not None:
            reason_parts.append("clear_discount_without_original")

    reason = ",".join(reason_parts) if reason_parts else "no_change"
    return current, original, normalized_discount, reason


async def _append_history_if_changed(db, listing: ProductListing, new_price: float) -> bool:
    latest = await db.execute(
        select(PriceHistory.price, PriceHistory.in_stock)
        .where(PriceHistory.product_listing_id == listing.id)
        .order_by(PriceHistory.recorded_at.desc(), PriceHistory.id.desc())
        .limit(1)
    )
    row = latest.first()

    in_stock = listing.in_stock if listing.in_stock is not None else True
    if row is not None:
        last_price, last_stock = row
        last_price_f = float(last_price) if last_price is not None else None
        last_stock_b = bool(last_stock) if last_stock is not None else True
        if last_price_f is not None and abs(last_price_f - float(new_price)) <= 0.01 and last_stock_b == bool(in_stock):
            return False

    db.add(
        PriceHistory(
            product_listing_id=listing.id,
            price=Decimal(str(new_price)),
            in_stock=in_stock,
            recorded_at=datetime.utcnow(),
        )
    )
    return True


async def run(platform_name: str, apply_changes: bool, record_history: bool, limit: Optional[int]) -> None:
    async with async_session_maker() as db:
        platform_id = await db.scalar(
            select(Platform.id).where(func.lower(Platform.name) == platform_name.lower())
        )

        if not platform_id:
            print(f"platform_not_found={platform_name}")
            return

        query = (
            select(ProductListing)
            .where(ProductListing.platform_id == platform_id)
            .order_by(ProductListing.last_scraped.asc().nullsfirst(), ProductListing.created_at.asc())
        )
        if limit and limit > 0:
            query = query.limit(limit)

        listings = (await db.execute(query)).scalars().all()
        if not listings:
            print("no_listings_found=1")
            return

        scanned = 0
        changed_rows = 0
        current_price_changed = 0
        original_price_changed = 0
        discount_changed = 0
        unfixable_rows = 0
        history_added = 0

        now = datetime.utcnow()

        for listing in listings:
            scanned += 1

            old_current = _to_float(listing.current_price)
            old_original = _to_float(listing.original_price)
            old_discount = float(listing.discount_percent) if listing.discount_percent is not None else None

            new_current, new_original, new_discount, reason = _normalize_prices(
                current_price=old_current,
                original_price=old_original,
                discount_percent=old_discount,
            )

            if new_current is None:
                unfixable_rows += 1
                continue

            current_changed = (old_current is None and new_current is not None) or (
                old_current is not None and abs(old_current - new_current) > 0.01
            )
            original_changed = (
                (old_original is None and new_original is not None)
                or (old_original is not None and new_original is None)
                or (old_original is not None and new_original is not None and abs(old_original - new_original) > 0.01)
            )
            discount_changed_flag = (
                (old_discount is None and new_discount is not None)
                or (old_discount is not None and new_discount is None)
                or (old_discount is not None and new_discount is not None and abs(old_discount - new_discount) > 0.15)
            )

            if not (current_changed or original_changed or discount_changed_flag):
                continue

            changed_rows += 1

            if apply_changes:
                listing.current_price = new_current
                listing.original_price = new_original
                listing.discount_percent = new_discount
                listing.last_scraped = now

                if current_changed:
                    listing.last_price_change_at = now
                    if record_history and await _append_history_if_changed(db, listing, new_current):
                        history_added += 1

            if current_changed:
                current_price_changed += 1
            if original_changed:
                original_price_changed += 1
            if discount_changed_flag:
                discount_changed += 1

        if apply_changes:
            await db.commit()
        else:
            await db.rollback()

        print(f"platform={platform_name.lower()}")
        print(f"mode={'apply' if apply_changes else 'dry_run'}")
        print(f"scanned={scanned}")
        print(f"changed_rows={changed_rows}")
        print(f"current_price_changed={current_price_changed}")
        print(f"original_price_changed={original_price_changed}")
        print(f"discount_changed={discount_changed}")
        print(f"unfixable_rows={unfixable_rows}")
        print(f"history_added={history_added}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize listing prices safely")
    parser.add_argument("--platform", required=True, help="Platform name, e.g. flipkart")
    parser.add_argument("--apply", action="store_true", help="Apply changes to DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes only")
    parser.add_argument("--no-history", action="store_true", help="Do not append price history on current_price changes")
    parser.add_argument("--limit", type=int, default=0, help="Optional listing limit")
    args = parser.parse_args()

    apply_changes = bool(args.apply)
    if args.dry_run:
        apply_changes = False

    asyncio.run(
        run(
            platform_name=args.platform,
            apply_changes=apply_changes,
            record_history=not bool(args.no_history),
            limit=args.limit if args.limit and args.limit > 0 else None,
        )
    )

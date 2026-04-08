#!/usr/bin/env python
"""Check today's Flipkart data in database"""

from app.database import SessionLocal
from app.models import ProductListing
from sqlalchemy import select, and_, func
from datetime import datetime, timedelta

db = SessionLocal()

# Get today's date range (UTC)
today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
today_end = today_start + timedelta(days=1)

# Count total Flipkart listings from today
stmt = select(func.count()).select_from(ProductListing).where(
    and_(
        ProductListing.created_at >= today_start,
        ProductListing.created_at < today_end,
        ProductListing.source_platform == 'flipkart'
    )
)
total_count = db.execute(stmt).scalar()

# Get sample listings to check for price issues
stmt_sample = select(ProductListing).where(
    and_(
        ProductListing.created_at >= today_start,
        ProductListing.created_at < today_end,
        ProductListing.source_platform == 'flipkart'
    )
).limit(10)
samples = db.execute(stmt_sample).scalars().all()

print(f"📊 Flipkart Listings from Today: {total_count}")
print(f"\n🔍 Sample Listings (checking for corrupted prices):")
print("=" * 80)

corrupted = 0
for listing in samples:
    price = listing.current_price
    price_int = int(price) if price else 0
    
    # Check for suspicious price patterns
    is_suspicious = False
    reason = ""
    
    if price_int >= 10000:
        ratio = price_int / 100
        if 20 <= ratio <= 50000:
            is_suspicious = True
            reason = f"x100 inflation ({price_int} → {int(ratio)})"
    
    if 1000 <= price_int <= 99999:
        last_two = price_int % 100
        if last_two in [25, 34, 50, 75, 99]:
            ratio = price_int / 100
            if 20 <= ratio <= 3000:
                is_suspicious = True
                reason = f"Decimal-as-integer ({price_int} → {int(ratio)})"
    
    status = "❌ CORRUPTED" if is_suspicious else "✓ OK"
    if is_suspicious:
        corrupted += 1
    
    print(f"{status}: {listing.title[:40]:40} | ₹{price:>8} | {reason}")

print("=" * 80)
print(f"\n📈 Summary:")
print(f"  Total today: {total_count}")
print(f"  Likely corrupted (sampled): {corrupted}/10 ({corrupted*10}%)")
print(f"  Estimated corrupted overall: ~{int(total_count * corrupted / 10)}")

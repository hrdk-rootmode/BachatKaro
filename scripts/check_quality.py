#!/usr/bin/env python3
"""
Data Quality Check Script
==========================

Analyze product data quality metrics.
Reports on confidence levels, null rates, and invalid values.

Usage:
    python scripts/check_quality.py
    python scripts/check_quality.py --platform amazon
    python scripts/check_quality.py --detailed

Author: DealHunt
Version: 1.0
"""

import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from sqlalchemy import select, func, and_

from app.core.database import async_session_maker
from app.models import Product, ProductListing, Platform


# =============================================================================
# INVALID VALUE DETECTION
# =============================================================================

INVALID_VALUES = [
    'null', 'none', 'n/a', 'na', 'unknown', 'not available',
    '-', '', 'undefined', 'not specified', 'blank'
]

GARBAGE_BRANDS = [
    'unknown', 'generic', 'unbranded', 'men', 'women', 'boys', 'girls',
    'cotton', 'silk', 'black', 'white', 'blue', 'red', 'casual', 'formal'
]


# =============================================================================
# QUALITY METRICS
# =============================================================================

async def get_overall_metrics() -> dict:
    """Get overall data quality metrics"""
    async with async_session_maker() as db:
        total_result = await db.execute(select(func.count(Product.id)))
        total_products = total_result.scalar() or 0

        color_null_result = await db.execute(
            select(func.count(Product.id)).where(Product.color.is_(None))
        )
        color_nulls = color_null_result.scalar() or 0

        brand_null_result = await db.execute(
            select(func.count(Product.id)).where(Product.brand.is_(None))
        )
        brand_nulls = brand_null_result.scalar() or 0

        invalid_brand_result = await db.execute(
            select(func.count(Product.id)).where(
                func.lower(Product.brand).in_(GARBAGE_BRANDS)
            )
        )
        invalid_brands = invalid_brand_result.scalar() or 0

        avg_brand_conf_result = await db.execute(
            select(func.avg(Product.brand_confidence)).where(
                Product.brand_confidence.isnot(None)
            )
        )
        avg_brand_conf = avg_brand_conf_result.scalar() or 0.0

        avg_color_conf_result = await db.execute(
            select(func.avg(Product.color_confidence)).where(
                Product.color_confidence.isnot(None)
            )
        )
        avg_color_conf = avg_color_conf_result.scalar() or 0.0

        enriched_result = await db.execute(
            select(func.count(Product.id)).where(
                Product.last_enriched_at.isnot(None)
            )
        )
        enriched_count = enriched_result.scalar() or 0

        return {
            "total_products": total_products,
            "color_nulls": color_nulls,
            "color_null_rate": (color_nulls / total_products * 100) if total_products > 0 else 0,
            "brand_nulls": brand_nulls,
            "brand_null_rate": (brand_nulls / total_products * 100) if total_products > 0 else 0,
            "invalid_brands": invalid_brands,
            "invalid_brand_rate": (invalid_brands / total_products * 100) if total_products > 0 else 0,
            "avg_brand_confidence": avg_brand_conf,
            "avg_color_confidence": avg_color_conf,
            "enriched_count": enriched_count,
            "enriched_rate": (enriched_count / total_products * 100) if total_products > 0 else 0,
        }


async def get_platform_metrics() -> list:
    """Get quality metrics per platform"""
    async with async_session_maker() as db:
        platforms_result = await db.execute(select(Platform))
        platforms = platforms_result.scalars().all()

        metrics = []

        for platform in platforms:
            count_result = await db.execute(
                select(func.count(Product.id)).select_from(Product).join(
                    ProductListing, Product.id == ProductListing.product_id
                ).where(ProductListing.platform_id == platform.id)
            )
            product_count = count_result.scalar() or 0

            if product_count == 0:
                continue

            color_null_result = await db.execute(
                select(func.count(Product.id)).select_from(Product).join(
                    ProductListing, Product.id == ProductListing.product_id
                ).where(
                    and_(
                        ProductListing.platform_id == platform.id,
                        Product.color.is_(None)
                    )
                )
            )
            color_nulls = color_null_result.scalar() or 0

            brand_null_result = await db.execute(
                select(func.count(Product.id)).select_from(Product).join(
                    ProductListing, Product.id == ProductListing.product_id
                ).where(
                    and_(
                        ProductListing.platform_id == platform.id,
                        Product.brand.is_(None)
                    )
                )
            )
            brand_nulls = brand_null_result.scalar() or 0

            avg_brand_conf_result = await db.execute(
                select(func.avg(Product.brand_confidence)).select_from(Product).join(
                    ProductListing, Product.id == ProductListing.product_id
                ).where(
                    and_(
                        ProductListing.platform_id == platform.id,
                        Product.brand_confidence.isnot(None)
                    )
                )
            )
            avg_brand_conf = avg_brand_conf_result.scalar() or 0.0

            avg_color_conf_result = await db.execute(
                select(func.avg(Product.color_confidence)).select_from(Product).join(
                    ProductListing, Product.id == ProductListing.product_id
                ).where(
                    and_(
                        ProductListing.platform_id == platform.id,
                        Product.color_confidence.isnot(None)
                    )
                )
            )
            avg_color_conf = avg_color_conf_result.scalar() or 0.0

            metrics.append({
                "platform": platform.name,
                "product_count": product_count,
                "color_null_rate": (color_nulls / product_count * 100) if product_count > 0 else 0,
                "brand_null_rate": (brand_nulls / product_count * 100) if product_count > 0 else 0,
                "avg_brand_confidence": avg_brand_conf,
                "avg_color_confidence": avg_color_conf,
            })

        return metrics


async def get_healing_metrics() -> dict:
    """Get self-healing metrics"""
    async with async_session_maker() as db:
        platforms_result = await db.execute(
            select(Platform).where(Platform.healing_stats.isnot(None))
        )
        platforms = platforms_result.scalars().all()

        total_attempts = 0
        total_heals = 0
        platforms_with_healing = 0

        for platform in platforms:
            if platform.healing_stats:
                total_attempts += platform.healing_stats.get("total_attempts", 0)
                total_heals += platform.healing_stats.get("successful_heals", 0)
                if platform.healing_stats.get("successful_heals", 0) > 0:
                    platforms_with_healing += 1

        return {
            "total_platforms": len(platforms),
            "platforms_with_healing": platforms_with_healing,
            "total_healing_attempts": total_attempts,
            "total_successful_heals": total_heals,
            "healing_success_rate": (total_heals / total_attempts * 100) if total_attempts > 0 else 0,
        }


# =============================================================================
# DISPLAY FUNCTIONS
# =============================================================================

def print_overall_metrics(metrics: dict):
    """Print overall quality metrics"""
    print("\n" + "=" * 70)
    print("📊 OVERALL DATA QUALITY METRICS")
    print("=" * 70)

    print(f"\n   Total Products: {metrics['total_products']:,}")
    print(f"   Enriched Products: {metrics['enriched_count']:,} ({metrics['enriched_rate']:.1f}%)")

    print("\n   🎨 COLOR QUALITY:")
    print(f"      • Null Rate: {metrics['color_null_rate']:.1f}% ({metrics['color_nulls']:,} products)")
    print(f"      • Avg Confidence: {metrics['avg_color_confidence']:.2f}")

    print("\n   🏷️  BRAND QUALITY:")
    print(f"      • Null Rate: {metrics['brand_null_rate']:.1f}% ({metrics['brand_nulls']:,} products)")
    print(f"      • Invalid Rate: {metrics['invalid_brand_rate']:.1f}% ({metrics['invalid_brands']:,} products)")
    print(f"      • Avg Confidence: {metrics['avg_brand_confidence']:.2f}")

    quality_score = 100
    quality_score -= metrics['color_null_rate'] * 0.3
    quality_score -= metrics['brand_null_rate'] * 0.3
    quality_score -= metrics['invalid_brand_rate'] * 0.4
    quality_score = max(0, quality_score)

    print(f"\n   📈 OVERALL QUALITY SCORE: {quality_score:.1f}/100")

    if quality_score >= 85:
        status = "🟢 EXCELLENT"
    elif quality_score >= 70:
        status = "🟡 GOOD"
    elif quality_score >= 50:
        status = "🟠 FAIR"
    else:
        status = "🔴 NEEDS IMPROVEMENT"

    print(f"   Status: {status}")


def print_platform_metrics(metrics: list):
    """Print per-platform quality metrics"""
    print("\n" + "=" * 70)
    print("🌐 PER-PLATFORM QUALITY METRICS")
    print("=" * 70)

    metrics = sorted(metrics, key=lambda x: x['product_count'], reverse=True)

    for m in metrics:
        print(f"\n   📌 {m['platform'].upper()}")
        print(f"      Products: {m['product_count']:,}")
        print(f"      Color Null: {m['color_null_rate']:.1f}% | Conf: {m['avg_color_confidence']:.2f}")
        print(f"      Brand Null: {m['brand_null_rate']:.1f}% | Conf: {m['avg_brand_confidence']:.2f}")


def print_healing_metrics(metrics: dict):
    """Print healing metrics"""
    print("\n" + "=" * 70)
    print("🔧 SELF-HEALING METRICS")
    print("=" * 70)

    print(f"\n   Platforms with Healing: {metrics['platforms_with_healing']}/{metrics['total_platforms']}")
    print(f"   Total Healing Attempts: {metrics['total_healing_attempts']:,}")
    print(f"   Successful Heals: {metrics['total_successful_heals']:,}")
    print(f"   Success Rate: {metrics['healing_success_rate']:.1f}%")


def print_recommendations(overall: dict, platforms: list):
    """Print actionable recommendations"""
    print("\n" + "=" * 70)
    print("💡 RECOMMENDATIONS")
    print("=" * 70)

    recommendations = []

    if overall['color_null_rate'] > 10:
        recommendations.append(
            f"• Color null rate is high ({overall['color_null_rate']:.1f}%). "
            "Consider running backfill script."
        )

    if overall['brand_null_rate'] > 5:
        recommendations.append(
            f"• Brand null rate is {overall['brand_null_rate']:.1f}%. "
            "Review brand extraction logic."
        )

    if overall['invalid_brand_rate'] > 2:
        recommendations.append(
            f"• Found {overall['invalid_brands']:,} invalid brands. "
            "Run cleanup: UPDATE products SET brand=NULL WHERE brand IN (...)."
        )

    if overall['avg_brand_confidence'] < 0.6:
        recommendations.append(
            "• Average brand confidence is low. Improve extraction sources."
        )

    for p in platforms:
        if p['color_null_rate'] > 15:
            recommendations.append(
                f"• {p['platform'].upper()}: High color null rate ({p['color_null_rate']:.1f}%). "
                "Check platform scraper."
            )

    if not recommendations:
        recommendations.append("✅ Data quality looks good! No critical issues found.")

    for rec in recommendations[:10]:
        print(f"\n   {rec}")


# =============================================================================
# MAIN
# =============================================================================

async def main(args):
    """Main quality check function"""
    print("=" * 70)
    print("🔍 DEALHUNT DATA QUALITY CHECK")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    overall = await get_overall_metrics()
    platforms = await get_platform_metrics()
    healing = await get_healing_metrics()

    print_overall_metrics(overall)

    if args.detailed or args.platform:
        if args.platform:
            platforms = [p for p in platforms if p['platform'] == args.platform]
        print_platform_metrics(platforms)

    print_healing_metrics(healing)
    print_recommendations(overall, platforms)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check Data Quality")
    parser.add_argument("--platform", type=str, help="Check specific platform only")
    parser.add_argument("--detailed", action="store_true", help="Show detailed per-platform metrics")

    args = parser.parse_args()

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")

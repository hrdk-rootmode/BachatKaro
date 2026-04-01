"""
Centralized Business Logic Module

All data transformation, filtering, and business rule logic is here:
- Response formatting
- Data validation
- Filtering (confidence, variants, platform)
- Price calculations
- Feature logic

Usage:
    from app.services.logic import BusinessLogic
    
    logic = BusinessLogic()
    formatted = logic.format_product_detail(product, listings)
    filtered = logic.filter_valid_listings(listings, product)
"""

from typing import List, Optional, Dict, Tuple, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.models import Product, ProductListing, PriceHistory, Platform
from app.schemas import (
    ProductResponse,
    ProductListingResponse,
    PriceHistoryResponse,
    PriceHistoryPoint,
    TrendingProductResponse,
    Platform as PlatformEnum
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class BusinessLogic:
    """
    SINGLE SOURCE OF TRUTH for all business logic
    
    Responsibilities:
    ✅ Filter invalid listings (confidence, platform settings)
    ✅ Check variant consistency
    ✅ Format responses
    ✅ Calculate price trends
    ✅ Process AI metadata
    ✅ Apply business rules
    """
    
    # ========================================================================
    # FILTERING & VALIDATION LOGIC
    # ========================================================================
    
    @staticmethod
    def is_listing_allowed(listing: ProductListing) -> bool:
        """
        Check if listing meets quality thresholds
        
        Rejects:
        - Disabled platforms (e.g., Croma)
        - Low confidence extractions
        
        Returns:
            True if listing should be displayed
        """
        # Platform check
        if hasattr(listing, "platform") and listing.platform:
            if listing.platform.name.lower() == "croma" and not getattr(settings, "CROMA_ENABLED", False):
                logger.debug(f"Listing {listing.id} rejected: Croma disabled")
                return False
        
        # Confidence check
        min_confidence = float(getattr(settings, "MIN_LISTING_CONFIDENCE", 0.6))
        if listing.extraction_confidence is not None and listing.extraction_confidence < min_confidence:
            logger.debug(f"Listing {listing.id} rejected: Low confidence ({listing.extraction_confidence})")
            return False
        
        return True
    
    @staticmethod
    def is_variant_consistent(
        listing: ProductListing,
        product: Product
    ) -> bool:
        """
        Check if listing variant matches product variant
        
        Prevents cross-variant leakage:
        - E.g., showing iPhone 14 storage and iPhone 14 Pro color together
        
        Returns:
            True if variant fingerprint matches
        """
        product_fp = getattr(product, "variant_fingerprint", None)
        listing_fp = getattr(listing, "variant_fingerprint", None)
        
        # If both have fingerprints, they must match
        if product_fp and listing_fp and str(product_fp) != str(listing_fp):
            logger.debug(
                f"Listing {listing.id} variant mismatch: "
                f"product_fp={product_fp} vs listing_fp={listing_fp}"
            )
            return False
        
        return True
    
    @staticmethod
    def filter_valid_listings(
        listings: List[ProductListing],
        product: Product
    ) -> List[ProductListing]:
        """
        Filter listings to only valid ones
        
        Applies both is_listing_allowed and is_variant_consistent
        
        Args:
            listings: Raw listings from database
            product: Parent product
            
        Returns:
            Filtered list of valid listings
        """
        valid = []
        for listing in listings:
            if listing and BusinessLogic.is_listing_allowed(listing) and \
               BusinessLogic.is_variant_consistent(listing, product):
                valid.append(listing)
        
        logger.debug(
            f"Filtered {len(listings)} listings → {len(valid)} valid "
            f"(removed {len(listings) - len(valid)} invalid)"
        )
        return valid
    
    # ========================================================================
    # HELPER: Get platform name safely
    # ========================================================================
    
    @staticmethod
    def _get_platform_name(listing: ProductListing) -> str:
        """Safely get platform name from listing"""
        if hasattr(listing, 'platform') and listing.platform:
            return listing.platform.name.lower()
        return "amazon"
    
    @staticmethod
    def _get_platform_enum(platform_name: str) -> PlatformEnum:
        """Convert platform name string to enum"""
        try:
            return PlatformEnum[platform_name.upper()]
        except (KeyError, AttributeError):
            return PlatformEnum.AMAZON
    
    # ========================================================================
    # RESPONSE FORMATTING
    # ========================================================================
    
    @staticmethod
    def format_listing_response(
        listing: ProductListing,
        product: Product
    ) -> ProductListingResponse:
        """
        Format ProductListing ORM to API response schema
        
        Args:
            listing: ProductListing ORM object
            product: Parent Product ORM object
            
        Returns:
            ProductListingResponse ready for API
        """
        platform_name = BusinessLogic._get_platform_name(listing)
        platform_enum = BusinessLogic._get_platform_enum(platform_name)
        
        return ProductListingResponse(
            id=str(listing.id),
            product_id=str(listing.product_id) if listing.product_id else None,
            platform_id=listing.platform_id,
            platform_name=platform_name,
            platform=platform_enum,
            platform_product_id=listing.external_id or "",
            url=listing.product_url or "",
            title=product.title or "",
            current_price=Decimal(str(listing.current_price)) if listing.current_price else Decimal("0"),
            original_price=Decimal(str(listing.original_price)) if listing.original_price else None,
            discount_percentage=int(listing.discount_percent) if listing.discount_percent else None,
            discount_percent=Decimal(str(listing.discount_percent)) if listing.discount_percent else None,
            rating=Decimal(str(listing.rating)) if listing.rating else None,
            review_count=listing.review_count,
            image_url=product.image_url,
            in_stock=listing.in_stock if listing.in_stock is not None else True,
            last_scraped_at=listing.last_scraped or datetime.utcnow(),
            extraction_confidence=listing.extraction_confidence,
            extraction_method=listing.extraction_method,
            data_source=listing.data_source,
            seller_name=listing.seller_name,
            seller_rating=Decimal(str(listing.seller_rating)) if listing.seller_rating is not None else None,
            variant_fingerprint=listing.variant_fingerprint
        )
    
    @staticmethod
    def format_product_response(
        product: Product,
        listings: List[ProductListing]
    ) -> ProductResponse:
        """
        Format complete product detail response
        
        Calculates:
        - Best price across platforms
        - Average price
        - Price trend
        - Formats all listings
        
        Args:
            product: Product ORM object
            listings: Filtered valid listings
            
        Returns:
            ProductResponse ready for API
        """
        # Calculate best price
        best_price = Decimal("0")
        best_platform = PlatformEnum.AMAZON
        avg_price = None
        
        listings_with_price = [l for l in listings if l.current_price is not None]
        
        if listings_with_price:
            # Get cheapest listing
            best_listing = min(listings_with_price, key=lambda x: x.current_price or 0)
            best_price = Decimal(str(best_listing.current_price or 0))
            
            platform_name = BusinessLogic._get_platform_name(best_listing)
            best_platform = BusinessLogic._get_platform_enum(platform_name)
            
            # Calculate average
            prices = [float(l.current_price) for l in listings_with_price if l.current_price]
            if prices:
                avg_price = Decimal(str(sum(prices) / len(prices)))
        
        # Calculate price trend
        price_trend = "stable"
        if avg_price and best_price:
            if best_price < avg_price * Decimal("0.9"):
                price_trend = "down"
            elif best_price > avg_price * Decimal("1.1"):
                price_trend = "up"
        
        # Get AI metadata
        ai_metadata = product.ai_metadata or {}
        
        # Format response - ✅ FIXED: Include all required fields
        return ProductResponse(
            id=str(product.id),
            fingerprint=product.fingerprint or "",
            # ✅ FIXED: Added missing required fields
            title=product.title,
            brand=product.brand,
            category=product.category,
            subcategory=product.subcategory,
            image_url=product.image_url,
            specifications=product.specifications or {},
            # Variant fields
            variant_fingerprint=product.variant_fingerprint,
            base_fingerprint=product.base_fingerprint,
            variant_type=product.variant_type,
            storage_gb=product.storage_gb,
            color=product.color,
            condition=product.condition,
            # Confidence fields
            brand_confidence=product.brand_confidence,
            brand_source=product.brand_source,
            color_confidence=product.color_confidence,
            color_source=product.color_source,
            specs_confidence=product.specs_confidence,
            specs_source=product.specs_source,
            last_enriched_at=product.last_enriched_at,
            enrichment_version=product.enrichment_version,
            # Pricing
            best_price=best_price,
            best_platform=best_platform,
            avg_price=avg_price,
            price_trend=price_trend,
            # AI metadata
            ai_generated_essence=ai_metadata.get("essence", product.title or ""),
            ai_extracted_specs=product.specifications or {},
            ai_tags=ai_metadata.get("tags", []),
            ai_metadata=ai_metadata,
            stats=product.stats or {},
            created_at=product.created_at or datetime.utcnow(),
            updated_at=product.updated_at,
            # Formatted listings
            listings=[
                BusinessLogic.format_listing_response(listing, product)
                for listing in listings
                if listing is not None
            ]
        )

    @staticmethod
    def _build_india_sale_calendar(year: int) -> List[Dict[str, Any]]:
        """Approximate major India e-commerce sale windows used for advisory context."""
        return [
            {
                "name": "Republic Day Sale",
                "start": datetime(year, 1, 18),
                "end": datetime(year, 1, 29),
                "discount_bias": 0.06,
            },
            {
                "name": "Holi Sale",
                "start": datetime(year, 3, 5),
                "end": datetime(year, 3, 18),
                "discount_bias": 0.05,
            },
            {
                "name": "Summer Sale",
                "start": datetime(year, 5, 1),
                "end": datetime(year, 5, 22),
                "discount_bias": 0.07,
            },
            {
                "name": "Independence Day Sale",
                "start": datetime(year, 8, 5),
                "end": datetime(year, 8, 18),
                "discount_bias": 0.07,
            },
            {
                "name": "Big Billion / Great Indian Festival",
                "start": datetime(year, 10, 1),
                "end": datetime(year, 10, 25),
                "discount_bias": 0.12,
            },
            {
                "name": "Diwali Sale",
                "start": datetime(year, 10, 20),
                "end": datetime(year, 11, 12),
                "discount_bias": 0.14,
            },
            {
                "name": "Year End Sale",
                "start": datetime(year, 12, 20),
                "end": datetime(year, 12, 31),
                "discount_bias": 0.08,
            },
        ]

    @staticmethod
    def _get_upcoming_india_sale_event(reference_date: datetime) -> Optional[Dict[str, Any]]:
        """Get nearest active/upcoming India sale event with days-to-start metadata."""
        events = (
            BusinessLogic._build_india_sale_calendar(reference_date.year)
            + BusinessLogic._build_india_sale_calendar(reference_date.year + 1)
        )
        active_or_upcoming = [event for event in events if event["end"] >= reference_date]
        if not active_or_upcoming:
            return None

        nearest = min(active_or_upcoming, key=lambda event: event["start"])
        days_until_start = max(0, (nearest["start"].date() - reference_date.date()).days)
        window_days = max(1, (nearest["end"].date() - nearest["start"].date()).days + 1)

        return {
            **nearest,
            "days_until_start": days_until_start,
            "window_days": window_days,
        }

    @staticmethod
    def _predict_price_signal(
        prices: List[float],
        dates: List[datetime],
        history_span_days: int,
        current_price: float,
        lowest_price: float,
        highest_price: float,
        average_price: float,
        price_drop_percentage: Optional[float],
    ) -> Dict[str, Any]:
        """
        Honest trend signal model.
        Rules:
        - Never provide directional prediction unless history is sufficient
        - Prefer observed 7-day movement and nearby sale-window context
        - Avoid absolute price forecasting output when confidence is limited
        """
        if not prices or current_price <= 0:
            return {
                "data_points_count": len(prices),
                "history_span_days": max(0, int(history_span_days or 0)),
                "observed_change_percentage_7d": None,
                "observed_drop_amount_7d": None,
                "prediction_available": False,
                "predicted_change_percentage_7d": None,
                "predicted_price_7d": None,
                "predicted_price_30d": None,
                "predicted_change_percentage_30d": None,
                "recommendation": "watch",
                "confidence_score": None,
                "recommendation_reasons": ["Not enough valid price points to build weekly insight."],
                "insight_basis": [],
                "upcoming_sale_event": None,
                "days_until_sale_event": None,
            }

        points_count = len(prices)
        upcoming_event = BusinessLogic._get_upcoming_india_sale_event(datetime.utcnow())

        observed_change_7d = None
        observed_drop_amount_7d = None
        if points_count >= 2 and len(dates) >= 2:
            latest_date = dates[-1]
            target_date = latest_date - timedelta(days=7)
            reference_idx = None

            for idx in range(len(dates) - 1, -1, -1):
                if dates[idx] <= target_date:
                    reference_idx = idx
                    break

            if reference_idx is None and history_span_days >= 5:
                reference_idx = 0

            if reference_idx is not None:
                ref_price = prices[reference_idx]
                if ref_price > 0:
                    observed_change_7d = ((current_price - ref_price) / ref_price) * 100.0
                    if current_price < ref_price:
                        observed_drop_amount_7d = ref_price - current_price

        prediction_available = bool(points_count >= 8 and history_span_days >= 21)
        predicted_change_7d = None

        if prediction_available and len(dates) >= 2:
            latest_date = dates[-1]
            weekly_samples: List[float] = []

            for days_back in [7, 14, 21, 28]:
                target_date = latest_date - timedelta(days=days_back)
                past_price = None
                for idx in range(len(dates) - 1, -1, -1):
                    if dates[idx] <= target_date:
                        past_price = prices[idx]
                        break

                if past_price and past_price > 0:
                    full_change_pct = ((current_price - past_price) / past_price) * 100.0
                    weekly_equivalent_pct = full_change_pct / max(1.0, days_back / 7.0)
                    weekly_samples.append(weekly_equivalent_pct)

            if weekly_samples:
                predicted_change_7d = sum(weekly_samples) / len(weekly_samples)

            if predicted_change_7d is None and observed_change_7d is not None:
                predicted_change_7d = observed_change_7d

            if predicted_change_7d is not None and upcoming_event and upcoming_event.get("days_until_start", 999) <= 21:
                event_bias = float(upcoming_event.get("discount_bias", 0.0))
                predicted_change_7d -= min(4.0, max(0.8, event_bias * 28.0))

            if predicted_change_7d is not None:
                predicted_change_7d = max(-15.0, min(15.0, predicted_change_7d))

        predicted_change_30d = None
        if predicted_change_7d is not None:
            predicted_change_30d = max(-30.0, min(30.0, predicted_change_7d * 4.0))

        near_low_pct = ((current_price - lowest_price) / lowest_price * 100.0) if lowest_price > 0 else 100.0
        recommendation = "watch"
        reasons: List[str] = []
        basis: List[str] = [f"{points_count} data point(s) across {history_span_days} day(s)"]

        if observed_change_7d is not None:
            if observed_change_7d < 0:
                drop_pct = abs(observed_change_7d)
                if observed_drop_amount_7d is not None:
                    reasons.append(
                        f"Observed drop in last 7 days: {drop_pct:.1f}% (about Rs {observed_drop_amount_7d:.0f})."
                    )
                else:
                    reasons.append(f"Observed drop in last 7 days: {drop_pct:.1f}%.")
            elif observed_change_7d > 0:
                reasons.append(f"Observed rise in last 7 days: {observed_change_7d:.1f}%.")
            else:
                reasons.append("Price remained almost flat over the last 7 days.")
            basis.append("uses observed 7-day movement")
        else:
            reasons.append("Recent 7-day movement is unavailable because history is too short.")

        confidence = None
        if prediction_available and predicted_change_7d is not None:
            confidence_value = 44.0
            confidence_value += min(24.0, points_count * 1.6)
            confidence_value += min(16.0, history_span_days * 0.35)
            if observed_change_7d is not None:
                confidence_value += 5.0
            if upcoming_event and upcoming_event.get("days_until_start", 999) <= 45:
                confidence_value += 3.0
            confidence = max(45.0, min(90.0, confidence_value))
            basis.append("prediction enabled by sufficient history")
            if predicted_change_7d <= -3.0:
                recommendation = "wait"
                reasons.append(
                    f"Trend signal suggests another ~{abs(predicted_change_7d):.1f}% downside over next week."
                )
            elif near_low_pct <= 3.0 and predicted_change_7d >= -1.5:
                recommendation = "buy_now"
                reasons.append("Current price is close to the 120-day low and sharp further drop is not indicated.")
        else:
            reasons.append("Prediction hidden: need at least 8 points across 21 days for a reliable trend signal.")

        if recommendation == "watch":
            if upcoming_event and upcoming_event.get("days_until_start", 999) <= 12:
                recommendation = "wait"
                reasons.append("Major sale window is very close, so waiting may unlock a better offer.")
            elif near_low_pct <= 2.5 and (observed_change_7d is None or observed_change_7d >= -2.0):
                recommendation = "buy_now"
                reasons.append("Price is already near the observed low range.")

        if (price_drop_percentage or 0.0) >= 12.0 and current_price <= (average_price * 0.94):
            if recommendation != "wait":
                recommendation = "buy_now"
            reasons.append("Current price is materially below the 120-day average.")

        if upcoming_event and upcoming_event.get("days_until_start", 999) <= 60:
            reasons.append(
                f"{upcoming_event['name']} starts in {upcoming_event['days_until_start']} day(s), which can unlock better India offers."
            )
            basis.append("uses nearby India sale calendar")

        return {
            "data_points_count": points_count,
            "history_span_days": max(0, int(history_span_days or 0)),
            "observed_change_percentage_7d": round(observed_change_7d, 2) if observed_change_7d is not None else None,
            "observed_drop_amount_7d": round(observed_drop_amount_7d, 2) if observed_drop_amount_7d is not None else None,
            "prediction_available": prediction_available,
            "predicted_change_percentage_7d": round(predicted_change_7d, 2) if predicted_change_7d is not None else None,
            "predicted_price_7d": None,
            "predicted_price_30d": None,
            "predicted_change_percentage_30d": round(predicted_change_30d, 2) if predicted_change_30d is not None else None,
            "recommendation": recommendation,
            "confidence_score": round(confidence, 1) if confidence is not None else None,
            "recommendation_reasons": reasons[:4],
            "insight_basis": basis[:3],
            "upcoming_sale_event": upcoming_event["name"] if upcoming_event else None,
            "days_until_sale_event": upcoming_event.get("days_until_start") if upcoming_event else None,
        }
    
    @staticmethod
    def format_price_history_response(
        product: Product,
        listing: ProductListing,
        history: List[PriceHistory]
    ) -> PriceHistoryResponse:
        """
        Format price history response
        
        Converts PriceHistory records to chart-ready points
        
        Args:
            product: Product ORM object
            listing: ProductListing ORM object
            history: List of PriceHistory records
            
        Returns:
            PriceHistoryResponse ready for API
        """
        # Get platform enum
        platform_name = BusinessLogic._get_platform_name(listing)
        platform_enum = BusinessLogic._get_platform_enum(platform_name)
        
        # ✅ FIXED: Convert history to PriceHistoryPoint with correct fields
        points = []
        prices = []
        
        ordered_history = sorted(history, key=lambda x: x.recorded_at)
        history_dates: List[datetime] = []

        for price_record in ordered_history:
            price_value = float(price_record.price) if price_record.price else 0
            prices.append(price_value)
            history_dates.append(price_record.recorded_at)
            
            points.append(
                PriceHistoryPoint(
                    date=price_record.recorded_at,
                    price=Decimal(str(price_value)),
                    platform=platform_enum  # ✅ FIXED: Added required platform field
                )
            )

        # If there is no recorded history yet but listing has a live price,
        # return a single-point baseline instead of zeroed stats.
        if not points and listing.current_price and float(listing.current_price) > 0:
            baseline_price = float(listing.current_price)
            prices.append(baseline_price)
            baseline_date = listing.last_scraped or datetime.utcnow()
            history_dates.append(baseline_date)
            points.append(
                PriceHistoryPoint(
                    date=baseline_date,
                    price=Decimal(str(baseline_price)),
                    platform=platform_enum,
                )
            )

        data_points_count = len(prices)
        history_span_days = 0
        if len(history_dates) >= 2:
            history_span_days = max(
                0,
                (history_dates[-1].date() - history_dates[0].date()).days,
            )
        
        # ✅ FIXED: Calculate required statistics
        lowest_price = Decimal(str(min(prices))) if prices else Decimal("0")
        highest_price = Decimal(str(max(prices))) if prices else Decimal("0")
        average_price = Decimal(str(sum(prices) / len(prices))) if prices else Decimal("0")
        
        # Calculate price drop percentage (current vs highest)
        current_price = float(listing.current_price) if listing.current_price else 0
        if current_price <= 0 and prices:
            current_price = float(prices[-1])
        price_drop_percentage = None
        if highest_price > 0 and current_price > 0:
            drop = ((float(highest_price) - current_price) / float(highest_price)) * 100
            if drop > 0:
                price_drop_percentage = Decimal(str(round(drop, 2)))

        forecast = BusinessLogic._predict_price_signal(
            prices=prices,
            dates=history_dates,
            history_span_days=history_span_days,
            current_price=current_price,
            lowest_price=float(lowest_price),
            highest_price=float(highest_price),
            average_price=float(average_price),
            price_drop_percentage=float(price_drop_percentage) if price_drop_percentage is not None else None,
        )
        
        # ✅ FIXED: Return with correct field names
        return PriceHistoryResponse(
            product_id=str(product.id),
            platform=platform_enum,
            history=points,  # ✅ FIXED: Changed from 'points' to 'history'
            data_points_count=data_points_count,
            history_span_days=history_span_days,
            lowest_price=lowest_price,
            highest_price=highest_price,
            average_price=average_price,
            price_drop_percentage=price_drop_percentage,
            observed_change_percentage_7d=(
                Decimal(str(forecast["observed_change_percentage_7d"]))
                if forecast.get("observed_change_percentage_7d") is not None
                else None
            ),
            observed_drop_amount_7d=(
                Decimal(str(forecast["observed_drop_amount_7d"]))
                if forecast.get("observed_drop_amount_7d") is not None
                else None
            ),
            prediction_available=bool(forecast.get("prediction_available", False)),
            predicted_change_percentage_7d=(
                Decimal(str(forecast["predicted_change_percentage_7d"]))
                if forecast.get("predicted_change_percentage_7d") is not None
                else None
            ),
            predicted_price_7d=(
                Decimal(str(forecast["predicted_price_7d"]))
                if forecast.get("predicted_price_7d") is not None
                else None
            ),
            predicted_price_30d=(
                Decimal(str(forecast["predicted_price_30d"]))
                if forecast.get("predicted_price_30d") is not None
                else None
            ),
            predicted_change_percentage_30d=(
                Decimal(str(forecast["predicted_change_percentage_30d"]))
                if forecast.get("predicted_change_percentage_30d") is not None
                else None
            ),
            recommendation=forecast.get("recommendation"),
            confidence_score=(
                Decimal(str(forecast["confidence_score"]))
                if forecast.get("confidence_score") is not None
                else None
            ),
            recommendation_reasons=forecast.get("recommendation_reasons", []),
            insight_basis=forecast.get("insight_basis", []),
            upcoming_sale_event=forecast.get("upcoming_sale_event"),
            days_until_sale_event=forecast.get("days_until_sale_event"),
        )
    
    @staticmethod
    def format_trending_response(
        product: Product,
        listing: ProductListing,
        platform_count: int = 1
    ) -> TrendingProductResponse:
        """
        Format product for trending/featured display
        
        Args:
            product: Product ORM object
            listing: ProductListing ORM object (preferred platform)
            platform_count: How many platforms have this product (for badge)
            
        Returns:
            TrendingProductResponse for carousel/list display
        """
        ai_metadata = product.ai_metadata or {}
        
        # Get best platform
        platform_name = BusinessLogic._get_platform_name(listing)
        best_platform_enum = BusinessLogic._get_platform_enum(platform_name)
        
        # ✅ FIXED: Ensure all required fields are present with correct types
        return TrendingProductResponse(
            product_id=str(product.id),
            title=ai_metadata.get("essence") or product.title or "Product",
            image_url=product.image_url,
            best_price=Decimal(str(listing.current_price or 0)),
            best_platform=best_platform_enum,
            discount_percentage=int(listing.discount_percent) if listing.discount_percent else None,
            search_count=0,  # ✅ FIXED: Added required field (set by caller if needed)
            rank=0,  # Set by caller
            # Variant info
            variant_fingerprint=getattr(listing, "variant_fingerprint", None),
            base_fingerprint=getattr(product, "base_fingerprint", None),
            variant_type=getattr(product, "variant_type", None),
            platform_count=platform_count
        )
    
    # ========================================================================
    # CALCULATION & AGGREGATION LOGIC
    # ========================================================================
    
    @staticmethod
    def calculate_best_price_info(listings: List[ProductListing]) -> Tuple[float, str]:
        """
        Calculate best price and best platform across listings
        
        Returns:
            Tuple of (best_price, best_platform_name)
        """
        best_price = 0
        best_platform = "amazon"
        
        listings_with_price = [l for l in listings if l.current_price is not None]
        if listings_with_price:
            best_listing = min(listings_with_price, key=lambda x: x.current_price or 0)
            best_price = float(best_listing.current_price or 0)
            best_platform = BusinessLogic._get_platform_name(best_listing)
        
        return best_price, best_platform
    
    @staticmethod
    def calculate_average_price(listings: List[ProductListing]) -> Optional[float]:
        """
        Calculate average price across all listings
        
        Returns:
            Average price or None if no listings
        """
        listings_with_price = [l for l in listings if l.current_price is not None]
        if not listings_with_price:
            return None
        
        prices = [float(l.current_price) for l in listings_with_price]
        return sum(prices) / len(prices)
    
    @staticmethod
    def calculate_price_trend(best_price: float, avg_price: Optional[float]) -> str:
        """
        Determine price trend (up/down/stable)
        
        Rules:
        - down: best < avg * 0.9 (10%+ below average)
        - up: best > avg * 1.1 (10%+ above average)
        - stable: otherwise
        
        Returns:
            'up', 'down', or 'stable'
        """
        if not avg_price or best_price == 0:
            return "stable"
        
        if best_price < avg_price * 0.9:
            return "down"
        elif best_price > avg_price * 1.1:
            return "up"
        else:
            return "stable"
    
    @staticmethod
    def get_price_points_for_chart(history: List[PriceHistory]) -> List[Dict]:
        """
        Convert PriceHistory records to chart-ready points
        
        Args:
            history: List of PriceHistory records
            
        Returns:
            List of dicts with 'date' and 'price' keys (sorted ascending)
        """
        points = []
        for record in sorted(history, key=lambda x: x.recorded_at):
            points.append({
                "date": record.recorded_at,
                "price": float(record.price),
            })
        
        return points
    
    # ========================================================================
    # FEATURE LOGIC
    # ========================================================================
    
    @staticmethod
    def select_diverse_listings(
        products: List[Product],
        all_listings_map: Dict[str, List[ProductListing]]
    ) -> List[Tuple[Product, ProductListing]]:
        """
        Select diverse platform listings for featured section
        
        Rotates platform preferences to show variety (Amazon, Flipkart, Meesho, etc)
        
        Args:
            products: List of products
            all_listings_map: Dict mapping product_id → list of listings
            
        Returns:
            List of (product, selected_listing) tuples
        """
        platform_rotation = ['amazon', 'flipkart', 'meesho', 'nykaa', 'myntra', 'croma']
        platform_index = 0
        
        results = []
        for product in products:
            product_id = str(product.id)
            listings = all_listings_map.get(product_id, [])
            
            if not listings:
                continue
            
            # Try to get from preferred platform
            preferred_platform = platform_rotation[platform_index % len(platform_rotation)]
            platform_index += 1
            
            selected_listing = None
            for listing in listings:
                platform_name = BusinessLogic._get_platform_name(listing)
                if platform_name == preferred_platform.lower():
                    selected_listing = listing
                    break
            
            # Fall back to cheapest if preferred not available
            if not selected_listing:
                listings_with_price = [l for l in listings if l.current_price is not None]
                if listings_with_price:
                    selected_listing = min(listings_with_price, key=lambda x: x.current_price or 0)
                else:
                    selected_listing = listings[0] if listings else None
            
            if selected_listing:
                results.append((product, selected_listing))
        
        return results
    
    @staticmethod
    def should_show_discount_badge(listing: ProductListing, min_discount: int = 10) -> bool:
        """
        Determine if listing should show discount badge
        
        Args:
            listing: ProductListing to check
            min_discount: Minimum discount % to show badge
            
        Returns:
            True if discount >= min_discount
        """
        if listing.discount_percent is None:
            return False
        return listing.discount_percent >= min_discount
    
    @staticmethod
    def categorize_price_level(
        current_price: float,
        average_price: float
    ) -> str:
        """
        Categorize price level relative to average
        
        Returns:
            'bargain', 'good', 'fair', 'expensive', or 'unknown'
        """
        if current_price == 0:
            return "unknown"
        
        ratio = current_price / average_price if average_price > 0 else 0
        
        if ratio < 0.85:
            return "bargain"
        elif ratio < 0.95:
            return "good"
        elif ratio < 1.1:
            return "fair"
        else:
            return "expensive"
    
    # ========================================================================
    # DATA AGGREGATION
    # ========================================================================
    
    @staticmethod
    def aggregate_category_stats(
        categories: Dict[str, int],
        limit: int = 10
    ) -> List[Dict]:
        """
        Format category stats for display
        
        Args:
            categories: Dict of {category: product_count}
            limit: Max categories to return
            
        Returns:
            List of {'name': category, 'count': count} dicts
        """
        return [
            {"name": category, "count": count}
            for category, count in sorted(
                categories.items(),
                key=lambda x: x[1],
                reverse=True
            )[:limit]
        ]
    
    @staticmethod
    def build_search_result_metadata(products: List[Product]) -> Dict:
        """
        Build metadata for search results
        
        Returns:
            Dict with stats: total_count, categories, price_range, etc
        """
        if not products:
            return {
                "total_count": 0,
                "categories": [],
                "price_range": {"min": 0, "max": 0}
            }
        
        # Collect categories
        categories = {}
        for product in products:
            if product.category:
                categories[product.category] = categories.get(product.category, 0) + 1
        
        return {
            "total_count": len(products),
            "categories": BusinessLogic.aggregate_category_stats(categories),
            "price_range": {
                "min": 0,
                "max": 0
            }
        }
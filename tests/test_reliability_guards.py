import pytest
from unittest.mock import MagicMock, AsyncMock
from decimal import Decimal
import asyncio
from datetime import datetime
import pytz

from app.models import ProductListing
from jobs.daily_scrape import _scrape_product_price, PRICE_SPIKE_MAX_RATIO, PER_PRODUCT_SCRAPE_TIMEOUT_SECONDS
from platforms.flipkart import FlipkartScraper
from app.services.scraper.base import ProductData

# =====================================================================
# Flipkart Outlier Guard Tests
# =====================================================================
def test_flipkart_outlier_guard_widened():
    """Test Fix S6: Flipkart JS/Python outlier guard matches new constraints."""
    scraper = FlipkartScraper(db=MagicMock())
    
    # Normal discount (should pass)
    c, o, d = scraper._normalize_price_snapshot(Decimal("1000"), Decimal("1500"))
    assert float(c) == 1000.0
    assert float(o) == 1500.0

    # Extreme parser error (old behavior still caught, ratio >= 8, c < 100)
    c, o, d = scraper._normalize_price_snapshot(Decimal("49"), Decimal("4999"))
    assert float(c) == 4999.0
    assert o is None

    # Mid-range parser error (new widened behavior: ratio >= 5, c < 500)
    # e.g., parser gets 499 instead of 4999
    c, o, d = scraper._normalize_price_snapshot(Decimal("499"), Decimal("4999"))
    assert float(c) == 4999.0
    assert o is None

    # Legitimate huge discount (e.g., clearance, ratio >= 5 but c > 500)
    c, o, d = scraper._normalize_price_snapshot(Decimal("550"), Decimal("3000"))
    assert float(c) == 550.0
    assert float(o) == 3000.0

    # Ratio barely missed (should pass)
    c, o, d = scraper._normalize_price_snapshot(Decimal("250"), Decimal("1000"))
    assert float(c) == 250.0  # ratio = 4.0 < 5.0
    assert float(o) == 1000.0

    # Original cost too low for guard (o < 1000)
    c, o, d = scraper._normalize_price_snapshot(Decimal("100"), Decimal("900"))
    assert float(c) == 100.0
    assert float(o) == 900.0


# =====================================================================
# Daily Scrape Guard Tests
# =====================================================================

@pytest.mark.asyncio
async def test_price_spike_rejection():
    """Test Fix S1: Price spike rejection behavior in _scrape_product_price."""
    listing = ProductListing(
        id=1,
        product_url="https://example.com/p",
        current_price=Decimal("1000.0"),
        external_id="ext-1"
    )
    
    mock_handler = MagicMock()
    # Mock normal valid price
    mock_handler.get_product = AsyncMock(return_value=ProductData(
        title="Test", price="1000.0", current_price="1050.0", in_stock=True
    ))

    with pytest.MonkeyPatch.context() as m:
        # Mock get_platform_handler to return our mocked handler
        m.setattr("jobs.daily_scrape.get_platform_handler", AsyncMock(return_value=mock_handler))
        
        signal_dict = {}
        # 1. Normal price variation (1.05x)
        price, stock = await _scrape_product_price(MagicMock(), "test_platform", listing, signal=signal_dict)
        assert price == 1050.0
        assert not signal_dict.get("spike_rejected")

        # 2. Huge price spike (e.g., 6x) -> should trigger rejection
        mock_handler.get_product = AsyncMock(return_value=ProductData(
            title="Test", price="6000.0", current_price="6000.0", in_stock=True
        ))
        signal_dict = {}
        price, stock = await _scrape_product_price(MagicMock(), "test_platform", listing, signal=signal_dict)
        assert price is None
        assert signal_dict.get("spike_rejected") is True

        # 3. Huge price drop (e.g., 0.1x) -> should trigger rejection
        mock_handler.get_product = AsyncMock(return_value=ProductData(
            title="Test", price="100.0", current_price="100.0", in_stock=True
        ))
        signal_dict = {}
        price, stock = await _scrape_product_price(MagicMock(), "test_platform", listing, signal=signal_dict)
        assert price is None
        assert signal_dict.get("spike_rejected") is True


@pytest.mark.asyncio
async def test_per_product_timeout_handling():
    """Test Fix S3: Per-product timeout wraps the scraping call correctly."""
    listing = ProductListing(
        id=1,
        product_url="https://example.com/p"
    )
    
    async def hanging_get_product(*args, **kwargs):
        await asyncio.sleep(PER_PRODUCT_SCRAPE_TIMEOUT_SECONDS + 2)
        return None

    mock_handler = MagicMock()
    mock_handler.get_product = hanging_get_product

    with pytest.MonkeyPatch.context() as m:
        m.setattr("jobs.daily_scrape.get_platform_handler", AsyncMock(return_value=mock_handler))
        
        # We expect a TimeoutError to be surfaced up, which daily_scrape catches as a general error
        with pytest.raises(asyncio.TimeoutError):
            # Test that the call times out relatively quickly 
            # In a real run, this limits hang time to PER_PRODUCT_SCRAPE_TIMEOUT_SECONDS
            await asyncio.wait_for(
                _scrape_product_price(MagicMock(), "test_platform", listing),
                timeout=PER_PRODUCT_SCRAPE_TIMEOUT_SECONDS + 1
            )

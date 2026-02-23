"""
Payment Router - Auto-selects payment method based on platform

Routes payments to:
- Razorpay (web browsers)
- Google Play Billing (Android app)
- Apple IAP (iOS app - future)

Usage:
    router = PaymentRouter()
    handler = router.get_handler("android")
    result = await handler.verify_purchase(token, product_id)
"""

import logging
from typing import Optional, Dict, Any, Union
from enum import Enum

from app.core.config import settings
from app.services.payments.razorpay_web import razorpay_client, RazorpayClient
from app.services.payments.google_play import google_play_client, GooglePlayBilling

logger = logging.getLogger(__name__)


class PaymentPlatform(str, Enum):
    """Supported payment platforms"""
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"


class PaymentRouter:
    """
    Routes payment requests to appropriate payment handler
    
    Features:
    - Auto-detect platform from request headers
    - Fallback to mock mode when credentials missing
    - Unified interface for all payment methods
    - Health check for all payment services
    
    Usage:
        router = PaymentRouter()
        
        # Get handler by platform
        handler = router.get_handler(PaymentPlatform.ANDROID)
        
        # Auto-detect from request
        handler = router.get_handler_from_request(request)
    """
    
    def __init__(self):
        self.razorpay = razorpay_client
        self.google_play = google_play_client
        # self.apple_iap = None  # Future
        
        logger.info("💳 Payment Router initialized")
        self._log_status()
    
    def _log_status(self):
        """Log payment service status"""
        logger.info(f"  ├── Razorpay: {'✅ Ready' if not self.razorpay.is_mock_mode else '⚠️ Mock Mode'}")
        logger.info(f"  └── Google Play: {'✅ Ready' if not self.google_play.is_mock_mode else '⚠️ Mock Mode'}")
    
    # =========================================================================
    # HANDLER SELECTION
    # =========================================================================
    
    def get_handler(
        self,
        platform: Union[PaymentPlatform, str]
    ) -> Union[RazorpayClient, GooglePlayBilling]:
        """
        Get payment handler for specified platform
        
        Args:
            platform: PaymentPlatform enum or string
            
        Returns:
            Payment handler instance
            
        Raises:
            ValueError: If platform not supported
        """
        if isinstance(platform, str):
            platform = platform.lower()
        
        if platform in [PaymentPlatform.WEB, "web", "razorpay"]:
            return self.razorpay
        
        elif platform in [PaymentPlatform.ANDROID, "android", "google", "google_play"]:
            return self.google_play
        
        elif platform in [PaymentPlatform.IOS, "ios", "apple", "apple_iap"]:
            raise ValueError("Apple IAP not yet implemented. Coming soon!")
        
        else:
            raise ValueError(f"Unknown payment platform: {platform}")
    
    def get_handler_from_headers(
        self,
        user_agent: str = "",
        x_platform: str = ""
    ) -> Union[RazorpayClient, GooglePlayBilling]:
        """
        Auto-detect payment handler from request headers
        
        Args:
            user_agent: User-Agent header
            x_platform: X-Platform custom header (recommended)
            
        Returns:
            Appropriate payment handler
        """
        # Check custom header first (most reliable)
        if x_platform:
            x_platform = x_platform.lower()
            if x_platform in ["android", "google"]:
                return self.google_play
            elif x_platform in ["ios", "apple"]:
                raise ValueError("Apple IAP not yet implemented")
            elif x_platform in ["web", "browser"]:
                return self.razorpay
        
        # Fallback to User-Agent detection
        user_agent = user_agent.lower()
        
        if "android" in user_agent and "mobile" in user_agent:
            # Android app should use Google Play
            return self.google_play
        
        elif "iphone" in user_agent or "ipad" in user_agent:
            # iOS app should use Apple IAP (not implemented)
            # For now, fall back to web
            logger.warning("iOS detected but Apple IAP not implemented. Using Razorpay.")
            return self.razorpay
        
        # Default to web (Razorpay)
        return self.razorpay
    
    # =========================================================================
    # STATUS & HEALTH
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all payment services
        
        Returns:
            Dict with status of each payment method
        """
        return {
            "razorpay": {
                "enabled": settings.RAZORPAY_ENABLED,
                "configured": settings.is_razorpay_configured,
                "mock_mode": self.razorpay.is_mock_mode,
                "platform": "web"
            },
            "google_play": {
                "enabled": settings.GOOGLE_PLAY_ENABLED,
                "configured": settings.is_google_play_configured,
                "mock_mode": self.google_play.is_mock_mode,
                "platform": "android"
            },
            "apple_iap": {
                "enabled": False,
                "configured": False,
                "mock_mode": True,
                "platform": "ios",
                "message": "Coming soon"
            }
        }
    
    def get_available_methods(
        self,
        platform: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get available payment methods for a platform
        
        Args:
            platform: Optional platform filter
            
        Returns:
            Dict of available payment methods
        """
        status = self.get_status()
        
        if platform:
            platform = platform.lower()
            if platform == "android":
                return {"google_play": status["google_play"]}
            elif platform == "ios":
                return {"apple_iap": status["apple_iap"]}
            elif platform == "web":
                return {"razorpay": status["razorpay"]}
        
        return status
    
    def get_recommended_method(
        self,
        user_agent: str = "",
        x_platform: str = ""
    ) -> str:
        """
        Get recommended payment method based on context
        
        Returns:
            Recommended platform string: "web", "android", or "ios"
        """
        try:
            handler = self.get_handler_from_headers(user_agent, x_platform)
            
            if isinstance(handler, GooglePlayBilling):
                return "android"
            else:
                return "web"
                
        except ValueError:
            return "web"  # Default fallback
    
    # =========================================================================
    # UNIFIED METHODS
    # =========================================================================
    
    async def verify_payment(
        self,
        platform: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Unified payment verification across platforms
        
        Args:
            platform: Payment platform
            **kwargs: Platform-specific arguments
                - web: razorpay_order_id, razorpay_payment_id, razorpay_signature
                - android: purchase_token, product_id
                - ios: receipt_data (future)
                
        Returns:
            Verification result dict
        """
        handler = self.get_handler(platform)
        
        if platform in ["web", "razorpay"]:
            is_valid = handler.verify_payment_signature(
                order_id=kwargs.get("razorpay_order_id"),
                payment_id=kwargs.get("razorpay_payment_id"),
                signature=kwargs.get("razorpay_signature")
            )
            return {
                "valid": is_valid,
                "platform": "web",
                "mock_mode": handler.is_mock_mode
            }
        
        elif platform in ["android", "google_play"]:
            result = await handler.verify_purchase(
                purchase_token=kwargs.get("purchase_token"),
                product_id=kwargs.get("product_id")
            )
            return {
                "valid": result.get("valid", False),
                "platform": "android",
                "order_id": result.get("order_id"),
                "expiry_time_millis": result.get("expiry_time_millis"),
                "auto_renewing": result.get("auto_renewing"),
                "mock_mode": result.get("mock_mode", handler.is_mock_mode)
            }
        
        else:
            raise ValueError(f"Unsupported platform: {platform}")
    
    def get_product_sku(
        self,
        plan_id: str,
        platform: str
    ) -> Optional[str]:
        """
        Get platform-specific product SKU for a plan
        
        Args:
            plan_id: Internal plan ID (pro, premium)
            platform: Payment platform
            
        Returns:
            Product SKU for the platform
        """
        if platform in ["android", "google_play"]:
            return self.google_play.get_sku_from_plan(plan_id)
        
        # Web doesn't need SKU (uses plan_id directly)
        return plan_id


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
payment_router = PaymentRouter()
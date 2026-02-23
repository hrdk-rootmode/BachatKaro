"""
Google Play Billing Integration
Handles purchase verification, subscription management, and webhooks

NOTE: Works in MOCK MODE when credentials are not configured
Mock mode allows development without Google Play Console access
"""

import logging
import json
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

class PurchaseState(int, Enum):
    """Google Play purchase states"""
    PURCHASED = 0
    CANCELED = 1
    PENDING = 2


class AcknowledgementState(int, Enum):
    """Google Play acknowledgement states"""
    NOT_ACKNOWLEDGED = 0
    ACKNOWLEDGED = 1


class SubscriptionState(int, Enum):
    """Google Play subscription states"""
    ACTIVE = 0
    CANCELED = 1
    IN_GRACE_PERIOD = 2
    ON_HOLD = 3
    PAUSED = 4
    EXPIRED = 5


# =============================================================================
# CHECK CREDENTIALS
# =============================================================================

GOOGLE_PLAY_MOCK_MODE = settings.GOOGLE_PLAY_MOCK_MODE

# Try to import Google libraries only if not in mock mode
if not GOOGLE_PLAY_MOCK_MODE:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        GOOGLE_LIBS_AVAILABLE = True
    except ImportError:
        GOOGLE_LIBS_AVAILABLE = False
        GOOGLE_PLAY_MOCK_MODE = True
        logger.warning("Google API libraries not installed. Running in mock mode.")
else:
    GOOGLE_LIBS_AVAILABLE = False
    logger.info("Google Play Billing running in MOCK MODE (development)")


# =============================================================================
# GOOGLE PLAY BILLING CLIENT
# =============================================================================

class GooglePlayBilling:
    """
    Google Play Billing API wrapper
    
    Features:
    - Verify purchase tokens
    - Check subscription status
    - Acknowledge purchases (required within 3 days!)
    - Handle subscription notifications (RTDN)
    - Mock mode for development
    
    Usage:
        client = GooglePlayBilling()
        result = await client.verify_purchase(token, product_id)
    """
    
    def __init__(self):
        self.package_name = settings.GOOGLE_PLAY_PACKAGE_NAME
        self.mock_mode = GOOGLE_PLAY_MOCK_MODE
        self.service = None
        
        if not self.mock_mode and GOOGLE_LIBS_AVAILABLE:
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    settings.GOOGLE_APPLICATION_CREDENTIALS,
                    scopes=['https://www.googleapis.com/auth/androidpublisher']
                )
                self.service = build('androidpublisher', 'v3', credentials=credentials)
                logger.info("✅ Google Play Billing client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Google Play client: {e}")
                self.mock_mode = True
        
        if self.mock_mode:
            logger.warning("⚠️ Google Play Billing running in MOCK mode")
    
    # =========================================================================
    # PURCHASE VERIFICATION
    # =========================================================================
    
    async def verify_purchase(
        self,
        purchase_token: str,
        product_id: str
    ) -> Dict[str, Any]:
        """
        Verify a purchase token with Google Play API
        
        Args:
            purchase_token: Token received from client after purchase
            product_id: Product SKU (e.g., "dealhunt_pro_monthly")
        
        Returns:
            Purchase details dict with:
            - valid: bool
            - order_id: str
            - purchase_state: int (0=purchased, 1=canceled, 2=pending)
            - acknowledgement_state: int (0=not_ack, 1=ack)
            - purchase_time_millis: int
            - expiry_time_millis: int (for subscriptions)
            - auto_renewing: bool
        
        Raises:
            ValueError: If verification fails
        """
        # Mock mode - accept test tokens
        if self.mock_mode:
            return self._mock_verify_purchase(purchase_token, product_id)
        
        try:
            # For subscriptions
            result = self.service.purchases().subscriptions().get(
                packageName=self.package_name,
                subscriptionId=product_id,
                token=purchase_token
            ).execute()
            
            logger.info(f"Purchase verified | Product: {product_id} | Order: {result.get('orderId')}")
            
            return {
                "valid": True,
                "kind": result.get("kind"),
                "order_id": result.get("orderId"),
                "purchase_state": int(result.get("paymentState", 1)),  # 1 = received
                "acknowledgement_state": int(result.get("acknowledgementState", 0)),
                "purchase_time_millis": int(result.get("startTimeMillis", 0)),
                "expiry_time_millis": int(result.get("expiryTimeMillis", 0)),
                "auto_renewing": result.get("autoRenewing", False),
                "price_currency_code": result.get("priceCurrencyCode", "INR"),
                "price_amount_micros": int(result.get("priceAmountMicros", 0)),
                "country_code": result.get("countryCode", "IN"),
                "cancel_reason": result.get("cancelReason"),
                "raw_response": result
            }
            
        except Exception as e:
            logger.error(f"Purchase verification failed: {e}")
            raise ValueError(f"Purchase verification failed: {str(e)}")
    
    def _mock_verify_purchase(
        self,
        purchase_token: str,
        product_id: str
    ) -> Dict[str, Any]:
        """Mock purchase verification for development"""
        
        # Accept tokens starting with "mock_" or containing "test"
        is_valid = (
            purchase_token.startswith("mock_") or 
            "test" in purchase_token.lower() or
            len(purchase_token) > 20  # Accept any long token in mock mode
        )
        
        if not is_valid:
            logger.warning(f"[MOCK] Invalid token format: {purchase_token[:20]}...")
            raise ValueError("Mock mode: Use token starting with 'mock_' or 'test'")
        
        # Determine plan duration based on product_id
        duration_days = 30
        if "premium" in product_id.lower():
            price_micros = 14900 * 10000  # ₹149 in micros
        else:
            price_micros = 4900 * 10000   # ₹49 in micros
        
        now = datetime.utcnow()
        expiry = now + timedelta(days=duration_days)
        
        mock_order_id = f"GPA.MOCK-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}"
        
        logger.info(f"[MOCK] Purchase verified | Product: {product_id} | Order: {mock_order_id}")
        
        return {
            "valid": True,
            "kind": "androidpublisher#subscriptionPurchase",
            "order_id": mock_order_id,
            "purchase_state": PurchaseState.PURCHASED.value,
            "acknowledgement_state": AcknowledgementState.NOT_ACKNOWLEDGED.value,
            "purchase_time_millis": int(now.timestamp() * 1000),
            "expiry_time_millis": int(expiry.timestamp() * 1000),
            "auto_renewing": True,
            "price_currency_code": "INR",
            "price_amount_micros": price_micros,
            "country_code": "IN",
            "cancel_reason": None,
            "mock_mode": True
        }
    
    # =========================================================================
    # SUBSCRIPTION STATUS
    # =========================================================================
    
    async def get_subscription_status(
        self,
        purchase_token: str,
        product_id: str
    ) -> Dict[str, Any]:
        """
        Get current subscription status
        
        Returns:
            Subscription status dict with:
            - is_active: bool
            - expiry_time: datetime
            - auto_renewing: bool
            - is_grace_period: bool
            - is_on_hold: bool
        """
        if self.mock_mode:
            return self._mock_subscription_status(purchase_token, product_id)
        
        try:
            result = await self.verify_purchase(purchase_token, product_id)
            
            now_millis = int(datetime.utcnow().timestamp() * 1000)
            expiry_millis = result.get("expiry_time_millis", 0)
            
            is_active = (
                result.get("purchase_state") == PurchaseState.PURCHASED.value and
                expiry_millis > now_millis
            )
            
            return {
                "is_active": is_active,
                "expiry_time": datetime.fromtimestamp(expiry_millis / 1000) if expiry_millis else None,
                "auto_renewing": result.get("auto_renewing", False),
                "is_grace_period": False,  # Would need additional API call
                "is_on_hold": False,
                "acknowledgement_state": result.get("acknowledgement_state", 0),
                "order_id": result.get("order_id")
            }
            
        except Exception as e:
            logger.error(f"Failed to get subscription status: {e}")
            return {
                "is_active": False,
                "error": str(e)
            }
    
    def _mock_subscription_status(
        self,
        purchase_token: str,
        product_id: str
    ) -> Dict[str, Any]:
        """Mock subscription status"""
        expiry = datetime.utcnow() + timedelta(days=30)
        
        return {
            "is_active": True,
            "expiry_time": expiry,
            "auto_renewing": True,
            "is_grace_period": False,
            "is_on_hold": False,
            "acknowledgement_state": AcknowledgementState.ACKNOWLEDGED.value,
            "order_id": f"GPA.MOCK-{uuid.uuid4().hex[:12]}",
            "mock_mode": True
        }
    
    # =========================================================================
    # ACKNOWLEDGEMENT
    # =========================================================================
    
    async def acknowledge_purchase(
        self,
        purchase_token: str,
        product_id: str
    ) -> bool:
        """
        Acknowledge a purchase (REQUIRED within 3 days!)
        
        If you don't acknowledge, Google will refund the purchase.
        
        Returns:
            True if acknowledged successfully
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Purchase acknowledged | Product: {product_id}")
            return True
        
        try:
            self.service.purchases().subscriptions().acknowledge(
                packageName=self.package_name,
                subscriptionId=product_id,
                token=purchase_token
            ).execute()
            
            logger.info(f"Purchase acknowledged | Product: {product_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to acknowledge purchase: {e}")
            return False
    
    # =========================================================================
    # WEBHOOK HANDLING (RTDN)
    # =========================================================================
    
    async def handle_notification(
        self,
        notification_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle Google Play Real-time Developer Notification (RTDN)
        
        Notification types:
        - SUBSCRIPTION_RECOVERED (1): Recovered from account hold
        - SUBSCRIPTION_RENEWED (2): Active subscription renewed
        - SUBSCRIPTION_CANCELED (3): User cancelled
        - SUBSCRIPTION_PURCHASED (4): New subscription
        - SUBSCRIPTION_ON_HOLD (5): Payment failed, account hold
        - SUBSCRIPTION_IN_GRACE_PERIOD (6): Payment failed, grace period
        - SUBSCRIPTION_RESTARTED (7): Restarted after being cancelled
        - SUBSCRIPTION_PRICE_CHANGE_CONFIRMED (8): User confirmed price change
        - SUBSCRIPTION_DEFERRED (9): Renewal deferred
        - SUBSCRIPTION_PAUSED (10): Subscription paused
        - SUBSCRIPTION_PAUSE_SCHEDULE_CHANGED (11): Pause date changed
        - SUBSCRIPTION_REVOKED (12): Subscription revoked
        - SUBSCRIPTION_EXPIRED (13): Subscription expired
        
        Args:
            notification_data: Decoded notification from Pub/Sub
            
        Returns:
            Action taken dict
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Notification received: {notification_data}")
            return {"action": "mock_processed", "mock_mode": True}
        
        try:
            subscription_notification = notification_data.get("subscriptionNotification", {})
            notification_type = subscription_notification.get("notificationType")
            purchase_token = subscription_notification.get("purchaseToken")
            subscription_id = subscription_notification.get("subscriptionId")
            
            logger.info(f"RTDN received | Type: {notification_type} | Product: {subscription_id}")
            
            # Map notification type to action
            actions = {
                1: "recovered",      # SUBSCRIPTION_RECOVERED
                2: "renewed",        # SUBSCRIPTION_RENEWED
                3: "canceled",       # SUBSCRIPTION_CANCELED
                4: "purchased",      # SUBSCRIPTION_PURCHASED
                5: "on_hold",        # SUBSCRIPTION_ON_HOLD
                6: "grace_period",   # SUBSCRIPTION_IN_GRACE_PERIOD
                7: "restarted",      # SUBSCRIPTION_RESTARTED
                12: "revoked",       # SUBSCRIPTION_REVOKED
                13: "expired"        # SUBSCRIPTION_EXPIRED
            }
            
            action = actions.get(notification_type, "unknown")
            
            return {
                "action": action,
                "notification_type": notification_type,
                "purchase_token": purchase_token,
                "subscription_id": subscription_id,
                "requires_verification": action in ["purchased", "renewed", "recovered", "restarted"]
            }
            
        except Exception as e:
            logger.error(f"Failed to handle notification: {e}")
            return {"action": "error", "error": str(e)}
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def get_plan_from_sku(self, product_id: str) -> Optional[str]:
        """Convert Google Play SKU to internal plan ID"""
        return settings.google_play_sku_to_plan.get(product_id)
    
    def get_sku_from_plan(self, plan_id: str) -> Optional[str]:
        """Convert internal plan ID to Google Play SKU"""
        return settings.google_play_plan_to_sku.get(plan_id)
    
    @property
    def is_mock_mode(self) -> bool:
        """Check if running in mock mode"""
        return self.mock_mode


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
google_play_client = GooglePlayBilling()
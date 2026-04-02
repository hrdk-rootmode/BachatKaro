"""
Razorpay Payment Gateway Integration
Handles order creation, payment verification, and webhooks

NOTE: Works in mock mode when credentials are placeholders
"""

import hmac
import hashlib
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_placeholder_credential(value: str) -> bool:
    """Treat obvious sample/dummy credentials as non-production and force mock mode."""
    text = (value or "").strip().lower()
    if not text:
        return True

    placeholder_markers = (
        "placeholder",
        "your_",
        "change_me",
        "dummy",
        "xxxx",
    )
    return any(marker in text for marker in placeholder_markers)

# Check if we have real Razorpay credentials
RAZORPAY_ENABLED = (
    settings.RAZORPAY_ENABLED and
    settings.RAZORPAY_KEY_ID and
    settings.RAZORPAY_KEY_SECRET and
    not _is_placeholder_credential(settings.RAZORPAY_KEY_ID) and
    not _is_placeholder_credential(settings.RAZORPAY_KEY_SECRET)
)

# Only import razorpay if we have real credentials
if RAZORPAY_ENABLED:
    try:
        import razorpay
        RAZORPAY_SDK_AVAILABLE = True
    except ImportError:
        RAZORPAY_SDK_AVAILABLE = False
        logger.warning("Razorpay SDK not installed. Running in mock mode.")
else:
    RAZORPAY_SDK_AVAILABLE = False
    logger.warning("Razorpay credentials not configured. Running in mock mode.")


class RazorpayClient:
    """
    Razorpay API wrapper with signature verification
    
    Features:
    - Create payment orders
    - Verify payment signatures (HMAC-SHA256)
    - Handle webhooks securely
    - Fetch payment details
    - Mock mode for development without credentials
    """
    
    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        self.mock_mode = not (RAZORPAY_ENABLED and RAZORPAY_SDK_AVAILABLE)
        
        if not self.mock_mode:
            self.client = razorpay.Client(
                auth=(self.key_id, self.key_secret)
            )
            logger.info("✅ Razorpay client initialized")
        else:
            self.client = None
            logger.warning("⚠️ Razorpay running in MOCK mode (no real payments)")
    
    def create_order(
        self,
        amount: int,
        currency: str = "INR",
        receipt: str = None,
        notes: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Create a Razorpay order
        
        Args:
            amount: Amount in paise (e.g., 4900 = ₹49)
            currency: Currency code (default: INR)
            receipt: Unique receipt ID for tracking
            notes: Additional metadata
            
        Returns:
            Razorpay order object with order_id
        """
        receipt = receipt or f"rcpt_{datetime.utcnow().timestamp()}"
        
        # Mock mode - return fake order
        if self.mock_mode:
            mock_order_id = f"order_mock_{uuid.uuid4().hex[:16]}"
            logger.info(f"[MOCK] Created order: {mock_order_id} for {amount} {currency}")
            return {
                "id": mock_order_id,
                "entity": "order",
                "amount": amount,
                "amount_paid": 0,
                "amount_due": amount,
                "currency": currency,
                "receipt": receipt,
                "status": "created",
                "notes": notes or {}
            }
        
        # Real Razorpay call
        try:
            order_data = {
                "amount": amount,
                "currency": currency,
                "receipt": receipt,
                "notes": notes or {}
            }
            
            order = self.client.order.create(data=order_data)
            
            logger.info(
                f"Razorpay order created | Order ID: {order['id']} | "
                f"Amount: {amount} {currency}"
            )
            
            return order
            
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {str(e)}")
            raise ValueError(f"Order creation failed: {str(e)}")
    
    def verify_payment_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str
    ) -> bool:
        """
        Verify Razorpay payment signature using HMAC-SHA256
        
        Args:
            order_id: Razorpay order ID
            payment_id: Razorpay payment ID
            signature: Signature from client
            
        Returns:
            True if signature is valid, False otherwise
        """
        # Mock mode - accept mock signatures
        if self.mock_mode:
            # Accept if signature matches pattern or is "mock_signature"
            if signature == "mock_signature" or order_id.startswith("order_mock_"):
                logger.info(f"[MOCK] Payment signature accepted for {order_id}")
                return True
            # Also generate expected mock signature for testing
            expected_mock = hmac.new(
                b"mock_secret",
                f"{order_id}|{payment_id}".encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            return signature == expected_mock
        
        # Real signature verification
        try:
            message = f"{order_id}|{payment_id}"
            expected_signature = hmac.new(
                self.key_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            is_valid = hmac.compare_digest(expected_signature, signature)
            
            if is_valid:
                logger.info(f"Payment signature verified | Order: {order_id}")
            else:
                logger.warning(
                    f"Payment signature INVALID | Order: {order_id} | "
                    f"Payment: {payment_id}"
                )
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Signature verification error: {str(e)}")
            return False
    
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Verify Razorpay webhook signature
        
        Args:
            payload: Raw request body
            signature: X-Razorpay-Signature header
            
        Returns:
            True if webhook is authentic
        """
        if self.mock_mode:
            logger.info("[MOCK] Webhook signature accepted")
            return True
        
        try:
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            logger.error(f"Webhook signature verification error: {str(e)}")
            return False
    
    def fetch_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Fetch payment details from Razorpay"""
        if self.mock_mode:
            logger.info(f"[MOCK] Fetching payment: {payment_id}")
            return {
                "id": payment_id,
                "entity": "payment",
                "amount": 4900,
                "currency": "INR",
                "status": "captured",
                "method": "upi",
                "captured": True
            }
        
        try:
            return self.client.payment.fetch(payment_id)
        except Exception as e:
            logger.error(f"Failed to fetch payment {payment_id}: {str(e)}")
            return None
    
    def fetch_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Fetch order details from Razorpay"""
        if self.mock_mode:
            logger.info(f"[MOCK] Fetching order: {order_id}")
            return {
                "id": order_id,
                "entity": "order",
                "amount": 4900,
                "currency": "INR",
                "status": "paid"
            }
        
        try:
            return self.client.order.fetch(order_id)
        except Exception as e:
            logger.error(f"Failed to fetch order {order_id}: {str(e)}")
            return None
    
    def capture_payment(
        self,
        payment_id: str,
        amount: int,
        currency: str = "INR"
    ) -> Optional[Dict[str, Any]]:
        """Capture an authorized payment"""
        if self.mock_mode:
            logger.info(f"[MOCK] Capturing payment: {payment_id} for {amount}")
            return {
                "id": payment_id,
                "amount": amount,
                "status": "captured"
            }
        
        try:
            payment = self.client.payment.capture(
                payment_id,
                amount,
                {"currency": currency}
            )
            logger.info(f"Payment captured | ID: {payment_id} | Amount: {amount}")
            return payment
        except Exception as e:
            logger.error(f"Payment capture failed: {str(e)}")
            return None
    
    def refund_payment(
        self,
        payment_id: str,
        amount: Optional[int] = None,
        notes: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Initiate refund for a payment"""
        if self.mock_mode:
            logger.info(f"[MOCK] Refunding payment: {payment_id}")
            return {
                "id": f"rfnd_mock_{uuid.uuid4().hex[:10]}",
                "payment_id": payment_id,
                "amount": amount,
                "status": "processed"
            }
        
        try:
            refund_data = {"notes": notes or {}}
            if amount:
                refund_data["amount"] = amount
            
            refund = self.client.payment.refund(payment_id, refund_data)
            logger.info(f"Refund initiated | Payment: {payment_id} | Amount: {amount}")
            return refund
        except Exception as e:
            logger.error(f"Refund failed: {str(e)}")
            return None
    
    @property
    def is_mock_mode(self) -> bool:
        """Check if running in mock mode"""
        return self.mock_mode


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
razorpay_client = RazorpayClient()
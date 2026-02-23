"""
Payment Services Package

Exports:
- RazorpayClient (web payments)
- GooglePlayBilling (Android payments)
- PaymentRouter (auto-select payment method)
- Singleton instances

Usage:
    from app.services.payments import (
        razorpay_client,
        google_play_client,
        payment_router
    )
    
    # Or get handler dynamically
    handler = payment_router.get_handler("android")
"""

from app.services.payments.razorpay_web import (
    RazorpayClient,
    razorpay_client
)

from app.services.payments.google_play import (
    GooglePlayBilling,
    google_play_client,
    PurchaseState,
    AcknowledgementState,
    SubscriptionState
)

from app.services.payments.payment_router import (
    PaymentRouter,
    PaymentPlatform,
    payment_router
)


__all__ = [
    # Classes
    "RazorpayClient",
    "GooglePlayBilling",
    "PaymentRouter",
    "PaymentPlatform",
    
    # Enums
    "PurchaseState",
    "AcknowledgementState",
    "SubscriptionState",
    
    # Singleton instances
    "razorpay_client",
    "google_play_client",
    "payment_router",
]
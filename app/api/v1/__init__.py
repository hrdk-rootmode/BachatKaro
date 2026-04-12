"""
API v1 Router
Combines all route modules
"""

from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("", tags=["API"])
@api_router.get("/", tags=["API"])
async def api_v1_root():
	"""API v1 root endpoint for quick connectivity checks."""
	return {
		"message": "DealHunt API v1 is running",
		"version": "v1",
		"status": "ok",
		"docs": "/docs"
	}

# Import routers
from app.api.v1 import auth, search, products, watchlist, streak, subscription, admin, home, notifications   

# Include routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["Watchlist"])
api_router.include_router(streak.router, prefix="/streak", tags=["Streak & Gamification"])
api_router.include_router(subscription.router, prefix="/subscription", tags=["Subscription & Payments"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin Dashboard"])
api_router.include_router(home.router, prefix="/home", tags=["Home"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

"""
FastAPI Application Entry Point
DealHunt Backend - Multi-Platform Price Comparison

Features:
- REST API with 60+ endpoints
- Background job scheduler (6 automated jobs)
- Multi-platform payment support (Razorpay + Google Play)
- Self-healing scrapers
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.core.redis_client import redis_client
from app.api.v1 import api_router  # Single import

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events
    
    Startup:
    - Connect to Redis
    - Start background scheduler
    
    Shutdown:
    - Stop scheduler gracefully
    - Close scraper handlers
    - Disconnect Redis
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    logger.info("🚀 Starting DealHunt Backend...")
    
    # Connect Redis
    try:
        await redis_client.connect()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.error(f"❌ Redis startup failed: {e}")
        
    # Start background scheduler
    if settings.ENABLE_SCHEDULER:
        try:
            from jobs import start_scheduler
            start_scheduler()
            logger.info("✅ Background scheduler started")
        except ImportError as e:
            logger.warning(f"⚠️ Jobs module not found: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to start scheduler: {e}")
            # Continue anyway - scheduler is not critical for API
    else:
        logger.warning("⚠️ Background scheduler is DISABLED")
    
    # Log startup complete
    logger.info("=" * 50)
    logger.info(f"🎯 DealHunt API v{settings.APP_VERSION} is ready!")
    logger.info(f"📍 Environment: {settings.ENVIRONMENT}")
    if settings.DEBUG:
        logger.info(f"📚 Docs: http://localhost:{settings.PORT}/docs")
        logger.info(f"📚 Docs: http://127.0.0.1:{settings.PORT}/docs")
    logger.info("=" * 50)
    
    yield
    
    # =========================================================================
    # SHUTDOWN
    # =========================================================================
    logger.info("🛑 Shutting down DealHunt Backend...")
    
    # Stop scheduler
    if settings.ENABLE_SCHEDULER:
        try:
            from jobs import shutdown_scheduler
            shutdown_scheduler()
            logger.info("✅ Background scheduler stopped")
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    # Close scraper handlers
    try:
        from app.services.scraper.factory import close_all_handlers
        await close_all_handlers()
        logger.info("✅ Scraper handlers closed")
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"Error closing scrapers: {e}")
    
    # Disconnect Redis
    await redis_client.disconnect()
    logger.info("✅ Redis disconnected")
    
    logger.info("👋 DealHunt Backend stopped")


# =============================================================================
# CREATE FASTAPI APP
# =============================================================================

app = FastAPI(
    title="DealHunt API",
    description="""
    ## Multi-Platform Price Comparison Backend
    
    ### Features:
    - 🔍 Search across Amazon, Flipkart, Meesho, Myntra
    - 💰 Price tracking & alerts
    - 📊 Price history (120 days)
    - 🔔 Push notifications
    - 💳 Subscriptions (Razorpay + Google Play)
    - 🏆 Gamification (streaks, rewards)
    - 🛡️ Admin dashboard
    - ⚙️ Background jobs (price updates, alerts)
    
    ### Authentication:
    All endpoints require Firebase JWT token in Authorization header.
    
    ### Rate Limits:
    - Free: 10 searches/day
    - Pro: 100 searches/day
    - Premium: Unlimited
    """,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)


# =============================================================================
# MIDDLEWARE
# =============================================================================

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# INCLUDE ROUTERS
# =============================================================================

# Include all API routes (single include - no duplicates!)
app.include_router(api_router, prefix="/api/v1")


# =============================================================================
# ROOT ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    """
    Health check endpoint
    
    Checks:
    - Redis connection
    - Scheduler status
    - Payment services status
    """
    # Check Redis
    redis_status = await redis_client.ping()
    
    # Check scheduler
    scheduler_status = "disabled"
    jobs_count = 0
    if settings.ENABLE_SCHEDULER:
        try:
            from jobs import get_scheduler_status
            scheduler_info = get_scheduler_status()
            scheduler_status = "running" if scheduler_info.get("running") else "stopped"
            jobs_count = scheduler_info.get("jobs_count", 0)
        except ImportError:
            scheduler_status = "not_installed"
        except Exception:
            scheduler_status = "error"
    
    # Check payment services
    payment_status = {
        "razorpay": "unknown",
        "google_play": "unknown"
    }
    try:
        from app.services.payments import payment_router
        status = payment_router.get_status()
        payment_status["razorpay"] = "mock" if status.get("razorpay", {}).get("mock_mode") else "live"
        payment_status["google_play"] = "mock" if status.get("google_play", {}).get("mock_mode") else "live"
    except ImportError:
        pass
    except Exception:
        pass
    
    # Determine overall status
    overall_status = "healthy"
    if not redis_status:
        overall_status = "degraded"
    
    return {
        "status": overall_status,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "services": {
            "redis": "connected" if redis_status else "disconnected",
            "scheduler": scheduler_status,
            "jobs_registered": jobs_count
        },
        "payments": payment_status
    }


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "Multi-Platform Price Comparison API",
        "endpoints": {
            "docs": "/docs" if settings.DEBUG else "disabled",
            "health": "/health",
            "api": "/api/v1"
        }
    }


# =============================================================================
# BACKGROUND JOBS ENDPOINTS
# =============================================================================

@app.get("/api/v1/jobs/status")
async def get_jobs_status():
    """
    Get background jobs status
    
    Returns:
    - List of registered jobs
    - Next run times
    - Last run status
    """
    if not settings.ENABLE_SCHEDULER:
        return {
            "enabled": False,
            "message": "Scheduler is disabled in settings"
        }
    
    try:
        from jobs import get_scheduler_status
        return get_scheduler_status()
    except ImportError:
        return {
            "enabled": True,
            "running": False,
            "error": "Jobs module not installed"
        }
    except Exception as e:
        return {
            "enabled": True,
            "running": False,
            "error": str(e)
        }


@app.post("/api/v1/jobs/{job_id}/run")
async def trigger_job(job_id: str):
    """
    Manually trigger a background job
    
    Available jobs:
    - daily_scrape: Update all product prices
    - load_trending: Refresh trending products cache
    - check_price_alerts: Send price drop notifications
    - streak_reminders: Send streak reminder notifications
    - sync_subscriptions: Sync Google Play subscriptions
    - monthly_archive: Archive old data
    
    Note: This should be admin-only in production
    """
    # TODO: Add admin authentication check
    # from app.api.deps import require_admin
    
    if not settings.ENABLE_SCHEDULER:
        return {
            "success": False,
            "error": "Scheduler is disabled"
        }
    
    try:
        from jobs import run_job_now
        result = await run_job_now(job_id)
        return result
    except ImportError:
        return {
            "success": False,
            "job_id": job_id,
            "error": "Jobs module not installed"
        }
    except Exception as e:
        return {
            "success": False,
            "job_id": job_id,
            "error": str(e)
        }


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Handle uncaught exceptions gracefully
    
    In production, this prevents exposing internal errors
    """
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    
    # In debug mode, show more details
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "path": str(request.url)
            }
        )
    
    # In production, hide internal details
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": "ServerError"
        }
    )


# =============================================================================
# RUN WITH UVICORN (for direct execution)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
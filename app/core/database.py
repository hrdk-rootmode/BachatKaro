"""
PostgreSQL Database Connection
Uses SQLAlchemy async engine with connection pooling
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, QueuePool
from typing import AsyncGenerator
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE ENGINE
# =============================================================================
# Replace the engine creation with this:
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    # Only use pooling in production
    **({
        "poolclass": QueuePool,
        "pool_size": settings.DATABASE_POOL_SIZE,
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        "pool_recycle": 3600,
    } if not settings.DEBUG else {})
)

# =============================================================================
# SESSION FACTORY
# =============================================================================
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autocommit=False,
    autoflush=False,
)

# =============================================================================
# BASE CLASS FOR MODELS
# =============================================================================
Base = declarative_base()

# =============================================================================
# LEGACY DB EXPORT (for script compatibility)
# =============================================================================
db = engine  # Export engine as 'db' for backward compatibility

# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get database session
    
    Usage in route:
        @router.get("/")
        async def route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            await session.close()


# =============================================================================
# DATABASE UTILITIES
# =============================================================================
async def init_db():
    """
    Create all tables (use Alembic migrations in production)
    Only for initial development
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables created")


async def close_db():
    """
    Close all database connections
    Call this on application shutdown
    """
    await engine.dispose()
    logger.info("🔌 Database connections closed")


async def check_db_connection() -> bool:
    """
    Health check for database
    Returns True if connection successful
    """
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"❌ Database health check failed: {str(e)}")
        return False
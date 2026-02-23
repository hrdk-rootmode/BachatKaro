"""
Platform Factory
Dynamically loads the correct handler (Scraper or API) based on configuration

Features:
- Auto-discovery of platform plugins
- Runtime switching between scraper/API
- Handler caching for performance
- Health-based fallback

Usage:
    handler = await get_platform_handler("amazon")
    results = await handler.search("iphone 15")
"""

import logging
import importlib
from typing import Dict, Optional, List, Type
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.scraper.base import (
    BasePlatformHandler,
    PlatformConfig,
    HandlerType,
    HealthStatus
)
from app.models import Platform
from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# HANDLER REGISTRY
# =============================================================================

# Maps platform name to handler class paths
# Format: "platform_name": {"scraper": "module.path.ClassName", "api": "module.path.ClassName"}
HANDLER_REGISTRY: Dict[str, Dict[str, str]] = {
    "amazon": {
        "scraper": "platforms.amazon.AmazonScraper",
        "api": "platforms.amazon_api.AmazonAPI"  # Future
    },
    "flipkart": {
        "scraper": "platforms.flipkart.FlipkartScraper",
        "api": "platforms.flipkart_api.FlipkartAPI"  # Future
    },
    "meesho": {
        "scraper": "platforms.meesho.MeeshoScraper",
        "api": None  # No API available
    },
    "myntra": {
        "scraper": "platforms.myntra.MyntraScraper",
        "api": None  # No API available
    }
}


# =============================================================================
# PLATFORM FACTORY
# =============================================================================

class PlatformFactory:
    """
    Factory for creating platform handlers
    
    Features:
    - Caches handler instances
    - Auto-loads based on config (scraper vs API)
    - Health-based fallback
    - Thread-safe singleton handlers
    
    Usage:
        factory = PlatformFactory()
        handler = await factory.get_handler("amazon", db)
        results = await handler.search("laptop")
    """
    
    # Cache of loaded handler classes
    _class_cache: Dict[str, Type[BasePlatformHandler]] = {}
    
    # Cache of handler instances (reuse for performance)
    _instance_cache: Dict[str, BasePlatformHandler] = {}
    
    # Cache expiry tracking
    _cache_expiry: Dict[str, datetime] = {}
    
    # Cache duration
    CACHE_DURATION_MINUTES = 30
    
    def __init__(self):
        self._initialized = False
    
    async def get_handler(
        self,
        platform_name: str,
        db: AsyncSession,
        force_type: Optional[HandlerType] = None,
        force_refresh: bool = False
    ) -> BasePlatformHandler:
        """
        Get handler for a platform
        
        Args:
            platform_name: Name of platform (amazon, flipkart, etc.)
            db: Database session
            force_type: Force specific handler type (scraper/api)
            force_refresh: Bypass cache and create new handler
        
        Returns:
            Platform handler instance
        
        Raises:
            ValueError: If platform not found or handler unavailable
        """
        platform_name = platform_name.lower().strip()
        
        # Check cache first
        cache_key = f"{platform_name}_{force_type.value if force_type else 'auto'}"
        
        if not force_refresh and cache_key in self._instance_cache:
            if self._is_cache_valid(cache_key):
                logger.debug(f"Returning cached handler for {platform_name}")
                return self._instance_cache[cache_key]
        
        # Load platform config from database
        config = await self._load_platform_config(platform_name, db)
        
        if not config:
            raise ValueError(f"Platform '{platform_name}' not found in database")
        
        if not config.is_active:
            raise ValueError(f"Platform '{platform_name}' is disabled")
        
        # Determine handler type
        handler_type = force_type or self._determine_handler_type(config)
        
        # Load handler class
        handler_class = self._load_handler_class(platform_name, handler_type)
        
        if not handler_class:
            raise ValueError(
                f"No {handler_type.value} handler available for {platform_name}"
            )
        
        # Create instance
        handler = handler_class(config)
        
        # Cache it
        self._instance_cache[cache_key] = handler
        self._cache_expiry[cache_key] = datetime.utcnow() + timedelta(
            minutes=self.CACHE_DURATION_MINUTES
        )
        
        logger.info(f"Created {handler_type.value} handler for {platform_name}")
        return handler
    
    async def get_all_handlers(
        self,
        db: AsyncSession,
        active_only: bool = True
    ) -> List[BasePlatformHandler]:
        """
        Get handlers for all platforms
        
        Args:
            db: Database session
            active_only: Only return handlers for active platforms
        
        Returns:
            List of platform handlers
        """
        handlers = []
        
        # Get all platforms from database
        query = select(Platform)
        if active_only:
            query = query.where(Platform.is_active == True)
        
        result = await db.execute(query)
        platforms = result.scalars().all()
        
        for platform in platforms:
            try:
                handler = await self.get_handler(platform.name, db)
                handlers.append(handler)
            except Exception as e:
                logger.error(f"Failed to load handler for {platform.name}: {e}")
        
        return handlers
    
    async def get_health_status(
        self,
        db: AsyncSession
    ) -> Dict[str, HealthStatus]:
        """
        Get health status for all platforms
        
        Returns:
            Dict mapping platform name to health status
        """
        health = {}
        
        handlers = await self.get_all_handlers(db)
        
        for handler in handlers:
            try:
                status = await handler.health_check()
                health[handler.platform_name] = status
            except Exception as e:
                health[handler.platform_name] = HealthStatus(
                    platform_name=handler.platform_name,
                    handler_type=handler.handler_type,
                    is_healthy=False,
                    last_error=str(e)
                )
        
        return health
    
    async def close_all(self) -> None:
        """Close all cached handlers"""
        for handler in self._instance_cache.values():
            try:
                await handler.close()
            except Exception as e:
                logger.error(f"Error closing handler: {e}")
        
        self._instance_cache.clear()
        self._cache_expiry.clear()
        logger.info("All handlers closed")
    
    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================
    
    async def _load_platform_config(
        self,
        platform_name: str,
        db: AsyncSession
    ) -> Optional[PlatformConfig]:
        """Load platform configuration from database"""
        result = await db.execute(
            select(Platform).where(Platform.name == platform_name)
        )
        platform = result.scalar_one_or_none()
        
        if not platform:
            return None
        
        selectors = platform.selectors or {}
        
        return PlatformConfig(
            id=platform.id,
            name=platform.name,
            base_url=platform.base_url,
            affiliate_tag=platform.affiliate_tag,
            selectors=selectors,
            scrape_delay_seconds=platform.scrape_delay_seconds or 2,
            is_active=platform.is_active,
            rate_limit_per_minute=selectors.get("rate_limit", 30),
            handler_type=HandlerType(selectors.get("handler_type", "scraper"))
        )
    
    def _determine_handler_type(self, config: PlatformConfig) -> HandlerType:
        """
        Determine which handler type to use
        
        Priority:
        1. API (if configured and credentials available)
        2. Scraper (default fallback)
        """
        # Check if API is configured
        if config.api_key and config.api_endpoint:
            return HandlerType.API
        
        # Check config preference
        if config.handler_type == HandlerType.API:
            # API preferred but no credentials - warn and use scraper
            logger.warning(
                f"{config.name}: API preferred but no credentials, using scraper"
            )
        
        return HandlerType.SCRAPER
    
    def _load_handler_class(
        self,
        platform_name: str,
        handler_type: HandlerType
    ) -> Optional[Type[BasePlatformHandler]]:
        """
        Dynamically load handler class
        
        Uses importlib for runtime loading
        """
        cache_key = f"{platform_name}_{handler_type.value}"
        
        # Check class cache
        if cache_key in self._class_cache:
            return self._class_cache[cache_key]
        
        # Get module path from registry
        if platform_name not in HANDLER_REGISTRY:
            logger.error(f"Platform '{platform_name}' not in registry")
            return None
        
        type_key = "api" if handler_type == HandlerType.API else "scraper"
        module_path = HANDLER_REGISTRY[platform_name].get(type_key)
        
        if not module_path:
            logger.error(f"No {type_key} handler registered for {platform_name}")
            return None
        
        try:
            # Split module and class name
            module_name, class_name = module_path.rsplit(".", 1)
            
            # Import module
            module = importlib.import_module(module_name)
            
            # Get class
            handler_class = getattr(module, class_name)
            
            # Validate it's a proper handler
            if not issubclass(handler_class, BasePlatformHandler):
                raise TypeError(f"{class_name} is not a BasePlatformHandler subclass")
            
            # Cache class
            self._class_cache[cache_key] = handler_class
            
            logger.debug(f"Loaded handler class: {module_path}")
            return handler_class
            
        except ImportError as e:
            logger.error(f"Failed to import {module_path}: {e}")
            return None
        except AttributeError as e:
            logger.error(f"Class not found in module: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading handler class: {e}")
            return None
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached handler is still valid"""
        if cache_key not in self._cache_expiry:
            return False
        
        return datetime.utcnow() < self._cache_expiry[cache_key]


# =============================================================================
# SINGLETON FACTORY & HELPER FUNCTIONS
# =============================================================================

# Global factory instance
_factory: Optional[PlatformFactory] = None


def get_factory() -> PlatformFactory:
    """Get global factory instance"""
    global _factory
    if _factory is None:
        _factory = PlatformFactory()
    return _factory


async def get_platform_handler(
    platform_name: str,
    db: AsyncSession,
    force_type: Optional[HandlerType] = None
) -> BasePlatformHandler:
    """
    Convenience function to get platform handler
    
    Usage:
        handler = await get_platform_handler("amazon", db)
        results = await handler.search("iphone")
    """
    factory = get_factory()
    return await factory.get_handler(platform_name, db, force_type)


async def get_all_handlers(
    db: AsyncSession,
    active_only: bool = True
) -> List[BasePlatformHandler]:
    """
    Get all platform handlers
    
    Usage:
        handlers = await get_all_handlers(db)
        for handler in handlers:
            results = await handler.search(query)
    """
    factory = get_factory()
    return await factory.get_all_handlers(db, active_only)


async def close_all_handlers() -> None:
    """Close all handlers (call on app shutdown)"""
    factory = get_factory()
    await factory.close_all()
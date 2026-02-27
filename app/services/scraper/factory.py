"""
Platform Factory - Auto-Discovery Edition
Dynamically loads scrapers with optional database support

Features:
- Auto-discovers all scrapers in platforms/
- Works WITHOUT database (file cache mode)
- Works WITH database (production mode)
- Auto-detects which mode to use
- Category-based platform routing

Author: DealHunt
"""

import logging
import importlib
import inspect
from typing import Dict, Optional, List, Type, Any
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.scraper.base import (
    BasePlatformHandler,
    PlatformConfig,
    HandlerType,
    HealthStatus,
    ProductCategory
)
from app.services.scraper.selector_cache import get_selector_cache
from app.models import Platform
from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# HANDLER REGISTRY (Fallback if auto-discovery fails)
# =============================================================================

HANDLER_REGISTRY: Dict[str, Dict[str, str]] = {
    "amazon": {
        "scraper": "platforms.amazon.AmazonScraper",
        "api": "platforms.amazon_api.AmazonAPI"
    },
    "flipkart": {
        "scraper": "platforms.flipkart.FlipkartScraper",
        "api": "platforms.flipkart_api.FlipkartAPI"
    },
    "meesho": {
        "scraper": "platforms.meesho.MeeshoScraper",
        "api": None
    },
    "myntra": {
        "scraper": "platforms.myntra.MyntraScraper",
        "api": None
    }
}


# =============================================================================
# PLATFORM FACTORY
# =============================================================================

class PlatformFactory:
    """
    Factory for creating platform handlers
    
    Features:
    - Auto-discovers scrapers from platforms/ directory
    - Works with OR without database
    - Caches handler instances
    - Category-based platform filtering
    
    Usage (No Database - Local Testing):
        factory = PlatformFactory()
        handler = factory.get_handler_sync("amazon")
        
    Usage (With Database - Production):
        handler = await factory.get_handler("amazon", db)
    """
    
    # Discovered platforms cache (class-level for singleton behavior)
    _discovered: Dict[str, Dict[str, Any]] = {}
    
    # Handler instance cache
    _instance_cache: Dict[str, BasePlatformHandler] = {}
    
    # Class cache
    _class_cache: Dict[str, Type[BasePlatformHandler]] = {}
    
    # Cache expiry tracking
    _cache_expiry: Dict[str, datetime] = {}
    
    # Cache duration
    CACHE_DURATION_MINUTES = 30
    
    def __init__(self):
        self._initialized = False
        self._selector_cache = get_selector_cache()
        
        # Auto-discover scrapers if not already done
        if not PlatformFactory._discovered:
            self._auto_discover_scrapers()
        
        self._initialized = True
    
    def _auto_discover_scrapers(self):
        """
        Auto-discover all scrapers in platforms/ directory
        
        Looks for:
        - Files: amazon.py, flipkart.py, etc.
        - Classes: AmazonScraper, FlipkartScraper, etc.
        - Metadata: PLATFORM_METADATA attribute
        """
        # Find platforms directory (relative to project root)
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        platforms_dir = project_root / "platforms"
        
        if not platforms_dir.exists():
            logger.warning(f"Platforms directory not found: {platforms_dir}")
            logger.info("Using fallback HANDLER_REGISTRY")
            return
        
        skip_files = {"__init__", "__pycache__"}
        
        for file_path in platforms_dir.glob("*.py"):
            if file_path.stem in skip_files:
                continue
            
            try:
                module_name = f"platforms.{file_path.stem}"
                module = importlib.import_module(module_name)
                
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (name.endswith("Scraper") and 
                        issubclass(obj, BasePlatformHandler) and 
                        obj != BasePlatformHandler):
                        
                        # Get metadata if available
                        metadata = getattr(obj, "PLATFORM_METADATA", {})
                        platform_name = metadata.get("name", file_path.stem)
                        
                        PlatformFactory._discovered[platform_name] = {
                            "class": obj,
                            "metadata": metadata,
                            "module": module_name,
                            "class_name": name,
                            "file": str(file_path)
                        }
                        
                        logger.info(f"✅ Discovered: {platform_name} → {name}")
            
            except Exception as e:
                logger.error(f"❌ Failed to load {file_path.name}: {e}")
        
        logger.info(f"📦 Total platforms discovered: {len(PlatformFactory._discovered)}")
    
    def get_handler_sync(
        self,
        platform_name: str,
        **config_overrides
    ) -> BasePlatformHandler:
        """
        Get handler WITHOUT database (for local testing)
        
        Args:
            platform_name: Platform name (amazon, flipkart, etc.)
            **config_overrides: Override config values
        
        Returns:
            Platform handler instance
        """
        platform_name = platform_name.lower().strip()
        
        # Check instance cache
        cache_key = f"{platform_name}_sync"
        if cache_key in PlatformFactory._instance_cache:
            if self._is_cache_valid(cache_key):
                logger.debug(f"Returning cached handler for {platform_name}")
                return PlatformFactory._instance_cache[cache_key]
        
        # Get scraper class
        scraper_class = self._get_scraper_class(platform_name)
        
        if not scraper_class:
            available = self.get_all_platform_names()
            raise ValueError(
                f"Platform '{platform_name}' not found. Available: {available}"
            )
        
        # Get metadata
        metadata = self._get_platform_metadata(platform_name)
        
        # Build config from metadata + file cache (NO database)
        config = self._build_config_no_db(platform_name, metadata, **config_overrides)
        
        # Create instance
        handler = scraper_class(config)
        
        # Cache it
        PlatformFactory._instance_cache[cache_key] = handler
        PlatformFactory._cache_expiry[cache_key] = datetime.utcnow() + timedelta(
            minutes=self.CACHE_DURATION_MINUTES
        )
        
        logger.info(f"Created handler: {platform_name} (no-db mode)")
        return handler
    
    async def get_handler(
        self,
        platform_name: str,
        db: Optional[AsyncSession] = None,
        force_type: Optional[HandlerType] = None,
        force_refresh: bool = False,
        **config_overrides
    ) -> BasePlatformHandler:
        """
        Get handler (async version, supports database)
        
        Args:
            platform_name: Platform name
            db: Database session (optional - if None, uses no-db mode)
            force_type: Force specific handler type (scraper/api)
            force_refresh: Bypass cache and create new handler
            **config_overrides: Override config values
        
        Returns:
            Platform handler instance
        """
        platform_name = platform_name.lower().strip()
        
        # Check cache first
        cache_key = f"{platform_name}_{'db' if db else 'sync'}_{force_type.value if force_type else 'auto'}"
        
        if not force_refresh and cache_key in PlatformFactory._instance_cache:
            if self._is_cache_valid(cache_key):
                logger.debug(f"Returning cached handler for {platform_name}")
                return PlatformFactory._instance_cache[cache_key]
        
        # Get scraper class
        scraper_class = self._get_scraper_class(platform_name)
        
        if not scraper_class:
            available = self.get_all_platform_names()
            raise ValueError(
                f"Platform '{platform_name}' not found. Available: {available}"
            )
        
        # Get metadata
        metadata = self._get_platform_metadata(platform_name)
        
        # Build config
        if db:
            # Try to load from database first
            config = await self._load_platform_config(platform_name, db)
            if not config:
                # Fallback to no-db config
                logger.warning(f"Platform '{platform_name}' not in database, using metadata")
                config = self._build_config_no_db(platform_name, metadata, **config_overrides)
            elif not config.is_active:
                raise ValueError(f"Platform '{platform_name}' is disabled")
        else:
            # No database - use metadata config
            config = self._build_config_no_db(platform_name, metadata, **config_overrides)
        
        # Create instance
        handler = scraper_class(config)
        
        # Cache it
        PlatformFactory._instance_cache[cache_key] = handler
        PlatformFactory._cache_expiry[cache_key] = datetime.utcnow() + timedelta(
            minutes=self.CACHE_DURATION_MINUTES
        )
        
        logger.info(f"Created handler: {platform_name} ({'db' if db else 'no-db'} mode)")
        return handler
    
    def _get_scraper_class(self, platform_name: str) -> Optional[Type[BasePlatformHandler]]:
        """Get scraper class by platform name"""
        platform_name = platform_name.lower()
        
        # Check class cache
        if platform_name in PlatformFactory._class_cache:
            return PlatformFactory._class_cache[platform_name]
        
        # Check discovered platforms
        if platform_name in PlatformFactory._discovered:
            scraper_class = PlatformFactory._discovered[platform_name]["class"]
            PlatformFactory._class_cache[platform_name] = scraper_class
            return scraper_class
        
        # Fallback to registry
        if platform_name in HANDLER_REGISTRY:
            module_path = HANDLER_REGISTRY[platform_name].get("scraper")
            if module_path:
                scraper_class = self._load_handler_class(module_path)
                if scraper_class:
                    PlatformFactory._class_cache[platform_name] = scraper_class
                    return scraper_class
        
        return None
    
    def _load_handler_class(self, module_path: str) -> Optional[Type[BasePlatformHandler]]:
        """Dynamically load handler class from module path"""
        try:
            module_name, class_name = module_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            handler_class = getattr(module, class_name)
            
            if not issubclass(handler_class, BasePlatformHandler):
                raise TypeError(f"{class_name} is not a BasePlatformHandler subclass")
            
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
    
    def _get_platform_metadata(self, platform_name: str) -> Dict[str, Any]:
        """Get metadata for a platform"""
        platform_name = platform_name.lower()
        
        if platform_name in PlatformFactory._discovered:
            return PlatformFactory._discovered[platform_name].get("metadata", {})
        
        return {}
    
    def _build_config_no_db(
        self,
        platform_name: str,
        metadata: Dict[str, Any],
        **overrides
    ) -> PlatformConfig:
        """Build config from metadata + file cache (no database)"""
        
        # Get affiliate tag from settings
        affiliate_tag = None
        if platform_name == "amazon":
            affiliate_tag = getattr(settings, "AMAZON_AFFILIATE_TAG", "dealhunt-21")
        elif platform_name == "flipkart":
            affiliate_tag = getattr(settings, "FLIPKART_AFFILIATE_ID", "dealhunt")
        elif platform_name == "meesho":
            affiliate_tag = getattr(settings, "MEESHO_AFFILIATE_ID", "dealhunt")
        elif platform_name == "myntra":
            affiliate_tag = getattr(settings, "AFFILIATE_MYNTRA_ID", None)
        
        # Get cached selectors from file
        cached_selectors = self._selector_cache.get_all(platform_name)
        
        # Merge with metadata selectors
        selectors = {**metadata.get("selectors", {}), **cached_selectors}
        
        return PlatformConfig(
            id=0,  # Dummy ID for no-db mode
            name=platform_name,
            base_url=metadata.get("base_url", f"https://www.{platform_name}.com"),
            affiliate_tag=overrides.get("affiliate_tag", affiliate_tag),
            selectors=selectors,
            scrape_delay_seconds=metadata.get("scrape_delay_seconds", 2),
            is_active=True,
            rate_limit_per_minute=metadata.get("rate_limit_per_minute", 30),
            handler_type=HandlerType.SCRAPER
        )
    
    async def _load_platform_config(
        self,
        platform_name: str,
        db: AsyncSession
    ) -> Optional[PlatformConfig]:
        """Load platform configuration from database"""
        try:
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
        except Exception as e:
            logger.error(f"Error loading platform config from DB: {e}")
            return None
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached handler is still valid"""
        if cache_key not in PlatformFactory._cache_expiry:
            return False
        return datetime.utcnow() < PlatformFactory._cache_expiry[cache_key]
    
    def get_all_platform_names(self) -> List[str]:
        """Get list of all available platforms"""
        # Combine discovered + registry
        platforms = set(PlatformFactory._discovered.keys())
        platforms.update(HANDLER_REGISTRY.keys())
        return list(platforms)
    
    def get_platforms_for_category(self, category: ProductCategory) -> List[str]:
        """Get platforms that support a specific category"""
        matching = []
        
        for name in self.get_all_platform_names():
            metadata = self._get_platform_metadata(name)
            categories = metadata.get("categories", ["general"])
            
            if category.value in categories or "general" in categories:
                matching.append(name)
        
        return matching
    
    def get_platform_metadata(self, platform_name: str) -> Dict[str, Any]:
        """Public method to get metadata for a platform"""
        return self._get_platform_metadata(platform_name)
    
    async def get_all_handlers(
        self,
        db: Optional[AsyncSession] = None,
        active_only: bool = True
    ) -> List[BasePlatformHandler]:
        """Get handlers for all platforms"""
        handlers = []
        
        for platform_name in self.get_all_platform_names():
            try:
                handler = await self.get_handler(platform_name, db)
                handlers.append(handler)
            except Exception as e:
                logger.error(f"Failed to get handler for {platform_name}: {e}")
        
        return handlers
    
    async def get_health_status(
        self,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, HealthStatus]:
        """Get health status for all platforms"""
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
        for handler in PlatformFactory._instance_cache.values():
            try:
                await handler.close()
            except Exception as e:
                logger.error(f"Error closing handler: {e}")
        
        PlatformFactory._instance_cache.clear()
        PlatformFactory._cache_expiry.clear()
        logger.info("All handlers closed")


# =============================================================================
# SINGLETON FACTORY & HELPER FUNCTIONS
# =============================================================================

_factory: Optional[PlatformFactory] = None


def get_factory() -> PlatformFactory:
    """Get global factory instance"""
    global _factory
    if _factory is None:
        _factory = PlatformFactory()
    return _factory


async def get_platform_handler(
    platform_name: str,
    db: Optional[AsyncSession] = None,
    force_type: Optional[HandlerType] = None
) -> BasePlatformHandler:
    """
    Convenience function to get platform handler
    
    Usage (No DB - Testing):
        handler = await get_platform_handler("amazon")
    
    Usage (With DB - Production):
        handler = await get_platform_handler("amazon", db)
    """
    factory = get_factory()
    return await factory.get_handler(platform_name, db, force_type)


def get_platform_handler_sync(platform_name: str) -> BasePlatformHandler:
    """
    Synchronous version - for testing without async
    
    Usage:
        handler = get_platform_handler_sync("amazon")
    """
    factory = get_factory()
    return factory.get_handler_sync(platform_name)


async def get_all_handlers(
    db: Optional[AsyncSession] = None,
    active_only: bool = True
) -> List[BasePlatformHandler]:
    """Get all platform handlers"""
    factory = get_factory()
    return await factory.get_all_handlers(db, active_only)


async def close_all_handlers() -> None:
    """Close all handlers (call on app shutdown)"""
    factory = get_factory()
    await factory.close_all()
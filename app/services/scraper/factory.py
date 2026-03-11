"""
Platform Factory - Auto-Discovery & Auto-Integration Edition
Dynamically loads scrapers with universal AI healing auto-adoption

🚀 NEW: Universal Auto-Adoption System
- Auto-discovers ALL scrapers in platforms/
- Auto-integrates AI healing into every platform (zero setup!)
- Works WITHOUT database (file cache mode)
- Works WITH database (production mode)
- Universal health monitoring
- Cross-platform analytics

Features:
- Zero configuration for new platforms
- Automatic healing engine initialization
- Universal extraction methods injected
- Performance tracking enabled automatically
- Health monitoring built-in

Author: DealHunt
"""

import logging
import importlib
import inspect
import asyncio
from typing import Dict, Optional, List, Type, Any
from datetime import datetime, timedelta
from pathlib import Path

from app.services.scraper.base import (
    BasePlatformHandler,
    PlatformConfig,
    HandlerType,
    HealthStatus,
    ProductCategory
)
from app.services.scraper.selector_cache import get_selector_cache

logger = logging.getLogger(__name__)

# Optional database imports
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models import Platform
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    AsyncSession = None
    logger.warning("⚠️ Database not available - using file cache mode")


# =============================================================================
# HANDLER REGISTRY (Fallback if auto-discovery fails)
# =============================================================================

HANDLER_REGISTRY: Dict[str, Dict[str, str]] = {
    "amazon": {
        "scraper": "platforms.amazon.AmazonScraper",
        "api": None
    },
    "flipkart": {
        "scraper": "platforms.flipkart.FlipkartScraper",
        "api": None
    },
    "meesho": {
        "scraper": "platforms.meesho.MeeshoScraper",
        "api": None
    },
    "myntra": {
        "scraper": "platforms.myntra.MyntraScraper",
        "api": None
    },
    "nykaa": {
        "scraper": "platforms.nykaa.NykaaScraper",
        "api": None
    },
    "croma": {
        "scraper": "platforms.croma.CromaScraper",
        "api": None
    }
}


# =============================================================================
# PLATFORM FACTORY WITH AUTO-ADOPTION
# =============================================================================

class PlatformFactory:
    """
    Factory for creating platform handlers with universal AI healing
    
    🚀 AUTO-ADOPTION SYSTEM:
    - Scans platforms/ directory for all platform scrapers
    - Automatically injects universal healing methods
    - Enables AI-powered extraction for ANY platform
    - Zero configuration required for new platforms
    
    Features:
    - Auto-discovers scrapers from platforms/ directory
    - Works with OR without database
    - Caches handler instances
    - Category-based platform filtering
    - Universal health monitoring
    - Cross-platform analytics
    
    Usage (No Database - Local Testing):
        factory = PlatformFactory()
        handler = factory.get_handler_sync("amazon")
        
    Usage (With Database - Production):
        factory = PlatformFactory()
        handler = await factory.get_handler("amazon", db)
    
    Adding New Platform:
        1. Create platforms/new_platform.py
        2. Inherit from BasePlatformHandler
        3. Done! Auto-healing enabled automatically! 🎉
    """
    
    # Discovered platforms cache (class-level for singleton behavior)
    _discovered: Dict[str, Dict[str, Any]] = {}
    
    # Handler instance cache
    _instance_cache: Dict[str, BasePlatformHandler] = {}
    
    # Class cache
    _class_cache: Dict[str, Type[BasePlatformHandler]] = {}
    
    # Cache expiry tracking
    _cache_expiry: Dict[str, datetime] = {}
    
    # Auto-integration tracking
    _auto_integrated: set = set()
    
    # Cache duration
    CACHE_DURATION_MINUTES = 30
    
    def __init__(self):
        """Initialize factory with auto-discovery and auto-integration"""
        self._initialized = False
        self._selector_cache = get_selector_cache()
        
        # Auto-discover scrapers if not already done
        if not PlatformFactory._discovered:
            self._auto_discover_scrapers()
        
        # 🚀 AUTO-INTEGRATE HEALING INTO ALL PLATFORMS
        self._auto_integrate_healing()
        
        self._initialized = True
        
        logger.info(
            f"🏭 Platform Factory initialized: "
            f"{len(PlatformFactory._discovered)} platforms discovered, "
            f"{len(PlatformFactory._auto_integrated)} platforms auto-integrated with AI healing"
        )
    
    # =========================================================================
    # AUTO-DISCOVERY
    # =========================================================================
    
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
            logger.warning(f"⚠️ Platforms directory not found: {platforms_dir}")
            logger.info("Using fallback HANDLER_REGISTRY")
            return
        
        skip_files = {"__init__", "__pycache__", "_template", "base"}
        discovered_count = 0
        
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
                        
                        discovered_count += 1
                        logger.info(f"✅ Discovered: {platform_name} → {name}")
            
            except Exception as e:
                logger.error(f"❌ Failed to load {file_path.name}: {e}")
        
        logger.info(f"📦 Total platforms discovered: {discovered_count}")
    
    # =========================================================================
    # 🚀 AUTO-INTEGRATION SYSTEM (Universal AI Healing)
    # =========================================================================
    
    def _auto_integrate_healing(self):
        """
        Automatically integrate AI healing into ALL discovered platforms
        
        This is the MAGIC that makes the system universal!
        
        What it does:
        1. Finds all platform classes
        2. Checks if they already have healing methods
        3. If not, injects universal healing methods
        4. Ensures healing engine is auto-initialized
        
        Result: ANY platform automatically gets AI healing! 🎉
        """
        if not PlatformFactory._discovered:
            logger.warning("⚠️ No platforms discovered, skipping auto-integration")
            return
        
        logger.info("🔧 Starting auto-integration of AI healing...")
        
        for platform_name, platform_info in PlatformFactory._discovered.items():
            if platform_name in PlatformFactory._auto_integrated:
                logger.debug(f"✓ {platform_name} already integrated")
                continue
            
            try:
                platform_class = platform_info["class"]
                
                # Verify it's a valid platform handler
                if not issubclass(platform_class, BasePlatformHandler):
                    logger.warning(f"⚠️ {platform_name} is not a BasePlatformHandler, skipping")
                    continue
                
                # Check if already has auto_healing_extraction method
                has_healing = hasattr(platform_class, 'auto_healing_extraction')
                has_init_healing = hasattr(platform_class, '_initialize_healing_engine')
                
                if has_healing and has_init_healing:
                    logger.debug(f"✓ {platform_name} already has healing methods (from base class)")
                    PlatformFactory._auto_integrated.add(platform_name)
                    continue
                
                # Inject healing methods if needed
                self._inject_healing_methods(platform_class, platform_name)
                
                PlatformFactory._auto_integrated.add(platform_name)
                logger.info(f"🤖 Auto-integrated AI healing: {platform_name}")
                
            except Exception as e:
                logger.error(f"❌ Failed to auto-integrate {platform_name}: {e}")
        
        logger.info(
            f"✅ Auto-integration complete: {len(PlatformFactory._auto_integrated)}/{len(PlatformFactory._discovered)} platforms"
        )
    
    def _inject_healing_methods(self, platform_class: Type, platform_name: str):
        """
        Inject universal healing methods into a platform class
        
        This ensures backward compatibility with platforms that don't
        inherit the latest BasePlatformHandler
        
        Args:
            platform_class: The platform scraper class
            platform_name: Platform name for logging
        """
        try:
            # Check if methods exist in the class itself (not just inherited)
            if not hasattr(platform_class, 'auto_healing_extraction'):
                # Methods should be inherited from BasePlatformHandler
                # If not, log warning but don't fail
                logger.debug(
                    f"⚠️ {platform_name} may be using old BasePlatformHandler. "
                    f"Methods should be inherited automatically."
                )
            
            # Ensure __init__ calls _initialize_healing_engine
            # This is handled by BasePlatformHandler.__init__
            # We just verify it's being called
            original_init = platform_class.__init__
            
            # Wrap __init__ to ensure healing is initialized
            def enhanced_init(self, config, *args, **kwargs):
                # Call original init
                original_init(self, config, *args, **kwargs)
                
                # Ensure healing engine is initialized (idempotent)
                if not hasattr(self, 'healing_engine') or self.healing_engine is None:
                    logger.debug(f"🔧 Force-initializing healing for {platform_name}")
                    self._initialize_healing_engine()
            
            # Only wrap if needed
            if not hasattr(original_init, '__wrapped__'):
                platform_class.__init__ = enhanced_init
                platform_class.__init__.__wrapped__ = True
                logger.debug(f"✓ Enhanced __init__ for {platform_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to inject methods into {platform_name}: {e}")
    
    # =========================================================================
    # HANDLER CREATION
    # =========================================================================
    
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
            Platform handler instance with AI healing enabled
        
        Example:
            handler = factory.get_handler_sync("amazon")
            # Handler has healing_engine and auto_healing_extraction!
        """
        platform_name = platform_name.lower().strip()
        
        # Check instance cache
        cache_key = f"{platform_name}_sync"
        if cache_key in PlatformFactory._instance_cache:
            if self._is_cache_valid(cache_key):
                logger.debug(f"♻️ Returning cached handler for {platform_name}")
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
        
        # Verify healing engine is initialized
        if not hasattr(handler, 'healing_engine'):
            logger.warning(f"⚠️ {platform_name} handler missing healing_engine, force-initializing")
            handler._initialize_healing_engine()
        
        # Cache it
        PlatformFactory._instance_cache[cache_key] = handler
        PlatformFactory._cache_expiry[cache_key] = datetime.utcnow() + timedelta(
            minutes=self.CACHE_DURATION_MINUTES
        )
        
        logger.info(f"✅ Created handler: {platform_name} (file-cache mode, AI healing: active)")
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
            Platform handler instance with AI healing enabled
        
        Example:
            # With database
            handler = await factory.get_handler("amazon", db)
            
            # Without database
            handler = await factory.get_handler("amazon")
        """
        platform_name = platform_name.lower().strip()
        
        # Check cache first
        cache_key = f"{platform_name}_{'db' if db else 'sync'}_{force_type.value if force_type else 'auto'}"
        
        if not force_refresh and cache_key in PlatformFactory._instance_cache:
            if self._is_cache_valid(cache_key):
                logger.debug(f"♻️ Returning cached handler for {platform_name}")
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
        if db and DB_AVAILABLE:
            # Try to load from database first
            config = await self._load_platform_config(platform_name, db)
            if not config:
                # Fallback to no-db config
                logger.warning(f"⚠️ Platform '{platform_name}' not in database, using metadata")
                config = self._build_config_no_db(platform_name, metadata, **config_overrides)
            elif not config.is_active:
                raise ValueError(f"Platform '{platform_name}' is disabled")
            
            # Apply overrides
            for key, value in config_overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        else:
            # No database - use metadata config
            config = self._build_config_no_db(platform_name, metadata, **config_overrides)
        
        # Create instance
        handler = scraper_class(config)
        
        # Verify healing engine is initialized
        if not hasattr(handler, 'healing_engine'):
            logger.warning(f"⚠️ {platform_name} handler missing healing_engine, force-initializing")
            handler._initialize_healing_engine()
        
        # Cache it
        PlatformFactory._instance_cache[cache_key] = handler
        PlatformFactory._cache_expiry[cache_key] = datetime.utcnow() + timedelta(
            minutes=self.CACHE_DURATION_MINUTES
        )
        
        mode = 'database' if db and DB_AVAILABLE else 'file-cache'
        logger.info(f"✅ Created handler: {platform_name} ({mode} mode, AI healing: active)")
        return handler
    
    # =========================================================================
    # PLATFORM CLASS RETRIEVAL
    # =========================================================================
    
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
            logger.error(f"❌ Failed to import {module_path}: {e}")
            return None
        except AttributeError as e:
            logger.error(f"❌ Class not found in module: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error loading handler class: {e}")
            return None
    
    # =========================================================================
    # CONFIGURATION BUILDING
    # =========================================================================
    
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
        from app.core.config import settings
        
        affiliate_tag = None
        if platform_name == "amazon":
            affiliate_tag = getattr(settings, "AMAZON_AFFILIATE_TAG", "dealhunt-21")
        elif platform_name == "flipkart":
            affiliate_tag = getattr(settings, "FLIPKART_AFFILIATE_ID", "dealhunt")
        elif platform_name == "meesho":
            affiliate_tag = getattr(settings, "MEESHO_AFFILIATE_ID", "dealhunt")
        elif platform_name == "myntra":
            affiliate_tag = getattr(settings, "AFFILIATE_MYNTRA_ID", None)
        elif platform_name == "croma":
            affiliate_tag = getattr(settings, "AFFILIATE_CROMA_ID", None)
        
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
        if not DB_AVAILABLE:
            return None
        
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
            logger.error(f"❌ Error loading platform config from DB: {e}")
            return None
    
    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached handler is still valid"""
        if cache_key not in PlatformFactory._cache_expiry:
            return False
        return datetime.utcnow() < PlatformFactory._cache_expiry[cache_key]
    
    def clear_cache(self, platform_name: Optional[str] = None):
        """
        Clear handler cache
        
        Args:
            platform_name: Specific platform to clear, or None for all
        """
        if platform_name:
            platform_name = platform_name.lower()
            keys_to_remove = [k for k in PlatformFactory._instance_cache.keys() if platform_name in k]
            for key in keys_to_remove:
                del PlatformFactory._instance_cache[key]
                if key in PlatformFactory._cache_expiry:
                    del PlatformFactory._cache_expiry[key]
            logger.info(f"🗑️ Cleared cache for {platform_name}")
        else:
            PlatformFactory._instance_cache.clear()
            PlatformFactory._cache_expiry.clear()
            logger.info("🗑️ Cleared all handler cache")
    
    # =========================================================================
    # 🚀 HEALTH MONITORING (Universal)
    # =========================================================================
    
    async def get_platform_health_report(self, platform_name: str) -> Dict[str, Any]:
        """
        Get comprehensive health report for a platform
        
        Args:
            platform_name: Platform name
        
        Returns:
            Dictionary with health metrics and recommendations
        
        Example:
            report = await factory.get_platform_health_report("amazon")
            print(report["summary"]["health_score"])
            print(report["recommendations"])
        """
        try:
            # Get handler (file-cache mode, no DB needed)
            handler = self.get_handler_sync(platform_name)
            
            # Get selector cache performance
            cache_report = self._selector_cache.get_performance_report(platform_name)
            
            # Get healing engine analytics
            healing_report = {}
            if hasattr(handler, 'healing_engine') and handler.healing_engine:
                healing_report = handler.healing_engine.get_health_summary()
                performance_report = handler.healing_engine.get_performance_report()
                healing_recommendations = handler.healing_engine.get_recommendations()
            else:
                healing_report = {"error": "No healing engine available"}
                performance_report = {}
                healing_recommendations = ["⚠️ Healing engine not initialized"]
            
            # Get handler health
            handler_health = await handler.health_check()
            
            # Combine reports
            return {
                "platform": platform_name,
                "timestamp": datetime.utcnow().isoformat(),
                "handler_health": {
                    "is_healthy": handler_health.is_healthy,
                    "success_rate": handler_health.success_rate,
                    "consecutive_failures": handler_health.consecutive_failures,
                    "healed_selectors_count": handler_health.healed_selectors_count
                },
                "cache_performance": cache_report,
                "healing_analytics": healing_report,
                "healing_performance": performance_report,
                "recommendations": self._generate_recommendations(
                    cache_report, 
                    healing_report,
                    healing_recommendations
                ),
                "summary": {
                    "health_score": cache_report["summary"].get("health_score", 50),
                    "total_selectors": cache_report["total_selectors"],
                    "avg_success_rate": cache_report["summary"].get("avg_success_rate", 0),
                    "avg_response_time_ms": cache_report["summary"].get("avg_response_time_ms", 0),
                    "healing_attempts": healing_report.get("total_healing_attempts", 0),
                    "ai_healing_active": hasattr(handler, 'healing_engine') and handler.healing_engine is not None
                }
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting health report for {platform_name}: {e}")
            return {
                "platform": platform_name,
                "error": str(e),
                "recommendations": [f"❌ Failed to generate health report: {str(e)}"]
            }
    
    async def get_all_platforms_health(self) -> Dict[str, Any]:
        """
        Get health report for ALL platforms
        
        Returns:
            Dictionary with system-wide health metrics
        
        Example:
            report = await factory.get_all_platforms_health()
            print(f"System health: {report['system_health']['overall_score']}")
        """
        health_report = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_platforms": 0,
            "platforms_with_healing": 0,
            "platforms": {},
            "system_health": {
                "overall_score": 0.0,
                "avg_success_rate": 0.0,
                "total_healing_attempts": 0,
                "total_selectors": 0,
                "platforms_healthy": 0,
                "platforms_unhealthy": 0
            },
            "recommendations": []
        }
        
        # Get all platform names
        platform_names = self.get_all_platform_names()
        health_report["total_platforms"] = len(platform_names)
        
        # Collect health data
        health_scores = []
        success_rates = []
        total_healing = 0
        total_selectors = 0
        
        for platform_name in platform_names:
            try:
                platform_health = await self.get_platform_health_report(platform_name)
                health_report["platforms"][platform_name] = platform_health
                
                # Check if has healing
                if platform_health.get("summary", {}).get("ai_healing_active", False):
                    health_report["platforms_with_healing"] += 1
                
                # Aggregate metrics
                summary = platform_health.get("summary", {})
                health_score = summary.get("health_score", 0)
                success_rate = summary.get("avg_success_rate", 0)
                
                health_scores.append(health_score)
                success_rates.append(success_rate)
                total_healing += summary.get("healing_attempts", 0)
                total_selectors += summary.get("total_selectors", 0)
                
                # Count healthy/unhealthy
                if health_score >= 70:
                    health_report["system_health"]["platforms_healthy"] += 1
                else:
                    health_report["system_health"]["platforms_unhealthy"] += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to get health for {platform_name}: {e}")
                health_report["platforms"][platform_name] = {
                    "error": str(e),
                    "summary": {"health_score": 0}
                }
        
        # Calculate system-wide metrics
        if health_scores:
            health_report["system_health"]["overall_score"] = round(
                sum(health_scores) / len(health_scores), 1
            )
        
        if success_rates:
            health_report["system_health"]["avg_success_rate"] = round(
                sum(success_rates) / len(success_rates), 1
            )
        
        health_report["system_health"]["total_healing_attempts"] = total_healing
        health_report["system_health"]["total_selectors"] = total_selectors
        
        # Generate system-wide recommendations
        overall_score = health_report["system_health"]["overall_score"]
        
        if overall_score >= 90:
            health_report["recommendations"].append("✅ Excellent system health! All platforms performing well.")
        elif overall_score >= 75:
            health_report["recommendations"].append("👍 Good system health. Minor optimizations possible.")
        elif overall_score >= 50:
            health_report["recommendations"].append("⚠️ Average system health. Review underperforming platforms.")
        else:
            health_report["recommendations"].append("🚨 Poor system health! Immediate attention needed.")
        
        # Check healing coverage
        healing_coverage = (health_report["platforms_with_healing"] / health_report["total_platforms"] * 100) if health_report["total_platforms"] > 0 else 0
        
        if healing_coverage < 100:
            missing = health_report["total_platforms"] - health_report["platforms_with_healing"]
            health_report["recommendations"].append(
                f"⚠️ {missing} platform(s) missing AI healing. Ensure all platforms inherit from BasePlatformHandler."
            )
        
        # Check unhealthy platforms
        if health_report["system_health"]["platforms_unhealthy"] > 0:
            unhealthy_platforms = [
                name for name, data in health_report["platforms"].items()
                if data.get("summary", {}).get("health_score", 0) < 70
            ]
            health_report["recommendations"].append(
                f"🔧 {len(unhealthy_platforms)} unhealthy platform(s): {', '.join(unhealthy_platforms[:3])}"
            )
        
        return health_report
    
    def _generate_recommendations(
        self,
        cache_report: Dict[str, Any],
        healing_report: Dict[str, Any],
        healing_recommendations: List[str]
    ) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []
        
        # Add healing engine recommendations
        recommendations.extend(healing_recommendations)
        
        # Cache performance recommendations
        cache_recs = cache_report.get("recommendations", [])
        recommendations.extend(cache_recs)
        
        # Overall health check
        health_score = cache_report.get("summary", {}).get("health_score", 50)
        
        if health_score >= 90:
            recommendations.insert(0, "✅ Platform is in excellent health!")
        elif health_score < 50:
            recommendations.insert(0, "🚨 Platform health is critical! Immediate action required.")
        
        # Deduplicate
        return list(dict.fromkeys(recommendations))[:10]  # Keep top 10 unique
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_all_platform_names(self) -> List[str]:
        """Get list of all available platforms"""
        # Combine discovered + registry
        platforms = set(PlatformFactory._discovered.keys())
        platforms.update(HANDLER_REGISTRY.keys())
        return sorted(list(platforms))
    
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
                logger.error(f"❌ Failed to get handler for {platform_name}: {e}")
        
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
                logger.error(f"❌ Health check failed for {handler.platform_name}: {e}")
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
                logger.error(f"❌ Error closing handler: {e}")
        
        PlatformFactory._instance_cache.clear()
        PlatformFactory._cache_expiry.clear()
        logger.info("🗑️ All handlers closed")


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
"""
Browser Manager for Playwright
Handles browser lifecycle, stealth mode, and resource optimization

Features:
- Singleton browser instance
- Stealth mode (anti-detection)
- Resource blocking (images, CSS, fonts)
- Automatic cleanup
- Human-like behavior
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import random

from app.core.config import settings

logger = logging.getLogger(__name__)

# Playwright is optional - only import if available
try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        Playwright
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Scraping features disabled.")


# User agents pool for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
]

# Viewport sizes for realism
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720}
]


class BrowserManager:
    """
    Manages Playwright browser instances
    
    Features:
    - Single browser instance (reused)
    - Multiple contexts (isolated sessions)
    - Stealth mode enabled
    - Resource optimization
    - Automatic cleanup
    
    Usage:
        manager = BrowserManager()
        await manager.initialize()
        
        async with manager.get_page() as page:
            await page.goto("https://amazon.in")
            content = await page.content()
        
        await manager.close()
    """
    
    def __init__(self):
        self._playwright: Optional['Playwright'] = None
        self._browser: Optional['Browser'] = None
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize Playwright and browser"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed")
        
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            try:
                self._playwright = await async_playwright().start()
                
                # Launch browser with stealth settings
                self._browser = await self._playwright.chromium.launch(
                    headless=settings.PLAYWRIGHT_HEADLESS,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-gpu',
                        '--disable-software-rasterizer'
                    ]
                )
                
                self._initialized = True
                logger.info("Browser manager initialized")
                
            except Exception as e:
                logger.error(f"Failed to initialize browser: {e}")
                raise
    
    async def close(self) -> None:
        """Close browser and cleanup"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        
        self._initialized = False
        logger.info("Browser manager closed")
    
    @asynccontextmanager
    async def get_page(
        self,
        block_resources: bool = True,
        stealth: bool = True
    ):
        """
        Get a new page with context
        
        Args:
            block_resources: Block images, CSS, fonts for speed
            stealth: Enable anti-detection features
        
        Yields:
            Page instance
        
        Usage:
            async with manager.get_page() as page:
                await page.goto(url)
        """
        if not self._initialized:
            await self.initialize()
        
        # Create context with random fingerprint
        context = await self._create_context(stealth)
        page = await context.new_page()
        
        try:
            # Block resources for speed
            if block_resources:
                await self._setup_resource_blocking(page)
            
            # Add stealth scripts
            if stealth:
                await self._inject_stealth_scripts(page)
            
            yield page
            
        finally:
            await page.close()
            await context.close()
    
    async def _create_context(self, stealth: bool = True) -> 'BrowserContext':
        """Create browser context with randomized fingerprint"""
        user_agent = random.choice(USER_AGENTS)
        viewport = random.choice(VIEWPORTS)
        
        context_options = {
            "user_agent": user_agent,
            "viewport": viewport,
            "locale": "en-IN",
            "timezone_id": "Asia/Kolkata",
            "geolocation": {"latitude": 28.6139, "longitude": 77.2090},  # Delhi
            "permissions": ["geolocation"]
        }
        
        if stealth:
            context_options["extra_http_headers"] = {
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1"
            }
        
        return await self._browser.new_context(**context_options)
    
    async def _setup_resource_blocking(self, page: 'Page') -> None:
        """Block unnecessary resources for speed"""
        await page.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in ["image", "stylesheet", "font", "media"]
                else route.continue_()
            )
        )
    
    async def _inject_stealth_scripts(self, page: 'Page') -> None:
        """Inject scripts to avoid bot detection"""
        # Hide webdriver
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        # Mock plugins
        await page.add_init_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)
        
        # Mock languages
        await page.add_init_script("""
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-IN', 'en-US', 'en']
            });
        """)
        
        # Mock chrome
        await page.add_init_script("""
            window.chrome = {
                runtime: {}
            };
        """)
    
    async def human_like_delay(self, min_ms: int = 500, max_ms: int = 2000) -> None:
        """Add human-like random delay"""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)
    
    async def scroll_page(
        self,
        page: 'Page',
        scroll_count: int = 3,
        delay_ms: int = 500
    ) -> None:
        """Scroll page like a human"""
        for _ in range(scroll_count):
            # Random scroll amount
            scroll_amount = random.randint(300, 700)
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await asyncio.sleep(delay_ms / 1000)
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_browser_manager: Optional[BrowserManager] = None


async def get_browser_manager() -> BrowserManager:
    """Get global browser manager instance"""
    global _browser_manager
    
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    
    if not _browser_manager.is_initialized:
        await _browser_manager.initialize()
    
    return _browser_manager


async def close_browser_manager() -> None:
    """Close global browser manager"""
    global _browser_manager
    
    if _browser_manager:
        await _browser_manager.close()
        _browser_manager = None
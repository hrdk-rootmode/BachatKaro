"""
Browser Manager for Playwright - STEALTH EDITION v2.0
Production-grade browser management with anti-detection and API interception

🚀 NEW FEATURES:
- Network/API Interception (capture XHR/Fetch JSON responses)
- Advanced stealth mode (bypasses Akamai, Cloudflare, PerimeterX)
- Human-like behavior simulation
- Cloud-deployment ready (Oracle Cloud, Render, Railway)
- Proxy support ready

Author: DealHunt
Version: 2.0.0 - God Mode Edition
"""

import logging
import sys

# Fix NotImplementedError on Windows for asyncio subprocess
# Playwright requires WindowsProactorEventLoopPolicy on Windows for subprocess support
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
else:
    import asyncio
    
import random
import json
from typing import Optional, List, Dict, Any, Callable, Set
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

# Playwright is optional - only import if available
try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        Playwright,
        Route,
        Response
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("⚠️ Playwright not installed. Scraping features disabled.")


# =============================================================================
# STEALTH CONFIGURATION
# =============================================================================

# Realistic user agents (Chrome on Windows/Mac - most common)
USER_AGENTS = [
    # Chrome 120+ on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# Mobile user agents (for sites that are easier on mobile)
MOBILE_USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

# Viewport sizes for realism
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
]

MOBILE_VIEWPORTS = [
    {"width": 412, "height": 915},  # Pixel 7
    {"width": 390, "height": 844},  # iPhone 14
    {"width": 360, "height": 800},  # Samsung Galaxy
]

# Browser launch arguments for stealth + cloud compatibility
STEALTH_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-gpu',
    '--disable-software-rasterizer',
    '--disable-extensions',
    '--disable-default-apps',
    '--disable-sync',
    '--disable-translate',
    '--hide-scrollbars',
    '--mute-audio',
    '--no-first-run',
    '--no-zygote',
    '--disable-background-networking',
    '--disable-background-timer-throttling',
    '--disable-backgrounding-occluded-windows',
    '--disable-breakpad',
    '--disable-client-side-phishing-detection',
    '--disable-component-update',
    '--disable-hang-monitor',
    '--disable-ipc-flooding-protection',
    '--disable-popup-blocking',
    '--disable-prompt-on-repost',
    '--disable-renderer-backgrounding',
    '--force-color-profile=srgb',
    '--metrics-recording-only',
    '--password-store=basic',
    '--use-mock-keychain',
]


# =============================================================================
# INTERCEPTED RESPONSE DATA CLASS
# =============================================================================

@dataclass
class InterceptedResponse:
    """Captured network response"""
    url: str
    status: int
    content_type: str
    data: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_json(self) -> bool:
        return 'application/json' in self.content_type
    
    @property
    def is_html(self) -> bool:
        return 'text/html' in self.content_type


# =============================================================================
# BROWSER MANAGER CLASS
# =============================================================================

class BrowserManager:
    """
    Manages Playwright browser instances with stealth and interception
    
    🚀 FEATURES:
    - Single browser instance (reused for efficiency)
    - Advanced stealth mode (anti-detection)
    - Network/API interception (capture JSON responses)
    - Human-like behavior simulation
    - Cloud-deployment ready
    
    Usage:
        manager = BrowserManager()
        await manager.initialize()
        
        async with manager.get_page() as page:
            await page.goto("https://myntra.com")
            content = await page.content()
        
        await manager.close()
    
    With API Interception:
        async with manager.get_page(intercept_api=True) as page:
            manager.set_interception_patterns(['api.myntra.com', '/api/'])
            await page.goto("https://myntra.com/product/123")
            product_data = manager.get_intercepted_json('/product/')
    """
    
    def __init__(self, proxy: Optional[str] = None):
        """Initialize browser manager"""
        self._playwright: Optional['Playwright'] = None
        self._browser: Optional['Browser'] = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self._proxy = proxy
        
        # Interception state
        self._intercepted_responses: Dict[str, InterceptedResponse] = {}
        self._interception_patterns: Set[str] = set()
        self._interception_enabled = False
    
    async def initialize(self) -> None:
        """Initialize Playwright and browser"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium")
        
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            try:
                self._playwright = await async_playwright().start()
                
                # Build launch options
                launch_options = {
                    "headless": getattr(settings, 'PLAYWRIGHT_HEADLESS', True),
                    "args": STEALTH_ARGS,
                }
                
                # Add proxy if configured
                if self._proxy:
                    launch_options["proxy"] = {"server": self._proxy}
                
                self._browser = await self._playwright.chromium.launch(**launch_options)
                
                self._initialized = True
                logger.info("✅ Browser Manager initialized (Stealth Mode: Active)")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize browser: {e}")
                raise
    
    async def close(self) -> None:
        """Close browser and cleanup properly"""
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            
            self._initialized = False
            self._intercepted_responses.clear()
            logger.info("🔒 Browser Manager closed")
            
        except Exception as e:
            logger.error(f"⚠️ Error during browser cleanup: {e}")
    
    # =========================================================================
    # PAGE CONTEXT MANAGEMENT
    # =========================================================================
    
    @asynccontextmanager
    async def get_page(
        self,
        block_resources: bool = True,
        stealth: bool = True,
        mobile: bool = False,
        intercept_api: bool = False
    ):
        """
        ✅ FIXED: Get a new page with timeout protection and safer cleanup
        
        Improvements:
        - Timeout wrapper around context/page creation
        - Guaranteed cleanup on exception
        - Isolated interception per page
        """
        if not self._initialized:
            await self.initialize()
        
        # Clear previous interceptions (prevent cross-contamination)
        self._intercepted_responses.clear()
        self._interception_enabled = intercept_api
        
        context = None
        page = None
        
        try:
            # ✅ NEW: Timeout wrapper for context creation
            try:
                context = await asyncio.wait_for(
                    self._create_context(stealth, mobile),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logger.error("❌ Browser context creation timeout (30s)")
                raise RuntimeError("Browser context creation timeout")
            
            # ✅ NEW: Timeout wrapper for page creation
            try:
                page = await asyncio.wait_for(
                    context.new_page(),
                    timeout=15.0  # 15 second timeout
                )
            except asyncio.TimeoutError:
                logger.error("❌ Page creation timeout (15s)")
                if context:
                    await context.close()
                raise RuntimeError("Page creation timeout")
            
            # Set page timeout
            page.set_default_timeout(30000)
            page.set_default_navigation_timeout(45000)
            
            # Block resources for speed
            if block_resources:
                await self._setup_resource_blocking(page)
            
            # Add stealth scripts
            if stealth:
                await self._inject_stealth_scripts(page)
            
            # Set up API interception
            if intercept_api:
                await self._setup_api_interception(page)
            
            yield page
            
        except Exception as e:
            error_text = str(e).lower()
            is_expected_rate_limit = (
                e.__class__.__name__.lower() == "ratelimitexceeded"
                or "rate limit exceeded" in error_text
                or "retry after" in error_text
            )
            if is_expected_rate_limit:
                logger.warning(f"⏳ get_page stopped due to platform rate limit: {e}")
            else:
                logger.error(f"❌ Error in get_page: {e}")
            raise
        
        finally:
            # ✅ FIXED: Guaranteed cleanup
            try:
                if page:
                    try:
                        await asyncio.wait_for(page.close(), timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning("Page close timeout, forcing")
                    except Exception as e:
                        logger.debug(f"Page close error: {e}")
            except Exception as e:
                logger.debug(f"Page cleanup error: {e}")
            
            try:
                if context:
                    try:
                        await asyncio.wait_for(context.close(), timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning("Context close timeout, forcing")
                    except Exception as e:
                        logger.debug(f"Context close error: {e}")
            except Exception as e:
                logger.debug(f"Context cleanup error: {e}")
                
    async def _create_context(self, stealth: bool = True, mobile: bool = False) -> 'BrowserContext':
        """Create browser context with randomized fingerprint"""
        if mobile:
            user_agent = random.choice(MOBILE_USER_AGENTS)
            viewport = random.choice(MOBILE_VIEWPORTS)
        else:
            user_agent = random.choice(USER_AGENTS)
            viewport = random.choice(VIEWPORTS)
        
        context_options = {
            "user_agent": user_agent,
            "viewport": viewport,
            "locale": "en-IN",
            "timezone_id": "Asia/Kolkata",
            "geolocation": {"latitude": 28.6139, "longitude": 77.2090},  # Delhi
            "permissions": ["geolocation"],
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "has_touch": mobile,
            "is_mobile": mobile,
            "device_scale_factor": 2 if mobile else 1,
        }
        
        if stealth:
            context_options["extra_http_headers"] = {
                "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8,hi;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                "Sec-Ch-Ua-Mobile": "?1" if mobile else "?0",
                "Sec-Ch-Ua-Platform": '"Android"' if mobile else '"Windows"',
                "Cache-Control": "max-age=0",
            }
        
        return await self._browser.new_context(**context_options)
    
    # =========================================================================
    # STEALTH INJECTION
    # =========================================================================
    
    async def _inject_stealth_scripts(self, page: 'Page') -> None:
        """Inject scripts to avoid bot detection"""
        
        # Master stealth script - comprehensive anti-detection
        await page.add_init_script("""
            // Hide webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            
            // Override plugins to look real
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
                        { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
                        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
                        { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: '' }
                    ];
                    plugins.item = (i) => plugins[i];
                    plugins.namedItem = (name) => plugins.find(p => p.name === name);
                    plugins.refresh = () => {};
                    return plugins;
                },
                configurable: true
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-IN', 'en-US', 'en', 'hi'],
                configurable: true
            });
            
            // Override platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32',
                configurable: true
            });
            
            // Override hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
                configurable: true
            });
            
            // Override device memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
                configurable: true
            });
            
            // Mock Chrome object
            window.chrome = {
                runtime: {
                    connect: () => {},
                    sendMessage: () => {},
                    onMessage: { addListener: () => {} }
                },
                loadTimes: () => {},
                csi: () => {},
                app: {}
            };
            
            // Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Fix iframe contentWindow access
            const originalContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: function() {
                    const window = originalContentWindow.get.call(this);
                    if (window) {
                        Object.defineProperty(window.navigator, 'webdriver', {
                            get: () => undefined
                        });
                    }
                    return window;
                }
            });
            
            // Override console.debug to hide automation messages
            const originalDebug = console.debug;
            console.debug = function(...args) {
                if (args[0] && typeof args[0] === 'string' && args[0].includes('puppeteer')) {
                    return;
                }
                return originalDebug.apply(console, args);
            };
            
            // Mock WebGL vendor and renderer
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            };
        """)
    
    # =========================================================================
    # RESOURCE BLOCKING
    # =========================================================================
    
    async def _setup_resource_blocking(self, page: 'Page') -> None:
        """Block unnecessary resources for speed"""
        
        blocked_types = {"image", "stylesheet", "font", "media"}
        blocked_domains = {
            "googletagmanager.com", "google-analytics.com", "analytics.",
            "facebook.com", "fbcdn.net", "doubleclick.net", "googlesyndication.com",
            "hotjar.com", "clarity.ms", "newrelic.com", "sentry.io"
        }
        
        async def handle_route(route: 'Route'):
            request = route.request
            
            # Block by resource type
            if request.resource_type in blocked_types:
                await route.abort()
                return
            
            # Block tracking/analytics domains
            url = request.url.lower()
            for domain in blocked_domains:
                if domain in url:
                    await route.abort()
                    return
            
            await route.continue_()
        
        await page.route("**/*", handle_route)
    
    # =========================================================================
    # 🚀 API/XHR INTERCEPTION (THE SECRET WEAPON!)
    # =========================================================================
    
    def set_interception_patterns(self, patterns: List[str]) -> None:
        """Set URL patterns to intercept"""
        self._interception_patterns = set(patterns)
        logger.debug(f"📡 Interception patterns set: {patterns}")
    
    async def _setup_api_interception(self, page: 'Page') -> None:
        """Set up network interception to capture API responses"""
        
        async def handle_response(response: 'Response'):
            """Capture JSON responses matching our patterns"""
            try:
                url = response.url
                content_type = response.headers.get('content-type', '')
                
                # Check if response matches any pattern
                should_intercept = False
                
                # Default patterns for e-commerce sites
                default_patterns = [
                    '/api/', '/graphql', '/_next/data/', '/pdp/', '/product/',
                    '/search/', '/catalog/', '/listing/', 'apollo', '/v1/', '/v2/'
                ]
                
                patterns = self._interception_patterns or default_patterns
                
                for pattern in patterns:
                    if pattern in url:
                        should_intercept = True
                        break
                
                if should_intercept and 'application/json' in content_type:
                    try:
                        body = await response.body()
                        data = json.loads(body.decode('utf-8'))
                        
                        self._intercepted_responses[url] = InterceptedResponse(
                            url=url,
                            status=response.status,
                            content_type=content_type,
                            data=data
                        )
                        
                        logger.debug(f"📥 Intercepted JSON: {url[:80]}...")
                        
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.debug(f"Interception decode error: {e}")
                        
            except Exception as e:
                logger.debug(f"Response handling error: {e}")
        
        page.on('response', handle_response)
    
    def get_intercepted_json(self, pattern: str) -> Optional[Dict[str, Any]]:
        """Get intercepted JSON response matching pattern"""
        for url, response in self._intercepted_responses.items():
            if pattern in url and response.is_json:
                return response.data
        return None
    
    def get_all_intercepted(self) -> Dict[str, InterceptedResponse]:
        """Get all intercepted responses"""
        return self._intercepted_responses.copy()
    
    def clear_intercepted(self) -> None:
        """Clear intercepted responses"""
        self._intercepted_responses.clear()
    
    # =========================================================================
    # HUMAN-LIKE BEHAVIOR
    # =========================================================================
    
    async def human_like_delay(self, min_ms: int = 500, max_ms: int = 2000) -> None:
        """Add human-like random delay"""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)
    
    async def scroll_page(
        self,
        page: 'Page',
        scroll_count: int = 3,
        delay_ms: int = 500,
        random_scroll: bool = True
    ) -> None:
        """Scroll page like a human"""
        for i in range(scroll_count):
            if random_scroll:
                scroll_amount = random.randint(200, 600)
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            else:
                await page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
            
            # Random delay between scrolls
            await asyncio.sleep(random.randint(delay_ms - 200, delay_ms + 300) / 1000)
    
    async def scroll_to_bottom(self, page: 'Page', max_scrolls: int = 10) -> None:
        """Scroll to page bottom (useful for infinite scroll pages)"""
        for i in range(max_scrolls):
            previous_height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break  # No more content to load
    
    async def random_mouse_movement(self, page: 'Page') -> None:
        """Move mouse randomly to appear human"""
        viewport = page.viewport_size
        if viewport:
            x = random.randint(100, viewport['width'] - 100)
            y = random.randint(100, viewport['height'] - 100)
            await page.mouse.move(x, y)
    
    async def type_like_human(self, page: 'Page', selector: str, text: str) -> None:
        """Type text with human-like delays"""
        await page.click(selector)
        for char in text:
            await page.keyboard.type(char, delay=random.randint(50, 150))
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def wait_for_network_idle(self, page: 'Page', timeout: int = 30000) -> None:
        """Wait for network to be idle (all requests complete)"""
        try:
            await page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception as e:
            logger.debug(f"Network idle timeout: {e}")
    
    async def safe_goto(
        self,
        page: 'Page',
        url: str,
        wait_until: str = 'domcontentloaded',
        timeout: int = 30000,
        retries: int = 2
    ) -> bool:
        """
        ✅ FIXED: Navigate to URL with strict timeout and retry logic
        
        Improvements:
        - Strict outer timeout wrapper
        - Better error handling
        - Returns partial success if page loads but timeout
        """
        for attempt in range(retries + 1):
            try:
                # ✅ NEW: Strict timeout wrapper
                await asyncio.wait_for(
                    page.goto(url, wait_until=wait_until, timeout=timeout),
                    timeout=(timeout / 1000) + 5  # Add 5s buffer
                )
                return True
            
            except asyncio.TimeoutError:
                if attempt < retries:
                    logger.warning(f"Navigation timeout (attempt {attempt + 1}/{retries + 1})")
                    await asyncio.sleep(random.uniform(1, 3))
                else:
                    logger.error(f"Navigation failed after {retries + 1} attempts (timeout)")
                    # Return True anyway - page may have partially loaded
                    return True
            
            except Exception as e:
                if attempt < retries:
                    logger.warning(f"Navigation retry {attempt + 1}/{retries + 1}: {e}")
                    await asyncio.sleep(random.uniform(1, 3))
                else:
                    logger.error(f"Navigation failed after {retries + 1} retries: {e}")
                    return False
        
        return False
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized


# =============================================================================
# SINGLETON INSTANCE & HELPER FUNCTIONS
# =============================================================================

_browser_manager: Optional[BrowserManager] = None
_cleanup_lock = asyncio.Lock()


async def get_browser_manager(proxy: Optional[str] = None) -> BrowserManager:
    """Get global browser manager instance"""
    global _browser_manager
    
    if _browser_manager is None:
        _browser_manager = BrowserManager(proxy=proxy)
    
    if not _browser_manager.is_initialized:
        await _browser_manager.initialize()
    
    return _browser_manager


async def close_browser_manager() -> None:
    """Close global browser manager (call on app shutdown)"""
    global _browser_manager
    
    async with _cleanup_lock:
        if _browser_manager:
            await _browser_manager.close()
            _browser_manager = None


def cleanup_browser_sync() -> None:
    """Synchronous cleanup for Windows asyncio teardown fix"""
    global _browser_manager
    
    if _browser_manager and _browser_manager.is_initialized:
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            loop.run_until_complete(close_browser_manager())
        except Exception as e:
            logger.debug(f"Sync cleanup error: {e}")
        finally:
            _browser_manager = None
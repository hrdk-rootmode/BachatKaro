"""
Debug Script - Captures screenshots and HTML for failed scrapers
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Create debug directory
DEBUG_DIR = Path("debug_output")
DEBUG_DIR.mkdir(exist_ok=True)


async def debug_flipkart():
    """Debug Flipkart page"""
    print("\n" + "="*60)
    print("🔍 DEBUGGING FLIPKART")
    print("="*60)
    
    from app.services.scraper.browser import get_browser_manager
    
    url = "https://www.flipkart.com/microsoft-xbox-series-s-512-gb/p/itm25150c366b5ac"
    
    browser = await get_browser_manager()
    
    async with browser.get_page(block_resources=False, stealth=True) as page:
        # Dismiss popup
        try:
            await page.goto("https://www.flipkart.com", wait_until="domcontentloaded", timeout=15000)
            close_btn = await page.query_selector("button._2KpZ6l._2doB4z")
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(500)
        except:
            pass
        
        print(f"📍 URL: {url[:60]}...")
        print("⏳ Loading page...")
        
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        
        # Screenshot
        screenshot_path = DEBUG_DIR / "flipkart_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"📸 Screenshot saved: {screenshot_path}")
        
        # Get page title
        title = await page.title()
        print(f"📄 Page Title: {title}")
        
        # Get URL (check for redirects)
        current_url = page.url
        print(f"🔗 Current URL: {current_url[:80]}...")
        
        # Check for captcha/block
        html = await page.content()
        if "captcha" in html.lower() or "robot" in html.lower():
            print("⚠️  CAPTCHA/BOT DETECTION DETECTED!")
        
        # Try to find elements
        print("\n🔎 Looking for elements...")
        
        test_selectors = {
            "title_1": "span.VU-ZEz",
            "title_2": "span.B_NuCI",
            "title_3": "h1._6EBuvT",
            "price_1": "div.Nx9bqj._4b5DiR",
            "price_2": "div._30jeq3._16Jk6d",
            "price_3": "div._30jeq3",
            "any_price": "[class*='price']",
            "any_title": "h1, h2"
        }
        
        for name, selector in test_selectors.items():
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.text_content()
                    print(f"   ✅ {name}: {selector} → '{text[:50] if text else 'empty'}...'")
                else:
                    print(f"   ❌ {name}: {selector} → NOT FOUND")
            except Exception as e:
                print(f"   ❌ {name}: {selector} → ERROR: {e}")
        
        # Try JavaScript extraction
        print("\n🔎 JavaScript extraction...")
        js_result = await page.evaluate('''() => {
            const result = {};
            
            // Get all text
            const allText = document.body.innerText.substring(0, 2000);
            result.bodyTextSample = allText;
            
            // Find any element with price
            const priceElements = document.querySelectorAll('*');
            for (const el of priceElements) {
                if (el.textContent && el.textContent.includes('₹') && el.textContent.length < 30) {
                    result.foundPrice = el.textContent.trim();
                    result.priceTag = el.tagName;
                    result.priceClass = el.className;
                    break;
                }
            }
            
            // Find h1
            const h1 = document.querySelector('h1');
            if (h1) {
                result.h1Text = h1.textContent.trim();
            }
            
            // Check for captcha
            result.hasCaptcha = document.body.innerHTML.toLowerCase().includes('captcha');
            result.hasRobot = document.body.innerHTML.toLowerCase().includes('robot');
            
            return result;
        }''')
        
        print(f"   H1 Text: {js_result.get('h1Text', 'NOT FOUND')}")
        print(f"   Found Price: {js_result.get('foundPrice', 'NOT FOUND')}")
        print(f"   Price Tag: {js_result.get('priceTag', 'N/A')}")
        print(f"   Price Class: {js_result.get('priceClass', 'N/A')[:50] if js_result.get('priceClass') else 'N/A'}")
        print(f"   Has Captcha: {js_result.get('hasCaptcha', False)}")
        print(f"   Has Robot: {js_result.get('hasRobot', False)}")
        
        # Save HTML sample
        html_path = DEBUG_DIR / "flipkart_page.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html[:50000])  # First 50KB
        print(f"📄 HTML saved: {html_path}")
        
        print(f"\n📝 Body text sample:\n{js_result.get('bodyTextSample', '')[:500]}...")


async def debug_meesho():
    """Debug Meesho page"""
    print("\n" + "="*60)
    print("🔍 DEBUGGING MEESHO")
    print("="*60)
    
    from app.services.scraper.browser import get_browser_manager
    
    url = "https://www.meesho.com/portronics-key2-a-combo-of-multimedia-wireless-keyboard-mouse-compact-light-weight-for-pcs-laptops-and-smart-tv-white/p/19sfl7"
    
    browser = await get_browser_manager()
    
    async with browser.get_page(block_resources=False, stealth=True) as page:
        print(f"📍 URL: {url[:60]}...")
        print("⏳ Loading page...")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        
        await page.wait_for_timeout(5000)
        
        # Screenshot
        screenshot_path = DEBUG_DIR / "meesho_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"📸 Screenshot saved: {screenshot_path}")
        
        # Get page title
        title = await page.title()
        print(f"📄 Page Title: {title}")
        
        # Get URL
        current_url = page.url
        print(f"🔗 Current URL: {current_url[:80]}...")
        
        # Check for block
        html = await page.content()
        if "captcha" in html.lower() or "robot" in html.lower() or "blocked" in html.lower():
            print("⚠️  BOT DETECTION DETECTED!")
        
        # JavaScript extraction
        print("\n🔎 JavaScript extraction...")
        js_result = await page.evaluate('''() => {
            const result = {};
            
            // Get body text
            result.bodyTextSample = document.body.innerText.substring(0, 2000);
            
            // Find all prices
            const allElements = document.querySelectorAll('*');
            const prices = [];
            for (const el of allElements) {
                const text = el.textContent.trim();
                if (text.includes('₹') && text.length < 30) {
                    prices.push({
                        text: text,
                        tag: el.tagName,
                        class: el.className.substring(0, 50)
                    });
                    if (prices.length >= 5) break;
                }
            }
            result.foundPrices = prices;
            
            // Find images
            const imgs = document.querySelectorAll('img[src*="meesho"]');
            result.imageCount = imgs.length;
            if (imgs.length > 0) {
                result.firstImageSrc = imgs[0].src.substring(0, 100);
            }
            
            // Check for specific patterns
            result.hasRupee = document.body.innerHTML.includes('₹');
            
            return result;
        }''')
        
        print(f"   Found {len(js_result.get('foundPrices', []))} price elements")
        for i, p in enumerate(js_result.get('foundPrices', [])[:3]):
            print(f"      [{i}] {p.get('tag')}: '{p.get('text')}' (class: {p.get('class')[:30]}...)")
        
        print(f"   Image count: {js_result.get('imageCount', 0)}")
        print(f"   Has ₹ symbol: {js_result.get('hasRupee', False)}")
        
        # Save HTML
        html_path = DEBUG_DIR / "meesho_page.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html[:50000])
        print(f"📄 HTML saved: {html_path}")
        
        print(f"\n📝 Body text sample:\n{js_result.get('bodyTextSample', '')[:500]}...")


async def main():
    print("\n🔧 SCRAPER DEBUG TOOL")
    print("This will capture screenshots and HTML for failing scrapers\n")
    
    # Import config first
    from app.core.config import settings
    print(f"Environment: {settings.ENVIRONMENT}")
    
    await debug_flipkart()
    await debug_meesho()
    
    print("\n" + "="*60)
    print("📁 Debug files saved to: debug_output/")
    print("="*60)
    print("\nCheck the screenshots to see what the scraper sees!")


if __name__ == "__main__":
    asyncio.run(main())
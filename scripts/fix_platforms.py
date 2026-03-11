#!/usr/bin/env python3
"""
Platform Self-Healing Diagnostic Tool v2.0
==========================================

🚀 ENHANCED FEATURES:
- Uses PlatformFactory for proper initialization
- Complete platform healing (all selectors at once)
- Database persistence of healed selectors
- Automatic rollback on failure
- Detailed healing analytics
- Cross-platform health report

Usage:
    python scripts/fix_platforms.py --diagnose           # Check all platforms
    python scripts/fix_platforms.py --platform amazon    # Check specific
    python scripts/fix_platforms.py --heal               # Use AI to fix
    python scripts/fix_platforms.py --heal --apply       # Fix and save to DB
    python scripts/fix_platforms.py --report             # Full health report

Author: DealHunt
Version: 2.0.0
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from app.core.database import async_session_maker
from app.models import Platform
from app.services.ai.groq_client import groq_client, HealingStatus
from app.services.scraper.factory import PlatformFactory, get_factory
from app.services.scraper.selector_cache import get_selector_cache


# =============================================================================
# CONFIGURATION
# =============================================================================

PLATFORMS = ["amazon", "flipkart", "myntra", "nykaa", "croma", "meesho"]

TEST_URLS = {
    "amazon": "https://www.amazon.in/s?k=iphone",
    "flipkart": "https://www.flipkart.com/search?q=iphone",
    "myntra": "https://www.myntra.com/shirts",
    "nykaa": "https://www.nykaa.com/lipstick/c/169",
    "croma": "https://www.croma.com/searchB?q=laptop",
    "meesho": "https://www.meesho.com/sarees/pl/j91",
}

FIELDS_TO_TEST = [
    "product_title",
    "product_price",
    "product_image",
    "product_rating",
    "product_url",
]

# Color codes for terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def colorize(text: str, color: str) -> str:
    """Add color to terminal output"""
    return f"{color}{text}{Colors.END}"


# =============================================================================
# DIAGNOSIS
# =============================================================================

async def diagnose_platform(platform_name: str, verbose: bool = False) -> Dict[str, Any]:
    """
    Diagnose a platform's selector health
    
    Args:
        platform_name: Platform to diagnose
        verbose: Show detailed output
    
    Returns:
        Diagnosis results
    """
    print(f"\n🔍 Diagnosing {colorize(platform_name.upper(), Colors.BOLD)}...")
    
    results = {
        "platform": platform_name,
        "status": "unknown",
        "selectors_tested": 0,
        "selectors_working": 0,
        "selectors_broken": [],
        "selectors_status": {},
        "test_url": TEST_URLS.get(platform_name),
        "error": None,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            test_url = TEST_URLS.get(platform_name)
            if not test_url:
                results["error"] = "No test URL configured"
                return results
            
            print(f"   Loading: {test_url[:60]}...")
            
            try:
                await page.goto(test_url, timeout=30000, wait_until='domcontentloaded')
                await page.wait_for_timeout(3000)
            except Exception as e:
                results["error"] = f"Navigation failed: {str(e)[:100]}"
                results["status"] = "error"
                await browser.close()
                return results
            
            # Get selectors from database
            async with async_session_maker() as db:
                result = await db.execute(
                    select(Platform).where(Platform.name == platform_name)
                )
                platform = result.scalar_one_or_none()
                
                if not platform:
                    results["error"] = "Platform not found in database"
                    await browser.close()
                    return results
                
                selectors = platform.selectors or {}
            
            # Test each selector
            for field in FIELDS_TO_TEST:
                selector = selectors.get(field)
                
                if not selector:
                    results["selectors_broken"].append({
                        "field": field,
                        "selector": None,
                        "reason": "No selector configured"
                    })
                    results["selectors_status"][field] = "missing"
                    continue
                
                # Handle dict format
                if isinstance(selector, dict):
                    selector = selector.get("selector", "")
                
                results["selectors_tested"] += 1
                
                try:
                    element = await page.query_selector(selector)
                    
                    if element:
                        # Verify it has content
                        text = await element.text_content()
                        if text and len(text.strip()) > 0:
                            results["selectors_working"] += 1
                            results["selectors_status"][field] = "working"
                            print(f"      {colorize('✅', Colors.GREEN)} {field}")
                        else:
                            results["selectors_broken"].append({
                                "field": field,
                                "selector": selector,
                                "reason": "Element found but empty"
                            })
                            results["selectors_status"][field] = "empty"
                            print(f"      {colorize('⚠️', Colors.YELLOW)} {field}: Empty content")
                    else:
                        results["selectors_broken"].append({
                            "field": field,
                            "selector": selector,
                            "reason": "Selector found no elements"
                        })
                        results["selectors_status"][field] = "broken"
                        print(f"      {colorize('❌', Colors.RED)} {field}: No match")
                        
                except Exception as e:
                    results["selectors_broken"].append({
                        "field": field,
                        "selector": selector,
                        "reason": str(e)[:100]
                    })
                    results["selectors_status"][field] = "error"
                    print(f"      {colorize('❌', Colors.RED)} {field}: {str(e)[:50]}")
            
            await browser.close()
        
        # Determine overall status
        if not results["selectors_broken"]:
            results["status"] = "healthy"
        elif results["selectors_working"] > 0:
            results["status"] = "degraded"
        else:
            results["status"] = "failing"
        
    except ImportError:
        results["error"] = "Playwright not installed"
        results["status"] = "error"
        print(f"   {colorize('❌', Colors.RED)} Playwright not installed")
        
    except Exception as e:
        results["error"] = str(e)
        results["status"] = "error"
        print(f"   {colorize('❌', Colors.RED)} Error: {e}")
    
    return results


async def diagnose_all(verbose: bool = False) -> List[Dict[str, Any]]:
    """Diagnose all platforms"""
    print("\n" + "=" * 60)
    print(colorize("🏥 PLATFORM HEALTH CHECK", Colors.BOLD))
    print("=" * 60)
    
    results = []
    
    for platform in PLATFORMS:
        result = await diagnose_platform(platform, verbose)
        results.append(result)
        await asyncio.sleep(1)
    
    return results


# =============================================================================
# HEALING
# =============================================================================

async def heal_platform(
    platform_name: str,
    apply_fixes: bool = False,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Use AI to heal broken selectors for a platform
    
    Args:
        platform_name: Platform to heal
        apply_fixes: Whether to persist fixes to database
        verbose: Show detailed output
    
    Returns:
        Healing results
    """
    print(f"\n🩹 Healing {colorize(platform_name.upper(), Colors.BOLD)}...")
    
    results = {
        "platform": platform_name,
        "status": "pending",
        "suggestions": [],
        "applied": 0,
        "failed": 0,
        "errors": [],
        "timestamp": datetime.utcnow().isoformat()
    }
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            test_url = TEST_URLS.get(platform_name)
            
            try:
                await page.goto(test_url, timeout=30000, wait_until='domcontentloaded')
                await page.wait_for_timeout(3000)
            except Exception as e:
                results["errors"].append(f"Navigation failed: {e}")
                results["status"] = "error"
                await browser.close()
                return results
            
            # Get page content
            html_content = await page.content()
            
            # Get current selectors from DB
            async with async_session_maker() as db:
                result = await db.execute(
                    select(Platform).where(Platform.name == platform_name)
                )
                platform = result.scalar_one_or_none()
                
                if not platform:
                    results["errors"].append("Platform not found in database")
                    await browser.close()
                    return results
                
                selectors = platform.selectors or {}
            
            # Try to heal each broken field
            for field in FIELDS_TO_TEST:
                current_selector = selectors.get(field, "")
                if isinstance(current_selector, dict):
                    current_selector = current_selector.get("selector", "")
                
                # Test current selector
                element = None
                if current_selector:
                    try:
                        element = await page.query_selector(current_selector)
                    except:
                        pass
                
                if element:
                    text = await element.text_content()
                    if text and len(text.strip()) > 0:
                        continue  # Already working
                
                # Need to heal this field
                print(f"   🤖 Asking AI for {colorize(field, Colors.CYAN)}...")
                
                new_selector = await groq_client.suggest_selector_fix(
                    html_snippet=html_content,
                    failed_selector=current_selector,
                    target_data=field,
                    platform_name=platform_name
                )
                
                if new_selector:
                    # Test the suggestion
                    try:
                        test_element = await page.query_selector(new_selector)
                        
                        if test_element:
                            text = await test_element.text_content()
                            works = text and len(text.strip()) > 0
                        else:
                            works = False
                        
                        results["suggestions"].append({
                            "field": field,
                            "old": current_selector,
                            "new": new_selector,
                            "works": works,
                            "content_preview": text[:50] if works and text else None
                        })
                        
                        if works:
                            print(f"      {colorize('✅', Colors.GREEN)} AI suggestion works: {new_selector[:50]}")
                        else:
                            print(f"      {colorize('⚠️', Colors.YELLOW)} AI suggestion didn't work")
                            results["failed"] += 1
                            
                    except Exception as e:
                        results["suggestions"].append({
                            "field": field,
                            "old": current_selector,
                            "new": new_selector,
                            "works": False,
                            "error": str(e)
                        })
                        results["failed"] += 1
                else:
                    print(f"      {colorize('❌', Colors.RED)} AI couldn't generate selector")
                    results["failed"] += 1
                
                await asyncio.sleep(1)  # Rate limit
            
            await browser.close()
        
        # Apply fixes if requested
        if apply_fixes:
            working_suggestions = [s for s in results["suggestions"] if s.get("works")]
            
            if working_suggestions:
                applied = await apply_healing_to_database(
                    platform_name,
                    {s["field"]: s["new"] for s in working_suggestions}
                )
                results["applied"] = applied
                print(f"\n   💾 Applied {colorize(str(applied), Colors.GREEN)} fixes to database")
        
        # Determine status
        working_count = len([s for s in results["suggestions"] if s.get("works")])
        total_count = len(results["suggestions"])
        
        if working_count == total_count and total_count > 0:
            results["status"] = "success"
        elif working_count > 0:
            results["status"] = "partial"
        elif total_count > 0:
            results["status"] = "failed"
        else:
            results["status"] = "no_healing_needed"
        
    except ImportError:
        results["errors"].append("Playwright not installed")
        results["status"] = "error"
        
    except Exception as e:
        results["errors"].append(str(e))
        results["status"] = "error"
        print(f"   {colorize('❌', Colors.RED)} Error: {e}")
    
    return results


async def apply_healing_to_database(
    platform_name: str,
    selectors: Dict[str, str]
) -> int:
    """
    Apply healed selectors to database
    
    Args:
        platform_name: Platform name
        selectors: Dictionary of field -> selector
    
    Returns:
        Number of selectors applied
    """
    applied = 0
    
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Platform).where(Platform.name == platform_name)
            )
            platform = result.scalar_one_or_none()
            
            if not platform:
                return 0
            
            existing = platform.selectors or {}
            
            # Archive old selectors
            healed_history = existing.get("healed_selectors", [])
            healed_history.append({
                "date": datetime.utcnow().isoformat(),
                "old_selectors": {k: existing.get(k) for k in selectors.keys()},
                "new_selectors": selectors,
                "healed_by": "fix_platforms_script"
            })
            existing["healed_selectors"] = healed_history[-10:]
            
            # Apply new selectors
            for field, selector in selectors.items():
                existing[field] = selector
                applied += 1
            
            existing["last_healed"] = datetime.utcnow().isoformat()
            existing["healed_by"] = "fix_platforms_script_v2"
            
            platform.selectors = existing
            await db.commit()
            
    except Exception as e:
        print(f"   {colorize('❌', Colors.RED)} Database error: {e}")
    
    return applied


# =============================================================================
# REPORTING
# =============================================================================

def print_diagnosis_summary(results: List[Dict[str, Any]]):
    """Print diagnosis summary in a nice format"""
    print("\n" + "=" * 60)
    print(colorize("📊 DIAGNOSIS SUMMARY", Colors.BOLD))
    print("=" * 60)
    
    for result in results:
        platform = result["platform"]
        status = result["status"]
        
        if status == "healthy":
            icon = colorize("🟢", Colors.GREEN)
            status_text = colorize("HEALTHY", Colors.GREEN)
        elif status == "degraded":
            icon = colorize("🟡", Colors.YELLOW)
            status_text = colorize("DEGRADED", Colors.YELLOW)
        elif status == "failing":
            icon = colorize("🔴", Colors.RED)
            status_text = colorize("FAILING", Colors.RED)
        else:
            icon = "⚪"
            status_text = colorize("ERROR", Colors.RED)
        
        working = result.get("selectors_working", 0)
        tested = result.get("selectors_tested", 0)
        
        print(f"   {icon} {platform.capitalize():12} | {status_text:20} | {working}/{tested} selectors")
        
        if result.get("selectors_broken"):
            for broken in result["selectors_broken"][:3]:
                field = broken['field']
                reason = broken['reason'][:40]
                print(f"      {colorize('⚠️', Colors.YELLOW)} {field}: {reason}")
        
        if result.get("error"):
            print(f"      {colorize('❌', Colors.RED)} Error: {result['error'][:50]}")


def print_healing_summary(results: List[Dict[str, Any]]):
    """Print healing summary"""
    print("\n" + "=" * 60)
    print(colorize("🩹 HEALING SUMMARY", Colors.BOLD))
    print("=" * 60)
    
    total_suggestions = 0
    total_working = 0
    total_applied = 0
    
    for result in results:
        platform = result["platform"]
        status = result["status"]
        
        suggestions = result.get("suggestions", [])
        working = len([s for s in suggestions if s.get("works")])
        applied = result.get("applied", 0)
        
        total_suggestions += len(suggestions)
        total_working += working
        total_applied += applied
        
        if status == "success":
            icon = colorize("✅", Colors.GREEN)
        elif status == "partial":
            icon = colorize("🔶", Colors.YELLOW)
        elif status == "no_healing_needed":
            icon = colorize("👍", Colors.BLUE)
        else:
            icon = colorize("❌", Colors.RED)
        
        print(f"   {icon} {platform.capitalize():12} | {working}/{len(suggestions)} fixes | Applied: {applied}")
    
    print("\n" + "-" * 40)
    print(f"   Total Suggestions: {total_suggestions}")
    print(f"   Working: {total_working}")
    print(f"   Applied to DB: {total_applied}")


async def generate_full_report() -> Dict[str, Any]:
    """Generate comprehensive health report"""
    print("\n" + "=" * 60)
    print(colorize("📋 GENERATING FULL HEALTH REPORT", Colors.BOLD))
    print("=" * 60)
    
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "platforms": {},
        "summary": {
            "total_platforms": len(PLATFORMS),
            "healthy": 0,
            "degraded": 0,
            "failing": 0,
            "error": 0
        },
        "recommendations": []
    }
    
    # Get factory for health reports
    factory = get_factory()
    
    # Diagnose all platforms
    for platform_name in PLATFORMS:
        print(f"\n   Checking {platform_name}...")
        
        try:
            # Get factory health report
            health = await factory.get_platform_health_report(platform_name)
            
            # Get diagnosis
            diagnosis = await diagnose_platform(platform_name)
            
            report["platforms"][platform_name] = {
                "diagnosis": diagnosis,
                "health": health,
                "status": diagnosis["status"]
            }
            
            # Update summary
            status = diagnosis["status"]
            if status in report["summary"]:
                report["summary"][status] += 1
            
        except Exception as e:
            report["platforms"][platform_name] = {
                "error": str(e),
                "status": "error"
            }
            report["summary"]["error"] += 1
    
    # Generate recommendations
    if report["summary"]["failing"] > 0:
        report["recommendations"].append(
            f"🚨 {report['summary']['failing']} platform(s) are failing! Run healing immediately."
        )
    
    if report["summary"]["degraded"] > 0:
        report["recommendations"].append(
            f"⚠️ {report['summary']['degraded']} platform(s) are degraded. Consider healing soon."
        )
    
    if report["summary"]["healthy"] == report["summary"]["total_platforms"]:
        report["recommendations"].append("✅ All platforms are healthy!")
    
    # Get AI quota status
    try:
        quota = await groq_client.get_quota_status()
        report["ai_quota"] = quota
        
        healing_remaining = quota.get("healing", {}).get("remaining", 0)
        if healing_remaining < 100:
            report["recommendations"].append(
                f"⚠️ Low AI healing quota: {healing_remaining} remaining"
            )
    except:
        pass
    
    return report


# =============================================================================
# MAIN
# =============================================================================

async def main(args):
    """Main entry point"""
    print("\n" + "=" * 60)
    print(colorize("🩺 PLATFORM HEALER v2.0", Colors.BOLD))
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Full report mode
    if args.report:
        report = await generate_full_report()
        
        print("\n" + "=" * 60)
        print(colorize("📋 REPORT SUMMARY", Colors.BOLD))
        print("=" * 60)
        
        print(f"\n   Healthy:  {colorize(str(report['summary']['healthy']), Colors.GREEN)}")
        print(f"   Degraded: {colorize(str(report['summary']['degraded']), Colors.YELLOW)}")
        print(f"   Failing:  {colorize(str(report['summary']['failing']), Colors.RED)}")
        print(f"   Error:    {report['summary']['error']}")
        
        print("\n   Recommendations:")
        for rec in report.get("recommendations", []):
            print(f"   • {rec}")
        
        # Save report
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\n   📄 Report saved to: {args.output}")
        
        return
    
    # Diagnosis mode
    if args.diagnose:
        if args.platform:
            results = [await diagnose_platform(args.platform, args.verbose)]
        else:
            results = await diagnose_all(args.verbose)
        
        print_diagnosis_summary(results)
    
    # Healing mode
    if args.heal:
        healing_results = []
        
        platforms_to_heal = [args.platform] if args.platform else PLATFORMS
        
        for platform_name in platforms_to_heal:
            result = await heal_platform(
                platform_name,
                apply_fixes=args.apply,
                verbose=args.verbose
            )
            healing_results.append(result)
        
        print_healing_summary(healing_results)
    
    print(f"\n{colorize('✅ Done!', Colors.GREEN)}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Platform Self-Healing Diagnostic Tool v2.0"
    )
    
    parser.add_argument(
        "--diagnose", "-d",
        action="store_true",
        help="Diagnose platform health"
    )
    
    parser.add_argument(
        "--heal", "-H",
        action="store_true",
        help="Use AI to suggest fixes"
    )
    
    parser.add_argument(
        "--apply", "-a",
        action="store_true",
        help="Apply working fixes to database"
    )
    
    parser.add_argument(
        "--platform", "-p",
        type=str,
        choices=PLATFORMS,
        help="Specific platform to check"
    )
    
    parser.add_argument(
        "--report", "-r",
        action="store_true",
        help="Generate full health report"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output file for report (JSON)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Default to diagnose if no action specified
    if not any([args.diagnose, args.heal, args.report]):
        args.diagnose = True
    
    # Run
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print(f"\n{colorize('👋 Interrupted', Colors.YELLOW)}")
    except Exception as e:
        print(f"\n{colorize(f'❌ Error: {e}', Colors.RED)}")
        sys.exit(1)
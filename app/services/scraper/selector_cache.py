"""
Universal Selector Cache - File-based storage with Performance Analytics
Works without database! Perfect for development and production.

🚀 NEW: Universal Multi-Platform Support
- Performance tracking per selector
- Response time analytics
- Success rate monitoring
- Auto-promotion support
- Cross-platform analytics
- Recommendations engine

Author: DealHunt
Why: Self-healing saves selectors to JSON file when DB unavailable
"""

import json
import logging
import hashlib
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


# =============================================================================
# PERFORMANCE DATA CLASS
# =============================================================================

@dataclass
class SelectorPerformance:
    """Performance metrics for a selector"""
    selector: str
    success_count: int = 0
    fail_count: int = 0
    total_response_time: float = 0.0
    avg_response_time: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    last_used: Optional[str] = None
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    healed_at: Optional[str] = None
    method: str = "unknown"
    version: int = 1
    promoted: bool = False
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.success_count + self.fail_count
        return (self.success_count / total) if total > 0 else 0.0
    
    @property
    def total_uses(self) -> int:
        """Total number of uses"""
        return self.success_count + self.fail_count
    
    @property
    def health_score(self) -> float:
        """Calculate health score (0-100)"""
        if self.total_uses == 0:
            return 50.0  # Unknown
        
        # Weight factors
        success_weight = 0.6
        speed_weight = 0.3
        recency_weight = 0.1
        
        # Success score (0-100)
        success_score = self.success_rate * 100
        
        # Speed score (0-100, faster is better)
        if self.avg_response_time <= 0.5:
            speed_score = 100
        elif self.avg_response_time <= 1.0:
            speed_score = 80
        elif self.avg_response_time <= 2.0:
            speed_score = 60
        elif self.avg_response_time <= 5.0:
            speed_score = 40
        else:
            speed_score = 20
        
        # Recency score (0-100, recently used is better)
        recency_score = 50  # Default
        if self.last_used:
            try:
                last_used_dt = datetime.fromisoformat(self.last_used)
                days_ago = (datetime.utcnow() - last_used_dt).days
                if days_ago <= 1:
                    recency_score = 100
                elif days_ago <= 7:
                    recency_score = 80
                elif days_ago <= 30:
                    recency_score = 60
                else:
                    recency_score = 40
            except:
                pass
        
        # Calculate weighted score
        health = (
            success_score * success_weight +
            speed_score * speed_weight +
            recency_score * recency_weight
        )
        
        return round(health, 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "selector": self.selector,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "total_response_time": round(self.total_response_time, 4),
            "avg_response_time": round(self.avg_response_time, 4),
            "min_response_time": round(self.min_response_time, 4) if self.min_response_time != float('inf') else 0,
            "max_response_time": round(self.max_response_time, 4),
            "success_rate": round(self.success_rate, 4),
            "health_score": self.health_score,
            "total_uses": self.total_uses,
            "last_used": self.last_used,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "healed_at": self.healed_at,
            "method": self.method,
            "version": self.version,
            "promoted": self.promoted
        }


# =============================================================================
# UNIVERSAL SELECTOR CACHE
# =============================================================================

class SelectorCache:
    """
    Universal file-based selector cache with performance analytics
    
    🚀 Features:
    - Persistent storage in JSON file
    - Auto-creates cache directory
    - Memory + file cache for speed
    - Performance tracking per selector
    - Cross-platform analytics
    - Health scoring
    - Recommendations engine
    - Thread-safe operations
    
    Usage:
        cache = SelectorCache()
        
        # Save healed selector
        cache.save("amazon", "product_title", "#productTitle")
        
        # Get cached selector
        selector = cache.get("amazon", "product_title")
        
        # Record performance
        cache.record_performance("amazon", "product_title", success=True, response_time=0.5)
        
        # Get analytics
        report = cache.get_performance_report("amazon")
    """
    
    def __init__(self, cache_dir: str = "cache"):
        """
        Initialize selector cache
        
        Args:
            cache_dir: Directory for cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "healed_selectors.json"
        self.performance_file = self.cache_dir / "selector_performance.json"
        self.analytics_file = self.cache_dir / "selector_analytics.json"
        
        # In-memory cache
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._performance: Dict[str, Dict[str, SelectorPerformance]] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Initialize
        self._initialize()
    
    def _initialize(self):
        """Create cache directory and load existing cache"""
        try:
            # Create cache directory
            self.cache_dir.mkdir(exist_ok=True)
            
            # Load selector cache
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                logger.info(f"📂 Loaded selector cache: {len(self._cache)} platforms")
            else:
                self._cache = {}
                self._save_to_file()
                logger.info("📂 Created new selector cache file")
            
            # Load performance cache
            if self.performance_file.exists():
                with open(self.performance_file, 'r', encoding='utf-8') as f:
                    perf_data = json.load(f)
                    # Convert to SelectorPerformance objects
                    for platform, fields in perf_data.items():
                        self._performance[platform] = {}
                        for field, data in fields.items():
                            self._performance[platform][field] = SelectorPerformance(
                                selector=data.get("selector", ""),
                                success_count=data.get("success_count", 0),
                                fail_count=data.get("fail_count", 0),
                                total_response_time=data.get("total_response_time", 0.0),
                                avg_response_time=data.get("avg_response_time", 0.0),
                                min_response_time=data.get("min_response_time", float('inf')),
                                max_response_time=data.get("max_response_time", 0.0),
                                last_used=data.get("last_used"),
                                last_success=data.get("last_success"),
                                last_failure=data.get("last_failure"),
                                healed_at=data.get("healed_at"),
                                method=data.get("method", "unknown"),
                                version=data.get("version", 1),
                                promoted=data.get("promoted", False)
                            )
                logger.info(f"📊 Loaded performance data: {len(self._performance)} platforms")
            else:
                self._performance = {}
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Cache file corrupted: {e}")
            self._cache = {}
            self._performance = {}
            self._save_to_file()
        except Exception as e:
            logger.error(f"❌ Cache initialization error: {e}")
            self._cache = {}
            self._performance = {}
    
    # =========================================================================
    # FILE I/O (Thread-Safe)
    # =========================================================================
    
    def _save_to_file(self):
        """Persist cache to JSON file (atomic write)"""
        with self._lock:
            try:
                # Write to temp file first (atomic)
                temp_file = self.cache_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(self._cache, f, indent=2, ensure_ascii=False)
                
                # Rename to actual file (atomic on most systems)
                temp_file.replace(self.cache_file)
                
            except Exception as e:
                logger.error(f"❌ Failed to save cache: {e}")
    
    def _save_performance_to_file(self):
        """Persist performance data to JSON file"""
        with self._lock:
            try:
                # Convert SelectorPerformance objects to dicts
                perf_data = {}
                for platform, fields in self._performance.items():
                    perf_data[platform] = {}
                    for field, perf in fields.items():
                        perf_data[platform][field] = perf.to_dict()
                
                # Atomic write
                temp_file = self.performance_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(perf_data, f, indent=2, ensure_ascii=False)
                
                temp_file.replace(self.performance_file)
                
            except Exception as e:
                logger.error(f"❌ Failed to save performance data: {e}")
    
    # =========================================================================
    # BASIC CRUD OPERATIONS
    # =========================================================================
    
    def get(self, platform: str, selector_name: str) -> Optional[str]:
        """
        Get cached selector
        
        Args:
            platform: Platform name (amazon, flipkart, etc.)
            selector_name: Selector/field name
        
        Returns:
            CSS selector string or None
        """
        with self._lock:
            platform = platform.lower()
            platform_cache = self._cache.get(platform, {})
            selector_data = platform_cache.get(selector_name, {})
            
            if isinstance(selector_data, dict):
                return selector_data.get("selector")
            elif isinstance(selector_data, str):
                return selector_data
            
            return None
    
    def get_with_metadata(self, platform: str, selector_name: str) -> Optional[Dict[str, Any]]:
        """
        Get cached selector with full metadata
        
        Args:
            platform: Platform name
            selector_name: Selector/field name
        
        Returns:
            Dictionary with selector and metadata
        """
        with self._lock:
            platform = platform.lower()
            platform_cache = self._cache.get(platform, {})
            selector_data = platform_cache.get(selector_name)
            
            if selector_data is None:
                return None
            
            if isinstance(selector_data, str):
                return {"selector": selector_data}
            
            return selector_data
    
    def get_all(self, platform: str) -> Dict[str, Any]:
        """
        Get all cached selectors for a platform
        
        Args:
            platform: Platform name
        
        Returns:
            Dictionary of selector_name -> selector/data
        """
        with self._lock:
            platform = platform.lower()
            return self._cache.get(platform, {}).copy()
    
    def save(
        self,
        platform: str,
        selector_name: str,
        selector: str,
        method: str = "healed"
    ):
        """
        Save healed selector to cache
        
        Args:
            platform: Platform name
            selector_name: Selector/field name
            selector: CSS selector string
            method: How selector was obtained (healed, ai_generated, manual, promoted)
        """
        with self._lock:
            platform = platform.lower()
            
            if platform not in self._cache:
                self._cache[platform] = {}
            
            # Get existing data for version tracking
            existing = self._cache[platform].get(selector_name, {})
            current_version = existing.get("version", 0) if isinstance(existing, dict) else 0
            
            # Check if selector changed
            old_selector = existing.get("selector") if isinstance(existing, dict) else existing
            is_new_selector = old_selector != selector
            
            # Build new entry
            self._cache[platform][selector_name] = {
                "selector": selector,
                "healed_at": datetime.utcnow().isoformat(),
                "method": method,
                "version": current_version + 1 if is_new_selector else current_version,
                "success_count": existing.get("success_count", 0) if isinstance(existing, dict) else 0,
                "fail_count": existing.get("fail_count", 0) if isinstance(existing, dict) else 0,
                "promoted": method == "promoted"
            }
            
            # Archive old selector if changed
            if is_new_selector and old_selector:
                self._archive_selector(platform, selector_name, old_selector, current_version)
            
            self._save_to_file()
            logger.debug(f"💾 Cached selector: {platform}.{selector_name} = {selector[:50]}...")
    
    def _archive_selector(
        self,
        platform: str,
        selector_name: str,
        old_selector: str,
        version: int
    ):
        """Archive old selector version"""
        try:
            archive_file = self.cache_dir / f"{platform}_selector_archive.json"
            
            if archive_file.exists():
                with open(archive_file, 'r') as f:
                    archive = json.load(f)
            else:
                archive = {}
            
            if selector_name not in archive:
                archive[selector_name] = []
            
            archive[selector_name].append({
                "selector": old_selector,
                "version": version,
                "archived_at": datetime.utcnow().isoformat()
            })
            
            # Keep only last 10 versions
            archive[selector_name] = archive[selector_name][-10:]
            
            with open(archive_file, 'w') as f:
                json.dump(archive, f, indent=2)
                
        except Exception as e:
            logger.debug(f"Archive error (non-critical): {e}")
    
    # =========================================================================
    # PERFORMANCE TRACKING
    # =========================================================================
    
    def record_success(self, platform: str, selector_name: str):
        """
        Record successful selector use
        
        Args:
            platform: Platform name
            selector_name: Selector/field name
        """
        with self._lock:
            platform = platform.lower()
            
            if platform in self._cache and selector_name in self._cache[platform]:
                data = self._cache[platform][selector_name]
                if isinstance(data, dict):
                    data["success_count"] = data.get("success_count", 0) + 1
                    data["last_success"] = datetime.utcnow().isoformat()
                    self._save_to_file()
    
    def record_failure(self, platform: str, selector_name: str):
        """
        Record failed selector use
        
        Args:
            platform: Platform name
            selector_name: Selector/field name
        """
        with self._lock:
            platform = platform.lower()
            
            if platform in self._cache and selector_name in self._cache[platform]:
                data = self._cache[platform][selector_name]
                if isinstance(data, dict):
                    data["fail_count"] = data.get("fail_count", 0) + 1
                    data["last_failure"] = datetime.utcnow().isoformat()
                    self._save_to_file()
    
    def record_performance(
        self,
        platform: str,
        selector_name: str,
        success: bool,
        response_time: float = 0.0
    ):
        """
        Record detailed selector performance metrics
        
        Args:
            platform: Platform name
            selector_name: Selector/field name
            success: Whether extraction succeeded
            response_time: Time taken for extraction (seconds)
        """
        with self._lock:
            platform = platform.lower()
            now = datetime.utcnow().isoformat()
            
            # Initialize platform performance
            if platform not in self._performance:
                self._performance[platform] = {}
            
            # Get or create performance entry
            if selector_name not in self._performance[platform]:
                # Get selector from cache
                selector = self.get(platform, selector_name) or ""
                self._performance[platform][selector_name] = SelectorPerformance(
                    selector=selector,
                    healed_at=now
                )
            
            perf = self._performance[platform][selector_name]
            
            # Update metrics
            perf.last_used = now
            
            if success:
                perf.success_count += 1
                perf.last_success = now
            else:
                perf.fail_count += 1
                perf.last_failure = now
            
            if response_time > 0:
                perf.total_response_time += response_time
                perf.avg_response_time = perf.total_response_time / perf.total_uses
                
                if response_time < perf.min_response_time:
                    perf.min_response_time = response_time
                if response_time > perf.max_response_time:
                    perf.max_response_time = response_time
            
            # Also update basic cache
            if success:
                self.record_success(platform, selector_name)
            else:
                self.record_failure(platform, selector_name)
            
            # Save performance data periodically (every 10 uses)
            if perf.total_uses % 10 == 0:
                self._save_performance_to_file()
    
    # =========================================================================
    # ANALYTICS & REPORTING
    # =========================================================================
    
    def get_performance_report(self, platform: str) -> Dict[str, Any]:
        """
        Get comprehensive performance report for a platform
        
        Args:
            platform: Platform name
        
        Returns:
            Dictionary with performance analytics
        """
        with self._lock:
            platform = platform.lower()
            platform_cache = self._cache.get(platform, {})
            platform_perf = self._performance.get(platform, {})
            
            report = {
                "platform": platform,
                "total_selectors": len(platform_cache),
                "selectors": {},
                "summary": {
                    "avg_success_rate": 0.0,
                    "avg_response_time_ms": 0.0,
                    "total_uses": 0,
                    "total_successes": 0,
                    "total_failures": 0,
                    "best_selector": None,
                    "worst_selector": None,
                    "slowest_selector": None,
                    "fastest_selector": None,
                    "health_score": 0.0
                },
                "recommendations": []
            }
            
            success_rates = []
            response_times = []
            health_scores = []
            
            for name, data in platform_cache.items():
                if not isinstance(data, dict):
                    continue
                
                success_count = data.get("success_count", 0)
                fail_count = data.get("fail_count", 0)
                total = success_count + fail_count
                success_rate = success_count / total if total > 0 else 0.0
                
                # Get performance data
                perf = platform_perf.get(name)
                avg_response_time = perf.avg_response_time if perf else 0.0
                health_score = perf.health_score if perf else 50.0
                
                selector_info = {
                    "selector": data.get("selector", "")[:50] + "..." if len(data.get("selector", "")) > 50 else data.get("selector", ""),
                    "success_rate": round(success_rate * 100, 1),
                    "total_uses": total,
                    "success_count": success_count,
                    "fail_count": fail_count,
                    "avg_response_time_ms": round(avg_response_time * 1000, 2),
                    "health_score": health_score,
                    "method": data.get("method", "unknown"),
                    "version": data.get("version", 1),
                    "healed_at": data.get("healed_at"),
                    "last_success": data.get("last_success"),
                    "last_failure": data.get("last_failure"),
                    "promoted": data.get("promoted", False)
                }
                
                report["selectors"][name] = selector_info
                
                if total > 0:
                    success_rates.append((name, success_rate))
                    health_scores.append(health_score)
                    report["summary"]["total_uses"] += total
                    report["summary"]["total_successes"] += success_count
                    report["summary"]["total_failures"] += fail_count
                
                if avg_response_time > 0:
                    response_times.append((name, avg_response_time))
            
            # Calculate summary statistics
            if success_rates:
                report["summary"]["avg_success_rate"] = round(
                    sum(r[1] for r in success_rates) / len(success_rates) * 100, 1
                )
                
                # Find best/worst
                sorted_by_success = sorted(success_rates, key=lambda x: x[1], reverse=True)
                report["summary"]["best_selector"] = sorted_by_success[0][0] if sorted_by_success else None
                report["summary"]["worst_selector"] = sorted_by_success[-1][0] if sorted_by_success else None
            
            if response_times:
                report["summary"]["avg_response_time_ms"] = round(
                    sum(r[1] for r in response_times) / len(response_times) * 1000, 2
                )
                
                # Find slowest/fastest
                sorted_by_time = sorted(response_times, key=lambda x: x[1])
                report["summary"]["fastest_selector"] = sorted_by_time[0][0] if sorted_by_time else None
                report["summary"]["slowest_selector"] = sorted_by_time[-1][0] if sorted_by_time else None
            
            if health_scores:
                report["summary"]["health_score"] = round(sum(health_scores) / len(health_scores), 1)
            
            # Generate recommendations
            report["recommendations"] = self._generate_recommendations(platform, report)
            
            return report
    
    def _generate_recommendations(self, platform: str, report: Dict[str, Any]) -> List[str]:
        """Generate optimization recommendations based on performance data"""
        recommendations = []
        
        # Check overall success rate
        avg_success = report["summary"].get("avg_success_rate", 0)
        if avg_success < 70:
            recommendations.append(
                f"⚠️ Low overall success rate ({avg_success}%). "
                f"Consider re-healing selectors or checking if website structure changed."
            )
        elif avg_success < 85:
            recommendations.append(
                f"🔶 Success rate could be improved ({avg_success}%). "
                f"Review failing selectors: {report['summary'].get('worst_selector')}"
            )
        
        # Check response times
        avg_time = report["summary"].get("avg_response_time_ms", 0)
        if avg_time > 2000:
            recommendations.append(
                f"🐌 Slow average response time ({avg_time}ms). "
                f"Slowest selector: {report['summary'].get('slowest_selector')}"
            )
        
        # Check for dead selectors
        dead_selectors = []
        for name, data in report.get("selectors", {}).items():
            if data.get("success_rate", 100) < 30 and data.get("total_uses", 0) >= 5:
                dead_selectors.append(name)
        
        if dead_selectors:
            recommendations.append(
                f"💀 {len(dead_selectors)} selectors have very low success rate: "
                f"{', '.join(dead_selectors[:3])}{'...' if len(dead_selectors) > 3 else ''}"
            )
        
        # Check for unused selectors
        unused_selectors = []
        for name, data in report.get("selectors", {}).items():
            if data.get("total_uses", 0) == 0:
                unused_selectors.append(name)
        
        if unused_selectors and len(unused_selectors) < 5:
            recommendations.append(
                f"📭 {len(unused_selectors)} selectors never used: {', '.join(unused_selectors)}"
            )
        
        # Check health score
        health_score = report["summary"].get("health_score", 50)
        if health_score >= 90:
            recommendations.append("✅ Excellent health! All selectors performing well.")
        elif health_score >= 75:
            recommendations.append("👍 Good health. Minor optimizations possible.")
        elif health_score >= 50:
            recommendations.append("⚠️ Average health. Review underperforming selectors.")
        else:
            recommendations.append("🚨 Poor health! Immediate attention needed.")
        
        return recommendations
    
    def get_cross_platform_report(self) -> Dict[str, Any]:
        """
        Get performance report across ALL platforms
        
        Returns:
            Dictionary with cross-platform analytics
        """
        with self._lock:
            report = {
                "total_platforms": len(self._cache),
                "platforms": {},
                "global_summary": {
                    "total_selectors": 0,
                    "total_uses": 0,
                    "avg_success_rate": 0.0,
                    "avg_health_score": 0.0,
                    "best_platform": None,
                    "worst_platform": None
                },
                "recommendations": []
            }
            
            platform_health = {}
            
            for platform in self._cache.keys():
                platform_report = self.get_performance_report(platform)
                report["platforms"][platform] = {
                    "total_selectors": platform_report["total_selectors"],
                    "success_rate": platform_report["summary"]["avg_success_rate"],
                    "health_score": platform_report["summary"]["health_score"],
                    "total_uses": platform_report["summary"]["total_uses"]
                }
                
                report["global_summary"]["total_selectors"] += platform_report["total_selectors"]
                report["global_summary"]["total_uses"] += platform_report["summary"]["total_uses"]
                
                platform_health[platform] = platform_report["summary"]["health_score"]
            
            # Calculate averages
            if platform_health:
                report["global_summary"]["avg_health_score"] = round(
                    sum(platform_health.values()) / len(platform_health), 1
                )
                report["global_summary"]["best_platform"] = max(platform_health, key=platform_health.get)
                report["global_summary"]["worst_platform"] = min(platform_health, key=platform_health.get)
            
            # Global recommendations
            if report["global_summary"]["avg_health_score"] < 70:
                report["recommendations"].append(
                    "🚨 Overall system health is low. Review all platform selectors."
                )
            
            return report
    
    def get_best_selector(self, platform: str, field: str) -> Optional[Dict[str, Any]]:
        """
        Get the best performing selector for a field
        
        Args:
            platform: Platform name
            field: Field name
        
        Returns:
            Selector info with highest health score
        """
        with self._lock:
            platform = platform.lower()
            
            # Check performance data
            if platform in self._performance and field in self._performance[platform]:
                perf = self._performance[platform][field]
                if perf.health_score >= 70:
                    return {
                        "selector": perf.selector,
                        "health_score": perf.health_score,
                        "success_rate": perf.success_rate,
                        "avg_response_time": perf.avg_response_time
                    }
            
            # Fallback to cache
            selector = self.get(platform, field)
            if selector:
                return {"selector": selector, "health_score": 50.0}
            
            return None
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get overall cache statistics"""
        with self._lock:
            total_selectors = sum(len(p) for p in self._cache.values())
            total_perf_entries = sum(len(p) for p in self._performance.values())
            
            return {
                "platforms": list(self._cache.keys()),
                "total_platforms": len(self._cache),
                "total_selectors": total_selectors,
                "total_performance_entries": total_perf_entries,
                "cache_file": str(self.cache_file),
                "performance_file": str(self.performance_file),
                "cache_file_exists": self.cache_file.exists(),
                "performance_file_exists": self.performance_file.exists(),
                "cache_file_size_kb": round(self.cache_file.stat().st_size / 1024, 2) if self.cache_file.exists() else 0
            }
    
    def clear_platform(self, platform: str):
        """
        Clear all cached selectors for a platform
        
        Args:
            platform: Platform name
        """
        with self._lock:
            platform = platform.lower()
            
            if platform in self._cache:
                del self._cache[platform]
                self._save_to_file()
                logger.info(f"🗑️ Cleared cache for {platform}")
            
            if platform in self._performance:
                del self._performance[platform]
                self._save_performance_to_file()
                logger.info(f"🗑️ Cleared performance data for {platform}")
    
    def clear_all(self):
        """Clear all cached data"""
        with self._lock:
            self._cache = {}
            self._performance = {}
            self._save_to_file()
            self._save_performance_to_file()
            logger.info("🗑️ Cleared all cache and performance data")
    
    def export_to_json(self, filepath: str = None) -> str:
        """
        Export all cache data to JSON file
        
        Args:
            filepath: Output file path (default: cache/export_TIMESTAMP.json)
        
        Returns:
            Path to exported file
        """
        with self._lock:
            if filepath is None:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filepath = str(self.cache_dir / f"export_{timestamp}.json")
            
            export_data = {
                "exported_at": datetime.utcnow().isoformat(),
                "selectors": self._cache,
                "performance": {
                    platform: {
                        field: perf.to_dict()
                        for field, perf in fields.items()
                    }
                    for platform, fields in self._performance.items()
                },
                "stats": self.get_stats()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📤 Exported cache to {filepath}")
            return filepath
    
    def flush(self):
        """Force save all data to files"""
        with self._lock:
            self._save_to_file()
            self._save_performance_to_file()
            logger.debug("💾 Flushed all cache data to files")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_selector_cache: Optional[SelectorCache] = None
_cache_lock = threading.Lock()


def get_selector_cache() -> SelectorCache:
    """
    Get global selector cache instance (thread-safe singleton)
    
    Returns:
        SelectorCache instance
    """
    global _selector_cache
    
    if _selector_cache is None:
        with _cache_lock:
            # Double-check locking
            if _selector_cache is None:
                _selector_cache = SelectorCache()
    
    return _selector_cache


def reset_selector_cache():
    """Reset the global selector cache (for testing)"""
    global _selector_cache
    with _cache_lock:
        if _selector_cache is not None:
            _selector_cache.flush()
        _selector_cache = None
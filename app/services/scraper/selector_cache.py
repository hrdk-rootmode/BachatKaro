"""
Selector Cache - File-based storage for healed selectors
Works without database! Perfect for local development.

Author: DealHunt
Why: Self-healing saves selectors to JSON file when DB unavailable
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class SelectorCache:
    """
    File-based selector cache (no database required)
    
    Features:
    - Persistent storage in JSON file
    - Auto-creates cache directory
    - Memory + file cache for speed
    - Easy migration to database later
    
    Usage:
        cache = SelectorCache()
        
        # Save healed selector
        cache.save("amazon", "product_title", "#productTitle")
        
        # Get cached selector
        selector = cache.get("amazon", "product_title")
    """
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "healed_selectors.json"
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._initialize()
    
    def _initialize(self):
        """Create cache directory and load existing cache"""
        try:
            self.cache_dir.mkdir(exist_ok=True)
            
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                logger.info(f"Loaded selector cache: {len(self._cache)} platforms")
            else:
                self._cache = {}
                self._save_to_file()
                logger.info("Created new selector cache file")
        except Exception as e:
            logger.error(f"Cache initialization error: {e}")
            self._cache = {}
    
    def _save_to_file(self):
        """Persist cache to JSON file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def get(self, platform: str, selector_name: str) -> Optional[str]:
        """Get cached selector"""
        platform_cache = self._cache.get(platform.lower(), {})
        selector_data = platform_cache.get(selector_name, {})
        return selector_data.get("selector")
    
    def get_all(self, platform: str) -> Dict[str, str]:
        """Get all cached selectors for a platform"""
        platform_cache = self._cache.get(platform.lower(), {})
        return {
            name: data.get("selector")
            for name, data in platform_cache.items()
            if data.get("selector")
        }
    
    def save(
        self,
        platform: str,
        selector_name: str,
        selector: str,
        method: str = "healed"
    ):
        """Save healed selector to cache"""
        platform = platform.lower()
        
        if platform not in self._cache:
            self._cache[platform] = {}
        
        existing = self._cache[platform].get(selector_name, {})
        
        self._cache[platform][selector_name] = {
            "selector": selector,
            "healed_at": datetime.utcnow().isoformat(),
            "method": method,
            "success_count": existing.get("success_count", 0),
            "fail_count": existing.get("fail_count", 0)
        }
        
        self._save_to_file()
        logger.debug(f"Cached selector: {platform}.{selector_name} = {selector}")
    
    def record_success(self, platform: str, selector_name: str):
        """Record successful selector use"""
        platform = platform.lower()
        if platform in self._cache and selector_name in self._cache[platform]:
            self._cache[platform][selector_name]["success_count"] = \
                self._cache[platform][selector_name].get("success_count", 0) + 1
            self._save_to_file()
    
    def record_failure(self, platform: str, selector_name: str):
        """Record failed selector use"""
        platform = platform.lower()
        if platform in self._cache and selector_name in self._cache[platform]:
            self._cache[platform][selector_name]["fail_count"] = \
                self._cache[platform][selector_name].get("fail_count", 0) + 1
            self._save_to_file()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_selectors = sum(len(p) for p in self._cache.values())
        return {
            "platforms": list(self._cache.keys()),
            "total_selectors": total_selectors,
            "cache_file": str(self.cache_file),
            "file_exists": self.cache_file.exists()
        }
    
    def clear_platform(self, platform: str):
        """Clear all cached selectors for a platform"""
        platform = platform.lower()
        if platform in self._cache:
            del self._cache[platform]
            self._save_to_file()
            logger.info(f"Cleared cache for {platform}")


# Singleton instance
_selector_cache: Optional[SelectorCache] = None


def get_selector_cache() -> SelectorCache:
    """Get global selector cache instance"""
    global _selector_cache
    if _selector_cache is None:
        _selector_cache = SelectorCache()
    return _selector_cache
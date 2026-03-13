"""
Redis Cache Client - Auto-Connect Edition
Singleton pattern for connection pooling with automatic connection management
"""
import redis.asyncio as redis
from typing import Optional, Any
import json
import logging
from datetime import timedelta
from fastapi import Depends
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Async Redis client with helper methods
    Implements singleton pattern + AUTO-CONNECT
    """
    
    _instance: Optional['RedisClient'] = None
    _client: Optional[redis.Redis] = None
    _connecting: bool = False  # Prevent duplicate connection attempts
    
    def __new__(cls):
        """Singleton implementation"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def connect(self):
        """Initialize Redis connection pool"""
        if self._client is None and not self._connecting:
            self._connecting = True
            try:
                self._client = await redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
                logger.info("✅ Redis connected successfully")
            except Exception as e:
                logger.error(f"❌ Redis connection failed: {e}")
                self._client = None
            finally:
                self._connecting = False
    
    async def disconnect(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("🔌 Redis connection closed")
    
    async def _ensure_connected(self):
        """Auto-connect if not already connected"""
        if self._client is None:
            await self.connect()
    
    async def ping(self) -> bool:
        """Health check"""
        await self._ensure_connected()
        if self._client is None:
            return False
        
        try:
            return await self._client.ping()
        except Exception as e:
            logger.error(f"❌ Redis ping failed: {str(e)}")
            return False
    
    # =========================================================================
    # BASIC OPERATIONS
    # =========================================================================
    
    async def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        await self._ensure_connected()
        if self._client is None:
            logger.warning("Redis not available")
            return None
        
        try:
            return await self._client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {str(e)}")
            return None
    
    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None,
        ex: Optional[int] = None
    ) -> bool:
        """
        Set key-value pair with optional TTL
        
        Args:
            key: Cache key
            value: Value to store
            ttl: Time to live in seconds
        """
        await self._ensure_connected()
        if self._client is None:
            logger.warning("Redis not available")
            return False
        
        try:
            expiry = ex or ttl
            if expiry:
                return await self._client.setex(key, expiry, value)
            else:
                return await self._client.set(key, value)
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key"""
        await self._ensure_connected()
        if self._client is None:
            return False
        
        try:
            return await self._client.delete(key) > 0
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {str(e)}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        await self._ensure_connected()
        if self._client is None:
            return False
        
        try:
            return await self._client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {str(e)}")
            return False
    
    # =========================================================================
    # JSON OPERATIONS (For complex data)
    # =========================================================================
    
    async def get_json(self, key: str) -> Optional[Any]:
        """Get JSON value and parse"""
        await self._ensure_connected()
        if self._client is None:
            return None
        
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in key {key}")
                return None
        return None
    
    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Store Python object as JSON"""
        await self._ensure_connected()
        if self._client is None:
            return False
        
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, ttl)
        except Exception as e:
            logger.error(f"Redis SET_JSON error for key {key}: {str(e)}")
            return False
    
    # =========================================================================
    # COUNTER OPERATIONS
    # =========================================================================
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter"""
        await self._ensure_connected()
        if self._client is None:
            return 0
        
        try:
            return await self._client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis INCR error for key {key}: {str(e)}")
            return 0
    
    async def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement counter"""
        await self._ensure_connected()
        if self._client is None:
            return 0
        
        try:
            return await self._client.decrby(key, amount)
        except Exception as e:
            logger.error(f"Redis DECR error for key {key}: {str(e)}")
            return 0
    
    # =========================================================================
    # LIST OPERATIONS
    # =========================================================================
    
    async def push_to_list(self, key: str, *values: str) -> int:
        """Push values to list (left push)"""
        await self._ensure_connected()
        if self._client is None:
            return 0
        
        try:
            return await self._client.lpush(key, *values)
        except Exception as e:
            logger.error(f"Redis LPUSH error for key {key}: {str(e)}")
            return 0
    
    async def get_list(self, key: str, start: int = 0, end: int = -1) -> list:
        """Get list range"""
        await self._ensure_connected()
        if self._client is None:
            return []
        
        try:
            return await self._client.lrange(key, start, end)
        except Exception as e:
            logger.error(f"Redis LRANGE error for key {key}: {str(e)}")
            return []
    
    # =========================================================================
    # HASH OPERATIONS
    # =========================================================================
    
    async def set_hash(self, key: str, field: str, value: str) -> bool:
        """Set hash field"""
        await self._ensure_connected()
        if self._client is None:
            return False
        
        try:
            return await self._client.hset(key, field, value)
        except Exception as e:
            logger.error(f"Redis HSET error for key {key}: {str(e)}")
            return False
    
    async def get_hash(self, key: str, field: str) -> Optional[str]:
        """Get hash field"""
        await self._ensure_connected()
        if self._client is None:
            return None
        
        try:
            return await self._client.hget(key, field)
        except Exception as e:
            logger.error(f"Redis HGET error for key {key}: {str(e)}")
            return None
    
    async def get_all_hash(self, key: str) -> dict:
        """Get all hash fields"""
        await self._ensure_connected()
        if self._client is None:
            return {}
        
        try:
            return await self._client.hgetall(key)
        except Exception as e:
            logger.error(f"Redis HGETALL error for key {key}: {str(e)}")
            return {}
    
    # =========================================================================
    # PATTERN OPERATIONS
    # =========================================================================
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern
        WARNING: Use carefully in production
        """
        await self._ensure_connected()
        if self._client is None:
            return 0
        
        try:
            keys = await self._client.keys(pattern)
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis DELETE_PATTERN error for {pattern}: {str(e)}")
            return 0
    
    # =========================================================================
    # EXPIRY OPERATIONS
    # =========================================================================
    
    async def set_expiry(self, key: str, seconds: int) -> bool:
        """Set expiry on existing key"""
        await self._ensure_connected()
        if self._client is None:
            return False
        
        try:
            return await self._client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis EXPIRE error for key {key}: {str(e)}")
            return False
    
    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL (-1 if no expiry, -2 if key doesn't exist)"""
        await self._ensure_connected()
        if self._client is None:
            return -2
        
        try:
            return await self._client.ttl(key)
        except Exception as e:
            logger.error(f"Redis TTL error for key {key}: {str(e)}")
            return -2
    
    async def info(self) -> dict:
        """Get Redis server information"""
        await self._ensure_connected()
        if self._client is None:
            return {}
        
        try:
            return await self._client.info()
        except Exception as e:
            logger.error(f"Redis INFO error: {str(e)}")
            return {}

# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
redis_client = RedisClient()


# =============================================================================
# HELPER FUNCTIONS (For common patterns)
# =============================================================================

async def cache_search_result(query: str, results: list, ttl: int = 3600):
    """Cache search results for 1 hour"""
    import hashlib
    query_hash = hashlib.md5(query.lower().encode()).hexdigest()
    key = f"search:{query_hash}"
    await redis_client.set_json(key, results, ttl)


async def get_cached_search(query: str) -> Optional[list]:
    """Get cached search results"""
    import hashlib
    query_hash = hashlib.md5(query.lower().encode()).hexdigest()
    key = f"search:{query_hash}"
    return await redis_client.get_json(key)


async def increment_user_search_count(user_id: str, date: str) -> int:
    """
    Track daily search count for rate limiting
    Auto-expires at midnight
    """
    key = f"user_quota:{user_id}:{date}"
    count = await redis_client.increment(key)
    
    # Set expiry to end of day on first increment
    if count == 1:
        import datetime
        now = datetime.datetime.now()
        end_of_day = datetime.datetime.combine(
            now.date() + datetime.timedelta(days=1),
            datetime.time.min
        )
        seconds_until_midnight = int((end_of_day - now).total_seconds())
        await redis_client.set_expiry(key, seconds_until_midnight)
    
    return count


async def get_user_search_count(user_id: str, date: str) -> int:
    """Get current search count for user today"""
    key = f"user_quota:{user_id}:{date}"
    value = await redis_client.get(key)
    return int(value) if value else 0


async def get_redis() -> RedisClient:
    """
    FastAPI dependency - returns the global RedisClient singleton
    Ensures connection is established before yielding
    """
    client = redis_client
    if client._client is None:
        await client.connect()
    return client


# Export for type hints
RedisDependency = Depends(get_redis)
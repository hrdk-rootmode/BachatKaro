"""
Advanced Rate Limiter with Anti-Ban Protection
Features: Token bucket, exponential backoff, human-like patterns, circuit breaker

FIXED:
- Circuit breaker with exponential backoff recovery
- Quiet hours multiplier bug (was 0.3, now 3.0 for slower)
- Added circuit state inspection helpers
- Better recovery attempt tracking

Author: DealHunt
Safety Level: MAXIMUM - Designed to prevent ANY bans
"""

import logging
import asyncio
from datetime import datetime, timedelta, time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
import random
import hashlib
from enum import Enum

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & EXCEPTIONS
# =============================================================================

class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(self, platform: str, retry_after: int):
        self.platform = platform
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for {platform}. Retry after {retry_after}s")


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests (too many failures)
    HALF_OPEN = "half_open"  # Testing if service recovered


class ThreatLevel(str, Enum):
    """Threat level from platform"""
    SAFE = "safe"          # No detection
    WARNING = "warning"    # Captcha or rate limit warning
    BLOCKED = "blocked"    # IP blocked or banned


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RateLimitConfig:
    """Enhanced rate limit configuration per platform"""
    # Conservative limits (MUCH lower than platform allows)
    requests_per_minute: int = 15
    requests_per_hour: int = 200
    requests_per_day: int = 2000
    
    # Delays (LONGER for safety)
    min_delay_seconds: float = 3.0
    max_delay_seconds: float = 8.0
    
    # Backoff settings
    backoff_multiplier: float = 3.0
    max_backoff_seconds: float = 300.0
    min_backoff_seconds: float = 10.0
    
    # Circuit breaker - ✅ FIXED: Added recovery attempt tracking
    failure_threshold: int = 3
    recovery_timeout: int = 300  # Base timeout (5 minutes)
    max_recovery_timeout: int = 3600  # Max timeout (1 hour)
    half_open_max_calls: int = 1
    
    # Human-like behavior
    burst_size: int = 3
    burst_cooldown: int = 60
    
    # Time-based restrictions
    quiet_hours_start: time = time(2, 0)
    quiet_hours_end: time = time(6, 0)
    quiet_hours_multiplier: float = 3.0  # ✅ FIXED: Was 0.3 (made it faster), now 3.0 (slower)
    
    # Session management
    max_requests_per_session: int = 50
    session_cooldown: int = 600


@dataclass
class RequestMetrics:
    """Track request metrics for adaptive rate limiting"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    captcha_count: int = 0
    timeout_count: int = 0
    
    last_request_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    
    session_request_count: int = 0
    session_start_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def needs_session_rotation(self) -> bool:
        """Check if session needs rotation"""
        return self.session_request_count >= 50


@dataclass
class CircuitBreaker:
    """Circuit breaker for automatic failure handling with exponential backoff"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    half_open_successes: int = 0
    recovery_attempts: int = 0  # ✅ NEW: Track recovery attempts
    
    def can_request(self, config: RateLimitConfig) -> Tuple[bool, Optional[str]]:
        """Check if request is allowed with exponential backoff"""
        now = datetime.utcnow()
        
        if self.state == CircuitState.CLOSED:
            return True, None
        
        if self.state == CircuitState.OPEN:
            if self.opened_at:
                # ✅ FIXED: Exponential backoff - 5min, 10min, 20min, 40min, 60min (max)
                recovery_backoff = min(
                    config.recovery_timeout * (2 ** min(self.recovery_attempts, 4)),
                    config.max_recovery_timeout
                )
                
                elapsed = (now - self.opened_at).total_seconds()
                if elapsed >= recovery_backoff:
                    # Move to half-open
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_successes = 0
                    self.recovery_attempts += 1
                    logger.info(
                        f"Circuit breaker moving to HALF_OPEN state "
                        f"(attempt {self.recovery_attempts}, waited {elapsed:.0f}s)"
                    )
                    return True, None
                
                remaining = int(recovery_backoff - elapsed)
                return False, f"Circuit open. Retry after {remaining}s (attempt {self.recovery_attempts})"
            
            return False, f"Circuit open. Retry after {config.recovery_timeout}s"
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_successes < config.half_open_max_calls:
                return True, None
            return False, "Circuit half-open, testing in progress"
        
        return False, "Unknown circuit state"
    
    def record_success(self) -> None:
        """Record successful request"""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= 1:
                # ✅ FIXED: Reset recovery attempts on successful recovery
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.recovery_attempts = 0
                logger.info("Circuit breaker CLOSED - service recovered")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    def record_failure(self, config: RateLimitConfig) -> None:
        """Record failed request"""
        now = datetime.utcnow()
        self.last_failure_time = now
        
        if self.state == CircuitState.HALF_OPEN:
            # Failure during testing - reopen circuit
            self.state = CircuitState.OPEN
            self.opened_at = now
            logger.warning(
                f"Circuit breaker RE-OPENED - service still down "
                f"(attempt {self.recovery_attempts})"
            )
            return
        
        if self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= config.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = now
                self.recovery_attempts = 0
                logger.error(
                    f"Circuit breaker OPENED after {self.failure_count} failures. "
                    f"Pausing for {config.recovery_timeout}s"
                )


# =============================================================================
# ADVANCED RATE LIMITER
# =============================================================================

class RateLimiter:
    """
    Military-grade rate limiter with anti-ban protection
    
    ✅ FIXES APPLIED:
    - Exponential backoff recovery
    - Fixed quiet-hours multiplier bug
    - Added circuit state inspection
    - Better recovery tracking
    """
    
    DEFAULT_CONFIGS: Dict[str, RateLimitConfig] = {
        "amazon": RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=150,
            requests_per_day=1500,
            min_delay_seconds=5.0,
            max_delay_seconds=12.0,
            failure_threshold=2,
            burst_size=max(8, int(getattr(settings, "DAILY_SCRAPE_AMAZON_BURST_SIZE", 8))),
            burst_cooldown=max(75, int(getattr(settings, "DAILY_SCRAPE_AMAZON_BURST_COOLDOWN_SECONDS", 90)))
        ),
        "flipkart": RateLimitConfig(
            requests_per_minute=12,
            requests_per_hour=180,
            requests_per_day=1800,
            min_delay_seconds=3.0,
            max_delay_seconds=8.0,
            failure_threshold=3
        ),
        "meesho": RateLimitConfig(
            requests_per_minute=15,
            requests_per_hour=200,
            requests_per_day=2000,
            min_delay_seconds=2.5,
            max_delay_seconds=7.0,
            failure_threshold=3
        ),
        "myntra": RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=150,
            requests_per_day=1500,
            min_delay_seconds=4.0,
            max_delay_seconds=9.0,
            failure_threshold=2
        ),
        "nykaa": RateLimitConfig(
            requests_per_minute=9,
            requests_per_hour=130,
            requests_per_day=1200,
            min_delay_seconds=4.5,
            max_delay_seconds=10.0,
            failure_threshold=2
        ),
        "croma": RateLimitConfig(
            requests_per_minute=8,
            requests_per_hour=110,
            requests_per_day=1000,
            min_delay_seconds=5.0,
            max_delay_seconds=11.0,
            failure_threshold=2
        )
    }
    
    def __init__(self, redis_client: Optional[Redis] = None):
        """Initialize advanced rate limiter"""
        self.redis = redis_client
        
        self._metrics: Dict[str, RequestMetrics] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._last_request_time: Dict[str, datetime] = {}
        self._burst_counters: Dict[str, List[datetime]] = {}
        self._backoff_until: Dict[str, datetime] = {}
        
        self._session_ids: Dict[str, str] = {}
        self._session_start: Dict[str, datetime] = {}
        
        logger.info("Advanced rate limiter initialized")
    
    def get_config(self, platform: str) -> RateLimitConfig:
        """Get rate limit config for platform"""
        return self.DEFAULT_CONFIGS.get(platform.lower(), RateLimitConfig())
    
    def _get_metrics(self, platform: str) -> RequestMetrics:
        """Get or create metrics for platform"""
        if platform not in self._metrics:
            self._metrics[platform] = RequestMetrics(session_start_time=datetime.utcnow())
        return self._metrics[platform]
    
    def _get_circuit_breaker(self, platform: str) -> CircuitBreaker:
        """Get or create circuit breaker for platform"""
        if platform not in self._circuit_breakers:
            self._circuit_breakers[platform] = CircuitBreaker()
        return self._circuit_breakers[platform]
    
    # ✅ NEW: Helper methods for circuit state inspection
    def get_circuit_state(self, platform: str) -> Dict[str, Any]:
        """Get current circuit breaker state for inspection"""
        circuit = self._get_circuit_breaker(platform)
        config = self.get_config(platform)
        
        can_request, reason = circuit.can_request(config)
        
        return {
            "state": circuit.state.value,
            "can_request": can_request,
            "reason": reason,
            "failure_count": circuit.failure_count,
            "recovery_attempts": circuit.recovery_attempts,
            "opened_at": circuit.opened_at.isoformat() if circuit.opened_at else None,
            "last_failure": circuit.last_failure_time.isoformat() if circuit.last_failure_time else None
        }
    
    def is_circuit_open(self, platform: str) -> bool:
        """Check if circuit is open (blocking requests)"""
        circuit = self._get_circuit_breaker(platform)
        return circuit.state == CircuitState.OPEN
    
    async def acquire(self, platform: str, priority: str = "normal") -> None:
        """Acquire permission to make request"""
        platform = platform.lower()
        config = self.get_config(platform)
        metrics = self._get_metrics(platform)
        circuit = self._get_circuit_breaker(platform)
        
        # 1. CHECK CIRCUIT BREAKER
        can_request, reason = circuit.can_request(config)
        if not can_request:
            logger.warning(f"{platform}: Circuit breaker blocked - {reason}")
            raise RateLimitExceeded(platform, config.recovery_timeout)
        
        # 2. CHECK IF IN BACKOFF
        if platform in self._backoff_until:
            if datetime.utcnow() < self._backoff_until[platform]:
                wait_time = (self._backoff_until[platform] - datetime.utcnow()).total_seconds()
                logger.debug(f"{platform}: Still in backoff ({wait_time:.1f}s remaining)")
                raise RateLimitExceeded(platform, int(wait_time) + 1)
        
        # 3. CHECK SESSION ROTATION
        if metrics.needs_session_rotation:
            logger.info(f"{platform}: Session rotation needed")
            await self._rotate_session(platform, config)
        
        # 4. CHECK RATE LIMITS
        if self.redis:
            await self._check_redis_limits(platform, config)
        else:
            await self._check_local_limits(platform, config)
        
        # 5. CHECK BURST PREVENTION
        await self._check_burst_limit(platform, config)
        
        # 6. ENFORCE HUMAN-LIKE DELAY
        delay = await self._calculate_delay(platform, config, priority)
        
        # 7. CHECK TIME-OF-DAY - ✅ FIXED: multiplier now slows down correctly
        if self._is_quiet_hours():
            delay *= config.quiet_hours_multiplier  # Now 3.0 (slower), was 0.3 (faster - bug!)
            logger.debug(f"{platform}: Quiet hours - delay increased to {delay:.1f}s")
        
        # 8. ADD RANDOM JITTER
        jitter = random.uniform(-0.3, 0.5) * delay
        delay += jitter
        
        # Wait if needed
        if delay > 0:
            logger.debug(f"{platform}: Waiting {delay:.2f}s before request")
            await asyncio.sleep(delay)
        
        # 9. RECORD REQUEST TIME
        now = datetime.utcnow()
        self._last_request_time[platform] = now
        metrics.last_request_time = now
        metrics.total_requests += 1
        metrics.session_request_count += 1
        
        # 10. UPDATE BURST COUNTER
        if platform not in self._burst_counters:
            self._burst_counters[platform] = []
        self._burst_counters[platform].append(now)
        
        logger.debug(
            f"{platform}: Request #{metrics.total_requests} authorized "
            f"(session: {metrics.session_request_count}/{config.max_requests_per_session})"
        )
    
    async def _check_redis_limits(self, platform: str, config: RateLimitConfig) -> None:
        """Check and update Redis-based rate limits"""
        now = datetime.utcnow()
        
        # Per-minute limit
        minute_key = f"rate:{platform}:min:{now.strftime('%Y%m%d%H%M')}"
        minute_count = await self.redis.incr(minute_key)
        
        if minute_count == 1:
            await self.redis.expire(minute_key, 60)
        
        if minute_count > config.requests_per_minute:
            wait_seconds = 60 - now.second + random.randint(5, 15)
            logger.warning(
                f"{platform}: Per-minute limit reached ({minute_count}/{config.requests_per_minute})"
            )
            raise RateLimitExceeded(platform, wait_seconds)
        
        # Per-hour limit
        hour_key = f"rate:{platform}:hour:{now.strftime('%Y%m%d%H')}"
        hour_count = await self.redis.incr(hour_key)
        
        if hour_count == 1:
            await self.redis.expire(hour_key, 3600)
        
        if hour_count > config.requests_per_hour:
            wait_seconds = 3600 - (now.minute * 60 + now.second) + random.randint(30, 120)
            logger.error(
                f"{platform}: Per-hour limit reached ({hour_count}/{config.requests_per_hour})"
            )
            raise RateLimitExceeded(platform, wait_seconds)
        
        # Per-day limit
        day_key = f"rate:{platform}:day:{now.strftime('%Y%m%d')}"
        day_count = await self.redis.incr(day_key)
        
        if day_count == 1:
            await self.redis.expire(day_key, 86400)
        
        if day_count > config.requests_per_day:
            wait_seconds = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
            logger.critical(
                f"{platform}: Daily limit reached ({day_count}/{config.requests_per_day})"
            )
            raise RateLimitExceeded(platform, wait_seconds)
    
    async def _check_local_limits(self, platform: str, config: RateLimitConfig) -> None:
        """Check local (in-memory) rate limits"""
        metrics = self._get_metrics(platform)
        
        if metrics.session_request_count >= config.max_requests_per_session:
            logger.warning(f"{platform}: Session limit reached, forcing rotation")
            raise RateLimitExceeded(platform, config.session_cooldown)
    
    async def _check_burst_limit(self, platform: str, config: RateLimitConfig) -> None:
        """Prevent burst requests"""
        if platform not in self._burst_counters:
            return
        
        now = datetime.utcnow()
        
        # Clean old entries
        self._burst_counters[platform] = [
            t for t in self._burst_counters[platform]
            if (now - t).total_seconds() < 30
        ]
        
        recent_count = len(self._burst_counters[platform])
        
        if recent_count >= config.burst_size:
            wait_time = config.burst_cooldown + random.randint(10, 30)
            logger.warning(
                f"{platform}: Burst limit reached ({recent_count}/{config.burst_size})"
            )
            raise RateLimitExceeded(platform, wait_time)
    
    async def _calculate_delay(
        self,
        platform: str,
        config: RateLimitConfig,
        priority: str = "normal"
    ) -> float:
        """Calculate delay before next request"""
        if platform not in self._last_request_time:
            return 0.0
        
        metrics = self._get_metrics(platform)
        elapsed = (datetime.utcnow() - self._last_request_time[platform]).total_seconds()
        
        min_delay = config.min_delay_seconds
        max_delay = config.max_delay_seconds
        
        # Adjust based on success rate
        success_rate = metrics.success_rate
        if success_rate < 50:
            min_delay *= 2.5
            max_delay *= 3.0
        elif success_rate < 80:
            min_delay *= 1.5
            max_delay *= 2.0
        
        # Adjust based on consecutive failures
        if metrics.consecutive_failures > 0:
            failure_multiplier = 1 + (metrics.consecutive_failures * 0.5)
            min_delay *= failure_multiplier
            max_delay *= failure_multiplier
        
        # Adjust based on priority
        if priority == "low":
            min_delay *= 1.5
            max_delay *= 1.5
        elif priority == "high":
            min_delay *= 0.8
            max_delay *= 0.8
        
        required_delay = random.uniform(min_delay, max_delay)
        remaining_delay = max(0, required_delay - elapsed)
        
        return remaining_delay
    
    def _is_quiet_hours(self) -> bool:
        """Check if current time is in quiet hours (2 AM - 6 AM IST)"""
        now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        current_time = now.time()
        
        if time(2, 0) <= current_time < time(6, 0):
            return True
        
        return False
    
    async def _rotate_session(self, platform: str, config: RateLimitConfig) -> None:
        """Rotate session to avoid detection"""
        metrics = self._get_metrics(platform)
        
        logger.info(f"{platform}: Rotating session after {metrics.session_request_count} requests")
        
        self._backoff_until[platform] = datetime.utcnow() + timedelta(
            seconds=config.session_cooldown
        )
        
        metrics.session_request_count = 0
        metrics.session_start_time = datetime.utcnow()
        
        session_id = hashlib.md5(
            f"{platform}_{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        self._session_ids[platform] = session_id
    
    async def record_success(
        self,
        platform: str,
        response_time_ms: Optional[int] = None
    ) -> None:
        """Record successful request"""
        platform = platform.lower()
        metrics = self._get_metrics(platform)
        circuit = self._get_circuit_breaker(platform)
        
        metrics.successful_requests += 1
        metrics.last_success_time = datetime.utcnow()
        metrics.consecutive_successes += 1
        metrics.consecutive_failures = 0
        
        circuit.record_success()
        
        if platform in self._backoff_until:
            del self._backoff_until[platform]
        
        logger.debug(
            f"{platform}: Request SUCCESS (total: {metrics.successful_requests}, "
            f"rate: {metrics.success_rate:.1f}%)"
        )
    
    async def record_failure(
        self,
        platform: str,
        threat_level: ThreatLevel = ThreatLevel.WARNING,
        error_type: str = "unknown"
    ) -> None:
        """Record failed request with adaptive backoff"""
        platform = platform.lower()
        config = self.get_config(platform)
        metrics = self._get_metrics(platform)
        circuit = self._get_circuit_breaker(platform)
        
        metrics.failed_requests += 1
        metrics.last_failure_time = datetime.utcnow()
        metrics.consecutive_failures += 1
        metrics.consecutive_successes = 0
        
        if error_type == "captcha":
            metrics.captcha_count += 1
        elif error_type == "timeout":
            metrics.timeout_count += 1
        
        circuit.record_failure(config)
        
        # Calculate backoff
        backoff_seconds = config.min_backoff_seconds
        
        if threat_level == ThreatLevel.BLOCKED:
            backoff_seconds = config.max_backoff_seconds
            logger.error(f"{platform}: BLOCKED! Backing off for {backoff_seconds}s")
        elif threat_level == ThreatLevel.WARNING:
            backoff_seconds = min(
                config.min_backoff_seconds * (config.backoff_multiplier ** metrics.consecutive_failures),
                config.max_backoff_seconds
            )
            logger.warning(f"{platform}: WARNING ({error_type}). Backoff: {backoff_seconds:.1f}s")
        else:
            backoff_seconds = config.min_backoff_seconds
        
        jitter = random.uniform(0.8, 1.3)
        backoff_seconds *= jitter
        
        self._backoff_until[platform] = datetime.utcnow() + timedelta(seconds=backoff_seconds)
        
        logger.info(
            f"{platform}: Request FAILED (consecutive: {metrics.consecutive_failures}, "
            f"backoff: {backoff_seconds:.1f}s, circuit: {circuit.state.value})"
        )
        
        if metrics.captcha_count >= 3:
            logger.critical(f"{platform}: Multiple captchas! Consider rotating proxy.")
    
    async def get_status(self, platform: str) -> Dict:
        """Get comprehensive rate limit status"""
        platform = platform.lower()
        config = self.get_config(platform)
        metrics = self._get_metrics(platform)
        circuit = self._get_circuit_breaker(platform)
        
        status = {
            "platform": platform,
            "config": {
                "requests_per_minute": config.requests_per_minute,
                "requests_per_hour": config.requests_per_hour,
                "min_delay": config.min_delay_seconds,
                "max_delay": config.max_delay_seconds
            },
            "metrics": {
                "total_requests": metrics.total_requests,
                "successful_requests": metrics.successful_requests,
                "failed_requests": metrics.failed_requests,
                "success_rate": round(metrics.success_rate, 2),
                "consecutive_failures": metrics.consecutive_failures,
                "captcha_count": metrics.captcha_count,
                "session_requests": metrics.session_request_count
            },
            "circuit_breaker": {
                "state": circuit.state.value,
                "failure_count": circuit.failure_count,
                "recovery_attempts": circuit.recovery_attempts,
                "is_healthy": circuit.state == CircuitState.CLOSED
            },
            "in_backoff": False,
            "backoff_remaining_seconds": 0,
            "in_quiet_hours": self._is_quiet_hours()
        }
        
        if platform in self._backoff_until:
            remaining = (self._backoff_until[platform] - datetime.utcnow()).total_seconds()
            if remaining > 0:
                status["in_backoff"] = True
                status["backoff_remaining_seconds"] = int(remaining)
        
        if self.redis:
            now = datetime.utcnow()
            minute_key = f"rate:{platform}:min:{now.strftime('%Y%m%d%H%M')}"
            hour_key = f"rate:{platform}:hour:{now.strftime('%Y%m%d%H')}"
            day_key = f"rate:{platform}:day:{now.strftime('%Y%m%d')}"
            
            minute_count = await self.redis.get(minute_key)
            hour_count = await self.redis.get(hour_key)
            day_count = await self.redis.get(day_key)
            
            status["redis_limits"] = {
                "requests_this_minute": int(minute_count or 0),
                "requests_this_hour": int(hour_count or 0),
                "requests_this_day": int(day_count or 0)
            }
        
        return status
    
    async def reset(self, platform: str) -> None:
        """Reset all tracking for platform"""
        platform = platform.lower()
        
        if platform in self._metrics:
            del self._metrics[platform]
        if platform in self._circuit_breakers:
            del self._circuit_breakers[platform]
        if platform in self._backoff_until:
            del self._backoff_until[platform]
        if platform in self._last_request_time:
            del self._last_request_time[platform]
        if platform in self._burst_counters:
            del self._burst_counters[platform]
        
        if self.redis:
            now = datetime.utcnow()
            await self.redis.delete(
                f"rate:{platform}:min:{now.strftime('%Y%m%d%H%M')}",
                f"rate:{platform}:hour:{now.strftime('%Y%m%d%H')}",
                f"rate:{platform}:day:{now.strftime('%Y%m%d')}",
                f"rate:backoff:{platform}"
            )
        
        logger.info(f"{platform}: Rate limiter fully reset")
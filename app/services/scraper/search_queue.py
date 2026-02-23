"""
URL Search Queue Manager
Handles concurrent URL searches with deduplication

Features:
- Request deduplication (same URL = 1 scrape)
- Multiple users wait for same result
- Priority queue (premium users first)
- Progress tracking
- Timeout handling
"""

import logging
import asyncio
import hashlib
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

from redis.asyncio import Redis

from app.models import User
from app.services.scraper.base import ProductData
from app.core.config import settings

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Search job status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class JobPriority(int, Enum):
    """Job priority levels"""
    LOW = 0       # Free users, non-urgent
    NORMAL = 1    # Free users, normal
    HIGH = 2      # Pro users
    URGENT = 3    # Premium users


@dataclass
class SearchJob:
    """Represents a URL search job"""
    job_id: str
    url: str
    user_id: str
    priority: JobPriority
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    waiters: List[asyncio.Future] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "user_id": self.user_id,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error
        }


class URLSearchQueue:
    """
    Manages concurrent URL searches with intelligent queuing
    
    Features:
    - Deduplication: Same URL only scraped once
    - Multiple waiters: Other requests wait for same job
    - Priority: Premium users processed first
    - Timeout: Jobs timeout after 60 seconds
    - Caching: Results cached in Redis
    
    Usage:
        queue = URLSearchQueue(redis_client)
        
        # Execute search (with deduplication)
        results = await queue.search_url(
            url="https://amazon.in/dp/B0CHX3TW6X",
            user=current_user,
            scrape_func=my_scrape_function
        )
    """
    
    # Configuration
    JOB_TIMEOUT_SECONDS = 60
    RESULT_CACHE_TTL = 3600  # 1 hour
    MAX_CONCURRENT_JOBS = 10
    
    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize queue manager
        
        Args:
            redis_client: Redis client for distributed state
        """
        self.redis = redis_client
        
        # In-memory tracking
        self._active_jobs: Dict[str, SearchJob] = {}
        self._job_lock = asyncio.Lock()
        
        # Semaphore for concurrent job limit
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_JOBS)
        
        logger.info("URLSearchQueue initialized")
    
    async def search_url(
        self,
        url: str,
        user: User,
        scrape_func: Callable,
        force_refresh: bool = False
    ) -> List[ProductData]:
        """
        Search by URL with queue management
        
        If URL already being scraped:
        - Wait for existing job to complete
        
        If new URL:
        - Start new scraping job
        - Other requests for same URL wait
        
        Args:
            url: Product URL to scrape
            user: Current user (for priority)
            scrape_func: Async function to perform actual scraping
            force_refresh: Skip cache and force new scrape
        
        Returns:
            List of ProductData (source + alternatives)
        """
        # Generate job key
        job_key = self._generate_job_key(url)
        
        # Check cache first (unless force refresh)
        if not force_refresh and self.redis:
            cached = await self._get_cached_result(job_key)
            if cached:
                logger.info(f"Cache HIT for URL search: {url[:50]}")
                return cached
        
        # Determine priority
        priority = self._get_user_priority(user)
        
        async with self._job_lock:
            # Check if job already exists
            if job_key in self._active_jobs:
                job = self._active_jobs[job_key]
                
                if job.status in [JobStatus.PENDING, JobStatus.IN_PROGRESS]:
                    logger.info(f"Joining existing job for URL: {url[:50]}")
                    return await self._wait_for_job(job)
            
            # Create new job
            job = SearchJob(
                job_id=job_key,
                url=url,
                user_id=str(user.id),
                priority=priority
            )
            self._active_jobs[job_key] = job
        
        # Execute job
        try:
            result = await self._execute_job(job, scrape_func)
            return result
        
        finally:
            # Cleanup
            async with self._job_lock:
                if job_key in self._active_jobs:
                    del self._active_jobs[job_key]
    
    async def _execute_job(
        self,
        job: SearchJob,
        scrape_func: Callable
    ) -> List[ProductData]:
        """Execute the actual scraping job"""
        async with self._semaphore:
            job.status = JobStatus.IN_PROGRESS
            job.started_at = datetime.utcnow()
            
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    scrape_func(job.url),
                    timeout=self.JOB_TIMEOUT_SECONDS
                )
                
                # Mark completed
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.result = result
                
                # Cache result
                if self.redis and result:
                    await self._cache_result(job.job_id, result)
                
                # Notify waiters
                self._notify_waiters(job, result)
                
                return result
            
            except asyncio.TimeoutError:
                job.status = JobStatus.TIMEOUT
                job.error = f"Job timed out after {self.JOB_TIMEOUT_SECONDS}s"
                logger.error(f"URL search timeout: {job.url[:50]}")
                
                self._notify_waiters(job, None, error=job.error)
                raise
            
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = str(e)
                logger.error(f"URL search failed: {job.url[:50]} - {e}")
                
                self._notify_waiters(job, None, error=str(e))
                raise
    
    async def _wait_for_job(self, job: SearchJob) -> List[ProductData]:
        """Wait for an existing job to complete"""
        # Create future for this waiter
        future = asyncio.get_event_loop().create_future()
        job.waiters.append(future)
        
        try:
            # Wait with timeout
            result = await asyncio.wait_for(
                future,
                timeout=self.JOB_TIMEOUT_SECONDS + 10  # Extra buffer
            )
            
            if isinstance(result, Exception):
                raise result
            
            return result
        
        except asyncio.TimeoutError:
            logger.error(f"Waiter timeout for job: {job.job_id}")
            raise
    
    def _notify_waiters(
        self,
        job: SearchJob,
        result: Optional[List[ProductData]],
        error: Optional[str] = None
    ) -> None:
        """Notify all waiters of job completion"""
        for future in job.waiters:
            if future.done():
                continue
            
            if error:
                future.set_exception(Exception(error))
            else:
                future.set_result(result)
        
        job.waiters.clear()
    
    def _generate_job_key(self, url: str) -> str:
        """Generate unique job key from URL"""
        # Normalize URL
        normalized = url.lower().strip()
        
        # Remove common tracking params
        normalized = self._remove_tracking_params(normalized)
        
        # Hash
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _remove_tracking_params(self, url: str) -> str:
        """Remove tracking parameters from URL"""
        import re
        from urllib.parse import urlparse, parse_qs, urlencode
        
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            # Remove tracking params
            tracking_keys = [
                'utm_source', 'utm_medium', 'utm_campaign', 'utm_term',
                'ref', 'gclid', 'fbclid', '_ga', 'tag'  # Keep affiliate tag separate
            ]
            
            filtered = {
                k: v[0] for k, v in params.items()
                if k.lower() not in tracking_keys
            }
            
            if filtered:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(filtered)}"
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        except Exception:
            return url
    
    def _get_user_priority(self, user: User) -> JobPriority:
        """Determine job priority based on user plan"""
        plan = user.plan.lower() if user.plan else "free"
        
        if plan == "premium":
            return JobPriority.URGENT
        elif plan == "pro":
            return JobPriority.HIGH
        else:
            return JobPriority.NORMAL
    
    async def _get_cached_result(self, job_key: str) -> Optional[List[ProductData]]:
        """Get cached result from Redis"""
        if not self.redis:
            return None
        
        try:
            cache_key = f"url_search:{job_key}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                data = json.loads(cached)
                
                # Convert back to ProductData
                from decimal import Decimal
                products = []
                for item in data:
                    item["current_price"] = Decimal(str(item["current_price"]))
                    if item.get("original_price"):
                        item["original_price"] = Decimal(str(item["original_price"]))
                    products.append(ProductData(**item))
                
                return products
        
        except Exception as e:
            logger.error(f"Cache read error: {e}")
        
        return None
    
    async def _cache_result(
        self,
        job_key: str,
        result: List[ProductData]
    ) -> None:
        """Cache result in Redis"""
        if not self.redis:
            return
        
        try:
            cache_key = f"url_search:{job_key}"
            
            # Convert ProductData to dict
            data = [p.to_dict() for p in result]
            
            await self.redis.setex(
                cache_key,
                self.RESULT_CACHE_TTL,
                json.dumps(data)
            )
            
            logger.debug(f"Cached URL search result: {job_key}")
        
        except Exception as e:
            logger.error(f"Cache write error: {e}")
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        async with self._job_lock:
            pending = sum(
                1 for j in self._active_jobs.values()
                if j.status == JobStatus.PENDING
            )
            in_progress = sum(
                1 for j in self._active_jobs.values()
                if j.status == JobStatus.IN_PROGRESS
            )
            
            return {
                "total_active_jobs": len(self._active_jobs),
                "pending": pending,
                "in_progress": in_progress,
                "max_concurrent": self.MAX_CONCURRENT_JOBS,
                "available_slots": self.MAX_CONCURRENT_JOBS - in_progress
            }
    
    async def cancel_job(self, job_key: str) -> bool:
        """Cancel a pending job"""
        async with self._job_lock:
            if job_key in self._active_jobs:
                job = self._active_jobs[job_key]
                
                if job.status == JobStatus.PENDING:
                    self._notify_waiters(job, None, error="Job cancelled")
                    del self._active_jobs[job_key]
                    return True
        
        return False


# Singleton instance
url_search_queue: Optional[URLSearchQueue] = None


def get_search_queue(redis_client: Redis) -> URLSearchQueue:
    """Get or create search queue singleton"""
    global url_search_queue
    
    if url_search_queue is None:
        url_search_queue = URLSearchQueue(redis_client)
    
    return url_search_queue
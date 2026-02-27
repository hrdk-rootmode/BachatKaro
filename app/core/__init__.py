"""
Core application modules
"""
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.redis_client import redis_client, get_redis
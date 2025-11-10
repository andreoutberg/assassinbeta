"""
Simple in-memory cache for API responses

Caches API responses to reduce database load for frequently accessed data.
TTL-based expiration ensures data stays reasonably fresh.
"""
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
import logging
import hashlib
import json

logger = logging.getLogger(__name__)


class SimpleCache:
    """
    Simple in-memory cache with TTL expiration
    
    Thread-safe for single-process deployment.
    For multi-process, consider Redis or Memcached.
    """
    
    def __init__(self):
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key in self.cache:
            value, expires_at = self.cache[key]
            if datetime.utcnow() < expires_at:
                self.hits += 1
                logger.debug(f"Cache HIT: {key}")
                return value
            else:
                # Expired, remove it
                del self.cache[key]
                logger.debug(f"Cache EXPIRED: {key}")
        
        self.misses += 1
        logger.debug(f"Cache MISS: {key}")
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int):
        """Set value in cache with TTL"""
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        self.cache[key] = (value, expires_at)
        logger.debug(f"Cache SET: {key} (TTL: {ttl_seconds}s)")
    
    def invalidate(self, key: str):
        """Remove key from cache"""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Cache INVALIDATE: {key}")
    
    def clear(self):
        """Clear entire cache"""
        self.cache.clear()
        logger.info("Cache CLEARED")
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_pct": round(hit_rate, 2)
        }


# Global cache instance
_cache = SimpleCache()


def get_cache() -> SimpleCache:
    """Get global cache instance"""
    return _cache


def cached(ttl_seconds: int = 60, key_func: Optional[Callable] = None):
    """
    Decorator to cache API endpoint responses
    
    Args:
        ttl_seconds: Time to live in seconds (default: 60)
        key_func: Optional function to generate cache key from args/kwargs
    
    Usage:
        @cached(ttl_seconds=30)
        async def get_trades():
            return await db.query(...)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default: hash function name + args + kwargs
                key_parts = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
                cache_key = hashlib.md5(key_parts.encode()).hexdigest()
            
            # Try to get from cache
            cached_value = _cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Cache miss - execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            _cache.set(cache_key, result, ttl_seconds)
            
            return result
        
        return wrapper
    return decorator

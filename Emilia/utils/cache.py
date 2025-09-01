"""
Simple in-memory cache for frequently accessed database data
"""
import time
import asyncio
from typing import Any, Dict, Optional, Callable
from Emilia import LOGGER
from functools import wraps

class SimpleCache:
    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = default_ttl
        
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        return time.time() > entry["expires"]
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if not self._is_expired(entry):
                return entry["value"]
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if ttl is None:
            ttl = self._default_ttl
        
        self._cache[key] = {
            "value": value,
            "expires": time.time() + ttl
        }
    
    def delete(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]
    
    def clear(self) -> None:
        self._cache.clear()
    
    def cleanup_expired(self) -> None:
        """Remove expired entries"""
        expired_keys = []
        for key, entry in self._cache.items():
            if self._is_expired(entry):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]

locks_cache = SimpleCache(default_ttl=120)  # 2 minutes for locks
admin_cache = SimpleCache(default_ttl=300)  # 5 minutes for admin status
blocklist_cache = SimpleCache(default_ttl=180)  # 3 minutes for blocklists
anonymous_admin_cache = SimpleCache(default_ttl=300)  # 5 minutes for anonymous admin checks
approvals_cache = SimpleCache(default_ttl=180)  # 3 minutes for user approvals per chat

def cached_db_call(cache_instance: SimpleCache, ttl: Optional[int] = None):
    """
    Decorator for caching database calls
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            cached_result = cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            result = await func(*args, **kwargs)
            
            cache_instance.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator

async def start_cache_cleanup():
    """Start periodic cache cleanup task"""
    while True:
        try:
            locks_cache.cleanup_expired()
            admin_cache.cleanup_expired()
            blocklist_cache.cleanup_expired()
            anonymous_admin_cache.cleanup_expired()
            approvals_cache.cleanup_expired()
        except Exception as e:
            LOGGER.error(f"Error during cache cleanup: {e}")
        
        await asyncio.sleep(60)  # Cleanup every minute

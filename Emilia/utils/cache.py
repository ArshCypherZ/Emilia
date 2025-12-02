"""
Multi-level cache implementation (L1 Memory + L2 Redis)
"""
import time
import asyncio
import pickle
import redis.asyncio as redis
from typing import Any, Dict, Optional, Callable
from functools import wraps
from Emilia import LOGGER

class MultiLevelCache:
    def __init__(self, redis_url: str, redis_password: Optional[str] = None, default_ttl: int = 300):
        self._l1_cache: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = default_ttl
        self._redis_url = redis_url
        self._redis_password = redis_password
        self._redis: Optional[redis.Redis] = None
        self._pubsub = None
        self._channel_name = "cache_invalidation"
        self._running = False

    async def start(self):
        if self._running:
            return
        
        try:
            self._redis = redis.from_url(self._redis_url, password=self._redis_password)
            await self._redis.ping()
            self._running = True
            asyncio.create_task(self._listen_for_invalidation())
            LOGGER.info("MultiLevelCache connected to Redis.")
        except Exception as e:
            LOGGER.error(f"Failed to connect to Redis: {e}. Falling back to L1 only.")
            self._redis = None

    async def stop(self):
        self._running = False
        if self._redis:
            await self._redis.close()
            LOGGER.info("MultiLevelCache disconnected from Redis.")

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        return time.time() > entry["expires"]

    async def get(self, key: str) -> Optional[Any]:
        # L1 Check
        if key in self._l1_cache:
            entry = self._l1_cache[key]
            if not self._is_expired(entry):
                return entry["value"]
            else:
                del self._l1_cache[key]
        
        # L2 Check
        if self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    value = pickle.loads(data)
                    # Populate L1
                    self._l1_cache[key] = {
                        "value": value,
                        "expires": time.time() + self._default_ttl
                    }
                    return value
            except Exception as e:
                LOGGER.error(f"Redis get error: {e}")
        
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if ttl is None:
            ttl = self._default_ttl
        
        # Update L1
        self._l1_cache[key] = {
            "value": value,
            "expires": time.time() + ttl
        }

        # Update L2
        if self._redis:
            try:
                data = pickle.dumps(value)
                await self._redis.set(key, data, ex=ttl)
                await self._redis.publish(self._channel_name, key)
            except Exception as e:
                LOGGER.error(f"Redis set error: {e}")

    async def delete(self, key: str) -> None:
        # Delete L1
        if key in self._l1_cache:
            del self._l1_cache[key]
        
        # Delete L2
        if self._redis:
            try:
                await self._redis.delete(key)
                await self._redis.publish(self._channel_name, key)
            except Exception as e:
                LOGGER.error(f"Redis delete error: {e}")

    async def clear(self) -> None:
        self._l1_cache.clear()
        if self._redis:
            try:
                await self._redis.flushdb()
                await self._redis.publish(self._channel_name, "__ALL__")
            except Exception as e:
                LOGGER.error(f"Redis clear error: {e}")

    async def _listen_for_invalidation(self):
        if not self._redis:
            return
        
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel_name)
        
        async for message in pubsub.listen():
            if not self._running:
                break
                
            if message["type"] == "message":
                key = message["data"].decode("utf-8")
                if key == "__ALL__":
                    self._l1_cache.clear()
                elif key in self._l1_cache:
                    # Invalidate L1
                    del self._l1_cache[key]

    def cleanup_expired(self) -> None:
        """Remove expired entries from L1"""
        expired_keys = []
        for key, entry in self._l1_cache.items():
            if self._is_expired(entry):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._l1_cache[key]

from Emilia.config import Config

locks_cache = MultiLevelCache(Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=120)
admin_cache = MultiLevelCache(Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=300)
blocklist_cache = MultiLevelCache(Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=180)
anonymous_admin_cache = MultiLevelCache(Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=300)
approvals_cache = MultiLevelCache(Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=180)

class SimpleCache(MultiLevelCache):
    def __init__(self, default_ttl: int = 300):
        super().__init__(Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl)

def cached_db_call(cache_instance: MultiLevelCache, ttl: Optional[int] = None):
    """
    Decorator for caching database calls
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            cached_result = await cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            result = await func(*args, **kwargs)
            
            await cache_instance.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator

async def start_cache_cleanup():
    """Start periodic cache cleanup task"""
    # Start all caches
    await locks_cache.start()
    await admin_cache.start()
    await blocklist_cache.start()
    await anonymous_admin_cache.start()
    await approvals_cache.start()

    while True:
        try:
            locks_cache.cleanup_expired()
            admin_cache.cleanup_expired()
            blocklist_cache.cleanup_expired()
            anonymous_admin_cache.cleanup_expired()
            approvals_cache.cleanup_expired()
        except Exception as e:
            LOGGER.error(f"Error during cache cleanup: {e}")
        
        await asyncio.sleep(60)
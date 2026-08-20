"""
Multi-level cache implementation (L1 Memory + L2 Redis)
"""

import asyncio
import time
import uuid
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Dict, Optional

import orjson
import redis.asyncio as redis

from Emilia import LOGGER
from Emilia.config import Config


class MultiLevelCache:
    # Class-level registry so lifecycle helpers (start/cleanup) can reach every
    # instance without a hardcoded list (see start_cache_cleanup / B3).
    _instances = []

    def __init__(
        self,
        redis_url: str,
        redis_password: Optional[str] = None,
        default_ttl: int = 300,
        namespace: str = "cache",
        max_l1_entries: int = 10_000,
    ):
        self._l1_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._max_l1 = max_l1_entries
        self._default_ttl = default_ttl
        self._redis_url = redis_url
        self._redis_password = redis_password
        self._redis: Optional[redis.Redis] = None
        self._pubsub_redis: Optional[redis.Redis] = None
        self._pubsub = None
        self._listener_task: Optional[asyncio.Task] = None
        self._namespace = namespace
        self._instance_id = uuid.uuid4().hex  # identifies this process/instance
        # Per-namespace channel: caches no longer cross-invalidate each other.
        self._channel_name = f"cache_inv:{namespace}"
        self._running = False
        MultiLevelCache._instances.append(self)

    def _rkey(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def start(self):
        if self._running:
            return
        try:
            self._redis = redis.from_url(self._redis_url, password=self._redis_password)
            await self._redis.ping()
            # redis-py defaults socket_timeout to 5s, which the regular get/set/publish
            # calls want (fail fast on a hung connection). But pubsub.listen() blocks
            # on that same read timeout while idling for the next message, so with the
            # default it raised TimeoutError ("Timeout reading from ...") every 5s with
            # nothing wrong. Give the listener its own connection with no read
            # timeout.
            self._pubsub_redis = redis.from_url(
                self._redis_url, password=self._redis_password, socket_timeout=None
            )
            self._running = True
            self._listener_task = asyncio.create_task(self._listen_for_invalidation())
            LOGGER.info(f"MultiLevelCache connected to Redis. [{self._namespace}]")
        except Exception as e:
            LOGGER.error(
                f"Failed to connect to Redis [{self._namespace}]: {e}. Falling back to L1 only."
            )
            self._redis = None

    async def stop(self):
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            LOGGER.info(f"MultiLevelCache disconnected from Redis. [{self._namespace}]")
        if self._pubsub_redis:
            try:
                await self._pubsub_redis.aclose()
            except Exception:
                pass

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        return time.time() > entry["expires"]

    def _store_l1(self, key: str, value: Any, expires: float) -> None:
        self._l1_cache[key] = {"value": value, "expires": expires}
        self._l1_cache.move_to_end(key)
        while len(self._l1_cache) > self._max_l1:
            self._l1_cache.popitem(last=False)

    async def get(self, key: str) -> Optional[Any]:
        # L1 Check (LRU)
        entry = self._l1_cache.get(key)
        if entry is not None:
            if not self._is_expired(entry):
                self._l1_cache.move_to_end(key)
                return entry["value"]
            del self._l1_cache[key]

        # L2 Check
        if self._redis:
            try:
                data = await self._redis.get(self._rkey(key))
                if data is not None:
                    value = orjson.loads(data)
                    self._store_l1(key, value, time.time() + self._default_ttl)
                    return value
            except Exception as e:
                LOGGER.error(f"Redis get error [{self._namespace}]: {e}")

        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if ttl is None:
            ttl = self._default_ttl

        # Update L1
        self._store_l1(key, value, time.time() + ttl)

        # Update L2
        if self._redis:
            try:
                await self._redis.set(self._rkey(key), orjson.dumps(value), ex=ttl)
                await self._redis.publish(
                    self._channel_name, orjson.dumps({"i": self._instance_id, "k": key})
                )
            except Exception as e:
                LOGGER.error(f"Redis set error [{self._namespace}]: {e}")

    async def delete(self, key: str) -> None:
        # Delete L1
        self._l1_cache.pop(key, None)

        # Delete L2
        if self._redis:
            try:
                await self._redis.delete(self._rkey(key))
                await self._redis.publish(
                    self._channel_name, orjson.dumps({"i": self._instance_id, "k": key})
                )
            except Exception as e:
                LOGGER.error(f"Redis delete error [{self._namespace}]: {e}")

    async def clear(self) -> None:
        self._l1_cache.clear()
        if self._redis:
            try:
                async for rk in self._redis.scan_iter(
                    match=f"{self._namespace}:*", count=500
                ):
                    await self._redis.delete(rk)
                await self._redis.publish(
                    self._channel_name,
                    orjson.dumps({"i": self._instance_id, "k": "__ALL__"}),
                )
            except Exception as e:
                LOGGER.error(f"Redis clear error [{self._namespace}]: {e}")

    async def _listen_for_invalidation(self):
        # Resilient: survives Redis drops by reconnecting/resubscribing.
        while self._running:
            pubsub = None
            try:
                if not self._pubsub_redis:
                    return
                pubsub = self._pubsub_redis.pubsub()
                self._pubsub = pubsub
                await pubsub.subscribe(self._channel_name)
                async for message in pubsub.listen():
                    if not self._running:
                        break
                    if message.get("type") != "message":
                        continue
                    try:
                        payload = orjson.loads(message["data"])
                    except Exception:
                        continue
                    # Skip our own writes: never evict the writer's fresh L1
                    # entry.
                    if payload.get("i") == self._instance_id:
                        continue
                    k = payload.get("k")
                    if k == "__ALL__":
                        self._l1_cache.clear()
                    elif k is not None:
                        self._l1_cache.pop(k, None)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    LOGGER.error(
                        f"Cache pubsub listener [{self._namespace}]: {e}; retrying in 5s"
                    )
                    await asyncio.sleep(5)
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass

    def cleanup_expired(self) -> None:
        """Remove expired entries from L1"""
        expired_keys = []
        for key, entry in self._l1_cache.items():
            if self._is_expired(entry):
                expired_keys.append(key)

        for key in expired_keys:
            self._l1_cache.pop(key, None)


locks_cache = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=120, namespace="locks"
)
admin_cache = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=300, namespace="admin"
)
blocklist_cache = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=180, namespace="blocklist"
)
linked_chat_cache = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=900, namespace="linked_chat"
)
anonymous_admin_cache = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=300, namespace="anon_admin"
)
approvals_cache = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=180, namespace="approvals"
)
playmenu_cache = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=300, namespace="playmenu"
)


class SimpleCache(MultiLevelCache):
    def __init__(self, default_ttl: int = 300, namespace: str = "cache"):
        super().__init__(
            Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl, namespace=namespace
        )


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
    """Start periodic cache cleanup task.

    Starts and periodically cleans EVERY registered cache (named caches plus
    all SimpleCache instances) via the _instances registry, rather than a
    hardcoded list that silently excluded the SimpleCache caches.
    """
    for cache in list(MultiLevelCache._instances):
        await cache.start()

    while True:
        try:
            for cache in list(MultiLevelCache._instances):
                cache.cleanup_expired()
        except Exception as e:
            LOGGER.error(f"Error during cache cleanup: {e}")

        await asyncio.sleep(60)

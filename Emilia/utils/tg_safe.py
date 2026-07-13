"""Shared FloodWait-safe caller for mass Telegram-API loops.

sleep_threshold=10 on the clients only auto-handles waits <=10s; mass operations
(fban propagation across many chats, etc.) need explicit backoff and pacing so a
long FloodWait or a transient RPCError doesn't abort the whole loop.
"""

import asyncio

from pyrogram.errors import FloodWait, RPCError

from Emilia import LOGGER


async def flood_safe(coro_factory, *, retries: int = 3, base_delay: float = 0.25):
    """Call coro_factory() with FloodWait/RPCError backoff.

    coro_factory: a zero-arg callable returning a FRESH coroutine per attempt
    (e.g. ``lambda: client.ban_chat_member(chat, user)``). Returns the call's
    result, or None if every attempt failed.
    """
    for attempt in range(retries):
        try:
            return await coro_factory()
        except FloodWait as e:
            wait = min(int(e.value), 300)
            LOGGER.warning(f"FloodWait {wait}s (attempt {attempt + 1})")
            await asyncio.sleep(wait + 1)
        except RPCError:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(base_delay * (2**attempt))
    return None

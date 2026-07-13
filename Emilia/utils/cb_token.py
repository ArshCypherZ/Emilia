"""Redis-backed token indirection for oversized callback_data.

Telegram rejects callback_data over 64 bytes. Long anime titles/JSON blobs
embedded in callback_data blow past that and make the button (and the whole
message) fail to send with BUTTON_DATA_INVALID. Stash the payload in Redis and
put a short token in the button instead.
"""

import secrets

import orjson

from Emilia import redis_client


async def stash(payload, ttl: int = 3600) -> str:
    token = secrets.token_urlsafe(8)  # ~11 chars
    await redis_client.set(f"cbt:{token}", orjson.dumps(payload).decode(), ex=ttl)
    return token


async def unstash(token: str):
    raw = await redis_client.get(f"cbt:{token}")
    return orjson.loads(raw) if raw else None

import asyncio
from typing import Optional

import aiohttp
import orjson
from aiohttp import ClientSession

# Lazily initialized clients to avoid creating event-loop-bound objects at
# import time
_aiohttp_session: Optional[ClientSession] = None
_session_lock = asyncio.Lock()


async def _get_aiohttp_session() -> ClientSession:
    global _aiohttp_session
    if _aiohttp_session is None or _aiohttp_session.closed:
        # Serialize creation so concurrent first-callers don't build two
        # sessions.
        async with _session_lock:
            if _aiohttp_session is None or _aiohttp_session.closed:
                connector = aiohttp.TCPConnector(ttl_dns_cache=300, limit_per_host=100)
                _aiohttp_session = ClientSession(
                    connector=connector,
                    json_serialize=lambda x: orjson.dumps(x).decode(),
                    timeout=aiohttp.ClientTimeout(total=30),
                )
    return _aiohttp_session


# Public: get shared aiohttp session
async def get_aiohttp_session() -> ClientSession:
    return await _get_aiohttp_session()


class _HTTPResp:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body

    def read(self) -> bytes:
        # Synchronous read that returns the pre-fetched bytes (compat shim)
        return self._body


class _HttpProxy:
    async def get(self, url: str, *args, **kwargs) -> _HTTPResp:
        session = await _get_aiohttp_session()
        async with session.get(url, *args, **kwargs) as resp:
            content = await resp.read()
            return _HTTPResp(resp.status, content)

    async def post(self, url: str, *args, **kwargs) -> _HTTPResp:
        session = await _get_aiohttp_session()
        async with session.post(url, *args, **kwargs) as resp:
            content = await resp.read()
            return _HTTPResp(resp.status, content)

    async def aclose(self):
        # No-op retained for API compatibility
        return None


# Public proxy used by existing code (e.g., pyro/stickers.py)
http = _HttpProxy()


async def post(url: str, *args, **kwargs):
    """POST helper using a shared aiohttp session; returns JSON or text."""
    session = await _get_aiohttp_session()
    async with session.post(url, *args, **kwargs) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = await resp.text()
    return data


async def close_http_clients():
    """Close lazily-created HTTP clients (aiohttp)."""
    global _aiohttp_session
    try:
        if _aiohttp_session and not _aiohttp_session.closed:
            await _aiohttp_session.close()
    finally:
        _aiohttp_session = None

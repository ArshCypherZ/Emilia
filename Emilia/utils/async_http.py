"""
Async HTTP helper to replace requests with aiohttp
"""
import asyncio
import random
import os
from urllib.parse import urlparse

import aiohttp
from Emilia.helper.http import get_aiohttp_session, close_http_clients


class AsyncResponse:
    """Response wrapper to mimic requests.Response interface
    and be resilient when underlying response is unavailable (e.g., on errors).
    """

    def __init__(self, response: aiohttp.ClientResponse | None, content: bytes | None):
        self._response = response
        self._content = content or b""
        self._text = None
        self._json = None

    @property
    def status_code(self):
        try:
            return self._response.status  # type: ignore[union-attr]
        except Exception:
            return 0

    @property
    def headers(self):
        try:
            return self._response.headers  # type: ignore[union-attr]
        except Exception:
            return {}

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        if self._text is None:
            try:
                self._text = self._content.decode("utf-8", errors="ignore")
            except Exception:
                self._text = ""
        return self._text

    def json(self):
        if self._json is None:
            import orjson

            self._json = orjson.loads(self.text or "{}")
        return self._json

    def raise_for_status(self):
        # Keep compatibility; only raise if we have the underlying response
        if self.status_code >= 400 and self._response is not None:
            self._response.raise_for_status()


def _default_headers_for(url: str) -> dict:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
    hdrs = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    if origin:
        hdrs.setdefault("Referer", origin)
        hdrs.setdefault("Origin", origin)
    return hdrs


def _coerce_requests_style_files(kwargs: dict) -> dict:
    """Translate requests-style `files` + `data` kwargs into aiohttp FormData.

    Also stores a list of file objects to close later under key `_close_fileobjs`.
    """
    files = kwargs.pop("files", None)
    if not files:
        return kwargs

    form = aiohttp.FormData()
    _close_fileobjs: list = []

    # Merge any simple form fields from `data`
    data = kwargs.pop("data", None)
    if isinstance(data, dict):
        for k, v in data.items():
            form.add_field(k, str(v))

    for field, fp in files.items():
        filename = None
        content_type = None
        fileobj = None

        if isinstance(fp, tuple):
            if len(fp) == 3:
                filename, fileobj, content_type = fp
            elif len(fp) == 2:
                fileobj, filename = fp
            elif len(fp) == 1:
                fileobj = fp[0]
            else:
                fileobj = fp[0]
        else:
            fileobj = fp

        # Track for later close
        if hasattr(fileobj, "close"):
            _close_fileobjs.append(fileobj)

        # Try to derive a filename if not provided
        if filename is None:
            name_attr = getattr(fileobj, "name", None)
            filename = os.path.basename(name_attr) if isinstance(name_attr, str) else field

        if content_type is not None:
            form.add_field(field, fileobj, filename=os.path.basename(str(filename)), content_type=content_type)
        else:
            form.add_field(field, fileobj, filename=os.path.basename(str(filename)))

    kwargs["data"] = form
    kwargs["_close_fileobjs"] = _close_fileobjs
    return kwargs


async def _request_with_retries(method: str, url: str, *, headers: dict | None = None, timeout: int | float = 15,
                                retries: int = 3, backoff: float = 1.5, **kwargs) -> AsyncResponse:
    # Merge default headers with any provided ones (caller headers take priority)
    merged_headers = {**_default_headers_for(url), **(headers or {})}

    # Coerce requests-style multipart if present
    has_files = "files" in kwargs
    if has_files:
        kwargs = _coerce_requests_style_files(kwargs)
        # Avoid retrying multipart with file objects to prevent consumed streams issues
        retries = 1

    close_fileobjs = kwargs.pop("_close_fileobjs", [])

    # Retry on common transient failures
    last_exc: Exception | None = None
    try:
        for attempt in range(retries):
            try:
                timeout_cfg = aiohttp.ClientTimeout(total=float(timeout))
                session = await get_aiohttp_session()
                async with session.request(method.upper(), url, timeout=timeout_cfg, headers=merged_headers, **kwargs) as response:
                    content = await response.read()
                    status = response.status
                    # Retry on 429 and 5xx; some sites also 403 without UA — retry once.
                    if status in (429,) or 500 <= status < 600 or (status == 403 and attempt < retries - 1):
                        await asyncio.sleep(backoff * (2 ** attempt) + random.uniform(0, 0.2))
                        continue
                    return AsyncResponse(response, content)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                if attempt == retries - 1:
                    break
                await asyncio.sleep(backoff * (2 ** attempt) + random.uniform(0, 0.2))
            except Exception as e:
                last_exc = e
                break
    finally:
        # Best-effort close any file objects we were passed
        for fo in close_fileobjs:
            try:
                fo.close()
            except Exception:
                pass
    # If all retries failed, return an empty response to let callers handle gracefully
    return AsyncResponse(None, None)


async def get(url, **kwargs):
    """Async GET request with sensible defaults and retries.

    Supported kwargs:
    - headers: dict of headers to merge with defaults
    - timeout: total timeout in seconds (default 15)
    - retries: number of attempts (default 3)
    - backoff: base backoff in seconds (default 1.5)
    - any aiohttp request kwargs such as params, ssl, etc.
    """
    return await _request_with_retries("GET", url, **kwargs)


async def post(url, **kwargs):
    """Async POST request with sensible defaults and retries.

    Supported kwargs are same as for get(). Also accepts requests-style `files`.
    """
    return await _request_with_retries("POST", url, **kwargs)


async def close_session():
    """Close the shared HTTP clients via helper closer for consistency."""
    await close_http_clients()
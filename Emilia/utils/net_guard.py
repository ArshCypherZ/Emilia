"""Shared SSRF guard for user-supplied URLs.

`is_safe_url` accepts only http/https URLs and rejects hosts that resolve to
private, loopback, link-local, reserved, multicast or unspecified addresses so
user input cannot be pointed at internal services. It performs a DNS lookup, so
call it off the event loop, e.g. `await asyncio.to_thread(is_safe_url, url)`.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import aiohttp
from yarl import URL

_ALLOWED_SCHEMES = ("http", "https")


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_safe_url(url: str) -> bool:
    """Return True only for public http(s) URLs (blunts SSRF)."""
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False
    host = parsed.hostname
    if not host:
        return False

    # IP literal in the URL: check it directly.
    try:
        return not _is_blocked_ip(ipaddress.ip_address(host))
    except ValueError:
        pass

    # Hostname: every resolved address must be public.
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if _is_blocked_ip(ip):
            return False
    return True


async def fetch_safe(url: str, *, max_redirects: int = 3, timeout: int = 15, **kwargs):
    """GET a user-supplied URL, re-validating every redirect hop.

    is_safe_url only vets the URL the user supplied; aiohttp follows redirects by
    default, so a public URL that 302s to an internal address would otherwise slip
    through. This disables auto-redirects and re-runs the guard on each Location.

    Note: full DNS-rebinding protection would require pinning the resolved IP into
    the connector; that is accepted as out of scope. Per-hop re-validation closes
    the practical redirect gap.
    """
    from Emilia.helper.http import get_aiohttp_session

    session = await get_aiohttp_session()
    for _ in range(max_redirects + 1):
        if not await asyncio.to_thread(is_safe_url, url):
            raise ValueError(f"Blocked URL: {url!r}")
        resp = await session.get(
            url,
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=timeout),
            **kwargs,
        )
        if resp.status in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            resp.release()
            if not location:
                raise ValueError("Redirect without Location")
            url = str(URL(url).join(URL(location)))
            continue
        return resp
    raise ValueError("Too many redirects")

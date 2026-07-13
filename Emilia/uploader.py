import asyncio
import os
from pathlib import Path

import aiohttp
import orjson
from PIL import Image

from Emilia import LOGGER
from Emilia.utils.async_http import post

TMP_DOWNLOAD_DIRECTORY = "upload_tmp/"
DEFAULT_ZIPLINE_URL = "http://127.0.0.1:8191"
DEFAULT_ZIPLINE_AUTH_URL = "https://files.arshjaved.in"
ZIPLINE_URL = os.getenv("EMILIA_ZIPLINE_URL", DEFAULT_ZIPLINE_URL).strip().rstrip("/")
ZIPLINE_AUTH_URL = os.getenv("EMILIA_ZIPLINE_AUTH_URL", "").strip().rstrip("/")
if not ZIPLINE_AUTH_URL:
    ZIPLINE_AUTH_URL = (
        ZIPLINE_URL if ZIPLINE_URL.startswith("https://") else DEFAULT_ZIPLINE_AUTH_URL
    )
ZIPLINE_TOKEN_FILE = os.getenv(
    "EMILIA_ZIPLINE_TOKEN_FILE",
    "/run/zipline-bootstrap/token",
).strip()
ZIPLINE_USERNAME = os.getenv("EMILIA_ZIPLINE_USERNAME", "emilia").strip()
ZIPLINE_PASSWORD = os.getenv("EMILIA_ZIPLINE_PASSWORD", "").strip()
UPLOAD_TIMEOUT = os.getenv("EMILIA_UPLOAD_TIMEOUT", "60").strip()
_ZIPLINE_TOKEN_CACHE = None
_ZIPLINE_TOKEN_LOCK = None


def resize_image(image_path: str) -> None:
    with Image.open(image_path) as image:
        image.save(image_path, "PNG")


def _get_timeout() -> float:
    try:
        return max(5.0, float(UPLOAD_TIMEOUT))
    except (TypeError, ValueError):
        return 60.0


async def _login_and_fetch_zipline_token() -> str:
    if not ZIPLINE_PASSWORD:
        raise RuntimeError(
            "Zipline token file is unavailable and EMILIA_ZIPLINE_PASSWORD is not set."
        )

    timeout = aiohttp.ClientTimeout(total=_get_timeout())
    # Zipline marks login cookies as Secure when CORE_RETURN_HTTPS_URLS=true.
    # Auth must therefore happen via the public HTTPS URL; token uploads can
    # still use the local host-network URL through the Authorization header.
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(timeout=timeout, cookie_jar=cookie_jar) as session:
        async with session.post(
            f"{ZIPLINE_AUTH_URL}/api/auth/login",
            json={
                "username": ZIPLINE_USERNAME,
                "password": ZIPLINE_PASSWORD,
            },
        ) as response:
            body = await response.text()
            if response.status != 200:
                raise RuntimeError(
                    f"Zipline login failed with status {response.status}: "
                    f"{body[:300] or 'empty response'}"
                )

        async with session.get(f"{ZIPLINE_AUTH_URL}/api/user/token") as response:
            body = await response.text()
            if response.status != 200:
                raise RuntimeError(
                    f"Zipline token fetch failed with status {response.status}: "
                    f"{body[:300] or 'empty response'}"
                )

    payload = orjson.loads(body or "{}")
    token = payload.get("token") if isinstance(payload, dict) else None
    if not token:
        raise RuntimeError("Zipline token response did not include a token.")
    return str(token)


async def _get_zipline_token() -> str:
    global _ZIPLINE_TOKEN_CACHE, _ZIPLINE_TOKEN_LOCK

    inline_token = os.getenv("EMILIA_ZIPLINE_TOKEN", "").strip()
    if inline_token:
        return inline_token

    if ZIPLINE_TOKEN_FILE:
        try:
            token = Path(ZIPLINE_TOKEN_FILE).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            token = ""
        except OSError as exc:
            LOGGER.warning(
                f"[Uploader] Failed to read Zipline token file {ZIPLINE_TOKEN_FILE}: {exc}"
            )
            token = ""
        if token:
            return token

    if _ZIPLINE_TOKEN_CACHE:
        return _ZIPLINE_TOKEN_CACHE

    if _ZIPLINE_TOKEN_LOCK is None:
        _ZIPLINE_TOKEN_LOCK = asyncio.Lock()

    async with _ZIPLINE_TOKEN_LOCK:
        if _ZIPLINE_TOKEN_CACHE:
            return _ZIPLINE_TOKEN_CACHE
        _ZIPLINE_TOKEN_CACHE = await _login_and_fetch_zipline_token()
        return _ZIPLINE_TOKEN_CACHE


async def upload_local_file(file_path: str, *, cleanup: bool = True) -> str:
    upload_path = Path(file_path)
    if upload_path.suffix.lower() == ".webp":
        resize_image(str(upload_path))

    try:
        response = await post(
            f"{ZIPLINE_URL}/api/upload",
            headers={
                "authorization": await _get_zipline_token(),
                "x-zipline-original-name": "true",
            },
            files={"file": open(upload_path, "rb")},
            timeout=_get_timeout(),
        )

        if response.status_code != 200:
            body = (response.text or "").strip()
            raise RuntimeError(
                f"Zipline upload failed with status {response.status_code or 'no-response'}: "
                f"{body[:300] or 'empty response'}"
            )

        payload = response.json()
        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, list) or not files:
            raise RuntimeError(
                f"Zipline upload did not return a file URL: {(response.text or '')[:300]}"
            )

        first_file = files[0]
        if not isinstance(first_file, dict) or not first_file.get("url"):
            raise RuntimeError(
                f"Zipline upload returned an invalid file payload: {(response.text or '')[:300]}"
            )

        return str(first_file["url"])
    except Exception as exc:
        LOGGER.error(f"[Uploader] Zipline upload failed for {upload_path.name}: {exc}")
        raise
    finally:
        if cleanup:
            try:
                upload_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                LOGGER.warning(
                    f"[Uploader] Failed to remove temp upload file {upload_path}: "
                    f"{cleanup_error}"
                )


async def upload(message) -> str:
    os.makedirs(TMP_DOWNLOAD_DIRECTORY, exist_ok=True)
    downloaded_file_name = await message.download(file_name=TMP_DOWNLOAD_DIRECTORY)
    return await upload_local_file(downloaded_file_name)

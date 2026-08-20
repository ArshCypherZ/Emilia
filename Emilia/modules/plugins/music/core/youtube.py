import asyncio
import logging
import os

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import yt_dlp

from Emilia import EVENT_LOGS, pgram
from Emilia.modules.plugins.music.utils.store import (
    get_cached_media,
    set_cached_media,
    get_cached_meta,
    set_cached_meta,
)

LOGGER = logging.getLogger(__name__)

# ---- yt-dlp executor (serialized for thread safety) ----

_search_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="YTSearch")
_download_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="YTDownload")
_COOKIES = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "..",
    "www.youtube.com_cookies.txt",
))

if os.path.isfile(_COOKIES):
    LOGGER.info("[Music] Using YouTube cookie file: %s", _COOKIES)
else:
    LOGGER.warning(
        "[Music] YouTube cookie file not found at %s — downloads may be rate-limited or blocked by YouTube.",
        _COOKIES,
    )

_CLEANUP_INTERVAL = 3600  # run cleanup every hour
_MAX_FILE_AGE_HOURS = 168  # delete files older than 7 days (or when folder > 25GB)


def _build_ydl_opts(extract_audio=True, is_video=False, use_cookies=True):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": _COOKIES if (use_cookies and _COOKIES and os.path.isfile(_COOKIES)) else None,
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "remote_components": ["ejs:github"],
        "js_runtimes": {"node": {}},
        "concurrent_fragments": 4,
        "buffer_size": "16K",
        "resize_buffer": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["web_safari", "tv_downgraded", "android_vr", "mweb", "web", "ios"],
            }
        },
    }
    if is_video:
        opts.update({
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best/best*",
            "merge_output_format": "mp4",
            "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
            "outtmpl": "downloads/%(id)s.%(ext)s",
        })
    elif extract_audio:
        opts.update({
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": "downloads/%(id)s.%(ext)s",
        })
    return opts


async def _yt_run(func, *args, executor=None, **kwargs):
    """Run a yt-dlp operation in a thread pool."""
    loop = asyncio.get_running_loop()
    pool = executor or _search_executor
    return await loop.run_in_executor(pool, lambda: func(*args, **kwargs))


# ---- Search ----

async def search_youtube(query: str, limit: int = 8):
    """Search YouTube for videos. Returns list of track candidates."""
    def _search():
        with yt_dlp.YoutubeDL(_build_ydl_opts(extract_audio=False)) as ydl:
            results = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            return results.get("entries", []) if results else []

    try:
        entries = await _yt_run(_search)
        candidates = []
        for entry in entries:
            vid = entry.get("id", "")
            candidates.append({
                "id": vid,
                "title": entry.get("title", "Unknown"),
                "uploader": entry.get("channel", "YouTube"),
                "thumbnail": entry.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                "duration": entry.get("duration") or 0,
                "webpage_url": entry.get("webpage_url", f"https://www.youtube.com/watch?v={vid}"),
                "source": "youtube",
            })
        return candidates
    except Exception as e:
        LOGGER.warning("[Music] YouTube search failed: %s", e)
        return []



# ---- Metadata ----

async def get_yt_metadata_from_url(url: str):
    """Get metadata from a YouTube URL."""
    def _meta():
        with yt_dlp.YoutubeDL(_build_ydl_opts(extract_audio=False)) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await _yt_run(_meta)
        if not info:
            return None
        vid = info.get("id", "")
        return {
            "id": vid,
            "title": info.get("title", "Unknown"),
            "uploader": info.get("channel", "YouTube"),
            "thumbnail": info.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "duration": info.get("duration") or 0,
            "webpage_url": info.get("webpage_url", f"https://www.youtube.com/watch?v={vid}"),
            "source": "youtube",
        }
    except Exception as e:
        LOGGER.warning("[Music] YouTube metadata fetch failed: %s", e)
        return None


# ---- Download ----

async def download_youtube_audio(url: str, video_id: str, is_video: bool = False, progress_callback=None) -> str | None:
    """Download audio or video from a YouTube URL to local file."""
    loop = asyncio.get_running_loop()

    def _download():
        opts = _build_ydl_opts(extract_audio=not is_video, is_video=is_video)
        if progress_callback:
            class ProgressHook:
                def __init__(self):
                    self.last_bytes = 0
                def __call__(self, d):
                    if d.get("status") == "downloading":
                        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                        downloaded = d.get("downloaded_bytes", 0)
                        if total > 0:
                            pct = downloaded / total
                            loop.call_soon_threadsafe(
                                progress_callback, downloaded, total, pct
                            )
            opts["progress_hooks"] = [ProgressHook()]
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                return ydl.prepare_filename(info)
        return None

    try:
        filename = await _yt_run(_download, executor=_download_executor)
        if filename and os.path.exists(filename):
            size = os.path.getsize(filename)
            LOGGER.info("[Music] Downloaded %s to %s (%d bytes)", video_id, filename, size)
            return filename
        LOGGER.error("[Music] YouTube download failed: file not found after download")
    except Exception as e:
        LOGGER.error("[Music] YouTube download failed for %s: %s", video_id, e)

    return None


async def _upload_to_event_logs(file_path: str, track_info: dict, is_video: bool = False) -> int | None:
    """Upload downloaded file to EVENT_LOGS channel and return the file_id without compression."""
    try:
        caption = f"{track_info.get('title', 'Unknown')} - {track_info.get('uploader', 'YouTube')}"
        # 1. Prefer send_document for both audio and video to guarantee 0% down-compression and exact binary preservation
        try:
            msg = await pgram.send_document(
                chat_id=EVENT_LOGS,
                document=file_path,
                caption=caption,
            )
            if msg:
                return msg.id
        except Exception as e:
            LOGGER.debug("[Music] send_document upload to EVENT_LOGS fallback: %s", e)

        # 2. Fallback to send_video/send_audio if send_document fails
        if is_video:
            msg = await pgram.send_video(
                chat_id=EVENT_LOGS,
                video=file_path,
                caption=caption,
                duration=track_info.get("duration", 0),
            )
            if msg:
                return msg.id
        else:
            msg = await pgram.send_audio(
                chat_id=EVENT_LOGS,
                audio=file_path,
                title=track_info.get("title", "Unknown"),
                performer=track_info.get("uploader", "YouTube"),
                duration=track_info.get("duration", 0),
            )
            if msg:
                return msg.id
    except Exception as e:
        LOGGER.warning("[Music] Failed to upload to EVENT_LOGS: %s", e)
    return None


async def _cache_media_background(local_path: str, track_info: dict, video_id: str, is_video: bool):
    """Upload to EVENT_LOGS and cache file_id|ext in background (non-blocking)."""
    try:
        await asyncio.sleep(5)  # Let VC stabilize before background upload
        message_id = await _upload_to_event_logs(local_path, track_info, is_video)
        if message_id:
            ext = os.path.splitext(local_path)[1].lstrip(".") or ("mp4" if is_video else "m4a")
            await set_cached_media(video_id, f"{message_id}|{ext}", is_video)
        else:
            LOGGER.warning("[Music] Background cache failed for %s (%s): no file_id returned", video_id, track_info.get("title"))
    except Exception as e:
        LOGGER.warning("[Music] Background cache failed for %s (%s): %s", video_id, track_info.get("title"), e)


# ---- File cleanup ----

def cleanup_old_downloads(max_age_hours: int = _MAX_FILE_AGE_HOURS, active_paths: set | None = None) -> int:
    """Delete audio files older than max_age_hours from downloads/, or if folder > 25GB."""
    if not os.path.isdir("downloads"):
        return 0
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    deleted = 0
    files = []
    total_size = 0
    for fname in os.listdir("downloads"):
        fpath = os.path.join("downloads", fname)
        if not os.path.isfile(fpath):
            continue
        if active_paths and os.path.abspath(fpath) in active_paths:
            continue
        try:
            mtime = os.path.getmtime(fpath)
            size = os.path.getsize(fpath)
            total_size += size
            files.append((fpath, datetime.fromtimestamp(mtime), size))
        except Exception:
            pass

    remaining_files = []
    for fpath, mtime, size in files:
        if mtime < cutoff:
            try:
                os.remove(fpath)
                deleted += 1
                total_size -= size
                LOGGER.info("[Music] Cleaned old file: %s", fpath)
            except Exception as e:
                LOGGER.warning("[Music] Failed to delete %s: %s", fpath, e)
        else:
            remaining_files.append((fpath, mtime, size))

    max_dir_size = 25 * 1024 * 1024 * 1024
    target_dir_size = 20 * 1024 * 1024 * 1024
    if total_size > max_dir_size:
        remaining_files.sort(key=lambda x: x[1])
        for fpath, mtime, size in remaining_files:
            if total_size <= target_dir_size:
                break
            try:
                os.remove(fpath)
                deleted += 1
                total_size -= size
                LOGGER.info("[Music] Size cleanup removed old file: %s", fpath)
            except Exception as e:
                LOGGER.warning("[Music] Failed to delete for size cleanup %s: %s", fpath, e)

    return deleted


def start_cleanup_task():
    """Start background cleanup loop. Call once at startup from async context."""
    async def _loop():
        while True:
            await asyncio.sleep(_CLEANUP_INTERVAL)
            try:
                count = await asyncio.get_event_loop().run_in_executor(None, cleanup_old_downloads)
                if count:
                    LOGGER.info("[Music] Cleanup removed %d old files", count)
            except Exception as e:
                LOGGER.warning("[Music] Cleanup task error: %s", e)

    return _loop()


# ---- Public API (used by play.py) ----

async def _resolve_file(track_info: dict, progress_callback=None):
    """Common local-disk → cache-hit → download → background-cache path."""
    video_id = track_info["id"]
    is_video = track_info.get("is_video", False)

    # 1. First, check if the file is ALREADY sitting right here on local server storage!
    possible_exts = ("mp4", "mkv", "webm") if is_video else ("m4a", "webm", "mp3", "opus", "mp4")
    for ext in possible_exts:
        local_path = os.path.abspath(f"downloads/{video_id}.{ext}")
        if os.path.exists(local_path) and os.path.getsize(local_path) > 1024:
            LOGGER.info("[Music] Local disk HIT for %s (%s). Instant stream!", video_id, local_path)
            track_info["file_path"] = local_path
            return track_info

    # 2. Telegram EVENT_LOGS cache HIT
    cached_val = await get_cached_media(video_id, is_video)
    if cached_val:
        LOGGER.info("[Music] Telegram cache HIT for %s.", video_id)
        parts = str(cached_val).split("|")
        if len(parts) == 2 and parts[0].isdigit():
            message_id = int(parts[0])
            ext = parts[1]
            local_path = os.path.abspath(f"downloads/{video_id}.{ext}")
            if not os.path.exists("downloads"):
                os.makedirs("downloads", exist_ok=True)
            try:
                msg = await pgram.get_messages(EVENT_LOGS, message_id)
                if msg:
                    local_path = await pgram.download_media(msg, file_name=local_path)
                    if local_path:
                        track_info["file_path"] = local_path
                        return track_info
            except Exception as e:
                LOGGER.warning("[Music] Failed to fetch message/download media from EVENT_LOGS for %s: %s", video_id, e)

    # 3. Download from YouTube
    url = track_info.get("webpage_url", "")
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id}"

    local_path = await download_youtube_audio(url, video_id, is_video=is_video, progress_callback=progress_callback)
    if not local_path:
        raise ValueError("Could not download audio for this track.")

    track_info["file_path"] = local_path

    # 4. Background upload to EVENT_LOGS
    if not await get_cached_media(video_id, is_video):
        asyncio.create_task(_cache_media_background(local_path, track_info, video_id, is_video))

    return track_info


async def ensure_local_file(track_info: dict) -> dict:
    """Guarantee `track_info['file_path']` points at a file that exists *now*.

    Queued tracks are stored as bare search results — nothing is downloaded
    until they are about to play, and the prefetcher only gets a head start,
    never a guarantee. A queue entry whose file never landed (or whose file the
    cleanup job has since deleted) used to reach ffmpeg as a missing path and
    fail with a FileNotFoundError carrying no message at all, which is how a
    silent voice chat came to be logged as `Failed to auto-play next track: `.
    """
    path = track_info.get("file_path")
    if path and os.path.exists(path) and os.path.getsize(path) > 1024:
        return track_info
    return await _resolve_file(track_info)


async def fetch_and_download(query: str, is_video: bool = False, progress_callback=None):
    """Resolve track metadata via YouTube, then download audio.

    Accepts a song name or a YouTube URL. Returns track_info with file_path.
    """
    norm = query.strip().lower()
    cached_meta = await get_cached_meta(norm)
    if cached_meta:
        track_info = dict(cached_meta)
    else:
        if query.startswith("http"):
            track_info = await get_yt_metadata_from_url(query)
        else:
            results = await search_youtube(query, limit=1)
            track_info = results[0] if results else None
        if not track_info:
            raise ValueError("Could not find any YouTube results for this query.")
        await set_cached_meta(norm, track_info)

    track_info["is_video"] = is_video
    return await _resolve_file(track_info, progress_callback=progress_callback)


async def resolve_audio(candidate: dict, is_video: bool = False, progress_callback=None):
    """Resolve the audio FILE for a CHOSEN YouTube candidate.

    Returns a full track_info with file_path. Shares the cache/download path
    with fetch_and_download via _resolve_file.
    """
    track_info = dict(candidate)
    track_info["is_video"] = is_video
    return await _resolve_file(track_info, progress_callback=progress_callback)


async def get_playlist_tracks(playlist_id: str, limit: int = 100):
    """Get tracks from a YouTube playlist ID."""
    def _fetch():
        opts = _build_ydl_opts(extract_audio=False)
        opts["extract_flat"] = True
        opts["noplaylist"] = False
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []
            entries = info.get("entries", [])[:limit]
            tracks = []
            for entry in entries:
                vid = entry.get("id", "")
                tracks.append({
                    "id": vid,
                    "title": entry.get("title", "Unknown"),
                    "uploader": entry.get("channel", "YouTube"),
                    "thumbnail": entry.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "duration": entry.get("duration") or 0,
                    "webpage_url": entry.get("webpage_url", f"https://www.youtube.com/watch?v={vid}"),
                    "source": "youtube",
                })
            return tracks

    try:
        return await _yt_run(_fetch)
    except Exception as e:
        LOGGER.warning("[Music] YouTube playlist fetch failed: %s", e)
        return []



"""
Import engine for the social playlists module.

Resolves Spotify and YouTube links into the canonical track dicts the music
subsystem already speaks (see music/core/youtube.py):

    {"id", "title", "uploader", "thumbnail", "duration", "webpage_url", "source"}

YouTube links resolve directly through yt-dlp.

Spotify deliberately does NOT use the Web API. Credentials exist in config, and
the Client Credentials flow still issues a token, but since Spotify's 2025 policy
change every data endpoint (/tracks, /albums, /playlists, /search) answers 403
"Active premium subscription required for the owner of the app" unless the app
owner holds Premium. Verified against this deployment's live credentials — so
adding OAuth here would not help.

Instead we read the *embed* page, which serves the track list unauthenticated as
JSON inside its Next.js payload, then re-resolve each "artist - title" against
YouTube. Consequences worth knowing:
  - Spotify imports are a best-effort audio match, not an exact one.
  - Durations in the payload are milliseconds; we convert to seconds.
  - A playlist embed caps at 50 entries with no unauthenticated pagination.
  - A /track embed has no trackList — the track is the entity itself.
"""

import asyncio
import json
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

import aiohttp

from Emilia import LOGGER
from Emilia.helper.http import get_aiohttp_session
from Emilia.modules.plugins.music.core.youtube import (
    get_playlist_tracks,
    get_yt_metadata_from_url,
    search_youtube,
)
from Emilia.modules.plugins.music.playlist.core import render_bar

# ---- URL patterns -----------------------------------------------------------

_YT_PLAYLIST = re.compile(r"[?&]list=([A-Za-z0-9_-]+)")
_YT_VIDEO = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})"
)
_YT_BARE_PLAYLIST = re.compile(r"^(?:PL|UU|OL|RD|LL|FL)[A-Za-z0-9_-]{10,}$")

_SPOTIFY = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z]{2}/)?(playlist|album|track)/([A-Za-z0-9]+)"
)
_SPOTIFY_URI = re.compile(r"spotify:(playlist|album|track):([A-Za-z0-9]+)")

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

# Spotify serves a lighter, unauthenticated payload to a plain browser UA.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# A single import can't be allowed to walk a 10k-track playlist — it would pin a
# yt-dlp worker for hours and blow past MAX_SONGS_PER_PLAYLIST anyway.
MAX_IMPORT = 200

# Spotify tracks each need their own YouTube search; run a few concurrently but
# not so many that we trip rate limiting.
_SEARCH_CONCURRENCY = 4


# ---- Source detection -------------------------------------------------------


def detect_source(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Classify an import target.

    Returns (kind, ident) where kind is one of:
        "yt_playlist", "yt_video",
        "sp_playlist", "sp_album", "sp_track"
    or (None, None) if nothing recognisable is present.
    """
    if not text:
        return None, None
    text = text.strip()

    m = _SPOTIFY.search(text) or _SPOTIFY_URI.search(text)
    if m:
        return f"sp_{m.group(1)}", m.group(2)

    m = _YT_PLAYLIST.search(text)
    if m:
        return "yt_playlist", m.group(1)

    m = _YT_VIDEO.search(text)
    if m:
        return "yt_video", m.group(1)

    if _YT_BARE_PLAYLIST.match(text):
        return "yt_playlist", text

    return None, None


# ---- Progress bar -----------------------------------------------------------

_BAR_WIDTH = 12


def render_progress(done: int, total: int, label: str = "Importing") -> str:
    """Monochrome progress bar for the import status message."""
    total = max(total, 1)
    pct = min(1.0, done / total)
    bar = render_bar(done, total, _BAR_WIDTH)
    return f"**{label}**\n\n`{bar}`  {int(pct * 100)}%\n`•` {done}/{total} tracks"


class ProgressReporter:
    """
    Throttled editor for the import status message.

    Telegram rate-limits edits hard, and an import fires one callback per track,
    so edits are coalesced: at most one every `interval` seconds, plus a
    guaranteed final one via flush().
    """

    def __init__(self, message, label: str = "Importing", interval: float = 3.0):
        self._message = message
        self._label = label
        self._interval = interval
        self._last_edit = 0.0
        self._last_text = ""
        self._done = 0
        self._total = 0

    async def update(self, done: int, total: int, force: bool = False):
        self._done, self._total = done, total
        now = time.monotonic()
        if not force and (now - self._last_edit) < self._interval:
            return
        text = render_progress(done, total, self._label)
        if text == self._last_text:
            return
        self._last_edit = now
        self._last_text = text
        try:
            await self._message.edit_text(text)
        except Exception:
            # A failed progress edit must never abort the import itself.
            pass

    async def flush(self):
        await self.update(self._done, self._total, force=True)


# ---- Spotify ----------------------------------------------------------------


async def _fetch(url: str, timeout: int = 20) -> Optional[str]:
    # The bot keeps one pooled session with a warm DNS cache; standing up a
    # fresh ClientSession per import would throw away the connection pool and
    # leak a connector every time an import failed mid-flight.
    session = await get_aiohttp_session()
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"User-Agent": _UA, "Accept-Language": "en"},
        ) as resp:
            if resp.status != 200:
                LOGGER.warning(f"[Playlists] fetch {url} -> HTTP {resp.status}")
                return None
            return await resp.text()
    except Exception as e:
        LOGGER.warning(f"[Playlists] fetch {url} failed: {e}")
        return None


def _find_entity(data: Dict) -> Optional[Dict]:
    """
    Locate the embed payload's entity node.

    The canonical location is props.pageProps.state.data.entity, verified against
    live track/album/playlist embeds. Spotify has moved this path between
    releases though, so if it's absent we fall back to walking the tree for the
    first dict that looks like an entity (a "type" plus a "title"/"name").
    """
    try:
        entity = data["props"]["pageProps"]["state"]["data"]["entity"]
        if isinstance(entity, dict):
            return entity
    except (KeyError, TypeError):
        pass

    found: List[Dict] = []

    def visit(n):
        if found:
            return
        if isinstance(n, dict):
            if n.get("type") in ("track", "album", "playlist") and (
                n.get("title") or n.get("name")
            ):
                found.append(n)
                return
            for v in n.values():
                visit(v)
        elif isinstance(n, list):
            for v in n:
                visit(v)

    visit(data)
    return found[0] if found else None


def _clean(text: str) -> str:
    """
    Normalise Spotify's display text.

    `subtitle` joins multiple artists with a non-breaking space ("Shakira,\xa0Burna
    Boy"). Left as-is it travels into the YouTube query and into stored track
    titles, where it renders as a stray glyph and breaks naive matching.
    """
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split())


def _entry_to_track_hint(entry: Dict) -> Optional[Dict]:
    """
    Turn one embed entry into a search hint.

    Durations in the embed payload are milliseconds (verified: 200040 for a
    3:20 track), whereas the rest of the music subsystem speaks seconds.
    """
    title = _clean(entry.get("title") or entry.get("name") or "")
    if not title:
        return None

    artist = _clean(entry.get("subtitle") or "")
    if not artist:
        artists = entry.get("artists")
        if isinstance(artists, list) and artists:
            artist = _clean(
                ", ".join(
                    a.get("name")
                    for a in artists
                    if isinstance(a, dict) and a.get("name")
                )
            )

    duration_ms = entry.get("duration") or 0
    return {
        "query": f"{artist} - {title}" if artist else title,
        "title": title,
        "artist": artist,
        "duration": int(duration_ms // 1000) if duration_ms else 0,
    }


async def fetch_spotify_hints(kind: str, ident: str) -> List[Dict]:
    """
    Resolve a Spotify link to search hints, in playlist order.

    Note the embed serves at most 50 entries for a playlist regardless of its
    real length — there is no pagination available unauthenticated, so a large
    playlist imports as its first 50 tracks. Returns [] if the page is private,
    region-locked, or the payload shape changed.
    """
    sp_type = kind.split("_", 1)[1]
    html = await _fetch(f"https://open.spotify.com/embed/{sp_type}/{ident}")
    if not html:
        return []

    m = _NEXT_DATA.search(html)
    if not m:
        LOGGER.warning("[Playlists] Spotify embed had no __NEXT_DATA__ payload")
        return []

    try:
        data = json.loads(m.group(1))
    except Exception as e:
        LOGGER.warning(f"[Playlists] Spotify payload parse failed: {e}")
        return []

    entity = _find_entity(data)
    if not entity:
        LOGGER.warning("[Playlists] Spotify embed had no recognisable entity")
        return []

    entries = entity.get("trackList")
    if not isinstance(entries, list) or not entries:
        # A /track embed carries no trackList — the track *is* the entity. Its
        # artist lives in `artists`, not `subtitle` (which is None there).
        if entity.get("type") == "track" or kind == "sp_track":
            hint = _entry_to_track_hint(entity)
            return [hint] if hint else []
        return []

    hints = []
    for entry in entries[:MAX_IMPORT]:
        hint = _entry_to_track_hint(entry)
        if hint:
            hints.append(hint)
    return hints


async def _resolve_hint(hint: Dict) -> Optional[Dict]:
    """
    Best-effort YouTube match for one Spotify track.

    Spotify's own title/artist are authoritative, so we keep them for display
    and only borrow the id/url/thumbnail from YouTube. Otherwise an import
    fills the playlist with "(Official Video) [HD] Lyrics" style noise.
    """
    try:
        results = await search_youtube(hint["query"], limit=1)
    except Exception as e:
        LOGGER.warning(f"[Playlists] search failed for {hint['query']!r}: {e}")
        return None
    if not results:
        return None

    track = dict(results[0])
    track["title"] = (
        f"{hint['artist']} - {hint['title']}" if hint["artist"] else hint["title"]
    )
    if hint["artist"]:
        track["uploader"] = hint["artist"]
    if hint["duration"]:
        track["duration"] = hint["duration"]
    track["source"] = "spotify"
    return track


async def import_from_spotify(
    kind: str,
    ident: str,
    progress: Optional[Callable] = None,
) -> List[Dict]:
    """
    Import a Spotify playlist/album/track as YouTube-resolved tracks.
    `progress` is awaited as progress(done, total).
    """
    queries = await fetch_spotify_hints(kind, ident)
    if not queries:
        return []

    total = len(queries)
    tracks: List[Dict] = []
    done = 0
    sem = asyncio.Semaphore(_SEARCH_CONCURRENCY)
    lock = asyncio.Lock()

    async def worker(idx: int, hint: Dict):
        nonlocal done
        async with sem:
            track = await _resolve_hint(hint)
        async with lock:
            done += 1
            if track:
                # Keep the original ordering of the Spotify playlist rather than
                # whatever order the searches happen to finish in.
                tracks.append((idx, track))
            if progress:
                try:
                    await progress(done, total)
                except Exception:
                    pass

    await asyncio.gather(*(worker(i, q) for i, q in enumerate(queries)))

    tracks.sort(key=lambda pair: pair[0])
    return [t for _, t in tracks]


# ---- YouTube ----------------------------------------------------------------


async def import_from_youtube(
    kind: str,
    ident: str,
    progress: Optional[Callable] = None,
) -> List[Dict]:
    """Import a YouTube playlist or single video."""
    if kind == "yt_video":
        meta = await get_yt_metadata_from_url(f"https://www.youtube.com/watch?v={ident}")
        if progress:
            try:
                await progress(1, 1)
            except Exception:
                pass
        return [meta] if meta else []

    tracks = await get_playlist_tracks(ident, limit=MAX_IMPORT) or []
    if progress:
        try:
            await progress(len(tracks), max(len(tracks), 1))
        except Exception:
            pass
    return tracks


# ---- Unified entry point ----------------------------------------------------


async def import_tracks(
    text: str,
    progress: Optional[Callable] = None,
) -> Tuple[List[Dict], Optional[str]]:
    """
    Resolve any supported link into tracks.

    Returns (tracks, error). `error` is a user-facing string when the import
    could not proceed; it is None on success (including an empty result, which
    the caller reports as "nothing importable").
    """
    kind, ident = detect_source(text)
    if not kind:
        return [], (
            "Unrecognised link. Supported: YouTube video/playlist links, "
            "and Spotify track/album/playlist links."
        )

    try:
        if kind.startswith("sp_"):
            tracks = await import_from_spotify(kind, ident, progress)
            if not tracks:
                return [], (
                    "Could not read that Spotify link. It may be private, "
                    "region-locked, or empty."
                )
        else:
            tracks = await import_from_youtube(kind, ident, progress)
            if not tracks:
                return [], "That YouTube link is empty or unavailable."
    except Exception as e:
        LOGGER.error(f"[Playlists] import failed for {text!r}: {e}", exc_info=True)
        return [], "Import failed while resolving that link."

    return tracks[:MAX_IMPORT], None


def source_label(kind: str) -> str:
    return {
        "yt_playlist": "YouTube playlist",
        "yt_video": "YouTube track",
        "sp_playlist": "Spotify playlist",
        "sp_album": "Spotify album",
        "sp_track": "Spotify track",
    }.get(kind, "link")

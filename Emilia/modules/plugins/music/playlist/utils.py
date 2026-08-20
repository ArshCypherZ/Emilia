"""
Utilities for the social playlists module: share links, offline export, QR
codes, and abuse protection.

Nothing here is hand-rolled that a maintained library already does properly:
  - QR generation is `segno` (pure-Python, zero native deps).
  - Rate limiting reuses `Emilia.utils.decorators.rate_limit`, the existing
    Redis sliding-window limiter, rather than a second parallel implementation.
    The only thing added here is `guard_action`, for the paths a decorator
    can't reach (callback queries, and per-playlist rather than per-user
    budgets) — and it is deliberately built on the same Redis ZSET shape.
"""

import csv
import io
import json
import time
from typing import Dict, List, Optional, Tuple

import segno

from Emilia import BOT_USERNAME, LOGGER
from Emilia.modules.plugins.music.playlist.core import format_duration
from Emilia.mongo import playlists_mongo as db

# ---- Share links ------------------------------------------------------------

# Playlist ids are already short and URL-safe by construction (10 chars from a
# no-look-alike alphabet, see playlists_mongo._ID_ALPHABET), so the deep link
# needs no extra hashing layer — hashing would only add a lookup table to keep
# in sync. The `pl_` prefix matches the `<verb>_<arg>` convention that
# start.py's startCheckQuery dispatch already splits on.
DEEPLINK_PREFIX = "pl"


def build_share_link(playlist_id: str) -> str:
    """t.me/<bot>?start=pl_<id>"""
    return f"https://t.me/{BOT_USERNAME}?start={DEEPLINK_PREFIX}_{playlist_id}"


def parse_deeplink(payload: str) -> Optional[str]:
    """
    Extract a playlist id from a /start payload.

    Accepts the raw payload ("pl_abc123") or the already-split remainder
    ("abc123"), so it works both from start.py's split chain and standalone.
    """
    if not payload:
        return None
    payload = payload.strip()
    if payload.startswith(f"{DEEPLINK_PREFIX}_"):
        payload = payload[len(DEEPLINK_PREFIX) + 1 :]
    return payload or None


async def resolve_shared_playlist(
    playlist_id: str, user_id: int
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Resolve a shared link to a playlist the recipient is allowed to open.

    Holding the link is itself the credential for Unlisted — that is the entire
    point of the mode — so Unlisted resolves for anyone. Private and Server-only
    do not: a leaked link must not widen access beyond what the owner chose.
    Returns (playlist, error_message).
    """
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return None, "That playlist link is invalid or the playlist was deleted."
    if pl.get("banned"):
        return None, "That playlist has been removed for violating the rules."

    mode = pl.get("access_mode", db.ACCESS_PRIVATE)
    if mode in (db.ACCESS_PUBLIC, db.ACCESS_UNLISTED):
        return pl, None
    if user_id == pl.get("owner_id") or user_id in (pl.get("editors") or []):
        return pl, None
    if mode == db.ACCESS_SERVER:
        return None, "That playlist is only available inside its own group."
    return None, "That playlist is private."


# ---- QR codes ---------------------------------------------------------------


def generate_qr(playlist_id: str, title: str = "") -> Optional[io.BytesIO]:
    """
    Render a share link as a PNG QR code, ready to upload.

    Scale 8 with a 3-module quiet zone keeps it comfortably scannable from a
    phone screen while staying well under a megabyte. Monochrome by design,
    matching the rest of the feature.
    """
    try:
        qr = segno.make(build_share_link(playlist_id), error="m")
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=8, border=3, dark="#000000", light="#ffffff")
        buf.seek(0)
        buf.name = f"playlist_{playlist_id}.png"
        return buf
    except Exception as e:
        LOGGER.warning(f"[Playlists] QR generation failed for {playlist_id}: {e}")
        return None


# ---- Offline export ---------------------------------------------------------

EXPORT_FORMATS = ("json", "m3u", "csv")


def _export_json(pl: Dict, songs: List[Dict]) -> str:
    payload = {
        "playlist_id": pl.get("playlist_id"),
        "title": pl.get("title"),
        "description": pl.get("description") or "",
        "access_mode": pl.get("access_mode"),
        "owner_id": pl.get("owner_id"),
        "created_at": pl.get("created_at"),
        "exported_at": time.time(),
        "share_link": build_share_link(pl.get("playlist_id", "")),
        "track_count": len(songs),
        "tracks": [
            {
                "position": s.get("position"),
                "title": s.get("title"),
                "uploader": s.get("uploader"),
                "duration": s.get("duration"),
                "url": s.get("webpage_url"),
                "video_id": s.get("video_id"),
                "source": s.get("source"),
            }
            for s in songs
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _export_m3u(pl: Dict, songs: List[Dict]) -> str:
    """
    Extended M3U. #EXTINF wants whole seconds and -1 when unknown, and the
    title line must not contain a newline, so titles are flattened.
    """
    lines = ["#EXTM3U", f"#PLAYLIST:{_flat(pl.get('title', 'Playlist'))}"]
    for s in songs:
        duration = int(s.get("duration") or -1)
        artist = _flat(s.get("uploader") or "")
        title = _flat(s.get("title") or "Unknown")
        label = f"{artist} - {title}" if artist else title
        lines.append(f"#EXTINF:{duration},{label}")
        lines.append(s.get("webpage_url") or "")
    return "\n".join(lines) + "\n"


def _export_csv(pl: Dict, songs: List[Dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["position", "title", "uploader", "duration", "url", "source"])
    for s in songs:
        writer.writerow(
            [
                s.get("position"),
                s.get("title") or "",
                s.get("uploader") or "",
                s.get("duration") or 0,
                s.get("webpage_url") or "",
                s.get("source") or "",
            ]
        )
    return buf.getvalue()


def _flat(text: str) -> str:
    """Collapse newlines/tabs — they corrupt line-oriented formats like M3U."""
    return " ".join(str(text or "").split())


async def export_playlist(
    playlist_id: str, fmt: str = "json"
) -> Tuple[Optional[io.BytesIO], Optional[str]]:
    """
    Serialise a playlist to an uploadable in-memory file.

    Returns (file, error). The file is BytesIO with `.name` set, which is what
    Pyrogram uses to name the uploaded document.
    """
    fmt = (fmt or "json").lower()
    if fmt not in EXPORT_FORMATS:
        return None, f"Unsupported format. Use: {', '.join(EXPORT_FORMATS)}."

    pl = await db.get_playlist(playlist_id)
    if not pl:
        return None, "That playlist no longer exists."

    songs = await db.get_songs(playlist_id, limit=db.MAX_SONGS_PER_PLAYLIST)
    if not songs:
        return None, "That playlist is empty — nothing to export."

    try:
        if fmt == "json":
            text = _export_json(pl, songs)
        elif fmt == "m3u":
            text = _export_m3u(pl, songs)
        else:
            text = _export_csv(pl, songs)
    except Exception as e:
        LOGGER.error(f"[Playlists] export {playlist_id} as {fmt} failed: {e}")
        return None, "Export failed."

    buf = io.BytesIO(text.encode("utf-8"))
    buf.name = f"{_safe_filename(pl.get('title', 'playlist'))}.{fmt}"
    buf.seek(0)
    return buf, None


def _safe_filename(title: str) -> str:
    """Keep only characters that are safe on every filesystem Telegram touches."""
    cleaned = "".join(
        c if (c.isalnum() or c in " -_") else "_" for c in _flat(title)
    ).strip()
    return (cleaned[:48] or "playlist").replace(" ", "_")


# ---- Abuse protection -------------------------------------------------------

# Budgets for actions a plain command decorator can't cover. Each is
# (max_actions, window_seconds).
LIMIT_CREATE = (5, 300)  # new playlists: 5 per 5 min
LIMIT_IMPORT = (3, 600)  # imports are the most expensive path we expose
LIMIT_FORK = (10, 600)
LIMIT_REPORT = (5, 3600)
LIMIT_EXPORT = (5, 300)
LIMIT_QR = (10, 300)
LIMIT_CALLBACK = (20, 10)  # menu taps; generous, catches only real hammering


async def guard_action(
    user_id: int, action: str, limit: Tuple[int, int]
) -> Tuple[bool, int]:
    """
    Sliding-window limiter for non-command paths (callbacks, per-action budgets).

    Same Redis ZSET technique as utils.decorators.rate_limit, now sharing the
    same underlying helper. Returns (allowed, retry_after_seconds).
    """
    from Emilia.utils.decorators import check_rate_limit_zset

    max_actions, window = limit
    key = f"pl_limit:{action}:{user_id}"

    allowed, request_count = await check_rate_limit_zset(key, max_actions, window)
    if not allowed:
        return False, window

    return True, 0


def limit_message(action: str, retry_after: int) -> str:
    return (
        f"`•` Too many {action} requests.\n"
        f"`•` Try again in about {format_duration(retry_after)}."
    )


# Spam heuristics for user-supplied titles/descriptions. Deliberately narrow:
# the goal is to stop link-farm playlists and invisible-character padding, not
# to police wording.
_SPAM_MARKERS = (
    "t.me/joinchat",
    "t.me/+",
    "bit.ly/",
    "tinyurl.com/",
    "chat.whatsapp.com",
    "porn",
    "xxx ",
    "free money",
    "click here",
)

# Zero-width and bidi-override characters: used to smuggle text past filters and
# to break the layout of every list the title appears in.
_INVISIBLES = "​‌‍‎‏‪‫‬‭‮﻿"


def sanitize_text(text: str, max_len: int = 64) -> str:
    """Strip invisibles and collapse whitespace before anything is stored."""
    if not text:
        return ""
    cleaned = "".join(c for c in text if c not in _INVISIBLES)
    return " ".join(cleaned.split())[:max_len]


def is_spam(text: str) -> bool:
    """True if a title/description looks like advertising rather than a name."""
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _SPAM_MARKERS):
        return True
    # A name that is mostly URL is a promo slot, not a playlist title.
    if lowered.count("http") >= 2:
        return True
    return False


def validate_title(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (clean_title, error). Used by every path that accepts a user title.
    """
    clean = sanitize_text(text, max_len=64)
    if len(clean) < 1:
        return None, "That title is empty."
    if is_spam(clean):
        return None, "That title looks like spam. Pick something else."
    return clean, None

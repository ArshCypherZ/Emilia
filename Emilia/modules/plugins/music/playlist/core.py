"""
Core playlist operations: access control, ranking, duplicate detection.
"""

import asyncio
import math
import time
from typing import Dict, List, Optional, Tuple

import orjson

from Emilia import LOGGER, redis_client
from Emilia.mongo import playlists_mongo as db

# ---- Access control ---------------------------------------------------------

# Monochrome glyph per access mode. Deliberately no colour emoji anywhere in
# this feature — the whole UI is drawn from the Unicode symbol/geometric blocks
# so it renders identically on every Telegram client and never reflows a row.
MODE_GLYPH = {
    db.ACCESS_PRIVATE: "◌",
    db.ACCESS_UNLISTED: "◍",
    db.ACCESS_PUBLIC: "◯",
    db.ACCESS_SERVER: "▣",
    db.ACCESS_COLLAB: "◈",
}

MODE_LABEL = {
    db.ACCESS_PRIVATE: "Private",
    db.ACCESS_UNLISTED: "Unlisted",
    db.ACCESS_PUBLIC: "Public",
    db.ACCESS_SERVER: "Server",
    db.ACCESS_COLLAB: "Collaborative",
}


async def can_view(playlist: Dict, user_id: int, chat_id: Optional[int] = None) -> bool:
    """Check if user can view this playlist."""
    if not playlist:
        return False
    if playlist.get("banned"):
        return False

    mode = playlist.get("access_mode")
    owner = playlist.get("owner_id")

    if mode == db.ACCESS_PUBLIC or mode == db.ACCESS_UNLISTED:
        return True
    if user_id == owner:
        return True
    if user_id in playlist.get("editors", []):
        return True
    if mode == db.ACCESS_SERVER and chat_id == playlist.get("server_chat_id"):
        return True
    return False


async def can_edit(playlist: Dict, user_id: int) -> bool:
    """Check if user can modify this playlist."""
    if not playlist or playlist.get("banned"):
        return False
    owner = playlist.get("owner_id")
    if user_id == owner:
        return True
    if user_id in playlist.get("editors", []):
        return True
    return False


# ---- Duplicate detection ----------------------------------------------------


async def check_duplicate(
    playlist_id: str, track: Dict
) -> Tuple[bool, Optional[Dict]]:
    """
    Check if track already exists in playlist.
    Returns (is_duplicate, existing_song_doc).
    """
    video_id = track.get("video_id") or track.get("id")
    if not video_id:
        return False, None
    existing = await db.find_song(playlist_id, video_id)
    return (existing is not None), existing


# ---- Trending score engine --------------------------------------------------


def compute_trending_score(pl: Dict) -> float:
    """
    Trending Score = (plays + likes*2 + forks*3 + saves*1.5 + completion*10) * decay

    Decay: exponential with half-life of 7 days.
    Age is measured from `updated_at` (not created_at) so actively maintained
    playlists stay fresh.
    """
    if pl.get("song_count", 0) == 0:
        return 0.0

    plays = pl.get("plays", 0)
    likes = pl.get("likes", 0)
    saves = pl.get("saves", 0)
    forks = pl.get("forks", 0)
    completion_sum = pl.get("completion_sum", 0.0)
    completion_n = pl.get("completion_n", 0)

    completion_avg = (completion_sum / completion_n) if completion_n > 0 else 0.0

    engagement = plays + likes * 2 + forks * 3 + saves * 1.5 + completion_avg * 10

    now = time.time()
    updated_at = pl.get("updated_at", pl.get("created_at", now))
    age_days = (now - updated_at) / 86400.0

    # Half-life decay: after 7 days, score is cut in half
    half_life = 7.0
    decay = math.pow(0.5, age_days / half_life)

    return max(0.0, engagement * decay)


async def update_all_trending_scores(batch_size: int = 500):
    """
    Recalculate trending scores for all public playlists.
    Run as a background task every few hours.
    """
    LOGGER.info("[Playlists] Starting trending score update...")
    count = 0
    scores = {}

    async for pl in db.iter_rankable(batch=batch_size):
        score = compute_trending_score(pl)
        scores[pl["playlist_id"]] = score
        count += 1

        if len(scores) >= batch_size:
            await db.set_trending_scores(scores)
            scores.clear()

    if scores:
        await db.set_trending_scores(scores)

    LOGGER.info(f"[Playlists] Updated trending scores for {count} playlists.")


# ---- Song addition with duplicate prompt ------------------------------------


async def add_song_with_prompt(
    playlist_id: str, track: Dict, added_by: int
) -> Tuple[str, int, Optional[Dict]]:
    """
    Add a song, detecting duplicates.

    Returns:
        (status, position, existing_song)
        - status: "added", "duplicate", "full", "invalid"
        - position: 1-indexed position if added
        - existing_song: the conflicting doc if duplicate
    """
    video_id = track.get("video_id") or track.get("id")
    if not video_id:
        return "invalid", 0, None

    is_dup, existing = await check_duplicate(playlist_id, track)
    if is_dup:
        return "duplicate", 0, existing

    status, pos = await db.add_song(playlist_id, track, added_by)
    if status == "added":
        # Log activity
        await db.log_activity(
            playlist_id,
            added_by,
            "added_song",
            {"title": track.get("title"), "video_id": video_id},
        )
    return status, pos, None


async def replace_duplicate(
    playlist_id: str, video_id: str, track: Dict, user_id: int
) -> bool:
    """Replace existing song metadata (user chose 'Replace' on duplicate prompt)."""
    success = await db.replace_song(playlist_id, video_id, track, user_id)
    if success:
        await db.log_activity(
            playlist_id,
            user_id,
            "replaced_song",
            {"title": track.get("title"), "video_id": video_id},
        )
    return success


# ---- Bulk import ------------------------------------------------------------


async def import_tracks_bulk(
    playlist_id: str, tracks: List[Dict], user_id: int
) -> Tuple[int, int]:
    """
    Import many tracks at once (from Spotify/YouTube playlist).
    Returns (added_count, skipped_count).
    """
    if not tracks:
        return 0, 0

    added, skipped = await db.add_songs_bulk(playlist_id, tracks, user_id)
    if added > 0:
        await db.log_activity(
            playlist_id, user_id, "bulk_import", {"count": added}
        )
    return added, skipped


# ---- Fork -------------------------------------------------------------------


async def fork_playlist(
    source_id: str, user_id: int, new_title: Optional[str] = None
) -> Optional[str]:
    """
    Fork a playlist (copy all songs and metadata).
    Returns new playlist_id, or None on failure.
    """
    source = await db.get_playlist(source_id)
    if not source:
        return None

    title = new_title or f"{source['title']} (fork)"
    fork_root = source.get("fork_root") or source_id
    fork_gen = source.get("fork_generation", 0) + 1

    new_pl = await db.create_playlist(
        owner_id=user_id,
        title=title,
        access_mode=db.ACCESS_PRIVATE,
        description=f"Forked from: {source['title']}",
        forked_from=source_id,
        fork_generation=fork_gen,
        fork_root=fork_root,
    )
    if not new_pl:
        return None

    new_id = new_pl["playlist_id"]

    # Copy songs
    songs = await db.get_songs(source_id)
    if songs:
        await db.add_songs_bulk(new_id, songs, user_id)

    # Update fork counter on source
    await db.register_fork(source_id)
    await db.log_activity(source_id, user_id, "forked", {"new_id": new_id})

    return new_id


# ---- Discovery helpers ------------------------------------------------------


async def get_trending(limit: int = 20, skip: int = 0) -> List[Dict]:
    """Get trending public playlists."""
    return await db.get_trending(limit=limit, skip=skip)


# ---- Listening sessions -----------------------------------------------------

# Completion rate is one of the five inputs to the trending score, and it is the
# only one that can't be read off a button press: it needs to know how much of a
# playlist a chat actually sat through. A chat can only stream one thing at a
# time, so one Redis key per chat is enough state to answer that.
_SESSION_TTL = 6 * 3600  # a voice chat that has been idle this long is over


def _session_key(chat_id: int) -> str:
    return f"pl_session:{chat_id}"


async def session_start(chat_id: int, playlist_id: str, user_id: int, total: int) -> None:
    """Note that `chat_id` has just started listening to a playlist."""
    await redis_client.setex(
        _session_key(chat_id),
        _SESSION_TTL,
        orjson.dumps(
            {"pid": playlist_id, "user": user_id, "total": max(total, 1), "played": 0}
        ).decode(),
    )


async def session_track_finished(chat_id: int) -> None:
    """One more track of the current playlist reached its end."""
    raw = await redis_client.get(_session_key(chat_id))
    if not raw:
        return
    state = orjson.loads(raw)
    state["played"] += 1
    await redis_client.setex(
        _session_key(chat_id), _SESSION_TTL, orjson.dumps(state).decode()
    )


# ---- "Which group is this user listening in?" --------------------------------

# Playback only exists in group voice chats, but a user's library lives in PM.
# To make Play work from either place we need the reverse of _session_key: given
# a user, the group they were last active in. Recorded when they open the
# playlist menu from a group's player, which is exactly the gesture that means
# "this is the chat I'm listening in".
_ACTIVE_GROUP_TTL = 6 * 3600  # matches _SESSION_TTL: same notion of "still here"


def _active_group_key(user_id: int) -> str:
    return f"pl_group:{user_id}"


async def remember_group(user_id: int, chat_id: int) -> None:
    """Note the group a user is driving playlists from."""
    if chat_id >= 0:  # PM ids are positive; there is nothing to remember
        return
    await redis_client.setex(_active_group_key(user_id), _ACTIVE_GROUP_TTL, str(chat_id))


async def recall_group(user_id: int) -> Optional[int]:
    """The group this user was last active in, or None if we don't know."""
    raw = await redis_client.get(_active_group_key(user_id))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def session_finish(chat_id: int) -> None:
    """
    The queue ran dry or the call ended: bank what fraction was heard.

    GETDEL, so a stream-end and a chat-left arriving together can't record the
    same session twice.
    """
    raw = await redis_client.getdel(_session_key(chat_id))
    if not raw:
        return
    state = orjson.loads(raw)
    completion = min(1.0, state["played"] / state["total"])
    await db.record_play(state["pid"], state["user"], completion)


# ---- Background tasks -------------------------------------------------------


async def start_trending_refresh_task(interval: int = 3600 * 4):
    """
    Periodically recalculate trending scores.
    Run this at startup via `spawn()`.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            await update_all_trending_scores()
        except Exception as e:
            LOGGER.error(f"[Playlists] Trending refresh failed: {e}")


# ---- User-facing helpers ----------------------------------------------------


def format_duration(seconds: int) -> str:
    """Format duration as H:MM:SS or M:SS."""
    if seconds <= 0:
        return "0:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


_BAR_FILLED = "▰"
_BAR_EMPTY = "▱"


def render_bar(value: float, maximum: float, width: int = 10) -> str:
    """Monochrome ▰/▱ meter shared by the stats panel and import progress."""
    if maximum <= 0:
        return _BAR_EMPTY * width
    filled = int(round(min(1.0, value / maximum) * width))
    return _BAR_FILLED * filled + _BAR_EMPTY * (width - filled)


def build_playlist_caption(pl: Dict) -> str:
    """Rich caption for playlist detail view."""
    title = pl.get("title", "Untitled")
    desc = pl.get("description", "")
    count = pl.get("song_count", 0)
    duration = format_duration(pl.get("duration_total", 0))

    mode = pl.get("access_mode", "private")
    mode_label = MODE_LABEL.get(mode, "Private")

    lines = [
        f"**{title}**",
        f"`•` **Songs:** {count}",
        f"`•` **Duration:** {duration}",
        f"`•` **Access:** {MODE_GLYPH.get(mode, '')} {mode_label}",
    ]

    if desc:
        lines.append(f"`•` **Description:** {desc}")

    plays = pl.get("plays", 0)
    likes = pl.get("likes", 0)
    saves = pl.get("saves", 0)
    forks = pl.get("forks", 0)
    if any([plays, likes, saves, forks]):
        lines.append(
            f"`•` **Stats:** {plays} plays, {likes} likes, {saves} saves, {forks} forks"
        )

    forked_from = pl.get("forked_from")
    if forked_from:
        gen = pl.get("fork_generation", 1)
        lines.append(f"`•` **Forked from:** `{forked_from}` (gen {gen})")

    return "\n".join(lines)

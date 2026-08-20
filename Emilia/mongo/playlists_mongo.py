"""
MongoDB layer for Global Social Playlists.

Collections
-----------
``playlists``            One doc per playlist: metadata, access control, counters.
``playlist_songs``       One doc per (playlist, track). Carries a cached copy of
                         the track metadata so rendering a playlist never needs
                         to hit yt-dlp.
``playlist_likes``       Per-user like/save edges. Kept out of the playlist doc
                         so the counters can't be inflated by repeat taps and so
                         "did I like this?" is an indexed point lookup.
``playlist_activity``    Capped-by-hand social feed ("Arsh added X").
``playlist_reports``     Abuse reports awaiting moderator action.
``playlist_plays``       Rolling play/completion samples feeding the ranking
                         engine's completion-rate term.

Counters (plays/likes/saves/forks) are denormalised onto the playlist doc so the
trending pipeline is a single indexed sort rather than a per-playlist fan-out.
"""

import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from pymongo import UpdateOne
from pymongo.errors import DuplicateKeyError

from Emilia import db

playlists = db.playlists
playlist_songs = db.playlist_songs
playlist_likes = db.playlist_likes
playlist_activity = db.playlist_activity
playlist_reports = db.playlist_reports
playlist_plays = db.playlist_plays

# ---- Access modes -----------------------------------------------------------

ACCESS_PRIVATE = "private"
ACCESS_UNLISTED = "unlisted"
ACCESS_PUBLIC = "public"
ACCESS_SERVER = "server"
ACCESS_COLLAB = "collab"

ACCESS_MODES = (
    ACCESS_PRIVATE,
    ACCESS_UNLISTED,
    ACCESS_PUBLIC,
    ACCESS_SERVER,
    ACCESS_COLLAB,
)

# Discovery (search / trending) only ever surfaces these.
DISCOVERABLE_MODES = (ACCESS_PUBLIC,)

LIKED_SONGS_TITLE = "Liked Songs"

MAX_SONGS_PER_PLAYLIST = 1000
MAX_PLAYLISTS_PER_USER = 100
ACTIVITY_KEEP = 100

# Short, URL-safe, unambiguous. Excludes look-alikes (0/O, 1/l/I) so a playlist
# id read off a QR code or dictated aloud round-trips.
_ID_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
_ID_LEN = 10


def _new_playlist_id() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LEN))


def _now() -> float:
    return time.time()


# ---- Playlist CRUD ----------------------------------------------------------


async def create_playlist(
    owner_id: int,
    title: str,
    access_mode: str = ACCESS_PRIVATE,
    description: str = "",
    server_chat_id: Optional[int] = None,
    forked_from: Optional[str] = None,
    fork_generation: int = 0,
    fork_root: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Insert a playlist and return the stored document.

    Returns ``None`` if the owner is already at ``MAX_PLAYLISTS_PER_USER``.
    """
    if access_mode not in ACCESS_MODES:
        access_mode = ACCESS_PRIVATE

    owned = await playlists.count_documents({"owner_id": owner_id})
    if owned >= MAX_PLAYLISTS_PER_USER:
        return None

    now = _now()
    for _ in range(5):  # retry on the (vanishingly unlikely) id collision
        doc = {
            "playlist_id": _new_playlist_id(),
            "owner_id": owner_id,
            "title": title,
            "description": description,
            "access_mode": access_mode,
            "server_chat_id": server_chat_id,
            "editors": [],
            "created_at": now,
            "updated_at": now,
            "song_count": 0,
            "duration_total": 0,
            "thumbnail": None,
            # Denormalised social counters, source of truth for ranking.
            "plays": 0,
            "likes": 0,
            "saves": 0,
            "forks": 0,
            "completion_sum": 0.0,
            "completion_n": 0,
            "trending_score": 0.0,
            "scored_at": 0.0,
            # Fork lineage. `fork_root` lets the whole tree be queried with one
            # indexed lookup instead of walking parents one hop at a time.
            "forked_from": forked_from,
            "fork_generation": fork_generation,
            "fork_root": fork_root,
            "banned": False,
        }
        try:
            await playlists.insert_one(doc)
            doc.pop("_id", None)
            return doc
        except DuplicateKeyError:
            continue
    return None


async def get_playlist(playlist_id: str) -> Optional[Dict[str, Any]]:
    return await playlists.find_one({"playlist_id": playlist_id}, {"_id": 0})


async def get_playlists_bulk(playlist_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch many playlists at once, keyed by id (avoids N round-trips)."""
    if not playlist_ids:
        return {}
    cursor = playlists.find({"playlist_id": {"$in": playlist_ids}}, {"_id": 0})
    return {d["playlist_id"]: d async for d in cursor}


async def update_playlist(playlist_id: str, updates: Dict[str, Any]) -> None:
    updates = dict(updates)
    updates["updated_at"] = _now()
    await playlists.update_one({"playlist_id": playlist_id}, {"$set": updates})


async def delete_playlist(playlist_id: str) -> None:
    """Delete a playlist and every row that hangs off it."""
    await playlists.delete_one({"playlist_id": playlist_id})
    await playlist_songs.delete_many({"playlist_id": playlist_id})
    await playlist_activity.delete_many({"playlist_id": playlist_id})
    await playlist_likes.delete_many({"playlist_id": playlist_id})
    await playlist_plays.delete_many({"playlist_id": playlist_id})
    # Orphaned forks keep their lineage pointer; the UI renders a missing parent
    # as "(deleted)" rather than us rewriting history.


async def count_user_playlists(user_id: int) -> int:
    return await playlists.count_documents({"owner_id": user_id})


async def get_user_playlists(
    user_id: int,
    include_editable: bool = True,
    skip: int = 0,
    limit: int = MAX_PLAYLISTS_PER_USER,
) -> List[Dict[str, Any]]:
    """Playlists the user owns, plus ones they can edit as a collaborator."""
    if include_editable:
        query = {"$or": [{"owner_id": user_id}, {"editors": user_id}]}
    else:
        query = {"owner_id": user_id}
    cursor = (
        playlists.find(query, {"_id": 0})
        .sort("updated_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_server_playlists(
    chat_id: int, skip: int = 0, limit: int = 50
) -> List[Dict[str, Any]]:
    cursor = (
        playlists.find(
            {"access_mode": ACCESS_SERVER, "server_chat_id": chat_id, "banned": False},
            {"_id": 0},
        )
        .sort("updated_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_or_create_liked_playlist(owner_id: int) -> Optional[Dict[str, Any]]:
    """The implicit per-user "Liked Songs" playlist backing the ❤ button.

    Uses a single atomic upsert so two concurrent ❤ taps can't create two
    playlists (the unique index on ``(owner_id, is_liked)`` is what makes this
    safe; see ``create_playlist_indexes``).
    """
    existing = await playlists.find_one({"owner_id": owner_id, "is_liked": True}, {"_id": 0})
    if existing:
        return existing

    now = _now()
    try:
        doc = await playlists.find_one_and_update(
            {"owner_id": owner_id, "is_liked": True},
            {
                "$setOnInsert": {
                    "playlist_id": _new_playlist_id(),
                    "owner_id": owner_id,
                    "title": LIKED_SONGS_TITLE,
                    "description": "Tracks you saved with the ❤ button.",
                    "access_mode": ACCESS_PRIVATE,
                    "server_chat_id": None,
                    "editors": [],
                    "created_at": now,
                    "updated_at": now,
                    "song_count": 0,
                    "duration_total": 0,
                    "thumbnail": None,
                    "plays": 0,
                    "likes": 0,
                    "saves": 0,
                    "forks": 0,
                    "completion_sum": 0.0,
                    "completion_n": 0,
                    "trending_score": 0.0,
                    "scored_at": 0.0,
                    "forked_from": None,
                    "fork_generation": 0,
                    "fork_root": None,
                    "banned": False,
                }
            },
            upsert=True,
            return_document=True,
            projection={"_id": 0},
        )
        return doc
    except DuplicateKeyError:
        return await playlists.find_one({"owner_id": owner_id, "is_liked": True}, {"_id": 0})


# ---- Songs ------------------------------------------------------------------


def _song_doc(playlist_id: str, position: int, track: Dict[str, Any], added_by: int) -> Dict[str, Any]:
    return {
        "playlist_id": playlist_id,
        "video_id": track.get("video_id") or track.get("id"),
        "position": position,
        "added_at": _now(),
        "added_by": added_by,
        # Cached track metadata — rendering never re-resolves.
        "title": track.get("title") or "Unknown",
        "duration": int(track.get("duration") or 0),
        "thumbnail": track.get("thumbnail"),
        "uploader": track.get("uploader"),
        "webpage_url": track.get("webpage_url"),
        "source": track.get("source", "youtube"),
    }


async def find_song(playlist_id: str, video_id: str) -> Optional[Dict[str, Any]]:
    return await playlist_songs.find_one(
        {"playlist_id": playlist_id, "video_id": video_id}, {"_id": 0}
    )


async def add_song(
    playlist_id: str, track: Dict[str, Any], added_by: int
) -> Tuple[str, int]:
    """Append one track.

    Returns ``(status, position)`` where status is ``"added"``, ``"duplicate"``
    (caller should prompt Replace/Skip) or ``"full"``.
    """
    video_id = track.get("video_id") or track.get("id")
    if not video_id:
        return "invalid", 0

    pl = await playlists.find_one(
        {"playlist_id": playlist_id}, {"song_count": 1, "_id": 0}
    )
    if pl and pl.get("song_count", 0) >= MAX_SONGS_PER_PLAYLIST:
        return "full", 0

    # Duplicates are caught authoritatively by the unique index below
    # (DuplicateKeyError); no need for a pre-check round-trip. Callers that want
    # the conflicting doc for a replace-prompt use check_duplicate() first.
    last = await playlist_songs.find_one(
        {"playlist_id": playlist_id}, {"position": 1}, sort=[("position", -1)]
    )
    position = (last["position"] + 1) if last else 1

    try:
        await playlist_songs.insert_one(_song_doc(playlist_id, position, track, added_by))
    except DuplicateKeyError:
        # Lost a race against a concurrent add of the same track.
        return "duplicate", 0

    await playlists.update_one(
        {"playlist_id": playlist_id},
        {
            "$inc": {"song_count": 1, "duration_total": int(track.get("duration") or 0)},
            "$set": {"updated_at": _now()},
        },
    )
    await _backfill_thumbnail(playlist_id, track.get("thumbnail"))
    return "added", position


async def add_songs_bulk(
    playlist_id: str, tracks: List[Dict[str, Any]], added_by: int
) -> Tuple[int, int]:
    """Insert many tracks in one round-trip. Returns ``(added, skipped)``.

    Used by the import engine and by forking, where per-track inserts would mean
    hundreds of sequential round-trips.
    """
    if not tracks:
        return 0, 0

    pl = await playlists.find_one(
        {"playlist_id": playlist_id}, {"song_count": 1, "_id": 0}
    )
    current = pl.get("song_count", 0) if pl else 0
    room = max(0, MAX_SONGS_PER_PLAYLIST - current)
    if room == 0:
        return 0, len(tracks)

    existing_ids = set()
    cursor = playlist_songs.find({"playlist_id": playlist_id}, {"video_id": 1, "_id": 0})
    async for row in cursor:
        existing_ids.add(row.get("video_id"))

    last = await playlist_songs.find_one(
        {"playlist_id": playlist_id}, {"position": 1}, sort=[("position", -1)]
    )
    position = (last["position"] + 1) if last else 1

    docs, skipped, added_duration = [], 0, 0
    for track in tracks:
        video_id = track.get("video_id") or track.get("id")
        if not video_id or video_id in existing_ids or len(docs) >= room:
            skipped += 1
            continue
        existing_ids.add(video_id)
        docs.append(_song_doc(playlist_id, position, track, added_by))
        added_duration += int(track.get("duration") or 0)
        position += 1

    if not docs:
        return 0, skipped

    try:
        await playlist_songs.insert_many(docs, ordered=False)
    except Exception:
        # ordered=False means partial success is normal on a duplicate race;
        # recount below rather than trusting the local tally.
        pass

    real_count = await playlist_songs.count_documents({"playlist_id": playlist_id})
    agg = playlist_songs.aggregate(
        [
            {"$match": {"playlist_id": playlist_id}},
            {"$group": {"_id": None, "total": {"$sum": "$duration"}}},
        ]
    )
    total_duration = 0
    async for row in agg:
        total_duration = row.get("total", 0)

    await playlists.update_one(
        {"playlist_id": playlist_id},
        {
            "$set": {
                "song_count": real_count,
                "duration_total": total_duration,
                "updated_at": _now(),
            }
        },
    )
    await _backfill_thumbnail(playlist_id, docs[0].get("thumbnail"))
    return len(docs), skipped


async def replace_song(playlist_id: str, video_id: str, track: Dict[str, Any], added_by: int) -> bool:
    """Overwrite the cached metadata of an existing entry, keeping its slot.

    This is the "Replace" branch of the duplicate prompt.
    """
    old = await find_song(playlist_id, video_id)
    if not old:
        return False
    new_duration = int(track.get("duration") or 0)
    await playlist_songs.update_one(
        {"playlist_id": playlist_id, "video_id": video_id},
        {
            "$set": {
                "title": track.get("title") or old.get("title"),
                "duration": new_duration,
                "thumbnail": track.get("thumbnail") or old.get("thumbnail"),
                "uploader": track.get("uploader") or old.get("uploader"),
                "webpage_url": track.get("webpage_url") or old.get("webpage_url"),
                "added_at": _now(),
                "added_by": added_by,
            }
        },
    )
    delta = new_duration - int(old.get("duration") or 0)
    if delta:
        await playlists.update_one(
            {"playlist_id": playlist_id},
            {"$inc": {"duration_total": delta}, "$set": {"updated_at": _now()}},
        )
    return True


async def get_songs(
    playlist_id: str, skip: int = 0, limit: int = MAX_SONGS_PER_PLAYLIST
) -> List[Dict[str, Any]]:
    cursor = (
        playlist_songs.find({"playlist_id": playlist_id}, {"_id": 0})
        .sort("position", 1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def remove_song(playlist_id: str, position: int) -> Optional[Dict[str, Any]]:
    """Remove by 1-based position and close the gap. Returns the removed doc."""
    song = await playlist_songs.find_one(
        {"playlist_id": playlist_id, "position": position}, {"_id": 0}
    )
    if not song:
        return None

    await playlist_songs.delete_one({"playlist_id": playlist_id, "position": position})
    await playlist_songs.update_many(
        {"playlist_id": playlist_id, "position": {"$gt": position}},
        {"$inc": {"position": -1}},
    )
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {
            "$inc": {"song_count": -1, "duration_total": -int(song.get("duration") or 0)},
            "$set": {"updated_at": _now()},
        },
    )
    return song


async def move_song(playlist_id: str, frm: int, to: int) -> bool:
    """Reorder within the playlist, shifting the span between the two slots."""
    if frm == to:
        return True
    song = await playlist_songs.find_one({"playlist_id": playlist_id, "position": frm})
    if not song:
        return False
    count = await playlist_songs.count_documents({"playlist_id": playlist_id})
    if not 1 <= to <= count:
        return False

    # Park the moved row outside the valid range so the shift can't collide with
    # it under the unique (playlist_id, position) index.
    await playlist_songs.update_one({"_id": song["_id"]}, {"$set": {"position": -1}})
    if frm < to:
        await playlist_songs.update_many(
            {"playlist_id": playlist_id, "position": {"$gt": frm, "$lte": to}},
            {"$inc": {"position": -1}},
        )
    else:
        await playlist_songs.update_many(
            {"playlist_id": playlist_id, "position": {"$gte": to, "$lt": frm}},
            {"$inc": {"position": 1}},
        )
    await playlist_songs.update_one({"_id": song["_id"]}, {"$set": {"position": to}})
    await playlists.update_one(
        {"playlist_id": playlist_id}, {"$set": {"updated_at": _now()}}
    )
    return True


async def clear_songs(playlist_id: str) -> None:
    await playlist_songs.delete_many({"playlist_id": playlist_id})
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {"$set": {"song_count": 0, "duration_total": 0, "updated_at": _now()}},
    )


async def _backfill_thumbnail(playlist_id: str, thumbnail: Optional[str]) -> None:
    """Adopt the first added track's art as the playlist cover."""
    if not thumbnail:
        return
    await playlists.update_one(
        {"playlist_id": playlist_id, "thumbnail": None}, {"$set": {"thumbnail": thumbnail}}
    )


# ---- Collaborators ----------------------------------------------------------


async def add_editor(playlist_id: str, user_id: int) -> None:
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {"$addToSet": {"editors": user_id}, "$set": {"updated_at": _now()}},
    )


async def remove_editor(playlist_id: str, user_id: int) -> None:
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {"$pull": {"editors": user_id}, "$set": {"updated_at": _now()}},
    )


# ---- Likes / saves ----------------------------------------------------------


async def _toggle_edge(playlist_id: str, user_id: int, kind: str, counter: str) -> bool:
    """Add or remove a like/save edge. Returns the resulting state.

    The unique index on ``(playlist_id, user_id, kind)`` makes the counter
    increment exactly-once per user: a repeat tap deletes instead of inflating.
    """
    existing = await playlist_likes.find_one(
        {"playlist_id": playlist_id, "user_id": user_id, "kind": kind}
    )
    if existing:
        await playlist_likes.delete_one({"_id": existing["_id"]})
        await playlists.update_one({"playlist_id": playlist_id}, {"$inc": {counter: -1}})
        return False
    try:
        await playlist_likes.insert_one(
            {
                "playlist_id": playlist_id,
                "user_id": user_id,
                "kind": kind,
                "created_at": _now(),
            }
        )
    except DuplicateKeyError:
        return True
    await playlists.update_one({"playlist_id": playlist_id}, {"$inc": {counter: 1}})
    return True


async def toggle_like(playlist_id: str, user_id: int) -> bool:
    return await _toggle_edge(playlist_id, user_id, "like", "likes")


async def toggle_save(playlist_id: str, user_id: int) -> bool:
    return await _toggle_edge(playlist_id, user_id, "save", "saves")


async def has_edge(playlist_id: str, user_id: int, kind: str) -> bool:
    return (
        await playlist_likes.count_documents(
            {"playlist_id": playlist_id, "user_id": user_id, "kind": kind}, limit=1
        )
        > 0
    )


async def get_saved_playlists(
    user_id: int, skip: int = 0, limit: int = 50
) -> List[Dict[str, Any]]:
    cursor = (
        playlist_likes.find({"user_id": user_id, "kind": "save"}, {"playlist_id": 1, "_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    ids = [row["playlist_id"] async for row in cursor]
    found = await get_playlists_bulk(ids)
    return [found[i] for i in ids if i in found]


# ---- Plays / completion -----------------------------------------------------


async def record_play(playlist_id: str, user_id: int, completion: float) -> None:
    """Record one listen. ``completion`` is the fraction of the playlist heard.

    Completion feeds the ranking engine as a rolling mean, stored as
    (sum, n) so the average updates without re-reading the samples.
    """
    completion = max(0.0, min(1.0, float(completion)))
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {
            "$inc": {
                "plays": 1,
                "completion_sum": completion,
                "completion_n": 1,
            }
        },
    )
    await playlist_plays.insert_one(
        {
            "playlist_id": playlist_id,
            "user_id": user_id,
            "completion": completion,
            "created_at": _now(),
        }
    )


# ---- Activity feed ----------------------------------------------------------


async def log_activity(
    playlist_id: str, user_id: int, action: str, meta: Optional[Dict[str, Any]] = None
) -> None:
    """Append a feed entry, trimming the tail past ``ACTIVITY_KEEP``."""
    await playlist_activity.insert_one(
        {
            "playlist_id": playlist_id,
            "user_id": user_id,
            "action": action,
            "meta": meta or {},
            "created_at": _now(),
        }
    )
    count = await playlist_activity.count_documents({"playlist_id": playlist_id})
    if count > ACTIVITY_KEEP:
        stale = (
            await playlist_activity.find({"playlist_id": playlist_id}, {"_id": 1})
            .sort("created_at", 1)
            .limit(count - ACTIVITY_KEEP)
            .to_list(length=count)
        )
        if stale:
            await playlist_activity.delete_many({"_id": {"$in": [d["_id"] for d in stale]}})


async def get_activity(playlist_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    cursor = (
        playlist_activity.find({"playlist_id": playlist_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


# ---- Fork lineage -----------------------------------------------------------


async def register_fork(source_id: str) -> None:
    await playlists.update_one({"playlist_id": source_id}, {"$inc": {"forks": 1}})


async def get_fork_children(playlist_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    cursor = (
        playlists.find({"forked_from": playlist_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_fork_ancestors(playlist_id: str, max_depth: int = 20) -> List[Dict[str, Any]]:
    """Walk parent pointers from the playlist up to the root, nearest first."""
    chain: List[Dict[str, Any]] = []
    seen = {playlist_id}
    current = await get_playlist(playlist_id)
    while current and current.get("forked_from") and len(chain) < max_depth:
        parent_id = current["forked_from"]
        if parent_id in seen:  # defensive: never loop on corrupt lineage
            break
        seen.add(parent_id)
        parent = await get_playlist(parent_id)
        if not parent:
            chain.append({"playlist_id": parent_id, "title": None, "missing": True})
            break
        chain.append(parent)
        current = parent
    return chain


# ---- Discovery / ranking ----------------------------------------------------


async def iter_rankable(batch: int = 500):
    """Yield playlists eligible for trending scoring."""
    cursor = playlists.find(
        {"access_mode": {"$in": list(DISCOVERABLE_MODES)}, "banned": False},
        {
            "_id": 0,
            "playlist_id": 1,
            "plays": 1,
            "likes": 1,
            "saves": 1,
            "forks": 1,
            "completion_sum": 1,
            "completion_n": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).batch_size(batch)
    async for doc in cursor:
        yield doc


async def set_trending_scores(scores: Dict[str, float]) -> None:
    """Persist a batch of computed scores."""
    if not scores:
        return
    now = _now()
    ops = [
        UpdateOne(
            {"playlist_id": pid},
            {"$set": {"trending_score": score, "scored_at": now}},
        )
        for pid, score in scores.items()
    ]
    for chunk_start in range(0, len(ops), 500):
        await playlists.bulk_write(ops[chunk_start : chunk_start + 500], ordered=False)


async def get_trending(limit: int = 20, skip: int = 0) -> List[Dict[str, Any]]:
    cursor = (
        playlists.find(
            {"access_mode": ACCESS_PUBLIC, "banned": False, "song_count": {"$gt": 0}},
            {"_id": 0},
        )
        .sort("trending_score", -1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_recent(limit: int = 20, skip: int = 0) -> List[Dict[str, Any]]:
    """Browse recent public playlists by creation/update time."""
    cursor = (
        playlists.find(
            {"access_mode": ACCESS_PUBLIC, "banned": False, "song_count": {"$gt": 0}},
            {"_id": 0},
        )
        .sort("updated_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def search(query: str, limit: int = 20, skip: int = 0) -> List[Dict[str, Any]]:
    """Full-text search over public playlists, ranked by relevance × trending.

    Falls back to a prefix regex when the text index is unavailable (e.g. a
    fresh deploy where ``create_playlist_indexes`` hasn't run yet).
    """
    try:
        cursor = (
            playlists.find(
                {
                    "$text": {"$search": query},
                    "access_mode": ACCESS_PUBLIC,
                    "banned": False,
                },
                {"_id": 0, "score": {"$meta": "textScore"}},
            )
            .sort([("score", {"$meta": "textScore"}), ("trending_score", -1)])
            .skip(skip)
            .limit(limit)
        )
        results = await cursor.to_list(length=limit)
        if results:
            return results
    except Exception:
        pass

    import re as _re

    safe = _re.escape(query)
    cursor = (
        playlists.find(
            {
                "access_mode": ACCESS_PUBLIC,
                "banned": False,
                "$or": [
                    {"title": {"$regex": safe, "$options": "i"}},
                    {"description": {"$regex": safe, "$options": "i"}},
                ],
            },
            {"_id": 0},
        )
        .sort("trending_score", -1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


# ---- Abuse ------------------------------------------------------------------


async def report_playlist(playlist_id: str, reporter_id: int, reason: str) -> bool:
    """File a report. Returns False if this user already reported this playlist."""
    try:
        await playlist_reports.insert_one(
            {
                "playlist_id": playlist_id,
                "reporter_id": reporter_id,
                "reason": reason[:500],
                "created_at": _now(),
                "resolved": False,
            }
        )
        return True
    except DuplicateKeyError:
        return False


async def get_open_reports(limit: int = 50) -> List[Dict[str, Any]]:
    cursor = (
        playlist_reports.find({"resolved": False}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def resolve_reports(playlist_id: str) -> None:
    await playlist_reports.update_many(
        {"playlist_id": playlist_id}, {"$set": {"resolved": True}}
    )


async def set_banned(playlist_id: str, banned: bool) -> None:
    await playlists.update_one(
        {"playlist_id": playlist_id}, {"$set": {"banned": banned, "updated_at": _now()}}
    )


# ---- Indexes ----------------------------------------------------------------


async def create_playlist_indexes() -> None:
    """Create the indexes this module's queries assume.

    Called from ``Emilia.create_indexes`` at startup; safe to re-run.
    """
    from Emilia import LOGGER

    try:
        await playlists.create_index([("playlist_id", 1)], unique=True)
        await playlists.create_index([("owner_id", 1), ("updated_at", -1)])
        await playlists.create_index(
            [("access_mode", 1), ("trending_score", -1)]
        )
        # Backs the "Browse" feed: recent public playlists by update time.
        await playlists.create_index(
            [("access_mode", 1), ("updated_at", -1)]
        )
        await playlists.create_index([("server_chat_id", 1)], sparse=True)
        await playlists.create_index([("editors", 1)])
        await playlists.create_index([("forked_from", 1)], sparse=True)
        await playlists.create_index([("fork_root", 1)], sparse=True)
        # One implicit "Liked Songs" per user — this is what makes the upsert in
        # get_or_create_liked_playlist race-safe.
        await playlists.create_index(
            [("owner_id", 1), ("is_liked", 1)],
            unique=True,
            partialFilterExpression={"is_liked": True},
        )
        try:
            await playlists.create_index(
                [("title", "text"), ("description", "text")],
                weights={"title": 10, "description": 3},
                name="playlist_text",
            )
        except Exception as e:
            LOGGER.warning(f"playlist text index: {e}")

        await playlist_songs.create_index(
            [("playlist_id", 1), ("position", 1)], unique=True
        )
        await playlist_songs.create_index(
            [("playlist_id", 1), ("video_id", 1)], unique=True
        )
        await playlist_songs.create_index([("video_id", 1)])

        await playlist_likes.create_index(
            [("playlist_id", 1), ("user_id", 1), ("kind", 1)],
            unique=True,
        )
        await playlist_likes.create_index(
            [("user_id", 1), ("kind", 1), ("created_at", -1)]
        )

        await playlist_activity.create_index(
            [("playlist_id", 1), ("created_at", -1)]
        )
        await playlist_reports.create_index(
            [("playlist_id", 1), ("reporter_id", 1)], unique=True
        )
        await playlist_reports.create_index([("resolved", 1), ("created_at", -1)])

        # Play samples are only needed for the rolling window; expire them so the
        # collection can't grow without bound.
        await playlist_plays.create_index([("playlist_id", 1)])
        await playlist_plays.create_index(
            [("created_at", 1)], expireAfterSeconds=60 * 60 * 24 * 30
        )
        LOGGER.info("Playlist indexes created successfully.")
    except Exception as e:
        LOGGER.warning(f"Playlist index creation: {e}")

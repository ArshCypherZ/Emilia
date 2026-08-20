"""
Social graph: activity feeds, fork lineage, and statistics rendering.
"""

import time
from typing import Dict, List

from Emilia import LOGGER, pgram
from Emilia.modules.plugins.music.playlist.core import format_duration, render_bar
from Emilia.mongo import playlists_mongo as db
from Emilia.utils.cache import SimpleCache

# Display names are resolved per user_id for every feed row. Without a cache a
# 20-row feed would fire 20 get_users calls; with one it's usually zero.
name_cache = SimpleCache(default_ttl=3600, namespace="pl_names")

MAX_LINEAGE_DEPTH = 10


async def resolve_name(user_id: int) -> str:
    """Best-effort display name for a user id."""
    key = str(user_id)
    cached = await name_cache.get(key)
    if cached:
        return cached

    name = f"User {user_id}"
    try:
        user = await pgram.get_users(user_id)
        if user:
            name = user.first_name or user.username or name
    except Exception:
        # Deleted account, or never seen by this bot — fall through to the id.
        pass

    await name_cache.set(key, name)
    return name


async def resolve_names(user_ids: List[int]) -> Dict[int, str]:
    """Resolve many ids, de-duplicated."""
    unique = list({uid for uid in user_ids if uid})
    out = {}
    for uid in unique:
        out[uid] = await resolve_name(uid)
    return out


# ---- Activity feed ---------------------------------------------------------

_ACTION_TEMPLATES = {
    "created": "created this playlist",
    "added_song": "added **{title}**",
    "replaced_song": "replaced **{title}**",
    "removed_song": "removed **{title}**",
    "bulk_import": "imported **{count}** tracks",
    "renamed": "renamed it to **{title}**",
    "described": "updated the description",
    "access_changed": "set access to **{mode}**",
    "editor_added": "added **{name}** as an editor",
    "editor_removed": "removed **{name}** as an editor",
    "forked": "forked this playlist",
    "cleared": "cleared every song",
    "moved_song": "reordered **{title}**",
}


def _relative_time(ts: float) -> str:
    """Compact age string: 3m, 5h, 2d."""
    delta = max(0, int(time.time() - ts))
    if delta < 60:
        return "now"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    if delta < 86400 * 30:
        return f"{delta // 86400}d"
    return f"{delta // (86400 * 30)}mo"


def _describe(entry: Dict) -> str:
    action = entry.get("action", "")
    meta = entry.get("meta") or {}
    template = _ACTION_TEMPLATES.get(action)
    if not template:
        return action.replace("_", " ") or "did something"

    title = meta.get("title") or "a track"
    if len(title) > 40:
        title = title[:39] + "…"

    try:
        return template.format(
            title=title,
            count=meta.get("count", 0),
            mode=meta.get("mode", "private"),
            name=meta.get("name", "someone"),
        )
    except Exception:
        return action.replace("_", " ")


async def render_activity_feed(playlist_id: str, limit: int = 20) -> str:
    """Render the in-playlist activity feed."""
    entries = await db.get_activity(playlist_id, limit=limit)
    if not entries:
        return "**◌ Activity**\n\n_Nothing has happened here yet._"

    names = await resolve_names([e.get("user_id") for e in entries])

    lines = ["**◌ Activity**", ""]
    for e in entries:
        who = names.get(e.get("user_id"), "Someone")
        when = _relative_time(e.get("created_at", time.time()))
        lines.append(f"`{when:>4}` **{who}** {_describe(e)}")

    return "\n".join(lines)


# ---- Fork lineage ----------------------------------------------------------


async def render_lineage(playlist_id: str) -> str:
    """
    Render fork lineage: ancestors above, direct forks below.

    The chain is walked with a depth cap. Ancestry is a tree, but a corrupt
    `forked_from` pointer could in principle form a cycle, and an unbounded walk
    would hang the handler rather than just showing a short list.
    """
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return "**⑂ Lineage**\n\n_Playlist not found._"

    lines = ["**⑂ Fork lineage**", ""]

    ancestors = await db.get_fork_ancestors(playlist_id, max_depth=MAX_LINEAGE_DEPTH)
    if ancestors:
        # get_fork_ancestors walks upward; show it root-first so the tree reads
        # top-down like a git history.
        for depth, anc in enumerate(reversed(ancestors)):
            indent = "  " * depth
            # A missing ancestor is a real state: the parent was deleted after
            # this playlist forked from it. get_fork_ancestors marks those with
            # title=None rather than dropping them, so the chain stays honest.
            title = anc.get("title") or "_(deleted)_"
            lines.append(f"`{indent}├─` **{title}** `({anc['playlist_id']})`")
        indent = "  " * len(ancestors)
        lines.append(
            f"`{indent}└─` **{pl.get('title', 'Untitled')}** ← _you are here_"
        )
    else:
        lines.append(f"`●` **{pl.get('title', 'Untitled')}** — original, not a fork")

    gen = pl.get("fork_generation", 0)
    if gen:
        lines.append("")
        lines.append(f"`•` **Generation:** {gen}")

    children = await db.get_fork_children(playlist_id, limit=10)
    lines.append("")
    if children:
        lines.append(f"**Forks of this playlist** ({pl.get('forks', 0)})")
        for c in children:
            lines.append(
                f"`  ↳` **{c.get('title', 'Untitled')}** — "
                f"{c.get('song_count', 0)} songs"
            )
        if pl.get("forks", 0) > len(children):
            lines.append(f"`  ⋮` and {pl['forks'] - len(children)} more")
    else:
        lines.append("_No one has forked this yet._")

    return "\n".join(lines)


# ---- Statistics ------------------------------------------------------------


async def render_stats(playlist_id: str) -> str:
    """Full statistics panel for one playlist."""
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return "**◫ Stats**\n\n_Playlist not found._"

    plays = pl.get("plays", 0)
    likes = pl.get("likes", 0)
    saves = pl.get("saves", 0)
    forks = pl.get("forks", 0)
    songs = pl.get("song_count", 0)

    completion_n = pl.get("completion_n", 0)
    completion_avg = (
        (pl.get("completion_sum", 0.0) / completion_n) if completion_n else 0.0
    )

    created = pl.get("created_at", time.time())
    age_days = max(1, int((time.time() - created) / 86400))

    peak = max(plays, likes, saves, forks, 1)

    owner = await resolve_name(pl.get("owner_id", 0))

    lines = [
        f"**◫ Stats — {pl.get('title', 'Untitled')}**",
        "",
        f"`•` **Owner:** {owner}",
        f"`•` **Created:** {age_days}d ago",
        f"`•` **Songs:** {songs} · {format_duration(pl.get('duration_total', 0))}",
        "",
        f"`▷ Plays ` `{render_bar(plays, peak)}` {plays}",
        f"`♡ Likes ` `{render_bar(likes, peak)}` {likes}",
        f"`⭳ Saves ` `{render_bar(saves, peak)}` {saves}",
        f"`⑂ Forks ` `{render_bar(forks, peak)}` {forks}",
        "",
        f"`•` **Completion rate:** `{render_bar(completion_avg, 1.0)}` "
        f"{completion_avg * 100:.0f}%"
        + (f" __(from {completion_n} sessions)__" if completion_n else " __(no data)__"),
        f"`•` **Trending score:** {pl.get('trending_score', 0):.1f}",
    ]

    if plays and age_days:
        lines.append(f"`•` **Plays/day:** {plays / age_days:.1f}")

    return "\n".join(lines)


# ---- Activity logging helpers ----------------------------------------------


async def log(playlist_id: str, user_id: int, action: str, **meta):
    """Thin wrapper so callers don't build the meta dict by hand."""
    try:
        await db.log_activity(playlist_id, user_id, action, meta or None)
    except Exception as e:
        LOGGER.warning(f"[Playlists] activity log failed: {e}")

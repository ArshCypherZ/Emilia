"""
Inline UI for the social playlists module.

Everything here is drawn from monochrome Unicode symbols — no colour emoji. The
glyph set is deliberately narrow so rows keep a consistent visual weight and
never reflow between Telegram clients:

    ⌘ library   ⭳ save    ◯ public    ◌ private   ◍ unlisted
    ▣ server    ◈ collab  ♡/♥ like    ⑂ fork      ⌕ search
    ▲ trending  ≡ queue   ⋮ more      ✎ edit      ✕ delete
    ‹ ›  prev/next        ⟲ back      ⇱ share     ⇩ export

Callback-data budget: Telegram caps `callback_data` at 64 bytes. Playlist ids
are 10 chars, so the layout is `pl:<verb>:<id>:<arg>` — comfortably inside the
cap even for the longest verb.
"""

import asyncio
from typing import Dict, List, Optional, Tuple

from pyrogram import Client
from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import BOT_USERNAME
from Emilia.modules.plugins.music.playlist.core import (
    MODE_GLYPH,
    MODE_LABEL,
    build_playlist_caption,
    format_duration,
)
from Emilia.modules.plugins.music.playlist.utils import EXPORT_FORMATS
from Emilia.mongo import playlists_mongo as db

# ---- Glyphs -----------------------------------------------------------------

G_LIBRARY = "⌘"
G_SAVE = "⭳"
G_LIKE = "♡"
G_LIKED = "♥"
G_FORK = "⑂"
G_SEARCH = "⌕"
G_TREND = "▲"
G_QUEUE = "≡"
G_MORE = "⋮"
G_EDIT = "✎"
G_DELETE = "✕"
G_PREV = "‹"
G_NEXT = "›"
G_BACK = "⟲"
G_SHARE = "⇱"
G_EXPORT = "⇩"
G_PLAY = "▷"
G_ADD = "＋"
G_STATS = "◫"
G_FEED = "◷"
G_REPORT = "⚑"
G_QR = "▦"
G_LINEAGE = "⋔"
G_BROWSE = "◎"

PAGE_SIZE = 8
SONG_PAGE_SIZE = 10

NOOP = "pl:noop"


# ---- Callback data helpers --------------------------------------------------


def cb(verb: str, pid: str = "", arg: str = "") -> str:
    """Build callback data: `pl:<verb>:<pid>:<arg>`."""
    return f"pl:{verb}:{pid}:{arg}"


def parse_cb(data: str) -> Tuple[str, str, str]:
    """
    Split callback data into (verb, pid, arg).

    Splits with maxsplit so an arg containing ':' (a search term, say) survives
    intact rather than being truncated at the first colon.
    """
    parts = data.split(":", 3)
    while len(parts) < 4:
        parts.append("")
    return parts[1], parts[2], parts[3]


# ---- Pagination ------------------------------------------------------------


def pager_row(
    verb: str,
    page: int,
    total_pages: int,
    pid: str = "",
) -> List[InlineKeyboardButton]:
    """
    Build a ‹ n/N › pager row. Returns [] when there is only one page, so a
    short list doesn't carry a dead row.
    """
    if total_pages <= 1:
        return []

    row = []
    if page > 0:
        row.append(
            InlineKeyboardButton(G_PREV, callback_data=cb(verb, pid, str(page - 1)))
        )
    else:
        row.append(InlineKeyboardButton(" ", callback_data=NOOP))

    row.append(
        InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=NOOP)
    )

    if page < total_pages - 1:
        row.append(
            InlineKeyboardButton(G_NEXT, callback_data=cb(verb, pid, str(page + 1)))
        )
    else:
        row.append(InlineKeyboardButton(" ", callback_data=NOOP))

    return row


def _total_pages(count: int, per_page: int) -> int:
    if count <= 0:
        return 1
    return (count + per_page - 1) // per_page


# ---- Root menu -------------------------------------------------------------


def render_root(user_id: int, in_group: bool = False, first_time: bool = False) -> Tuple[str, InlineKeyboardMarkup]:
    """The `/playlist` landing menu."""
    if first_time:
        text = (
            f"**{G_LIBRARY} Playlists**\n\n"
            "Create playlists, save songs, and share with anyone.\n\n"
            "`•` Tap **♡ Save to Liked** while a song plays\n"
            "`•` Browse public playlists below\n"
            "`•` Create your own or copy others"
        )
    else:
        text = (
            f"**{G_LIBRARY} Playlists**\n\n"
            "Build playlists, share them with a link, and stream any of it "
            "into a voice chat."
        )

    rows = [
        [
            InlineKeyboardButton(
                f"{G_ADD} New Playlist",
                callback_data=cb("newprompt"),
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                f"{G_LIKED} Liked Songs",
                callback_data=cb("liked"),
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                f"{G_LIBRARY} My Library",
                callback_data=cb("lib", "", "0"),
            ),
            InlineKeyboardButton(
                f"{G_SAVE} Saved",
                callback_data=cb("saved", "", "0")
            ),
        ],
        [
            InlineKeyboardButton(
                f"{G_BROWSE} Browse All",
                callback_data=cb("browse", "", "0"),
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                f"{G_TREND} Trending",
                callback_data=cb("trend", "", "0"),
            ),
        ],
        [
            InlineKeyboardButton(
                f"{G_SEARCH} Search", callback_data=cb("searchprompt")
            ),
        ],
    ]
    if in_group:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{MODE_GLYPH[db.ACCESS_SERVER]} Group playlists",
                    callback_data=cb("server", "", "0"),
                ),
            ]
        )
    return text, InlineKeyboardMarkup(rows)


# ---- Playlist lists --------------------------------------------------------


def _list_rows(
    playlists: List[Dict], show_owner: bool = False
) -> List[List[InlineKeyboardButton]]:
    rows = []
    for pl in playlists:
        glyph = MODE_GLYPH.get(pl.get("access_mode"), "")
        count = pl.get("song_count", 0)
        title = pl.get("title", "Untitled")
        # Telegram truncates long button labels mid-glyph; clip ourselves so the
        # song count stays readable.
        if len(title) > 24:
            title = title[:23] + "…"
        label = f"{glyph} {title} · {count}"
        rows.append(
            [InlineKeyboardButton(label, callback_data=cb("view", pl["playlist_id"]))]
        )
    return rows


def render_library(
    playlists: List[Dict], page: int, total: int
) -> Tuple[str, InlineKeyboardMarkup]:
    total_pages = _total_pages(total, PAGE_SIZE)

    if not playlists:
        text = (
            f"**{G_LIBRARY} Your Library**\n\n"
            "You don't have any playlists yet.\n\n"
            "`•` Tap **♡ Save to Liked** while a song plays\n"
            f"`•` Or tap **{G_ADD} New Playlist** to create your first one\n"
            f"`•` Browse public playlists and **{G_FORK} Copy** the ones you like"
        )
    else:
        text = (
            f"**{G_LIBRARY} Your Library**\n\n"
            f"`•` **{total}** playlist{'s' if total != 1 else ''}\n"
            f"`•` Page **{page + 1}** of **{total_pages}**"
        )

    rows = _list_rows(playlists)
    pager = pager_row("lib", page, total_pages)
    if pager:
        rows.append(pager)
    rows.append(
        [
            InlineKeyboardButton(
                f"{G_ADD} New", callback_data=cb("newprompt"), style=ButtonStyle.SUCCESS
            ),
            InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("root")),
        ]
    )
    return text, InlineKeyboardMarkup(rows)


def render_discovery(
    playlists: List[Dict],
    page: int,
    kind: str,
    query: str = "",
) -> Tuple[str, InlineKeyboardMarkup]:
    """Trending / browse / search / saved / server-group listings."""
    if kind == "trend":
        header = f"**{G_TREND} Trending**"
        empty = (
            "Nothing is trending yet.\n\n"
            f"Be the first — tap **{G_ADD} New Playlist**, add some songs, "
            "and set it **Public**."
        )
    elif kind == "browse":
        header = f"**{G_BROWSE} Browse All**"
        empty = (
            "No public playlists yet.\n\n"
            f"Make the first one — tap **{G_ADD} New Playlist**, add songs, "
            "and set it **Public** so everyone can find it."
        )
    elif kind == "search":
        header = f"**{G_SEARCH} Results for** `{query}`"
        empty = (
            "No public playlists matched that.\n\n"
            f"Try a different word, or tap **{G_ADD} New Playlist** to make your own."
        )
    elif kind == "server":
        header = f"**{MODE_GLYPH[db.ACCESS_SERVER]} Group playlists**"
        empty = "No group playlists yet. Create one and set its access to **Group**."
    else:
        header = f"**{G_SAVE} Saved**"
        empty = (
            "You haven't saved any playlists yet.\n\n"
            f"Tap **{G_BROWSE} Browse All** to find playlists, then **{G_SAVE} Save** "
            "the ones you like."
        )

    if not playlists:
        text = f"{header}\n\n{empty}"
        rows = [
            [
                InlineKeyboardButton(
                    f"{G_ADD} New Playlist",
                    callback_data=cb("newprompt"),
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("root"))],
        ]
        return text, InlineKeyboardMarkup(rows)

    lines = [header, ""]
    for i, pl in enumerate(playlists, start=page * PAGE_SIZE + 1):
        glyph = MODE_GLYPH.get(pl.get("access_mode"), "")
        lines.append(
            f"`{i:>2}.` {glyph} **{pl.get('title', 'Untitled')}** — "
            f"{pl.get('song_count', 0)} songs · "
            f"{pl.get('plays', 0)} plays · {pl.get('likes', 0)} {G_LIKE}"
        )

    rows = _list_rows(playlists, show_owner=True)

    # Discovery feeds are cursor-paged: we ask for one extra row to learn whether
    # a next page exists, rather than counting the whole collection every tap.
    has_next = len(playlists) >= PAGE_SIZE
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                G_PREV, callback_data=cb(kind, "", f"{page - 1}|{query}")
            )
        )
    nav.append(InlineKeyboardButton(f"{page + 1}", callback_data=NOOP))
    if has_next:
        nav.append(
            InlineKeyboardButton(
                G_NEXT, callback_data=cb(kind, "", f"{page + 1}|{query}")
            )
        )
    if len(nav) > 1:
        rows.append(nav)

    rows.append([InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("root"))])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


# ---- Playlist detail view --------------------------------------------------


async def render_playlist_view(
    pl: Dict,
    user_id: int,
    client: Optional[Client] = None,
    page: int = 0,
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Full playlist view: caption, first page of songs, and action rows.
    Buttons shown depend on whether the viewer owns / can edit the playlist.
    """
    pid = pl["playlist_id"]
    is_owner = pl.get("owner_id") == user_id
    can_edit = is_owner or user_id in pl.get("editors", [])

    songs, liked, saved = await asyncio.gather(
        db.get_songs(pid, skip=page * SONG_PAGE_SIZE, limit=SONG_PAGE_SIZE),
        db.has_edge(pid, user_id, "like"),
        db.has_edge(pid, user_id, "save"),
    )

    caption = build_playlist_caption(pl)

    if songs:
        lines = [caption, "", "**Tracks**"]
        for s in songs:
            lines.append(
                f"`{s.get('position', 0):>3}.` {s.get('title', 'Unknown')} "
                f"`({format_duration(s.get('duration', 0))})`"
            )
        text = "\n".join(lines)
    else:
        text = caption + "\n\n_This playlist is empty._"

    total_pages = _total_pages(pl.get("song_count", 0), SONG_PAGE_SIZE)

    rows: List[List[InlineKeyboardButton]] = []

    rows.append(
        [
            InlineKeyboardButton(
                f"{G_PLAY} Play",
                callback_data=cb("play", pid),
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                f"{G_QUEUE} Queue", callback_data=cb("enqueue", pid)
            ),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                f"{G_LIKED if liked else G_LIKE} {pl.get('likes', 0)}",
                callback_data=cb("like", pid),
            ),
            InlineKeyboardButton(
                f"{G_SAVE} {'Saved' if saved else 'Save'}",
                callback_data=cb("save", pid),
            ),
            InlineKeyboardButton(
                f"{G_FORK} Copy", callback_data=cb("fork", pid)
            ),
        ]
    )

    pager = pager_row("view", page, total_pages, pid)
    if pager:
        rows.append(pager)

    if can_edit:
        rows.append(
            [
                InlineKeyboardButton(f"{G_ADD} Add", callback_data=cb("addprompt", pid)),
                InlineKeyboardButton(
                    f"{G_EDIT} Manage", callback_data=cb("manage", pid)
                ),
            ]
        )

    # Share stays visible for everyone — it's the whole point of a social
    # playlist, and burying it under "More" was one taps too many.
    rows.append(
        [
            InlineKeyboardButton(f"{G_SHARE} Share", callback_data=cb("share", pid)),
            InlineKeyboardButton(f"{G_MORE} More", callback_data=cb("more", pid)),
        ]
    )
    rows.append(
        [InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("root"))]
    )

    return text, InlineKeyboardMarkup(rows)


def render_more(pl: Dict, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Secondary actions: stats, feed, lineage, export, report."""
    pid = pl["playlist_id"]
    is_owner = pl.get("owner_id") == user_id

    text = (
        f"**{G_MORE} More — {pl.get('title', 'Untitled')}**\n\n"
        f"`{G_STATS}` **Stats** — plays, likes, completion\n"
        f"`{G_FEED}` **Activity** — who changed what\n"
        f"`{G_LINEAGE}` **Lineage** — fork history\n"
        f"`{G_EXPORT}` **Export** — JSON / M3U / CSV\n"
        f"`{G_QR}` **QR code** — share outside Telegram"
    )

    rows = [
        [
            InlineKeyboardButton(f"{G_STATS} Stats", callback_data=cb("stats", pid)),
            InlineKeyboardButton(f"{G_FEED} Activity", callback_data=cb("feed", pid)),
        ],
        [
            InlineKeyboardButton(
                f"{G_LINEAGE} Lineage", callback_data=cb("lineage", pid)
            ),
            InlineKeyboardButton(
                f"{G_EXPORT} Export", callback_data=cb("export", pid)
            ),
        ],
        [
            InlineKeyboardButton(f"{G_QR} QR code", callback_data=cb("qr", pid)),
        ],
    ]

    if not is_owner:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{G_REPORT} Report",
                    callback_data=cb("report", pid),
                    style=ButtonStyle.DANGER,
                )
            ]
        )

    rows.append(
        [InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("view", pid, "0"))]
    )
    return text, InlineKeyboardMarkup(rows)


# ---- Manage / settings -----------------------------------------------------


def render_manage(pl: Dict, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    is_owner = pl.get("owner_id") == user_id
    mode = pl.get("access_mode")

    editors = pl.get("editors", [])
    text = (
        f"**{G_EDIT} Manage — {pl.get('title', 'Untitled')}**\n\n"
        f"`•` **Access:** {MODE_GLYPH.get(mode, '')} {MODE_LABEL.get(mode, 'Private')}\n"
        f"`•` **Editors:** {len(editors)}\n"
        f"`•` **Songs:** {pl.get('song_count', 0)}"
    )

    rows = [
        [
            InlineKeyboardButton(f"{G_EDIT} Rename", callback_data=cb("rename", pid)),
            InlineKeyboardButton(
                f"{G_EDIT} Description", callback_data=cb("redesc", pid)
            ),
        ],
        [
            InlineKeyboardButton(
                f"{G_QUEUE} Reorder", callback_data=cb("reorder", pid, "0")
            ),
            InlineKeyboardButton(
                f"{G_DELETE} Remove song", callback_data=cb("rmsong", pid, "0")
            ),
        ],
    ]

    if is_owner:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{MODE_GLYPH.get(mode, '')} Access", callback_data=cb("access", pid)
                ),
                InlineKeyboardButton(
                    f"{G_ADD} Editors", callback_data=cb("editors", pid)
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    f"{G_DELETE} Delete playlist",
                    callback_data=cb("delprompt", pid),
                    style=ButtonStyle.DANGER,
                )
            ]
        )

    rows.append(
        [InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("view", pid, "0"))]
    )
    return text, InlineKeyboardMarkup(rows)


def render_access(pl: Dict) -> Tuple[str, InlineKeyboardMarkup]:
    """Access-mode picker. The current mode is marked with a leading bullet."""
    pid = pl["playlist_id"]
    current = pl.get("access_mode")

    text = (
        f"**Access — {pl.get('title', 'Untitled')}**\n\n"
        f"`{MODE_GLYPH[db.ACCESS_PRIVATE]}` **Private** — only you and editors\n"
        f"`{MODE_GLYPH[db.ACCESS_UNLISTED]}` **Unlisted** — anyone with the link\n"
        f"`{MODE_GLYPH[db.ACCESS_PUBLIC]}` **Public** — listed in search and trending\n"
        f"`{MODE_GLYPH[db.ACCESS_SERVER]}` **Server** — only members of one group\n"
        f"`{MODE_GLYPH[db.ACCESS_COLLAB]}` **Collaborative** — editors can add songs"
    )

    rows = []
    for mode in db.ACCESS_MODES:
        marker = "•" if mode == current else " "
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} {MODE_GLYPH[mode]} {MODE_LABEL[mode]}",
                    callback_data=cb("setaccess", pid, mode),
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("manage", pid))]
    )
    return text, InlineKeyboardMarkup(rows)


# ---- Duplicate prompt ------------------------------------------------------


def render_duplicate_prompt(
    pl: Dict, existing: Dict, new_track: Dict, token: str
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Replace/Skip prompt shown when an added song is already present.

    The pending track is held in Redis under `token` rather than packed into the
    callback data — a title and url would blow straight past the 64-byte cap.
    """
    pid = pl["playlist_id"]
    text = (
        f"**Already in this playlist**\n\n"
        f"`•` **Existing:** {existing.get('title', 'Unknown')} "
        f"`({format_duration(existing.get('duration', 0))})`\n"
        f"`•` **Position:** {existing.get('position', 0)}\n"
        f"`•` **New:** {new_track.get('title', 'Unknown')} "
        f"`({format_duration(new_track.get('duration', 0))})`\n\n"
        "Replace the stored copy, or skip?"
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Replace",
                    callback_data=cb("dupreplace", pid, token),
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    "Skip",
                    callback_data=cb("dupskip", pid, token),
                    style=ButtonStyle.DEFAULT,
                ),
            ]
        ]
    )
    return text, markup


# ---- Confirmations ---------------------------------------------------------


def render_delete_confirm(pl: Dict) -> Tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    text = (
        f"**{G_DELETE} Delete “{pl.get('title', 'Untitled')}”?**\n\n"
        f"This removes the playlist and all **{pl.get('song_count', 0)}** of its "
        "songs. Forks other people made stay untouched.\n\n"
        "This cannot be undone."
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"{G_DELETE} Delete",
                    callback_data=cb("delete", pid),
                    style=ButtonStyle.DANGER,
                ),
                InlineKeyboardButton("Cancel", callback_data=cb("manage", pid)),
            ]
        ]
    )
    return text, markup


def render_share(pl: Dict, link: str) -> Tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    mode = pl.get("access_mode")

    note = ""
    if mode == db.ACCESS_PRIVATE:
        note = (
            f"\n\n__{MODE_GLYPH[db.ACCESS_PRIVATE]} This playlist is **private** — the "
            "link only works for you and its editors. Switch it to Unlisted or "
            "Public to let others open it.__"
        )
    elif mode == db.ACCESS_SERVER:
        note = (
            f"\n\n__{MODE_GLYPH[db.ACCESS_SERVER]} This playlist is **server-only** — "
            "the link only works for members of its group.__"
        )

    text = (
        f"**{G_SHARE} Share — {pl.get('title', 'Untitled')}**\n\n"
        f"`{link}`\n\n"
        f"`•` **ID:** `{pid}`{note}"
    )
    rows = [
        [InlineKeyboardButton(f"{G_SHARE} Open link", url=link)],
    ]
    # A private/server playlist's link won't open for anyone else, so the note
    # above tells the owner to widen access. Give them the button to do it right
    # here instead of sending them hunting through Manage → Access. Non-owners who
    # tap it hit the owner-only gate in _h_access — no extra check needed.
    if mode in (db.ACCESS_PRIVATE, db.ACCESS_SERVER):
        rows.append(
            [InlineKeyboardButton(f"{G_EDIT} Change access", callback_data=cb("access", pid))]
        )
    rows.append(
        [
            InlineKeyboardButton(f"{G_QR} QR code", callback_data=cb("qr", pid)),
            InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("view", pid, "0")),
        ]
    )
    return text, InlineKeyboardMarkup(rows)


def back_row(pid: str) -> List[InlineKeyboardButton]:
    return [InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("more", pid))]


def simple_view(text: str, pid: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Text panel with a single Back button — stats, feed, lineage all use this."""
    return text, InlineKeyboardMarkup([back_row(pid)])


# ---- Typed-input prompts ---------------------------------------------------


def render_prompt(text: str, pid: str) -> Tuple[str, InlineKeyboardMarkup]:
    """A prompt awaiting a typed reply, with a way back out."""
    back = cb("view", pid, "0") if pid else cb("root")
    return text, InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"{G_BACK} Cancel", callback_data=back)]]
    )


def render_pm_handoff(prompt_text: str) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Shown when a typed-input prompt is opened from a group.

    Replies are only captured in PM, so rather than leaving the user typing into
    a void we say so plainly and hand them a one-tap way over. Their pending
    prompt is already stored against their user id, so it's waiting when they
    arrive.
    """
    text = f"{prompt_text}\n\n`•` I can only read your reply in a private chat."
    return text, InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"{G_SHARE} Continue in PM", url=f"https://t.me/{BOT_USERNAME}")]]
    )


# ---- Song pickers ----------------------------------------------------------


def render_song_picker(
    pl: Dict, songs: List[Dict], page: int, mode: str
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    One paged list of tracks, used for both removing and reordering.

    The two flows differ only in glyph, wording, and the arg prefix they encode,
    so they share a renderer rather than each carrying their own copy of the
    pagination and back-navigation.
    """
    title = pl.get("title", "Untitled")
    glyph, heading, hint, prefix = _PICKER_MODES[mode]

    if not songs:
        return (
            f"**{glyph} {heading} — {title}**\n\nThis playlist is empty.",
            InlineKeyboardMarkup([[InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("manage", pl["playlist_id"]))]]),
        )

    pid = pl["playlist_id"]
    rows = [
        [
            InlineKeyboardButton(
                f"{glyph} {s.get('position')}. {(s.get('title') or '')[:28]}",
                callback_data=cb(mode, pid, f"{prefix}{s.get('position')}"),
            )
        ]
        for s in songs
    ]

    pager = pager_row(mode, page, _total_pages(pl.get("song_count", 0), SONG_PAGE_SIZE), pid)
    if pager:
        rows.append(pager)
    rows.append([InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("manage", pid))])

    return f"**{glyph} {heading} — {title}**\n\n{hint}", InlineKeyboardMarkup(rows)


# mode -> (glyph, heading, hint, callback arg prefix)
_PICKER_MODES = {
    "rmsong": (G_DELETE, "Remove", "Tap a track to remove it.", "p"),
    "reorder": (G_QUEUE, "Reorder", "Tap a track to move it one place earlier.", "u"),
}


# ---- Editors ---------------------------------------------------------------


def render_editors(
    pl: Dict, names: Dict[int, str]
) -> Tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    editors = pl.get("editors", []) or []

    if editors:
        blurb = (
            "Editors can add and remove songs. Only you can delete the playlist "
            "or change who has access."
        )
    else:
        blurb = "No editors yet. Add one to make this playlist collaborative."

    text = f"**{G_ADD} Editors — {pl.get('title', 'Untitled')}**\n\n{blurb}"

    rows = [
        [
            InlineKeyboardButton(
                f"{G_DELETE} {names.get(uid, str(uid))}",
                callback_data=cb("editors", pid, f"r{uid}"),
            )
        ]
        for uid in editors
    ]
    rows.append([InlineKeyboardButton(f"{G_ADD} Add editor", callback_data=cb("addeditor", pid))])
    rows.append([InlineKeyboardButton(f"{G_BACK} Back", callback_data=cb("manage", pid))])
    return text, InlineKeyboardMarkup(rows)


# ---- Export ----------------------------------------------------------------


def render_export_picker(pl: Dict) -> Tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    text = (
        f"**{G_EXPORT} Export — {pl.get('title', 'Untitled')}**\n\n"
        f"`•` **JSON** — full metadata, re-importable\n"
        f"`•` **M3U** — opens in most media players\n"
        f"`•` **CSV** — spreadsheets"
    )
    rows = [
        [
            InlineKeyboardButton(fmt.upper(), callback_data=cb("export", pid, fmt))
            for fmt in EXPORT_FORMATS
        ],
        back_row(pid),
    ]
    return text, InlineKeyboardMarkup(rows)

"""
Command and callback surface for Global Social Playlists.

Entry point is `/playlist`:
  - `/playlist`            → the social menu (library, trending, search, saved)
  - `/playlist <url|id>`   → the original behaviour, kept intact: load a
                             YouTube playlist straight into the voice-chat
                             queue. Spotify links work here too now.

Every inline button routes through one callback handler (`pl:<verb>:<pid>:<arg>`)
rather than one handler per verb — 33 separate pattern filters would all be
tested on every callback in the bot.

Text input (naming a playlist, searching, adding a song) uses a short-lived
Redis pending-state keyed by user, so the flow survives across worker processes
and expires on its own if the user wanders off.
"""

import asyncio

import orjson
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from Emilia import EVENT_LOGS, LOGGER, pgram, redis_client
from Emilia.custom_filter import auth
from Emilia.custom_filter import callbackquery, listen, register
from Emilia.utils import cb_token
from Emilia.utils.menu_guard import claim_tap, menu_owner_ok, remember_menu
from Emilia.modules.plugins.music.playlist import social, ui
from Emilia.modules.plugins.music.playlist import core as plcore
from Emilia.modules.plugins.music.playlist import import_engine as imports
from Emilia.modules.plugins.music.playlist.utils import (
    LIMIT_CALLBACK,
    LIMIT_CREATE,
    LIMIT_EXPORT,
    LIMIT_FORK,
    LIMIT_IMPORT,
    LIMIT_QR,
    LIMIT_REPORT,
    build_share_link,
    export_playlist,
    generate_qr,
    guard_action,
    limit_message,
    sanitize_text,
    validate_title,
)
from Emilia.mongo import playlists_mongo as db
from Emilia.utils.decorators import RATE_LIMIT_GENERAL, rate_limit
from Emilia.utils.errors import report_error

# ---- Pending text input ------------------------------------------------------

_PENDING_TTL = 300  # a prompt the user ignored shouldn't capture their next
# unrelated message ten minutes later


def _pending_key(user_id: int) -> str:
    return f"pl_pending:{user_id}"


async def _set_pending(user_id: int, action: str, pid: str = "") -> None:
    await redis_client.setex(
        _pending_key(user_id),
        _PENDING_TTL,
        orjson.dumps({"action": action, "pid": pid}).decode(),
    )


async def _get_pending(user_id: int):
    raw = await redis_client.get(_pending_key(user_id))
    return orjson.loads(raw) if raw else None


async def _clear_pending(user_id: int) -> None:
    await redis_client.delete(_pending_key(user_id))


# Pending duplicate-resolution tracks, held out of callback data (a title and a
# url would blow past Telegram's 64-byte limit). cb_token already solves exactly
# this for the anime module, so it is reused rather than re-implemented.
async def _stash_track(track: dict) -> str:
    return await cb_token.stash(track, ttl=_PENDING_TTL)


async def _stashed_track(token: str):
    return await cb_token.unstash(token)


async def send_menu(message: Message, text: str, markup=None) -> Message:
    """Reply with a menu and record who it belongs to, so nobody else can drive it."""
    sent = await message.reply_text(text, reply_markup=markup)
    await remember_menu(sent, message.from_user.id)
    return sent


# ---- Shared helpers ----------------------------------------------------------


async def _load_viewable(query: CallbackQuery, pid: str):
    """Fetch a playlist and confirm the tapper may see it. Answers on failure."""
    pl = await db.get_playlist(pid)
    if not pl:
        await query.answer("That playlist no longer exists.", show_alert=True)
        return None
    if pl.get("banned"):
        await query.answer("That playlist has been removed.", show_alert=True)
        return None
    chat_id = query.message.chat.id if query.message else None
    if not await plcore.can_view(pl, query.from_user.id, chat_id):
        await query.answer("You don't have access to that playlist.", show_alert=True)
        return None
    return pl


async def _load_editable(query: CallbackQuery, pid: str):
    pl = await _load_viewable(query, pid)
    if not pl:
        return None
    if not await plcore.can_edit(pl, query.from_user.id):
        await query.answer("You can't edit that playlist.", show_alert=True)
        return None
    return pl


async def _edit(query: CallbackQuery, text: str, markup=None):
    """
    Edit the menu in place.

    Telegram rejects an edit whose content is byte-identical to what's already
    shown (MESSAGE_NOT_MODIFIED); that happens whenever someone taps the button
    for the page they're already on, and it isn't an error worth surfacing.
    """
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" not in str(e):
            LOGGER.warning(f"[Playlists] menu edit failed: {e}")


async def _refresh_if_owner(query: CallbackQuery, pid: str) -> None:
    """
    Repaint the card after a like/save, but only for whoever opened it.

    Liking someone else's shared card is allowed and welcome; redrawing their
    message with *your* like state on the buttons is not.
    """
    if not await menu_owner_ok(query):
        return
    pl = await db.get_playlist(pid)
    if pl:
        await _show_view(query, pl)


async def _show_view(query: CallbackQuery, pl: dict, page: int = 0):
    text, markup = await ui.render_playlist_view(
        pl, query.from_user.id, query._client, page
    )
    await _edit(query, text, markup)


def _int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_page_arg(arg: str):
    """Discovery pagers pack "<page>|<query>" into the arg slot."""
    if "|" in arg:
        page_str, _, query = arg.partition("|")
        return _int(page_str), query
    return _int(arg), ""


# ---- /playlist ---------------------------------------------------------------


@register(pattern="playlist")
@rate_limit(RATE_LIMIT_GENERAL)
async def playlist_command(client: Client, message: Message):
    """
    `/playlist` opens the social menu; `/playlist <link>` keeps the original
    load-into-voice-chat behaviour that this command already had.
    """
    from Emilia.modules.plugins.music.play import _check_if_clone, playlist_cmd

    if await _check_if_clone(client, message):
        return

    parts = (message.text or "").split()
    if len(parts) > 1:
        # A link/id argument still means "queue this in the voice chat", which
        # is what /playlist has always done and what info/music.py documents.
        return await playlist_cmd(client, message)

    user_id = message.from_user.id
    in_group = message.chat.type.name != "PRIVATE"
    if in_group:
        # Opening your library from a group is the clearest statement of which
        # voice chat you mean, so Play works from PM later on too.
        await plcore.remember_group(user_id, message.chat.id)

    # Show first-time onboarding hint if user has zero playlists (never created one)
    count = await db.count_user_playlists(user_id)
    first_time = (count == 0)

    text, markup = ui.render_root(
        user_id,
        in_group=in_group,
        first_time=first_time
    )
    await send_menu(message, text, markup)


# ---- Callback router ---------------------------------------------------------


@callbackquery(pattern=r"^pl:")
async def playlist_callbacks(client: Client, query: CallbackQuery):
    verb, pid, arg = ui.parse_cb(query.data)
    user_id = query.from_user.id

    if verb == "noop":
        return await query.answer()

    handler = _ROUTES.get(verb)
    if handler is None:
        return await query.answer()

    # A playlist card posted in a group is meant to be acted on by the people who
    # see it — that is the whole point of sharing one. Those verbs are listed in
    # _SOCIAL and act on the tapper's own account, never on the opener's. Every
    # other verb navigates or edits the opener's private workspace, so it stays
    # with whoever opened the menu.
    if verb not in _SOCIAL and not await menu_owner_ok(query):
        return await query.answer(
            "This menu belongs to someone else — send /playlist to open your own.",
            show_alert=True,
        )

    allowed, _ = await guard_action(user_id, "menu", LIMIT_CALLBACK)
    if not allowed:
        return await query.answer("Slow down a moment.", show_alert=True)

    # Buttons that produce a new message (an upload, a confirmation) must not run
    # twice concurrently; the in-place menu edits are idempotent and don't care.
    if verb in _DEBOUNCED and not await claim_tap(user_id, query.data):
        return await query.answer("Already working on that…")

    try:
        await handler(client, query, pid, arg)
    except Exception as e:
        await report_error("playlists.callback", e, verb=verb, user=user_id)
        try:
            await query.answer("Something went wrong.", show_alert=True)
        except Exception:
            pass


# Verbs anyone may tap on a shared card: read-only views, plus the actions that
# land in the *tapper's* own library or in the chat's voice queue.
_SOCIAL = frozenset(
    {"like", "save", "fork", "play", "enqueue", "share", "qr", "export", "report",
     # "root" is on the shared Now Playing card, which nobody owns: any member who
     # taps Playlists there gets their own fresh menu (see _h_root's "new" arg).
     "root"}
)

# Verbs whose handler sends a message or uploads a file, rather than editing the
# menu in place — the ones where a double tap would visibly duplicate output.
# "export" isn't here: its first tap only draws a picker, so it debounces itself
# once a format has actually been chosen.
_DEBOUNCED = frozenset({"qr", "play", "enqueue", "fork"})


# ---- Navigation --------------------------------------------------------------


async def _h_root(client, query, pid, arg):
    in_group = query.message.chat.type.name != "PRIVATE" if query.message else False
    text, markup = ui.render_root(query.from_user.id, in_group=in_group)

    # `arg == "new"` means this came from a shared card (the Now Playing player),
    # not from a menu this user owns. Editing it in place would replace the whole
    # group's player with one person's library, so open a fresh menu owned by the
    # tapper instead. Everyone gets their own, and the player stays put.
    if arg == "new" and query.message:
        await query.answer()
        await plcore.remember_group(query.from_user.id, query.message.chat.id)
        sent = await query.message.reply_text(text, reply_markup=markup)
        return await remember_menu(sent, query.from_user.id)

    await _edit(query, text, markup)
    await query.answer()


async def _h_lib(client, query, pid, arg):
    page = _int(arg)
    user_id = query.from_user.id
    total = await db.count_user_playlists(user_id)
    playlists = await db.get_user_playlists(
        user_id, skip=page * ui.PAGE_SIZE, limit=ui.PAGE_SIZE
    )
    text, markup = ui.render_library(playlists, page, total)
    await _edit(query, text, markup)
    await query.answer()


async def _h_trend(client, query, pid, arg):
    page, _ = _split_page_arg(arg)
    playlists = await plcore.get_trending(
        limit=ui.PAGE_SIZE, skip=page * ui.PAGE_SIZE
    )
    text, markup = ui.render_discovery(playlists, page, "trend")
    await _edit(query, text, markup)
    await query.answer()


async def _h_browse(client, query, pid, arg):
    """Browse all public playlists by recency (created/updated)."""
    page, _ = _split_page_arg(arg)
    playlists = await db.get_recent(
        limit=ui.PAGE_SIZE, skip=page * ui.PAGE_SIZE
    )
    text, markup = ui.render_discovery(playlists, page, "browse")
    await _edit(query, text, markup)
    await query.answer()


async def _h_saved(client, query, pid, arg):
    page, _ = _split_page_arg(arg)
    playlists = await db.get_saved_playlists(
        query.from_user.id, skip=page * ui.PAGE_SIZE, limit=ui.PAGE_SIZE
    )
    text, markup = ui.render_discovery(playlists, page, "saved")
    await _edit(query, text, markup)
    await query.answer()


async def _h_server(client, query, pid, arg):
    """Server-mode playlists belonging to this group.

    Without this the "Server" access mode was a dead end: you could set it, but
    nobody could find the playlist again without the share link.
    """
    if not query.message or query.message.chat.type.name == "PRIVATE":
        return await query.answer("Only works inside a group.", show_alert=True)
    page, _ = _split_page_arg(arg)
    playlists = await db.get_server_playlists(
        query.message.chat.id, skip=page * ui.PAGE_SIZE, limit=ui.PAGE_SIZE
    )
    text, markup = ui.render_discovery(playlists, page, "server")
    await _edit(query, text, markup)
    await query.answer()


async def _h_search(client, query, pid, arg):
    page, term = _split_page_arg(arg)
    playlists = await db.search(term, limit=ui.PAGE_SIZE, skip=page * ui.PAGE_SIZE)
    text, markup = ui.render_discovery(playlists, page, "search", term)
    await _edit(query, text, markup)
    await query.answer()


async def _h_view(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        await _show_view(query, pl, _int(arg))
        await query.answer()


async def _h_more(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.render_more(pl, query.from_user.id)
        await _edit(query, text, markup)
        await query.answer()


async def _h_manage(client, query, pid, arg):
    pl = await _load_editable(query, pid)
    if pl:
        text, markup = ui.render_manage(pl, query.from_user.id)
        await _edit(query, text, markup)
        await query.answer()


async def _h_liked(client, query, pid, arg):
    """The auto-liked default playlist, created on first use."""
    pl = await db.get_or_create_liked_playlist(query.from_user.id)
    if not pl:
        return await query.answer("Could not open Liked Songs.", show_alert=True)
    await _show_view(query, pl)
    await query.answer()


# ---- Social panels -----------------------------------------------------------


async def _h_stats(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.simple_view(await social.render_stats(pid), pid)
        await _edit(query, text, markup)
        await query.answer()


async def _h_feed(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.simple_view(await social.render_activity_feed(pid), pid)
        await _edit(query, text, markup)
        await query.answer()


async def _h_lineage(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.simple_view(await social.render_lineage(pid), pid)
        await _edit(query, text, markup)
        await query.answer()


# ---- Engagement --------------------------------------------------------------


async def _h_like(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    liked = await db.toggle_like(pid, query.from_user.id)
    await query.answer("Liked." if liked else "Like removed.")
    await _refresh_if_owner(query, pid)


async def _h_save(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    saved = await db.toggle_save(pid, query.from_user.id)
    await query.answer("Saved to your library." if saved else "Removed from saved.")
    await _refresh_if_owner(query, pid)


async def _h_fork(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    user_id = query.from_user.id
    if pl.get("owner_id") == user_id:
        return await query.answer("This is already your playlist.", show_alert=True)

    allowed, retry = await guard_action(user_id, "fork", LIMIT_FORK)
    if not allowed:
        return await query.answer(limit_message("fork", retry), show_alert=True)

    if await db.count_user_playlists(user_id) >= db.MAX_PLAYLISTS_PER_USER:
        return await query.answer(
            f"You've reached the limit of {db.MAX_PLAYLISTS_PER_USER} playlists.",
            show_alert=True,
        )

    new_id = await plcore.fork_playlist(pid, user_id)
    if not new_id:
        # The "Forking…" toast already consumed this callback's one answer, so a
        # second answer() would be silently dropped. Say it in the chat instead.
        return await query.message.reply_text("`•` Could not fork that playlist.")

    await query.answer("Forked into your library.")
    forked = await db.get_playlist(new_id)
    if forked:
        await _show_view(query, forked)


# ---- Voice-chat integration --------------------------------------------------


async def _say(client, query, chat_id: int, text: str):
    """Post playback status into the chat being played into.

    A Play tapped from PM has to talk to the group, not to the PM card, or the
    people in the voice chat never see what happened.
    """
    if query.message and query.message.chat.id == chat_id:
        return await query.message.reply_text(text)
    return await client.send_message(chat_id, text)


async def _resolve_target_chat(query):
    """The group whose voice chat a Play/Queue tap should act on.

    In a group that's simply the current chat. From PM there is no chat to play
    into, so fall back to the group this user was last active in — which is what
    they mean by "play" when they opened their library from a group's player.
    Returns (chat_id, error_text); chat_id is None when we genuinely can't tell.
    """
    if query.message and query.message.chat.type.name != "PRIVATE":
        return query.message.chat.id, None

    chat_id = await plcore.recall_group(query.from_user.id)
    if not chat_id:
        return None, (
            "Open this from the group you're listening in — tap **📚 Playlists** "
            "on the player there, and Play will stream straight into that voice chat."
        )

    from Emilia.modules.plugins.music.utils.store import get_now_playing

    # Only reuse the remembered group while it's actually a live session; a group
    # the user left hours ago is not a place to start blasting music unannounced.
    if not await get_now_playing(chat_id):
        return None, (
            "There's no voice chat playing where I last saw you. Start one, then "
            "tap **📚 Playlists** on the player to queue this up."
        )
    return chat_id, None


async def _h_play(client, query, pid, arg):
    """Stream a whole playlist into the group's voice chat."""
    pl = await _load_viewable(query, pid)
    if not pl:
        return

    chat_id, error = await _resolve_target_chat(query)
    if not chat_id:
        return await query.answer(error, show_alert=True)

    songs = await db.get_songs(pid, limit=db.MAX_SONGS_PER_PLAYLIST)
    if not songs:
        return await query.answer("That playlist is empty.", show_alert=True)

    from Emilia.modules.plugins.music.core.youtube import fetch_and_download
    from Emilia.modules.plugins.music.play import (
        _check_callback_access,
        _start_playback,
        prefetch_next,
    )
    from Emilia.modules.plugins.music.utils.store import (
        add_many_to_queue,
        get_now_playing,
    )

    # Same gate the rest of the music module uses for playback control: free for
    # all while nothing is playing, then restricted to whoever started the
    # session plus admins. Dropping a whole playlist onto someone else's queue
    # is a bigger interruption than /skip, so it can't be looser than /skip is.
    if not await _check_callback_access(query, chat_id):
        return await query.answer(
            "Only the person who started playback or an admin can do that.",
            show_alert=True,
        )

    tracks = [
        _song_to_track(s, query.from_user.id, query.from_user.mention)
        for s in songs
    ]

    await query.answer(f"Queueing {len(tracks)} tracks…")

    if await get_now_playing(chat_id):
        await add_many_to_queue(chat_id, tracks)
        await _say(client, query, chat_id,
            f"`•` Added **{len(tracks)}** tracks from **{pl.get('title')}** to the queue."
        )
        # Get the next few files on disk while the current track still plays.
        asyncio.create_task(prefetch_next(chat_id))
    else:
        first, rest = tracks[0], tracks[1:]
        if rest:
            await add_many_to_queue(chat_id, rest)
        # Fetching the first track can take a few seconds; the toast has already
        # been spent, so leave a visible message rather than a silent gap.
        status = await _say(client, query, chat_id,
            f"`•` Starting **{pl.get('title')}** — loading the first track…"
        )
        try:
            first = await fetch_and_download(first["webpage_url"], False)
        except Exception as e:
            LOGGER.warning("[Playlist] Could not load first track of %s: %s", pid, e)
            return await status.edit_text(
                "`•` Could not start that track. The rest of the playlist is queued —"
                " use /skip to move on."
            )
        first["user_id"] = query.from_user.id
        first["requester_mention"] = query.from_user.mention
        await _start_playback(
            chat_id,
            first,
            query.from_user.mention,
            # The player card belongs in the group being played into, which isn't
            # query.message when the tap came from PM.
            reply_message=status,
            user_id=query.from_user.id,
        )
        await status.delete()

    # The play itself is banked when the queue runs dry, together with how much
    # of the playlist the chat actually sat through (see core.session_finish).
    await plcore.session_start(chat_id, pid, query.from_user.id, len(tracks))


async def _h_enqueue(client, query, pid, arg):
    """Append to the queue without disturbing what's already playing."""
    pl = await _load_viewable(query, pid)
    if not pl:
        return

    chat_id, error = await _resolve_target_chat(query)
    if not chat_id:
        return await query.answer(error, show_alert=True)

    songs = await db.get_songs(pid, limit=db.MAX_SONGS_PER_PLAYLIST)
    if not songs:
        return await query.answer("That playlist is empty.", show_alert=True)

    from Emilia.modules.plugins.music.play import _check_callback_access, prefetch_next
    from Emilia.modules.plugins.music.utils.store import add_many_to_queue

    if not await _check_callback_access(query, chat_id):
        return await query.answer(
            "Only the person who started playback or an admin can do that.",
            show_alert=True,
        )

    await add_many_to_queue(
        chat_id,
        [
            _song_to_track(s, query.from_user.id, query.from_user.mention)
            for s in songs
        ],
    )
    asyncio.create_task(prefetch_next(chat_id))
    await query.answer(f"Queued {len(songs)} tracks.")
    await _say(
        client, query, chat_id,
        f"`•` Added **{len(songs)}** tracks from **{pl.get('title')}** to the queue.",
    )
    await plcore.session_start(chat_id, pid, query.from_user.id, len(songs))


def _song_to_track(
    song: dict, user_id: int = None, requester_mention: str = None
) -> dict:
    """Stored song doc → the track shape the music subsystem expects."""
    return {
        "id": song.get("video_id"),
        "title": song.get("title"),
        "uploader": song.get("uploader"),
        "thumbnail": song.get("thumbnail"),
        "duration": song.get("duration"),
        "webpage_url": song.get("webpage_url"),
        "source": song.get("source", "youtube"),
        "user_id": user_id,
        "requester_mention": requester_mention,
    }


# ---- Sharing / export --------------------------------------------------------


async def _h_share(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.render_share(pl, build_share_link(pid))
        await _edit(query, text, markup)
        await query.answer()


async def _h_qr(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    allowed, retry = await guard_action(query.from_user.id, "qr", LIMIT_QR)
    if not allowed:
        return await query.answer(limit_message("QR", retry), show_alert=True)

    await query.answer("Generating…")
    png = await asyncio.to_thread(generate_qr, pid, pl.get("title", ""))
    if not png:
        return await query.message.reply_text("`•` Could not build that QR code.")

    await query.message.reply_photo(
        png,
        caption=(
            f"**{ui.G_QR} {pl.get('title', 'Untitled')}**\n\n"
            f"`•` Scan to open this playlist."
        ),
    )


async def _h_export(client, query, pid, arg):
    """First tap shows the format picker; the arg carries the chosen format."""
    pl = await _load_viewable(query, pid)
    if not pl:
        return

    if not arg:
        await query.answer()
        return await _edit(query, *ui.render_export_picker(pl))

    allowed, retry = await guard_action(query.from_user.id, "export", LIMIT_EXPORT)
    if not allowed:
        return await query.answer(limit_message("export", retry), show_alert=True)
    if not await claim_tap(query.from_user.id, query.data):
        return await query.answer("Already building that…")

    await query.answer("Building your file…")
    doc, error = await export_playlist(pid, arg)
    if error:
        return await query.message.reply_text(f"`•` {error}")

    await query.message.reply_document(
        doc, caption=f"`•` **{pl.get('title', 'Untitled')}** — {arg.upper()} export"
    )


# ---- Reporting ---------------------------------------------------------------


async def _h_report(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    user_id = query.from_user.id
    if pl.get("owner_id") == user_id:
        return await query.answer("You can't report your own playlist.", show_alert=True)

    allowed, retry = await guard_action(user_id, "report", LIMIT_REPORT)
    if not allowed:
        return await query.answer(limit_message("report", retry), show_alert=True)

    filed = await db.report_playlist(pid, user_id, "user_report")
    if filed:
        # A report nobody sees is the same as no report. Push it to the log
        # channel so a dev can act on it with /plreports → /plban.
        try:
            reporter = query.from_user
            handle = f"@{reporter.username}" if reporter.username else reporter.mention
            await pgram.send_message(
                EVENT_LOGS,
                f"#PLAYLIST_REPORT\n"
                f"`•` **{pl.get('title', 'Untitled')}**\n"
                f"`•` id: `{pid}`\n"
                f"`•` owner: `{pl.get('owner_id')}`\n"
                f"`•` reported by: {handle} (`{user_id}`)\n\n"
                f"Review: `/plreports` · ban: `/plban {pid}`",
            )
        except Exception as e:
            LOGGER.warning("[Playlists] Could not forward report to log channel: %s", e)
    await query.answer(
        "Reported. Moderators will review it."
        if filed
        else "You've already reported this playlist.",
        show_alert=True,
    )


# ---- Moderation (dev-only) ---------------------------------------------------
#
# These are gated by @auth (DEV_USERS only) — the same gate as /eval and
# /restart. User reports land in EVENT_LOGS; a dev triages them here.


@auth(pattern="plreports")
async def plreports_cmd(client: Client, message: Message):
    reports = await db.get_open_reports(limit=20)
    if not reports:
        return await message.reply_text("`•` No open playlist reports.")

    # Collapse duplicate reports of the same playlist into one line with a count.
    counts: dict = {}
    for r in reports:
        counts.setdefault(r["playlist_id"], 0)
        counts[r["playlist_id"]] += 1

    pls = await db.get_playlists_bulk(list(counts))
    lines = ["**Open playlist reports**", ""]
    for pid, n in counts.items():
        pl = pls.get(pid)
        title = pl.get("title", "Untitled") if pl else "(deleted)"
        banned = " — already banned" if pl and pl.get("banned") else ""
        lines.append(f"`•` **{title}** — {n} report{'s' if n != 1 else ''}{banned}\n   `{pid}`")
    lines.append("\nBan: `/plban <id>` · unban: `/plunban <id>`")
    await message.reply_text("\n".join(lines))


@auth(pattern="plban")
async def plban_cmd(client: Client, message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        return await message.reply_text("Usage: `/plban <playlist_id>`")
    pid = parts[1]
    pl = await db.get_playlist(pid)
    if not pl:
        return await message.reply_text("`•` No playlist with that id.")
    await db.set_banned(pid, True)
    await db.resolve_reports(pid)
    await message.reply_text(f"`•` Banned **{pl.get('title', 'Untitled')}** and cleared its reports.")


@auth(pattern="plunban")
async def plunban_cmd(client: Client, message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        return await message.reply_text("Usage: `/plunban <playlist_id>`")
    pid = parts[1]
    pl = await db.get_playlist(pid)
    if not pl:
        return await message.reply_text("`•` No playlist with that id.")
    await db.set_banned(pid, False)
    await message.reply_text(f"`•` Unbanned **{pl.get('title', 'Untitled')}**.")


# ---- Editing -----------------------------------------------------------------


async def _h_access(client, query, pid, arg):
    """Access-mode picker. Owner-only: editors can add songs, not change reach."""
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer("Only the owner can change access.", show_alert=True)
    text, markup = ui.render_access(pl)
    await _edit(query, text, markup)
    await query.answer()


async def _h_setaccess(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer("Only the owner can change access.", show_alert=True)
    if arg not in db.ACCESS_MODES:
        return await query.answer()

    updates = {"access_mode": arg}
    if arg == db.ACCESS_SERVER:
        if not query.message or query.message.chat.type.name == "PRIVATE":
            return await query.answer(
                "Set server-only from inside the group it belongs to.", show_alert=True
            )
        updates["server_chat_id"] = query.message.chat.id

    await db.update_playlist(pid, updates)
    await social.log(pid, query.from_user.id, "access_changed", mode=arg)
    await query.answer(f"Access set to {ui.MODE_LABEL.get(arg, arg)}.")

    refreshed = await db.get_playlist(pid)
    if refreshed:
        text, markup = ui.render_access(refreshed)
        await _edit(query, text, markup)


async def _h_delprompt(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer("Only the owner can delete this.", show_alert=True)
    text, markup = ui.render_delete_confirm(pl)
    await _edit(query, text, markup)
    await query.answer()


async def _h_delete(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer("Only the owner can delete this.", show_alert=True)

    await db.delete_playlist(pid)
    await query.answer("Playlist deleted.")
    text, markup = ui.render_library(
        await db.get_user_playlists(query.from_user.id, limit=ui.PAGE_SIZE),
        0,
        await db.count_user_playlists(query.from_user.id),
    )
    await _edit(query, text, markup)


async def _h_rmsong(client, query, pid, arg):
    """Paged remove-song list; arg is either a page ("0") or "p<position>"."""
    pl = await _load_editable(query, pid)
    if not pl:
        return

    if arg.startswith("p"):
        removed = await db.remove_song(pid, _int(arg[1:], -1))
        if removed:
            await social.log(
                pid, query.from_user.id, "removed_song", title=removed.get("title")
            )
            await query.answer(f"Removed {removed.get('title', 'track')}.")
        else:
            await query.answer("That track is already gone.")
        pl = await db.get_playlist(pid)
        arg = "0"
    else:
        await query.answer()

    await _render_picker(query, pl, "rmsong", _int(arg))


async def _h_reorder(client, query, pid, arg):
    """
    Move a track one slot up. Two taps beats a drag-and-drop we can't render in
    an inline keyboard, and it composes: repeat to walk a track anywhere.
    """
    pl = await _load_editable(query, pid)
    if not pl:
        return

    if arg.startswith("u"):
        position = _int(arg[1:], 0)
        if position > 1:
            await db.move_song(pid, position, position - 1)
            await social.log(pid, query.from_user.id, "moved_song", position=position)
            await query.answer("Moved up.")
        else:
            await query.answer("Already first.")
        pl = await db.get_playlist(pid)
        arg = "0"
    else:
        await query.answer()

    await _render_picker(query, pl, "reorder", _int(arg))


async def _render_picker(query, pl, mode: str, page: int):
    songs = await db.get_songs(
        pl["playlist_id"], skip=page * ui.SONG_PAGE_SIZE, limit=ui.SONG_PAGE_SIZE
    )
    await _edit(query, *ui.render_song_picker(pl, songs, page, mode))


async def _h_editors(client, query, pid, arg):
    """List collaborators; arg "r<user_id>" removes one."""
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer("Only the owner manages editors.", show_alert=True)

    if arg.startswith("r"):
        removed_id = _int(arg[1:], 0)
        if removed_id:
            await db.remove_editor(pid, removed_id)
            await social.log(pid, query.from_user.id, "editor_removed", target=removed_id)
            await query.answer("Editor removed.")
        pl = await db.get_playlist(pid)
    else:
        await query.answer()

    names = await social.resolve_names(pl.get("editors", []) or [])
    await _edit(query, *ui.render_editors(pl, names))


# ---- Duplicate resolution ----------------------------------------------------


async def _h_dupreplace(client, query, pid, arg):
    pl = await _load_editable(query, pid)
    if not pl:
        return
    track = await _stashed_track(arg)
    if not track:
        return await query.answer("That prompt expired — add it again.", show_alert=True)

    video_id = track.get("video_id") or track.get("id")
    ok = await plcore.replace_duplicate(pid, video_id, track, query.from_user.id)
    await query.answer("Replaced." if ok else "Could not replace that track.")
    refreshed = await db.get_playlist(pid)
    if refreshed:
        await _show_view(query, refreshed)


async def _h_dupskip(client, query, pid, arg):
    await _stashed_track(arg)
    await query.answer("Skipped.")
    pl = await _load_viewable(query, pid)
    if pl:
        await _show_view(query, pl)


# ---- Prompts that need typed input ------------------------------------------


# Every prompt captures the next thing you type; /cancel backs out. Keep the
# hint in one place instead of repeating it in each string.
_CANCEL_HINT = "\n\n`•` /cancel to stop."

_PROMPTS = {
    "newprompt": (
        "new",
        f"**{ui.G_ADD} New playlist**\n\nSend a name." + _CANCEL_HINT,
    ),
    "searchprompt": (
        "search",
        f"**{ui.G_SEARCH} Search**\n\nSend a playlist name to look for." + _CANCEL_HINT,
    ),
    "addprompt": (
        "add",
        f"**{ui.G_ADD} Add music**\n\nSend a song name, or a YouTube or "
        "Spotify link." + _CANCEL_HINT,
    ),
    "rename": (
        "rename",
        f"**{ui.G_EDIT} Rename**\n\nSend the new name." + _CANCEL_HINT,
    ),
    "redesc": (
        "redesc",
        f"**{ui.G_EDIT} Description**\n\nSend the new description." + _CANCEL_HINT,
    ),
    "addeditor": (
        "addeditor",
        f"**{ui.G_ADD} Add editor**\n\nForward a message from them, or send "
        "their user id." + _CANCEL_HINT,
    ),
}


async def _h_prompt(client, query, pid, arg):
    verb, _, _ = ui.parse_cb(query.data)
    action, text = _PROMPTS[verb]

    # Editing prompts need edit rights before we start capturing their input.
    if action in ("add", "rename", "redesc", "addeditor"):
        if not await _load_editable(query, pid):
            return

    await _set_pending(query.from_user.id, action, pid)

    # Typed replies are only captured in PM (a group listener would have to read
    # every message in every chat). The pending state is keyed by user in Redis,
    # so it's already waiting for them there — this just walks them over, the
    # same way notes/rules/connect hand off to PM.
    if query.message and query.message.chat.type.name != "PRIVATE":
        await _edit(query, *ui.render_pm_handoff(text))
        return await query.answer("Continue in my PM.", show_alert=True)

    await _edit(query, *ui.render_prompt(text, pid))
    await query.answer()


# ---- Text input capture ------------------------------------------------------


@register(pattern="cancel")
async def cancel_pending_cmd(client: Client, message: Message):
    """Cancel any pending playlist prompt."""
    if getattr(client, "is_clone", False):
        return
    if not message.from_user:
        return

    pending = await _get_pending(message.from_user.id)
    if pending:
        await _clear_pending(message.from_user.id)
        await message.reply_text("Cancelled.")
    else:
        await message.reply_text("Nothing to cancel.")


@listen(filters=filters.private & filters.incoming & filters.text)
async def playlist_text_input(client: Client, message: Message):
    """
    Capture the reply to a playlist prompt.

    No-op unless this user has a pending prompt, so it stays out of the way of
    every other private message the bot handles.
    """
    if getattr(client, "is_clone", False):
        return
    if not message.from_user:
        return

    user_id = message.from_user.id
    pending = await _get_pending(user_id)
    if not pending:
        return

    text = (message.text or "").strip()
    if text.lower() in ("/cancel", "cancel"):
        await _clear_pending(user_id)
        return await message.reply_text("`•` Cancelled.")
    if text.startswith("/"):
        # Another command means they've moved on; don't swallow it.
        return

    action, pid = pending.get("action"), pending.get("pid", "")
    await _clear_pending(user_id)

    handler = _INPUT_ROUTES.get(action)
    if handler:
        try:
            await handler(client, message, pid, text)
        except Exception as e:
            await report_error("playlists.input", e, action=action, user=user_id)
            await message.reply_text("`•` Something went wrong.")


async def _i_new(client, message, pid, text):
    user_id = message.from_user.id

    allowed, retry = await guard_action(user_id, "create", LIMIT_CREATE)
    if not allowed:
        return await message.reply_text(limit_message("create", retry))

    title, error = validate_title(text)
    if error:
        return await message.reply_text(f"`•` {error}")

    if await db.count_user_playlists(user_id) >= db.MAX_PLAYLISTS_PER_USER:
        return await message.reply_text(
            f"`•` You've reached the limit of {db.MAX_PLAYLISTS_PER_USER} playlists."
        )

    pl = await db.create_playlist(user_id, title)
    if not pl:
        return await message.reply_text("`•` Could not create that playlist.")

    view_text, markup = await ui.render_playlist_view(pl, user_id, client)
    await send_menu(message, view_text, markup)


async def _i_search(client, message, pid, text):
    term = sanitize_text(text, max_len=64)
    playlists = await db.search(term, limit=ui.PAGE_SIZE)
    view_text, markup = ui.render_discovery(playlists, 0, "search", term)
    await send_menu(message, view_text, markup)


async def _i_rename(client, message, pid, text):
    pl = await db.get_playlist(pid)
    if not pl or not await plcore.can_edit(pl, message.from_user.id):
        return await message.reply_text("`•` You can't edit that playlist.")

    title, error = validate_title(text)
    if error:
        return await message.reply_text(f"`•` {error}")

    await db.update_playlist(pid, {"title": title})
    await social.log(pid, message.from_user.id, "renamed", title=title)
    refreshed = await db.get_playlist(pid)
    view_text, markup = await ui.render_playlist_view(
        refreshed, message.from_user.id, client
    )
    await send_menu(message, view_text, markup)


async def _i_redesc(client, message, pid, text):
    pl = await db.get_playlist(pid)
    if not pl or not await plcore.can_edit(pl, message.from_user.id):
        return await message.reply_text("`•` You can't edit that playlist.")

    description = sanitize_text(text, max_len=200)
    await db.update_playlist(pid, {"description": description})
    await social.log(pid, message.from_user.id, "described")
    refreshed = await db.get_playlist(pid)
    view_text, markup = await ui.render_playlist_view(
        refreshed, message.from_user.id, client
    )
    await send_menu(message, view_text, markup)


async def _i_addeditor(client, message, pid, text):
    pl = await db.get_playlist(pid)
    if not pl or pl.get("owner_id") != message.from_user.id:
        return await message.reply_text("`•` Only the owner manages editors.")

    target = None
    if message.forward_from:
        target = message.forward_from.id
    elif text.isdigit():
        target = int(text)
    else:
        try:
            target = (await client.get_users(text.lstrip("@"))).id
        except Exception:
            target = None

    if not target:
        return await message.reply_text(
            "`•` Couldn't identify that user. Forward one of their messages, or "
            "send their numeric id."
        )
    if target == pl.get("owner_id"):
        return await message.reply_text("`•` You already own this playlist.")

    await db.add_editor(pid, target)
    await social.log(pid, message.from_user.id, "editor_added", target=target)
    name = await social.resolve_name(target)
    await message.reply_text(f"`•` **{name}** can now edit this playlist.")


async def _i_add(client, message, pid, text):
    """Add one song, or bulk-import a whole playlist link."""
    user_id = message.from_user.id
    pl = await db.get_playlist(pid)
    if not pl or not await plcore.can_edit(pl, user_id):
        return await message.reply_text("`•` You can't edit that playlist.")

    kind, _ = imports.detect_source(text)

    # A single video/track is a plain add; anything with a track list goes
    # through the import path with its progress bar.
    if kind in ("yt_playlist", "sp_playlist", "sp_album"):
        return await _bulk_import(client, message, pl, text, kind)

    status_msg = await message.reply_text(f"`•` Looking up **{sanitize_text(text, 80)}**…")

    if kind:
        tracks, error = await imports.import_tracks(text)
        if error:
            return await status_msg.edit_text(f"`•` {error}")
        track = tracks[0] if tracks else None
    else:
        from Emilia.modules.plugins.music.core.youtube import search_youtube

        results = await search_youtube(text, limit=1)
        track = results[0] if results else None

    if not track:
        return await status_msg.edit_text("`•` Nothing found for that.")

    status, position, existing = await plcore.add_song_with_prompt(pid, track, user_id)

    if status == "duplicate":
        token = await _stash_track(track)
        prompt_text, markup = ui.render_duplicate_prompt(pl, existing, track, token)
        return await status_msg.edit_text(prompt_text, reply_markup=markup)
    if status == "full":
        return await status_msg.edit_text(
            f"`•` That playlist is full ({db.MAX_SONGS_PER_PLAYLIST} songs)."
        )
    if status != "added":
        return await status_msg.edit_text("`•` Could not add that track.")

    await status_msg.edit_text(
        f"`•` Added **{track.get('title', 'track')}** at position **{position}**."
    )


async def _bulk_import(client, message, pl, text, kind):
    user_id = message.from_user.id
    pid = pl["playlist_id"]

    allowed, retry = await guard_action(user_id, "import", LIMIT_IMPORT)
    if not allowed:
        return await message.reply_text(limit_message("import", retry))

    label = imports.source_label(kind)
    status_msg = await message.reply_text(f"`•` Reading {label}…")
    reporter = imports.ProgressReporter(status_msg, label=f"Importing {label}")

    tracks, error = await imports.import_tracks(text, progress=reporter.update)
    await reporter.flush()

    if error:
        return await status_msg.edit_text(f"`•` {error}")
    if not tracks:
        return await status_msg.edit_text("`•` Nothing importable at that link.")

    added, skipped = await plcore.import_tracks_bulk(pid, tracks, user_id)

    summary = [f"**{ui.G_LIBRARY} Import complete**", ""]
    summary.append(f"`•` Added **{added}** track{'s' if added != 1 else ''}")
    if skipped:
        summary.append(f"`•` Skipped **{skipped}** already in the playlist")
    if kind.startswith("sp_"):
        summary.append("`•` Spotify tracks are matched to their closest audio on YouTube.")

    refreshed = await db.get_playlist(pid)
    view_text, markup = await ui.render_playlist_view(refreshed, user_id, client)
    await status_msg.edit_text("\n".join(summary))
    await send_menu(message, view_text, markup)


# ---- Auto-Liked Songs --------------------------------------------------------


@callbackquery(pattern=r"^pl_like:")
async def auto_like_callback(client: Client, query: CallbackQuery):
    """
    The ♡ on every Playing Now card: one tap, straight into the tapper's
    "Liked Songs" playlist. No menus, no confirmation step.

    Callback data carries only the video id — 64 bytes doesn't fit a title and
    url — so the full track is recovered from the chat's live playback state,
    which already holds it.
    """
    user_id = query.from_user.id
    video_id = query.data.split(":", 1)[1] if ":" in query.data else ""
    if not video_id:
        return await query.answer()

    allowed, _ = await guard_action(user_id, "like", LIMIT_CALLBACK)
    if not allowed:
        return await query.answer("Slow down a moment.", show_alert=True)

    track = await _find_live_track(query.message.chat.id, video_id)
    if not track:
        return await query.answer(
            "That track is no longer playing — open it again to like it.",
            show_alert=True,
        )

    # Liking from a group's player is a "listening here" signal too, so a later
    # Play from PM knows where to stream.
    await plcore.remember_group(user_id, query.message.chat.id)

    pl = await db.get_or_create_liked_playlist(user_id)
    if not pl:
        return await query.answer("Could not open your Liked Songs.", show_alert=True)

    pid = pl["playlist_id"]
    status, position, existing = await plcore.add_song_with_prompt(pid, track, user_id)

    if status == "duplicate":
        # Already liked. Tapping again is far more likely to mean "undo" than a
        # request to overwrite identical metadata, so treat the heart as a
        # toggle rather than showing the Replace/Skip prompt here.
        if existing:
            await db.remove_song(pid, existing.get("position"))
        return await query.answer("Removed from Liked Songs.")
    if status == "full":
        return await query.answer(
            f"Liked Songs is full ({db.MAX_SONGS_PER_PLAYLIST}).", show_alert=True
        )
    if status != "added":
        return await query.answer("Could not save that track.", show_alert=True)

    if position == 1:
        # First track they've ever liked, and the only moment where an alert is
        # worth the interruption: this is how most people will find out the
        # playlist system exists at all.
        return await query.answer(
            "♥ Saved to your Liked Songs.\n\n"
            "Send /playlist to see it, add more, and share it with anyone.",
            show_alert=True,
        )

    await query.answer(f"♥ Saved to Liked Songs ({position}).")


async def _find_live_track(chat_id: int, video_id: str):
    """Recover a full track dict from the chat's current playback state."""
    from Emilia.modules.plugins.music.utils.store import get_now_playing, get_queue

    now = await get_now_playing(chat_id)
    if now and (now.get("id") == video_id):
        return now
    for track in await get_queue(chat_id) or []:
        if track.get("id") == video_id:
            return track
    return None


# ---- Routing tables ----------------------------------------------------------

_ROUTES = {
    "root": _h_root,
    "lib": _h_lib,
    "trend": _h_trend,
    "browse": _h_browse,
    "saved": _h_saved,
    "server": _h_server,
    "search": _h_search,
    "view": _h_view,
    "more": _h_more,
    "manage": _h_manage,
    "liked": _h_liked,
    "stats": _h_stats,
    "feed": _h_feed,
    "lineage": _h_lineage,
    "like": _h_like,
    "save": _h_save,
    "fork": _h_fork,
    "play": _h_play,
    "enqueue": _h_enqueue,
    "share": _h_share,
    "qr": _h_qr,
    "export": _h_export,
    "report": _h_report,
    "access": _h_access,
    "setaccess": _h_setaccess,
    "delprompt": _h_delprompt,
    "delete": _h_delete,
    "rmsong": _h_rmsong,
    "reorder": _h_reorder,
    "editors": _h_editors,
    "dupreplace": _h_dupreplace,
    "dupskip": _h_dupskip,
    "newprompt": _h_prompt,
    "searchprompt": _h_prompt,
    "addprompt": _h_prompt,
    "rename": _h_prompt,
    "redesc": _h_prompt,
    "addeditor": _h_prompt,
}

_INPUT_ROUTES = {
    "new": _i_new,
    "search": _i_search,
    "add": _i_add,
    "rename": _i_rename,
    "redesc": _i_redesc,
    "addeditor": _i_addeditor,
}

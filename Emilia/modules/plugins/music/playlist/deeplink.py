"""
Deep-link entry for shared playlists.

Follows the same shape as every other redirect in this codebase (note_redirect,
rulesRedirect, connectRedirect): a plain coroutine the /start handler in
start.py calls once startCheckQuery matches. No second on_message handler for
"start" — one command, one handler, one dispatch chain.
"""

from Emilia import LOGGER
from Emilia.modules.plugins.music.playlist.ui import render_playlist_view
from Emilia.modules.plugins.music.playlist.utils import (
    parse_deeplink,
    resolve_shared_playlist,
)


async def playlist_redirect(client, message):
    """
    Handle `t.me/<bot>?start=pl_<id>`.

    startCheckQuery has already confirmed the "pl" prefix; everything after the
    first underscore is the playlist id.
    """
    user_id = message.from_user.id
    payload = message.text.split()[1]
    playlist_id = parse_deeplink(payload)

    if not playlist_id:
        return await message.reply_text("`•` That playlist link is malformed.")

    pl, error = await resolve_shared_playlist(playlist_id, user_id)
    if error:
        return await message.reply_text(f"`•` {error}")

    try:
        text, markup = await render_playlist_view(pl, user_id, client)
    except Exception as e:
        LOGGER.error(
            f"[Playlists] deeplink render failed for {playlist_id}: {e}", exc_info=True
        )
        return await message.reply_text("`•` Could not open that playlist.")

    # Imported here rather than at module scope: commands.py imports this module
    # for the /start dispatch chain, so a top-level import would be circular.
    from Emilia.modules.plugins.music.playlist.commands import send_menu

    await send_menu(message, text, markup)


async def playlist_menu_redirect(client, message):
    """
    Handle `t.me/<bot>?start=playlists` from the Now Playing "Playlists" button.

    Opens the root playlist menu. First-time user detection happens at the
    playlist_command level, so here we default to first_time=False.
    """
    from Emilia.modules.plugins.music.playlist import ui
    from Emilia.modules.plugins.music.playlist.commands import send_menu
    from Emilia.mongo import playlists_mongo as db

    user_id = message.from_user.id
    count = await db.count_user_playlists(user_id)
    first_time = (count == 0)

    text, markup = ui.render_root(
        user_id,
        in_group=False,  # Deep-link always lands in PM
        first_time=first_time
    )
    await send_menu(message, text, markup)

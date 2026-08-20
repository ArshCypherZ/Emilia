import asyncio
import html
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle, ChatMemberStatus, ChatType, ParseMode
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    LinkPreviewOptions,
)
from ntgcalls import ConnectionNotFound
from pytgcalls.types import (
    AudioQuality,
    GroupCallConfig,
    MediaStream,
    StreamEnded,
    VideoQuality,
)
from pytgcalls.exceptions import NoActiveGroupCall, CallBusy, ClientNotStarted, NotInCallError
from pyrogram.errors import (
    ChannelPrivate,
    ChatAdminRequired,
    FloodWait,
    GroupCallInvalid,
    GroupcallForbidden,
    InviteRequestSent,
    PeerIdInvalid,
    UserAlreadyParticipant,
    UserBannedInChannel,
    UserNotParticipant,
    UserPrivacyRestricted,
)

from Emilia.custom_filter import register
from Emilia import Config, redis_client, strings
from Emilia.modules.plugins.music.core.call import emilia_call, assistant
from Emilia import pgram
from Emilia.helper.admins import is_admin
from Emilia.modules.plugins.music.playlist.core import session_finish
from Emilia.utils.errors import report_error
from Emilia.utils.menu_guard import claim_tap
from Emilia.mongo.chats_settings_mongo import get_playmenu_setting_cached, playmenu_db
from Emilia.modules.plugins.music.core.youtube import (
    ensure_local_file,
    fetch_and_download,
    search_youtube,
    resolve_audio,
    get_playlist_tracks,
)
from Emilia.modules.plugins.music.utils.store import (
    add_to_queue,
    add_many_to_queue,
    get_now_playing,
    set_now_playing,
    set_menu,
    get_menu,
    clear_menu,
    pop_next,
    clear_queue,
    get_queue,
    set_loop_mode,
    get_loop_mode,
    set_shuffle_mode,
    get_shuffle_mode,
    set_queue_direct,
    get_paused,
    set_paused,
    get_playback_message_id,
    set_playback_message_id,
)

LOGGER = logging.getLogger(__name__)

# ---- Constants ----

THUMB = ""

# Membership lasts until someone kicks the assistant, which arrives as a chat
# update we listen for — the TTL is just a backstop for kicks we never saw.
_ASSISTANT_TTL = 3600
_join_locks: dict[int, asyncio.Lock] = {}
_stream_end_state: dict[int, tuple[set, set]] = {}

_NEEDS_INVITE_RIGHTS = (
    "I need to be an admin here with the 'Invite users via link' permission "
    "so I can bring my music assistant into the group."
)
_ASSISTANT_BANNED = (
    "My music assistant (@{username}) is banned from this group. "
    "Unban it and try again."
)
_ACTIVE_STATUSES = {
    ChatMemberStatus.OWNER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.RESTRICTED,
}


def _assistant_key(chat_id) -> str:
    return f"music_assistant_in:{chat_id}"


async def forget_assistant_membership(chat_id) -> None:
    """Drop the cached 'assistant is in this chat' flag after a kick or leave."""
    await redis_client.delete(_assistant_key(chat_id))


async def _assistant_me():
    me = getattr(assistant, "me", None)
    if not me:
        me = await assistant.get_me()
        assistant.me = me
    return me


# ---- Authorization ----

async def _check_access(user_id, message, chat_id):
    """Return True if the user can control playback for this chat.
    Allows: command sender + group admins.
    """
    now = await get_now_playing(chat_id)
    if now and now.get("user_id"):
        if user_id == now["user_id"]:
            return True
        if await is_admin(message, user_id, chat_id=chat_id):
            return True
        return False
    return True


async def _check_callback_access(query, chat_id):
    return await _check_access(query.from_user.id, query.message, chat_id)


async def _check_command_access(message, chat_id):
    return await _check_access(message.from_user.id, message, chat_id)


async def _ensure_assistant_in_chat(chat_id: int) -> tuple[bool, str | None]:
    """Ensure the assistant userbot is present in the chat before streaming."""
    if await redis_client.get(_assistant_key(chat_id)):
        return True, None

    lock = _join_locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        if await redis_client.get(_assistant_key(chat_id)):
            return True, None
        ok, err = await _join_assistant(chat_id)
        if ok:
            await redis_client.setex(_assistant_key(chat_id), _ASSISTANT_TTL, "1")
        return ok, err


async def _join_assistant(chat_id: int) -> tuple[bool, str | None]:
    """Join the assistant userbot into the chat using member checks, direct add, or invite links."""
    me = await _assistant_me()
    assistant_id = me.username or me.id

    # 1. Check if already an active member in the group
    try:
        member = await pgram.get_chat_member(chat_id, assistant_id)
        if member.status in _ACTIVE_STATUSES:
            return True, None
    except UserNotParticipant:
        pass
    except FloodWait as e:
        await report_error("music.assistant_join.flood_wait", e, chat_id=chat_id, wait_seconds=e.value)
        return False, "I couldn't add my music assistant to this group. Please add it manually."
    except Exception:
        pass

    # 2. Try direct add
    try:
        if not await pgram.add_chat_members(chat_id, assistant_id):
            return True, None
    except ChatAdminRequired:
        return False, _NEEDS_INVITE_RIGHTS
    except UserBannedInChannel:
        return False, _ASSISTANT_BANNED.format(username=me.username or me.first_name)
    except FloodWait as e:
        await report_error("music.assistant_add.flood_wait", e, chat_id=chat_id, wait_seconds=e.value)
        return False, "I couldn't add my music assistant to this group. Please add it manually."
    except Exception:
        pass

    # 3. Fallback: Join via invite link (public username or single-use invite link)
    try:
        chat = await pgram.get_chat(chat_id)
        link = (
            f"https://t.me/{chat.username}"
            if getattr(chat, "username", None)
            else (
                await pgram.create_chat_invite_link(
                    chat_id,
                    name="Music assistant",
                    member_limit=1,
                    expire_date=datetime.now(timezone.utc) + timedelta(minutes=15),
                )
            ).invite_link
        )
        await assistant.join_chat(link)
        return True, None
    except UserAlreadyParticipant:
        return True, None
    except InviteRequestSent:
        return False, "An admin must approve the assistant's join request, then play again."
    except ChatAdminRequired:
        return False, _NEEDS_INVITE_RIGHTS
    except UserBannedInChannel:
        return False, _ASSISTANT_BANNED.format(username=me.username or me.first_name)
    except FloodWait as e:
        await report_error("music.assistant_link.flood_wait", e, chat_id=chat_id, wait_seconds=e.value)
        return False, "I couldn't add my music assistant to this group. Please add it manually."
    except Exception as e:
        LOGGER.warning("[Music] Assistant join via invite link failed for %s: %s", chat_id, e)

    username = getattr(me, "username", None)
    return False, (
        f"Could not add music assistant (@{username}). Add it manually or make me admin with invite permissions."
        if username
        else "Could not add music assistant to this group. Please add it manually."
    )


async def _is_in_call(chat_id):
    """Check if assistant is currently in a voice/video call in this chat."""
    try:
        participants = await emilia_call.get_participants(chat_id)
        return bool(participants)
    except Exception:
        return False


# ---- Helpers ----

async def _safe_edit_reply_markup(message, markup):
    """Safely edit reply markup, ignoring MESSAGE_NOT_MODIFIED and MESSAGE_ID_INVALID."""
    try:
        await message.edit_reply_markup(markup)
    except Exception as e:
        LOGGER.debug("[Music] Failed to edit reply markup: %s", e)


def _fmt_duration(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "N/A"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_file_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / 1024 / 1024:.1f} MB"


def _make_progress_callback(message, title="Downloading"):
    """Create a progress callback that edits message caption with download progress (time-throttled)."""
    last_update = [0.0, 0.0]  # [last_pct, last_time]
    loop = asyncio.get_running_loop()

    def _callback(downloaded, total, pct):
        now_time = time.time()
        if abs(pct - last_update[0]) < 0.05 and (now_time - last_update[1]) < 4.0:
            return
        if (now_time - last_update[1]) < 4.0 and pct < 0.99:
            return
        last_update[0] = pct
        last_update[1] = now_time
        loop.create_task(_update_progress(message, title, downloaded, total, pct))

    return _callback


async def _update_progress(message, title, downloaded, total, pct):
    try:
        await message.edit_caption(
            f"{title}...\n"
            f"**{_fmt_file_size(downloaded)}** / {_fmt_file_size(total)}\n"
            f"**{pct * 100:.0f}%**"
        )
    except Exception:
        pass


# ---- Markup builders ----

async def _build_playback_markup(track_info: dict, chat_id: int = None):
    """Build playback control markup with loop, shuffle."""
    loop_mode = track_info.get("loop_mode", "off")
    shuffle = track_info.get("shuffle", False)

    loop_emoji = {"off": "🔁", "one": "🔂", "all": "🔁"}.get(loop_mode, "🔁")
    shuffle_text = "🔀 Shuffle" if not shuffle else "🔀 Shuffle on"

    # Auto-Liked Songs: one tap saves this track to the tapper's "Liked Songs"
    # playlist, no menus. The label stays a hollow heart rather than reflecting
    # liked-state, because this card is shared by everyone in the chat while
    # liking is per-user — a filled heart would show one person's state to all
    # of them. The tap's answer() confirms instead.
    rows = [
        [
            InlineKeyboardButton("Pause", callback_data="music_pause", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("Resume", callback_data="music_resume", style=ButtonStyle.PRIMARY),
        ],
        [
            InlineKeyboardButton(f"{loop_emoji} Loop", callback_data=f"music_loop:{loop_mode}", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton(shuffle_text, callback_data="music_shuffle", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("Stop", callback_data="music_stop", style=ButtonStyle.DANGER),
        ],
    ]

    video_id = track_info.get("id") or ""
    if video_id:
        rows.append([
            InlineKeyboardButton("♡ Save to Liked", callback_data=f"pl_like:{video_id}"),
            # Opens the playlist menu right here in the group rather than
            # deep-linking to PM. Playback only happens in a group voice chat, so
            # sending the user to PM to pick a playlist put them somewhere Play
            # could never work. The whole menu is callback-driven, so it renders
            # in-chat and its Play button streams on the first tap.
            InlineKeyboardButton("📚 Playlists", callback_data="pl:root::new"),
        ])

    return InlineKeyboardMarkup(rows)


def _build_menu_markup(idx: int, total: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Play", callback_data="music_choose", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("➕ Queue", callback_data="music_queue_add", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("Cancel", callback_data="music_cancel", style=ButtonStyle.DANGER),
        ],
        [
            InlineKeyboardButton("◀️ Prev", callback_data="music_prev", style=ButtonStyle.DEFAULT),
            InlineKeyboardButton(f"{idx + 1}/{total}", callback_data="music_ignore", style=ButtonStyle.DEFAULT),
            InlineKeyboardButton("Next ▶️", callback_data="music_next", style=ButtonStyle.DEFAULT),
        ],
    ])


# ---- Caption builders ----

def _build_caption(track_info, mention, prefix="**Playing Now**"):
    loop_mode = track_info.get("loop_mode", "off")
    shuffle = track_info.get("shuffle", False)
    extra = ""
    if loop_mode != "off":
        extra += f"\n`•` **Loop:** `{loop_mode}`"
    if shuffle:
        extra += "\n`•` **Shuffle:** `on`"
        
    title = track_info['title']
    url = track_info.get('webpage_url')
    track_display = f"[{title}]({url})" if url else title
    
    return (
        f"**{prefix.strip('*')}**\n\n"
        f"`•` **Track:** {track_display}\n"
        f"`•` **Duration:** `{_fmt_duration(track_info.get('duration'))}`\n"
        f"`•` **User:** {mention}"
        f"{extra}"
    )


def _menu_text(cand, idx, total):
    return (
        f"**Pick a track** ({idx + 1}/{total})\n\n"
        f"**Track:** {cand['title']}\n"
        f"**Channel:** {cand.get('uploader', 'Unknown')}\n"
        f"**Duration:** {_fmt_duration(cand.get('duration'))}\n\n"
        "Use ◀️ / ▶️ to browse, then ▶️ Play or ➕ Queue."
    )


# ---- Stream ----

def _make_stream(track_info):
    path = track_info.get("file_path", "")
    title = track_info.get("title", "Unknown")
    # An empty path sails straight through pytgcalls' own checks and streams
    # silence, so it has to be caught here where the track is still nameable.
    if not path:
        raise FileNotFoundError(f"no local file for {title!r}")
    LOGGER.debug("[Music] Creating stream for '%s' from '%s'", title, path)
    if track_info.get("is_video"):
        return MediaStream(
            path,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
        )

    return MediaStream(
        path,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE,
    )


def _stream_end_ready(chat_id, stream_type):
    state = _stream_end_state.get(chat_id)
    if not state:
        return False
    expected, ended = state
    if stream_type not in expected:
        return False
    ended.add(stream_type)
    if ended != expected:
        return False
    _stream_end_state.pop(chat_id, None)
    return True


def _clear_stream_end_state(chat_id):
    _stream_end_state.pop(chat_id, None)


async def _safe_play(chat_id, stream):
    """Start a stream and record which EOF events complete the playback."""
    config = GroupCallConfig(auto_start=True)
    _clear_stream_end_state(chat_id)
    try:
        await emilia_call.play(chat_id, stream, config=config)
    except (ConnectionNotFound, NotInCallError):
        LOGGER.info("[Music] Re-joining voice call for chat %s before playing", chat_id)
        try:
            await emilia_call.leave_call(chat_id)
        except NotInCallError:
            pass
        await emilia_call.play(chat_id, stream, config=config)
    except (ChannelPrivate, UserNotParticipant):
        LOGGER.info("[Music] Assistant not joined in %s during play; re-joining and retrying", chat_id)
        await forget_assistant_membership(chat_id)
        ok, _ = await _ensure_assistant_in_chat(chat_id)
        if not ok:
            raise
        await emilia_call.play(chat_id, stream, config=config)
    expected = set()
    if stream.microphone is not None:
        expected.add(StreamEnded.Type.AUDIO)
    if stream.camera is not None:
        expected.add(StreamEnded.Type.VIDEO)
    _stream_end_state[chat_id] = (expected, set())


async def _edit_sent(sent, text: str):
    try:
        await sent.edit_caption(text)
    except Exception:
        await sent.edit_text(text)


async def _delete_old_playback_message(chat_id):
    """Delete the previous playback message if it exists."""
    old_msg_id = await get_playback_message_id(chat_id)
    if old_msg_id:
        try:
            await pgram.delete_messages(chat_id, old_msg_id)
        except Exception:
            pass
        await set_playback_message_id(chat_id, None)


# ---- Prefetch ----

_prefetch_tasks: dict[int, asyncio.Task] = {}


def _clear_prefetch_task(chat_id, task):
    if _prefetch_tasks.get(chat_id) is task:
        _prefetch_tasks.pop(chat_id, None)


async def _prefetch_and_update(chat_id, track_key, url, is_video):
    try:
        track_info = await fetch_and_download(url, is_video)
        q = await get_queue(chat_id)
        track_id = track_info.get("id")
        for queued in q:
            queued_key = queued.get("id") or queued.get("webpage_url")
            if queued_key == track_id or queued_key == track_key:
                queued["file_path"] = track_info["file_path"]
                await set_queue_direct(chat_id, q)
                break
    except Exception as exc:
        LOGGER.debug("[Music] Prefetch failed for %s: %s", track_key, exc)


async def prefetch_next(chat_id):
    """Background: ensure next tracks' files are local for gap-free transitions."""
    q = await get_queue(chat_id)
    if not q:
        return
    # One in-flight download is enough to hide the normal handoff latency.
    # Starting three downloads per transition competes with FFmpeg and can
    # starve the active voice call on small hosts.
    track = q[0]
    path = track.get("file_path")
    if path and os.path.exists(path) and os.path.getsize(path) > 1024:
        return
    url = track.get("webpage_url", "")
    if not url.startswith("http"):
        return
    track_key = track.get("id") or url
    existing = _prefetch_tasks.get(chat_id)
    if existing and not existing.done():
        return
    task = asyncio.create_task(
        _prefetch_and_update(chat_id, track_key, url, track.get("is_video", False)),
        name=f"prefetch:{chat_id}:{track_key}",
    )
    _prefetch_tasks[chat_id] = task
    task.add_done_callback(lambda done, key=chat_id: _clear_prefetch_task(key, done))


# ---- Playback logic ----

async def _start_playback(chat_id, track_info, mention, menu_message=None, reply_message=None, user_id=None):
    """Start playback. Edits the chooser message in place when menu_message is
    given, otherwise replies with a fresh 'Playing Now' card."""
    now = await get_now_playing(chat_id)
    in_call = await _is_in_call(chat_id)
    is_playing = in_call and now and now.get("file_path") and os.path.exists(now.get("file_path", ""))

    if is_playing:
        existing = await get_queue(chat_id)
        now_url = now.get("webpage_url") if now else None
        track_url = track_info.get("webpage_url")
        if now_url == track_url or any(t.get("webpage_url") == track_url for t in existing):
            target = menu_message or reply_message
            if menu_message:
                await menu_message.delete()
            await target.reply_text(
                text="This track is already in the queue!",
                reply_markup=await _build_playback_markup(track_info, chat_id),
            )
            return

        if user_id is not None:
            track_info["user_id"] = user_id
        if mention:
            track_info["requester_mention"] = mention
        pos = await add_to_queue(chat_id, track_info)
        if menu_message:
            try:
                await menu_message.delete()
            except Exception:
                pass
        photo = track_info.get("thumbnail", THUMB)
        cap = _build_caption(track_info, mention, f"**Added to Queue #{pos}**")
        markup = await _build_playback_markup(track_info, chat_id)
        if reply_message is not None:
            try:
                sent = await reply_message.reply_photo(photo=photo, caption=cap, reply_markup=markup)
            except Exception:
                sent = await reply_message.reply_text(text=cap, reply_markup=markup)
        else:
            try:
                sent = await pgram.send_photo(chat_id, photo=photo, caption=cap, reply_markup=markup)
            except Exception:
                sent = await pgram.send_message(chat_id, text=cap, reply_markup=markup)
        await set_playback_message_id(chat_id, sent.id)
        asyncio.create_task(prefetch_next(chat_id))
        return

    if user_id is not None:
        track_info["user_id"] = user_id
    if mention:
        track_info["requester_mention"] = mention
    cap = _build_caption(track_info, mention)
    markup = await _build_playback_markup(track_info, chat_id)
    thumb = track_info.get("thumbnail", THUMB)

    await _delete_old_playback_message(chat_id)
    if menu_message:
        try:
            await menu_message.delete()
        except Exception:
            pass
    if reply_message is not None:
        try:
            sent = await reply_message.reply_photo(photo=thumb, caption=cap, reply_markup=markup)
        except Exception:
            sent = await reply_message.reply_text(text=cap, reply_markup=markup)
    else:
        try:
            sent = await pgram.send_photo(chat_id, photo=thumb, caption=cap, reply_markup=markup)
        except Exception:
            sent = await pgram.send_message(chat_id, text=cap, reply_markup=markup)

    ok, err = await _ensure_assistant_in_chat(chat_id)
    if not ok:
        await _edit_sent(sent, err)
        return

    try:
        await _safe_play(chat_id, _make_stream(track_info))
    except (ChannelPrivate, UserNotParticipant):
        await _edit_sent(sent, "Please add the music assistant to this group so it can join the voice chat.")
        return
    except FloodWait as e:
        await report_error("music.play.flood_wait", e, chat_id=chat_id, track=track_info.get("title"), wait_seconds=e.value)
        await _edit_sent(sent, "I couldn't start the stream right now. Please try again in a moment.")
        return
    except NoActiveGroupCall:
        await sent.edit_caption("I couldn't find or start the voice chat. Start it manually, then try again.")
        return
    except (ConnectionNotFound, GroupCallInvalid, GroupcallForbidden):
        await sent.edit_caption("Voice chat is unavailable. Start it manually, then try again.")
        return
    except ChatAdminRequired:
        await sent.edit_caption(
            "I couldn't start or join the voice chat. Start it manually, or grant "
            "the music assistant permission to manage video chats."
        )
        return
    except PeerIdInvalid:
        await sent.edit_caption("Unable to resolve this chat. Try sending a message first.")
        return
    except CallBusy:
        await sent.edit_caption("The voice chat is currently busy or experiencing high traffic.")
        return
    except ClientNotStarted:
        await sent.edit_caption("The assistant client is offline. Please report this to the admins.")
        return
    except Exception as e:
        await report_error("music.play", e, chat_id=chat_id, track=track_info.get("title"))
        await sent.edit_caption(
            "I couldn't start the stream. The developers have been notified — "
            "please try again in a moment."
        )
        return

    await set_paused(chat_id, False)
    await set_now_playing(chat_id, track_info)
    await set_playback_message_id(chat_id, sent.id)
    asyncio.create_task(prefetch_next(chat_id))


# ---- Chooser menu ----

async def _show_menu(message: Message, query: str, is_video: bool):
    msg = await message.reply_text("🔍 Searching...")
    try:
        candidates = await search_youtube(query, limit=8)
    except Exception as e:
        return await msg.edit_text(f"Search failed: {e}")
    if not candidates:
        return await msg.edit_text("No results found.")
    await set_menu(message.chat.id, {
        "candidates": candidates,
        "index": 0,
        "user_id": message.from_user.id,
        "is_video": is_video,
        "query": query,
    })
    await msg.delete()
    cand = candidates[0]
    try:
        await message.reply_photo(
            photo=cand.get("thumbnail") or THUMB,
            caption=_menu_text(cand, 0, len(candidates)),
            reply_markup=_build_menu_markup(0, len(candidates)),
        )
    except Exception:
        await message.reply_text(
            _menu_text(cand, 0, len(candidates)),
            reply_markup=_build_menu_markup(0, len(candidates)),
        )


async def _navigate(query, delta):
    menu = await get_menu(query.message.chat.id)
    if not menu or query.from_user.id != menu["user_id"]:
        return await query.answer("This isn't your menu.", show_alert=True)
    cands = menu["candidates"]
    i = (menu["index"] + delta) % len(cands)
    menu["index"] = i
    await set_menu(query.message.chat.id, menu)
    cand = cands[i]
    try:
        await query.message.edit_media(
            InputMediaPhoto(cand.get("thumbnail") or THUMB, caption=_menu_text(cand, i, len(cands))),
            reply_markup=_build_menu_markup(i, len(cands)),
        )
    except Exception:
        try:
            await query.message.edit_caption(
                _menu_text(cand, i, len(cands)),
                reply_markup=_build_menu_markup(i, len(cands)),
            )
        except Exception:
            pass
    await query.answer()


async def _check_if_clone(client, target):
    """Check if target is in private chat or if bot is a clone, blocking music commands when appropriate."""
    chat = getattr(target, "chat", None)
    if not chat and hasattr(target, "message") and target.message:
        chat = target.message.chat

    if chat and chat.type == ChatType.PRIVATE:
        if isinstance(target, CallbackQuery):
            try:
                await target.answer(strings.is_pvt, show_alert=True)
            except Exception:
                pass
        else:
            try:
                await target.reply_text(strings.is_pvt)
            except Exception:
                pass
        return True

    if getattr(client, "is_clone", False) or (getattr(client, "me", None) and client.me.id != Config.BOT_ID):
        text = (
            f"🎵 **Music System is Disabled on Clones**\n\n"
            f"To prevent server overloads and YouTube IP rate limits, music streaming is only enabled on our official bot:\n\n"
            f"👉 **[@{Config.BOT_USERNAME}](https://t.me/{Config.BOT_USERNAME})**\n\n"
            f"Add @{Config.BOT_USERNAME} to your group to enjoy high-quality music streaming!"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🤖 Add @{Config.BOT_USERNAME}", url=f"https://t.me/{Config.BOT_USERNAME}?startgroup=true")]
        ])
        if isinstance(target, CallbackQuery):
            try:
                await target.answer("Music system is disabled on cloned bots. Use the official bot!", show_alert=True)
            except Exception:
                pass
            try:
                if target.message:
                    await target.message.reply_text(
                        text,
                        reply_markup=markup,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
            except Exception:
                pass
        else:
            try:
                await target.reply_text(
                    text,
                    reply_markup=markup,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            except Exception:
                pass
        return True
    return False


# ---- Menu callbacks ----

@Client.on_callback_query(filters.regex("^music_ignore$"))
async def menu_ignore_cb(client, query):
    if await _check_if_clone(client, query):
        return
    await query.answer()


@Client.on_callback_query(filters.regex("^music_prev$"))
async def menu_prev_cb(client, query):
    if await _check_if_clone(client, query):
        return
    await _navigate(query, -1)


@Client.on_callback_query(filters.regex("^music_next$"))
async def menu_next_cb(client, query):
    if await _check_if_clone(client, query):
        return
    await _navigate(query, 1)


@Client.on_callback_query(filters.regex("^music_cancel$"))
async def menu_cancel_cb(client, query):
    if await _check_if_clone(client, query):
        return
    menu = await get_menu(query.message.chat.id)
    if not menu or query.from_user.id != menu["user_id"]:
        return await query.answer("This isn't your menu.", show_alert=True)
    await clear_menu(query.message.chat.id)
    await query.message.delete()
    await query.answer("Cancelled.")


@Client.on_callback_query(filters.regex("^music_choose$"))
async def menu_choose_cb(client, query):
    if await _check_if_clone(client, query):
        return
    menu = await get_menu(query.message.chat.id)
    if not menu or query.from_user.id != menu["user_id"]:
        return await query.answer("This isn't your menu.", show_alert=True)
    # Resolving audio is slow, so the card sits there inviting a second tap.
    # Claim first, then delete the card: nothing to tap, and nothing queued twice.
    if not await claim_tap(query.from_user.id, f"music_choose:{query.message.id}", ttl=30):
        return await query.answer("Already loading that...")
    cand = menu["candidates"][menu["index"]]
    try:
        await query.message.delete()
        track_info = await resolve_audio(cand, menu["is_video"])
    except ValueError as ve:
        return await query.message.reply_text(f"{ve}")
    except Exception as e:
        LOGGER.error("Failed to resolve audio: %s", e, exc_info=True)
        return await query.message.reply_text("Failed to download track. Try again.")

    await _start_playback(
        query.message.chat.id, track_info, query.from_user.mention, menu_message=query.message, user_id=query.from_user.id
    )


@Client.on_callback_query(filters.regex("^music_queue_add$"))
async def menu_queue_add_cb(client, query):
    if await _check_if_clone(client, query):
        return
    menu = await get_menu(query.message.chat.id)
    if not menu or query.from_user.id != menu["user_id"]:
        return await query.answer("This isn't your menu.", show_alert=True)
    if not await claim_tap(query.from_user.id, f"music_queue_add:{query.message.id}"):
        return await query.answer("Already adding that...")
    cand = menu["candidates"][menu["index"]]
    chat_id = query.message.chat.id

    # Duplicate detection
    existing = await get_queue(chat_id)
    if any(t.get("webpage_url") == cand.get("webpage_url") for t in existing):
        return await query.answer("This track is already in the queue!", show_alert=True)

    cand["user_id"] = query.from_user.id
    cand["requester_mention"] = query.from_user.mention
    await add_to_queue(chat_id, cand)
    # Start fetching it now rather than when the current track ends, so the
    # handover between songs has no silent gap.
    asyncio.create_task(prefetch_next(chat_id))
    await query.answer(f"Added to queue: {cand['title']}", show_alert=False)


# ---- Playback callbacks ----

async def _do_pause(chat_id):
    now = await get_now_playing(chat_id)
    if not now:
        return False, "Nothing is playing."
    if await get_paused(chat_id):
        return False, "Playback is already paused."
    try:
        await emilia_call.pause(chat_id)
        await set_paused(chat_id, True)
        return True, None
    except Exception as e:
        LOGGER.error("[Music] Failed to pause chat %s: %s", chat_id, e)
        return False, "Could not pause playback."


async def _do_resume(chat_id):
    now = await get_now_playing(chat_id)
    if not now:
        return False, "Nothing is playing."
    if not await get_paused(chat_id):
        return False, "Playback is already active (not paused)."
    try:
        await emilia_call.resume(chat_id)
        await set_paused(chat_id, False)
        return True, None
    except Exception as e:
        LOGGER.error("[Music] Failed to resume chat %s: %s", chat_id, e)
        return False, "Could not resume playback."


async def _do_stop(chat_id):
    now = await get_now_playing(chat_id)
    in_call = await _is_in_call(chat_id)
    q = await get_queue(chat_id)
    if not now and not in_call and not q:
        return False, "Nothing to stop."
    try:
        await emilia_call.leave_call(chat_id)
    except Exception:
        pass
    _clear_stream_end_state(chat_id)
    await clear_queue(chat_id)
    await set_now_playing(chat_id, None)
    await set_paused(chat_id, False)
    await set_loop_mode(chat_id, "off")
    await set_shuffle_mode(chat_id, False)
    await _delete_old_playback_message(chat_id)
    # Stopping early still counts as listening — bank however much was heard.
    await session_finish(chat_id)
    return True, None


@Client.on_callback_query(filters.regex("^music_pause$"))
async def pause_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    if not await _check_callback_access(query, chat_id):
        return await query.answer("You don't have permission to control this playback.", show_alert=True)
    ok, err = await _do_pause(chat_id)
    await query.answer("Playback paused" if ok else err, show_alert=not ok)


@Client.on_callback_query(filters.regex("^music_resume$"))
async def resume_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    if not await _check_callback_access(query, chat_id):
        return await query.answer("You don't have permission to control this playback.", show_alert=True)
    ok, err = await _do_resume(chat_id)
    await query.answer("Playback resumed" if ok else err, show_alert=not ok)


async def _handle_skip(chat_id):
    """Handle skip with loop/shuffle logic. Returns (msg_dict, err).
    Does NOT stop playback if queue is empty — just returns an alert.
    """
    now = await get_now_playing(chat_id)
    loop_mode = await get_loop_mode(chat_id)
    shuffle = await get_shuffle_mode(chat_id)

    if not now:
        return None, "Nothing is playing."

    requester_mention = now.get("requester_mention") or "User"

    # Loop "one" repeats a track when it *ends on its own* (that path lives in
    # events.py). Reaching here means a human pressed Skip, and honouring the
    # loop would replay the exact track they asked to leave — the button would
    # look broken. So Skip always moves forward; we just say loop is still on so
    # the next track doesn't start repeating unexpectedly either.
    skipped_past_loop_one = loop_mode == "one"

    nxt = await pop_next(chat_id)

    # Loop "all" with an empty queue: a *stream ending* should wrap around to the
    # start, but an explicit Skip should not. Replaying the very track someone
    # just asked to leave looks like the button is broken — and it's how a user
    # who forgot loop was on gets stuck hammering Skip on a track that never
    # changes. So skip stops instead, and says why, naming the culprit.
    if not nxt and loop_mode == "all":
        await _do_stop(chat_id)
        return {
            "caption": (
                "⏭ **Skipped track.** That was the last one and **Loop: all** "
                "had nothing left to repeat, so playback stopped.\n"
                "`•` Turn it off with `/loop off`."
            ),
            "photo": None,
            "reply_markup": None,
        }, None
    if not nxt:
        await _do_stop(chat_id)
        tail = (
            "\n`•` **Loop: one** is still on — turn it off with `/loop off`."
            if skipped_past_loop_one else ""
        )
        return {
            "caption": "⏭ **Skipped track.** Queue is empty, playback stopped." + tail,
            "photo": None,
            "reply_markup": None
        }, None

    # Handle shuffle
    if shuffle:
        remaining = await get_queue(chat_id)
        if len(remaining) > 1:
            random.shuffle(remaining)
            await set_queue_direct(chat_id, remaining)

    nxt_mention = nxt.get("requester_mention") or requester_mention
    nxt.setdefault("loop_mode", now.get("loop_mode", "off"))
    nxt.setdefault("shuffle", now.get("shuffle", False))
    await set_now_playing(chat_id, nxt)

    await set_paused(chat_id, False)

    try:
        nxt = await ensure_local_file(nxt)
        await _safe_play(chat_id, _make_stream(nxt))
        asyncio.create_task(prefetch_next(chat_id))
    except NoActiveGroupCall:
        await set_now_playing(chat_id, None)
        return None, "I couldn't find or start the voice chat. Start it manually, then try again."
    except (ConnectionNotFound, GroupCallInvalid, GroupcallForbidden):
        await set_now_playing(chat_id, None)
        return None, "Voice chat is unavailable. Start it manually, then try again."
    except (ChannelPrivate, UserNotParticipant):
        await set_now_playing(chat_id, None)
        return None, "Music assistant is not in this group. Please add or invite the assistant."
    except FloodWait as e:
        await set_now_playing(chat_id, None)
        await report_error("music.skip.flood_wait", e, chat_id=chat_id, track=nxt.get("title"), wait_seconds=e.value)
        return None, "I couldn't play the next track right now. Please try again in a moment."
    except ValueError as e:
        await set_now_playing(chat_id, None)
        LOGGER.warning("[Music] Could not fetch %s for %s: %s", nxt.get("title"), chat_id, e)
        return None, f"I couldn't download **{nxt.get('title')}**. Skip again to move on."
    except Exception as e:
        await set_now_playing(chat_id, None)
        await report_error("music.skip", e, chat_id=chat_id, track=nxt.get("title"))
        return None, "I couldn't play the next track. The developers have been notified."

    caption = _build_caption(nxt, nxt_mention, "**Track Skipped**")
    if skipped_past_loop_one:
        # They pressed Skip while loop:one was on. We moved on, as asked, but the
        # loop would trap the *next* track too — so say so while it's relevant.
        caption += "\n`•` **Loop: one** is still on — `/loop off` to stop repeating."

    return {
        "photo": nxt.get("thumbnail", THUMB),
        "caption": caption,
        "reply_markup": await _build_playback_markup(nxt, chat_id),
    }, None


@Client.on_callback_query(filters.regex("^music_skip$"))
async def skip_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    if not await _check_callback_access(query, chat_id):
        return await query.answer("You don't have permission to control this playback.", show_alert=True)
    # Skipping takes a moment (download + stream swap) and posts a fresh card.
    # Without this, an impatient double tap skips two tracks and posts two cards.
    if not await claim_tap(chat_id, "music_skip"):
        return await query.answer("Already skipping...")
    msg_dict, err = await _handle_skip(chat_id)
    if err:
        await query.answer(err, show_alert=True)
    elif msg_dict:
        await _delete_old_playback_message(chat_id)
        await query.message.delete()
        try:
            sent = await query.message.reply_photo(**msg_dict)
        except Exception:
            sent = await query.message.reply_text(msg_dict.get("caption", ""), reply_markup=msg_dict.get("reply_markup"))
        await set_playback_message_id(chat_id, sent.id)


@Client.on_callback_query(filters.regex("^music_stop$"))
async def stop_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    if not await _check_callback_access(query, chat_id):
        return await query.answer("You don't have permission to control this playback.", show_alert=True)
    if not await claim_tap(chat_id, "music_stop"):
        return await query.answer("Already stopping...")
    ok, err = await _do_stop(chat_id)
    if not ok:
        return await query.answer(err, show_alert=True)
    await _delete_old_playback_message(chat_id)
    await query.message.delete()
    await query.message.reply_text("Playback stopped and queue cleared")


@Client.on_callback_query(filters.regex("^music_loop:"))
async def loop_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    if not await _check_callback_access(query, chat_id):
        return await query.answer("You don't have permission to control this playback.", show_alert=True)
    modes = ["off", "one", "all"]
    current = await get_loop_mode(chat_id)
    next_mode = modes[(modes.index(current) + 1) % len(modes)] if current in modes else "off"
    await set_loop_mode(chat_id, next_mode)

    now = await get_now_playing(chat_id)
    if now:
        now["loop_mode"] = next_mode
        await set_now_playing(chat_id, now)
        await _safe_edit_reply_markup(query.message, await _build_playback_markup(now, chat_id))
    await query.answer(f"Loop: {next_mode}", show_alert=False)


@Client.on_callback_query(filters.regex("^music_shuffle$"))
async def shuffle_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    if not await _check_callback_access(query, chat_id):
        return await query.answer("You don't have permission to control this playback.", show_alert=True)
    current = await get_shuffle_mode(chat_id)
    new = not current
    await set_shuffle_mode(chat_id, new)

    now = await get_now_playing(chat_id)
    if now:
        now["shuffle"] = new
        await set_now_playing(chat_id, now)
        await _safe_edit_reply_markup(query.message, await _build_playback_markup(now, chat_id))
    await query.answer(f"Shuffle: {'on' if new else 'off'}", show_alert=False)


# ---- Commands ----

@register(pattern="play|vplay")
async def play_command(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    text = message.text or message.caption
    if not text:
        return
    
    # Fire and forget assistant joining concurrently so it's ready by the time audio is resolved
    asyncio.create_task(_ensure_assistant_in_chat(message.chat.id))

    parts = text.split()
    command = parts[0].lower()
    is_video = "vplay" in command

    track_info = None

    if len(parts) < 2:
        if message.reply_to_message:
            media = (
                getattr(message.reply_to_message, "audio", None)
                or getattr(message.reply_to_message, "voice", None)
                or getattr(message.reply_to_message, "video", None)
            )
            if media:
                os.makedirs("downloads", exist_ok=True)
                safe_name = f"downloads/{int(time.time())}_{message.reply_to_message.id}"
                try:
                    file_path = await message.reply_to_message.download(file_name=safe_name)
                except Exception as e:
                    LOGGER.error("Failed to download media: %s", e, exc_info=True)
                    return await message.reply_text("Failed to download media. Please try again.")
                if not file_path:
                    return await message.reply_text("Failed to download media.")
                title = (
                    getattr(media, "title", None)
                    or getattr(media, "file_name", None)
                    or "Telegram Media"
                )
                track_info = {
                    "id": str(message.reply_to_message.id),
                    "title": title,
                    "duration": getattr(media, "duration", 0),
                    "uploader": (
                        message.reply_to_message.from_user.first_name
                        if message.reply_to_message.from_user
                        else "Unknown"
                    ),
                    "thumbnail": THUMB,
                    "webpage_url": message.reply_to_message.link or "https://t.me",
                    "is_video": bool(message.reply_to_message.video),
                    "file_path": file_path,
                }
            elif message.reply_to_message.text:
                query = message.reply_to_message.text
            else:
                return await message.reply_text(
                    "Provide a song name, link, or reply to an audio file."
                )
        else:
            return await message.reply_text(
                "Provide a song name, link, or reply to an audio file.\nExample: `/play shape of you`"
            )
    else:
        query = text.split(None, 1)[1]

    chat_id = message.chat.id
    mention = getattr(message.from_user, "mention", None) or getattr(message.from_user, "first_name", "User")

    if track_info:
        track_info["user_id"] = message.from_user.id
        await _start_playback(chat_id, track_info, mention, reply_message=message, user_id=message.from_user.id)
        return

    # Detect playlist URLs
    if "list=" in query:
        await message.reply_text("Loading playlist...")
        try:
            pl_id = re.search(r'[?&]list=([^&]+)', query)
            if pl_id:
                tracks = await get_playlist_tracks(pl_id.group(1), limit=100)
                if not tracks:
                    return await message.reply_text("Playlist is empty or unavailable.")
                now = await get_now_playing(chat_id)
                in_call = await _is_in_call(chat_id)
                is_playing = in_call and now and now.get("file_path") and os.path.exists(now.get("file_path", ""))

                limit_note = " *(limited to 100 tracks per request for stability)*" if len(tracks) == 100 else ""
                if is_playing:
                    await add_many_to_queue(chat_id, tracks)
                    await message.reply_text(f"Added **{len(tracks)} tracks** from playlist to queue.{limit_note}")
                    asyncio.create_task(prefetch_next(chat_id))
                    return
                else:
                    first = tracks[0]
                    remaining = tracks[1:]
                    if remaining:
                        await add_many_to_queue(chat_id, remaining)
                    await message.reply_text(f"Playing the first track and added **{len(remaining)} tracks** from playlist to queue.{limit_note}")
                    resolved = await fetch_and_download(first["webpage_url"], is_video)
                    if resolved:
                        first["file_path"] = resolved["file_path"] if isinstance(resolved, dict) else resolved
                        first["user_id"] = message.from_user.id
                        await _start_playback(chat_id, first, mention, reply_message=message, user_id=message.from_user.id)
                    return
        except Exception as e:
            LOGGER.error("Playlist load failed: %s", e, exc_info=True)
            return await message.reply_text("Playlist load failed. Try again.")

    playmenu = await get_playmenu_setting_cached(chat_id)
    if playmenu:
        await _show_menu(message, query, is_video)
    else:
        # fetch_and_download consults the metadata cache first, so a query someone
        # has already asked for skips the yt-dlp search entirely — that search is
        # the slowest part of a cold /play.
        try:
            track_info = await fetch_and_download(query, is_video)
        except ValueError:
            return await message.reply_text("No results found.")
        except Exception as e:
            await report_error("music.play_command", e, chat_id=chat_id, query=query)
            return await message.reply_text("I couldn't load that track. Please try again.")

        await _start_playback(
            chat_id, track_info, mention, reply_message=message, user_id=message.from_user.id
        )


@register(pattern="now")
async def now_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    chat_id = message.chat.id
    now = await get_now_playing(chat_id)
    if not now:
        return await message.reply_text("Nothing is playing right now.")
    await _delete_old_playback_message(chat_id)
    try:
        sent = await message.reply_photo(
            photo=now.get("thumbnail", THUMB),
            caption=_build_caption(now, message.from_user.mention, "**Now Playing**"),
            reply_markup=await _build_playback_markup(now, chat_id),
        )
    except Exception:
        sent = await message.reply_text(
            text=_build_caption(now, message.from_user.mention, "**Now Playing**"),
            reply_markup=await _build_playback_markup(now, chat_id),
        )
    await set_playback_message_id(chat_id, sent.id)


@register(pattern="queue")
async def queue_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    chat_id = message.chat.id
    q = await get_queue(chat_id)
    if not q:
        return await message.reply_text("The queue is currently empty.")

    lines = []
    for i, track in enumerate(q, start=1):
        title = html.escape(str(track.get("title") or "Unknown"), quote=False)
        title = title.replace("\r", " ").replace("\n", " ")
        raw_url = str(track.get("webpage_url") or "")
        url = html.escape(raw_url, quote=True)
        dur = html.escape(_fmt_duration(track.get("duration")), quote=False)
        display_title = f"<a href=\"{url}\">{title}</a>" if raw_url.startswith("http") else title
        lines.append(f"<code>{i}.</code> {display_title} | <code>{dur}</code>")
    text = "<b>Queue</b>\n\n<blockquote expandable>" + "\n".join(lines) + "</blockquote>"

    await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@register(pattern="remove")
async def remove_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.reply_text("Usage: `/remove <position>`")
    try:
        pos = int(args[1])
    except ValueError:
        return await message.reply_text("Position must be a number.")
    chat_id = message.chat.id
    q = await get_queue(chat_id)
    if pos < 1 or pos > len(q):
        return await message.reply_text(f"Invalid position. Queue has {len(q)} tracks.")
    removed = q.pop(pos - 1)
    await set_queue_direct(chat_id, q)
    await message.reply_text(f"Removed from queue: **{removed['title']}**")


@register(pattern="clear")
async def clear_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    await clear_queue(message.chat.id)
    await message.reply_text("Queue cleared.")


@register(pattern="loop")
async def loop_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1].lower() not in ["off", "one", "all"]:
        return await message.reply_text("Usage: `/loop off|one|all`")
    mode = args[1].lower()
    chat_id = message.chat.id
    await set_loop_mode(chat_id, mode)
    now = await get_now_playing(chat_id)
    if now:
        now["loop_mode"] = mode
        await set_now_playing(chat_id, now)
    await message.reply_text(f"Loop mode set to: **{mode}**")


@register(pattern="shuffle")
async def shuffle_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1].lower() not in ["on", "off"]:
        return await message.reply_text("Usage: `/shuffle on|off`")
    mode = (args[1].lower() == "on")
    chat_id = message.chat.id
    await set_shuffle_mode(chat_id, mode)
    now = await get_now_playing(chat_id)
    if now:
        now["shuffle"] = mode
        await set_now_playing(chat_id, now)
    await message.reply_text(f"Shuffle set to: **{'on' if mode else 'off'}**")


@register(pattern="playmenu")
async def playmenu_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await is_admin(message, message.from_user.id):
        return await message.reply_text("Admin rights needed to change this setting.")
    
    parts = message.text.split()
    if len(parts) < 2:
        current = await get_playmenu_setting_cached(message.chat.id)
        state = "Enabled" if current else "Disabled"
        return await message.reply_text(f"Music menu is currently **{state}**.\nUse `/playmenu on` or `/playmenu off`.")
    
    arg = parts[1].lower()
    if arg in ["on", "true", "enable"]:
        await playmenu_db(message.chat.id, True)
        await message.reply_text("Play menu **Enabled**. Users will now select songs from a list before playing.")
    elif arg in ["off", "false", "disable"]:
        await playmenu_db(message.chat.id, False)
        await message.reply_text("Play menu **Disabled**. The bot will now automatically play the first search result.")
    else:
        await message.reply_text("Invalid argument. Use `on` or `off`.")


async def playlist_cmd(client: Client, message: Message):
    """Load a link's tracks straight into the voice-chat queue.

    Resolution goes through the playlist import engine rather than yt-dlp
    directly, so Spotify playlists/albums work here for free and the progress
    bar is shared with the /playlist menu's import flow.
    """
    from Emilia.modules.plugins.music.playlist import import_engine as imports

    text = message.text or message.caption
    parts = text.split()
    if len(parts) < 2:
        return await message.reply_text(
            "Usage: `/playlist <YouTube or Spotify link>`\n"
            "Send `/playlist` on its own to open your library.",
            quote=True,
        )

    target = parts[1]
    kind, _ = imports.detect_source(target)
    if not kind:
        # Bare playlist ids used to work here; keep that path alive.
        match = re.search(r'[?&]list=([^&]+)', target)
        pl_id = match.group(1) if match else target
        msg = await message.reply_text("Loading playlist...")
        tracks = await get_playlist_tracks(pl_id, limit=30)
    else:
        msg = await message.reply_text(f"Loading {imports.source_label(kind)}...")
        reporter = imports.ProgressReporter(msg, label="Loading")
        tracks, error = await imports.import_tracks(target, progress=reporter.update)
        await reporter.flush()
        if error:
            return await msg.edit_text(error)

    if not tracks:
        return await msg.edit_text("Playlist is empty or unavailable.")

    if not await get_now_playing(message.chat.id):
        # Queue everything *after* the first track, otherwise the track we are
        # about to play is still sitting at the head of the queue and plays twice.
        first, rest = tracks[0], tracks[1:]
        if rest:
            await add_many_to_queue(message.chat.id, rest)
        await msg.edit_text(f"Added {len(tracks)} tracks from playlist to queue.")
        try:
            first = await fetch_and_download(first["webpage_url"], False)
        except Exception as e:
            await report_error("music.playlist_cmd", e, chat_id=message.chat.id)
            return await msg.edit_text(
                "I couldn't start the first track. The rest is queued — use /skip to move on."
            )
        first["user_id"] = message.from_user.id
        await _start_playback(message.chat.id, first, message.from_user.mention, reply_message=message, user_id=message.from_user.id)
    else:
        await add_many_to_queue(message.chat.id, tracks)
        await msg.edit_text(f"Added {len(tracks)} tracks from playlist to queue.")
        asyncio.create_task(prefetch_next(message.chat.id))


# ---- Play command handlers (text) ----

@Client.on_message(filters.command("pause") & filters.group)
async def pause_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    ok, err = await _do_pause(message.chat.id)
    await message.reply_text("Playback paused" if ok else err)


@Client.on_message(filters.command("resume") & filters.group)
async def resume_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    ok, err = await _do_resume(message.chat.id)
    await message.reply_text("Playback resumed" if ok else err)


@Client.on_message(filters.command("skip") & filters.group)
async def skip_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    msg_dict, err = await _handle_skip(message.chat.id)
    if err:
        await message.reply_text(err)
    elif msg_dict:
        await _delete_old_playback_message(message.chat.id)
        try:
            sent = await message.reply_photo(**msg_dict)
        except Exception:
            sent = await message.reply_text(msg_dict.get("caption", ""), reply_markup=msg_dict.get("reply_markup"))
        await set_playback_message_id(message.chat.id, sent.id)


@Client.on_message(filters.command("stop") & filters.group)
async def stop_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    ok, err = await _do_stop(message.chat.id)
    if not ok:
        return await message.reply_text(err)
    await _delete_old_playback_message(message.chat.id)
    await message.reply_text("Playback stopped and queue cleared")


@Client.on_chat_member_updated(filters.group, group=800)
async def _on_assistant_member_update(client: Client, update):
    try:
        me = await _assistant_me()
        user = getattr(update.old_chat_member, "user", None) or getattr(update.new_chat_member, "user", None)
        if user and user.id == me.id:
            new_status = getattr(update.new_chat_member, "status", None)
            if new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                await forget_assistant_membership(update.chat.id)
    except Exception as e:
        LOGGER.debug("[Music] Assistant member update handler error for %s: %s", getattr(update.chat, 'id', '?'), e)


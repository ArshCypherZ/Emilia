import asyncio
import html
import secrets
import time
import traceback
from datetime import datetime, timezone
from functools import wraps

import redis.exceptions
from pyrogram import Client, enums, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden
from pyrogram.types import (LinkPreviewOptions,
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from Emilia import BOT_ID, EVENT_LOGS, LOGGER, db, pgram, redis_client
from Emilia.helper.chat_status import anon_admin_checker
from Emilia.helper.get_data import GetChat
from Emilia.mongo.chats_settings_mongo import get_anon_setting_cached
from Emilia.mongo.connection_mongo import GetConnectedChat
from Emilia.strings import error_messages
from Emilia.utils.cache import SimpleCache

# Rate Limit Constants
# (requests, window_seconds)
# Telegram Global Limit: ~30 msgs/sec
# Per Chat/User Limit: ~1 msg/sec (sustained) or burst of ~20
# We want to be safe but not annoying.
RATE_LIMIT_GENERAL = (3, 5)  # 3 commands per 5 seconds (Standard)
# 1 command per 5 seconds (Heavy ops like mass actions)
RATE_LIMIT_HEAVY = (1, 5)
RATE_LIMIT_SUPER_HEAVY = (1, 30)  # 1 command per 30 seconds (Very heavy ops)


async def usage_string(message, func) -> None:
    await message.reply(
        f"{func.description}\n\n**Usage:**\n`{func.usage}`\n\n**Example:**\n`{func.example}`"
    )


def description(description_doc: str):
    def wrapper(func):
        func.description = description_doc
        return func

    return wrapper


def usage(usage_doc: str):
    def wrapper(func):
        func.usage = usage_doc
        return func

    return wrapper


def example(example_doc: str):
    def wrapper(func):
        func.example = example_doc
        return func

    return wrapper


def exception(func):
    @wraps(func)
    async def wrapped(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # Never echo raw exception text to chat: RPC strings can leak internal
            # identifiers/paths. Use a mapped message or a generic one, and log
            # the original with traceback.
            error_message = error_messages.get(type(e))
            if error_message is None:
                error_message = "Something went wrong — the error has been logged."
                LOGGER.exception(f"Unhandled error in {func.__name__}")
                try:
                    tb = html.escape(traceback.format_exc()[-3500:])
                    await pgram.send_message(
                        chat_id=EVENT_LOGS,
                        text=f"#UNHANDLED_ERROR\nfunc: {func.__name__}\n\n<pre>{tb}</pre>",
                    )
                except Exception:
                    LOGGER.warning(
                        f"{func.__name__}: failed to forward traceback to log channel"
                    )

            if (
                isinstance(e, RPCError)
                and getattr(e, "CODE", None) == 403
                and "CHAT_SEND_DOCS_FORBIDDEN" in (getattr(e, "ID", None) or str(e))
            ):
                error_message = "I am not allowed to send documents in this chat. Please make me an admin to do so."

            # Pyrogram handler signatures pass (client, message)
            reply_target = None
            if len(args) >= 2:
                reply_target = args[1]
            elif args and hasattr(args[0], "reply_text"):
                reply_target = args[0]

            try:
                if reply_target is not None:
                    if hasattr(reply_target, "reply"):
                        await reply_target.reply(error_message)
                    elif hasattr(reply_target, "reply_text"):
                        await reply_target.reply_text(error_message)
                    else:
                        LOGGER.error(
                            f"Unhandled error in {func.__name__}: {error_message} (no reply method)"
                        )
                else:
                    LOGGER.error(
                        f"Unhandled error in {func.__name__}: {error_message} (no target)"
                    )
            except Exception as send_err:
                LOGGER.error(
                    f"Failed to send error message in {func.__name__}: {send_err} | Original: {e}"
                )

    return wrapped


# log channel stuff
mongo_collection = db.logchannels

# Per-chat log-channel config changes only on /setlog /unsetlog, so cache it
# (TTL + explicit invalidation) instead of a Mongo round-trip per command.

_logch_cache = SimpleCache(default_ttl=300, namespace="logchannels")


async def _get_log_channel_id(chat_id):
    """Return the configured log channel id for chat_id, or None. Cached."""
    key = f"logch:{chat_id}"
    cached = await _logch_cache.get(key)
    if cached is not None:
        return None if cached == "none" else cached
    chat_data = await mongo_collection.find_one({"chat_id": chat_id})
    channel_id = (
        chat_data["channel_id"] if chat_data and "channel_id" in chat_data else None
    )
    await _logch_cache.set(key, "none" if channel_id is None else channel_id)
    return channel_id


async def invalidate_log_channel_cache(chat_id):
    await _logch_cache.delete(f"logch:{chat_id}")


async def get_telegram_info_pyrogram(client, event):
    id_ = "connected"
    if not hasattr(event, "chat"):
        # event isn't a Message (e.g. raw int/id) — nothing to log against
        return (None, None, None, None, "manual")
    if not event.chat.type == enums.ChatType.PRIVATE:
        try:
            id_ = event.id
        except AttributeError:
            id_ = "manual"

    try:
        first_name = event.from_user.first_name if event.from_user else None
        admin_id = event.from_user.id if event.from_user else None
    except AttributeError:
        first_name = None
        admin_id = None

    chat_id = event.chat.id

    if event.chat.type == enums.ChatType.PRIVATE:
        connected = await GetConnectedChat(admin_id) if admin_id else None
        if connected:
            chat_id = connected
            id_ = "connected"
            title = await GetChat(chat_id) or (
                event.chat.title if hasattr(event.chat, "title") else "Chat"
            )
        else:
            # PM with no connection
            title = event.chat.title if hasattr(event.chat, "title") else "Private Chat"
            chat_id = None
            id_ = "manual"
    else:
        title = await GetChat(chat_id) or (
            event.chat.title if hasattr(event.chat, "title") else "Chat"
        )

    return (chat_id, title, first_name, admin_id, id_)


async def get_telegram_info(client, event):
    return await get_telegram_info_pyrogram(client, event)


def log_to_channel(func):
    async def wrapper(*args, **kwargs):
        log_message = " "
        client = args[0]
        event = args[1] if args[1] is not None else args[0]

        chat_id, chat_title, admin_name, admin_id, message_id = await get_telegram_info(
            client, event
        )

        # If we don't have a valid chat to log against, just run the handler
        if chat_id is None:
            return await func(*args, **kwargs)

        channel_id = await _get_log_channel_id(chat_id)
        if channel_id is None:
            return await func(*args, **kwargs)
        # Run the actual handler unguarded - its exceptions must propagate to
        # unified_wrapper so they're logged/reported like any other command
        # failure, instead of being swallowed here and never surfacing.
        result = await func(*args, **kwargs)
        # Only proceed with logging when the handler returns a structured
        # tuple
        if not isinstance(result, tuple):
            return result

        try:
            result_tuple = result
            if len(result_tuple) == 3:
                event_type, user_id, user_name = result_tuple
            else:
                event_type, user_id, user_name, adminid, adminname = result_tuple
                admin_id = adminid
                admin_name = adminname
        except Exception as e:
            LOGGER.error(f"log_to_channel: bad result tuple {result!r}: {e}")
            return result

        datetime_fmt = "%H:%M - %d-%m-%Y"

        log_message += f"**{chat_title}** `{chat_id}`\n#{event_type}\n"

        if admin_name and admin_id is not None:
            clear_admin_name = admin_name.replace("[", "").replace("]", "")
            log_message += f"\n**Admin**: [{clear_admin_name}](tg://user?id={admin_id})"

        if user_name and user_id:
            clear_user_name = user_name.replace("[", "").replace("]", "")
            log_message += f"\n**User**: [{clear_user_name}](tg://user?id={user_id})"

        if user_id:
            log_message += f"\n**User ID**: `{user_id}`"

        log_message += (
            f"\n**Event Stamp**: `{datetime.now(timezone.utc).strftime(datetime_fmt)}`"
        )

        try:
            if message_id and message_id not in ("connected", "manual"):
                if getattr(event.chat, "username", None):
                    log_message += f"\n**Link**: [click here](https://t.me/{event.chat.username}/{message_id})"
                else:
                    cid = str(chat_id).replace("-100", "")
                    log_message += (
                        f"\n**Link**: [click here](https://t.me/c/{cid}/{message_id})"
                    )
            elif message_id == "connected":
                log_message += "\n**Link**: No message link for connected commands."
            elif message_id == "manual":
                log_message += "\n**Link**: No message link for manual actions."
        except AttributeError:
            pass

        await pgram.send_message(
            channel_id, log_message, link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

    return wrapper


async def _invalidate_admin_caches(chat_id, user_id):
    """Drop both admin caches for a (chat, user) so rights changes apply now."""
    try:
        from Emilia.utils.cache import admin_cache

        await admin_cache.delete(f"chat_member:{chat_id}:{user_id}")
        # Lazy import: functions.admins imports this module (circular
        # otherwise).
        from Emilia.helper.admins import cache_collection

        await cache_collection.delete_one({"chat_id": chat_id, "user_id": user_id})
    except Exception:
        LOGGER.warning("Failed to invalidate admin caches", exc_info=True)


@Client.on_chat_member_updated(filters.group)
@log_to_channel
async def NewMemer(client: Client, message: ChatMemberUpdated):

    if message.new_chat_member and not message.old_chat_member:
        if message.from_user and message.new_chat_member.user:
            if message.new_chat_member.user.id != message.from_user.id:
                return (
                    "WELCOME",
                    message.new_chat_member.user.id,
                    message.new_chat_member.user.first_name,
                    message.from_user.id,
                    message.from_user.first_name,
                )

        return (
            "WELCOME",
            message.new_chat_member.user.id,
            message.new_chat_member.user.first_name,
            None,
            None,
        )

    if not message.new_chat_member and message.old_chat_member:
        return (
            "GOODBYE",
            message.old_chat_member.user.id,
            message.old_chat_member.user.first_name,
            None,
            None,
        )

    if message.old_chat_member and message.new_chat_member:
        if (
            message.old_chat_member.status == ChatMemberStatus.MEMBER
            and message.new_chat_member.status == ChatMemberStatus.ADMINISTRATOR
        ):
            # Telegram may omit promoted_by; fall back to the acting user.
            promoted_by = message.new_chat_member.promoted_by
            admin_title = getattr(promoted_by, "first_name", None) or (
                message.from_user.first_name if message.from_user else None
            )
            admin_id = getattr(promoted_by, "id", None) or (
                message.from_user.id if message.from_user else None
            )
            if admin_id == BOT_ID:
                return
            await _invalidate_admin_caches(
                message.chat.id, message.old_chat_member.user.id
            )
            return (
                "PROMOTE",
                message.old_chat_member.user.id,
                message.old_chat_member.user.first_name,
                admin_id,
                admin_title,
            )

        elif (
            message.old_chat_member.status == ChatMemberStatus.ADMINISTRATOR
            and message.new_chat_member.status == ChatMemberStatus.MEMBER
        ):
            admin_title = message.from_user.first_name
            admin_id = message.from_user.id
            if admin_id == BOT_ID:
                return
            await _invalidate_admin_caches(
                message.chat.id, message.old_chat_member.user.id
            )
            return (
                "DEMOTE",
                message.old_chat_member.user.id,
                message.old_chat_member.user.first_name,
                admin_id,
                admin_title,
            )

        elif (
            message.old_chat_member.status != ChatMemberStatus.BANNED
            and message.new_chat_member.status == ChatMemberStatus.BANNED
        ):
            admin_title = message.from_user.first_name
            admin_id = message.from_user.id
            if admin_id == BOT_ID:
                return
            await _invalidate_admin_caches(
                message.chat.id, message.old_chat_member.user.id
            )
            return (
                "BAN",
                message.old_chat_member.user.id,
                message.old_chat_member.user.first_name,
                admin_id,
                admin_title,
            )

    elif message.old_chat_member.status == ChatMemberStatus.BANNED:
        admin_title = message.from_user.first_name
        admin_id = message.from_user.id
        if admin_id == BOT_ID:
            return
        await _invalidate_admin_caches(message.chat.id, message.old_chat_member.user.id)
        return (
            "UNBAN",
            message.old_chat_member.user.id,
            message.old_chat_member.user.first_name,
            admin_id,
            admin_title,
        )


# Redis Rate Limiting
_rate_limit_redis_warned = False


def rate_limit(limit_config=RATE_LIMIT_GENERAL):
    """
    Decorator that limits the rate at which a function can be called using Redis.
    limit_config: Tuple of (messages_per_window, window_seconds)
    """
    messages_per_window, window_seconds = limit_config

    def decorator(func):
        async def wrapper(*args, **kwargs):
            target = args[1] if args[1] is not None else args[0]
            user = getattr(target, "from_user", None)
            if user is None:
                # Anonymous admins / channel senders have no user; don't limit.
                return await func(*args, **kwargs)
            user_id = user.id

            current_time = time.time()
            key = f"rate_limit:{BOT_ID}:{user_id}:{func.__name__}"

            # Redis Pipeline for atomic operations
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, current_time - window_seconds)
            pipe.zcard(key)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.expire(key, window_seconds + 1)
            try:
                results = await pipe.execute()
            except redis.exceptions.RedisError as e:
                # Fail open: if the rate-limit backend is unavailable, run the
                # command anyway rather than dropping it silently. Log once.
                global _rate_limit_redis_warned
                if not _rate_limit_redis_warned:
                    LOGGER.error(f"Rate limiter Redis error, failing open: {e}")
                    _rate_limit_redis_warned = True
                return await func(*args, **kwargs)

            # results[1] is the count of timestamps already in the window
            request_count = results[1]

            if request_count >= messages_per_window:
                LOGGER.warning(
                    f"Rate limit exceeded for user {user_id}. Allowed {messages_per_window} updates in {window_seconds} seconds for {func.__name__}"
                )
                # Notify exactly once per window (only at the boundary).
                if request_count == messages_per_window:
                    try:
                        await target.reply_text(
                            "Slow down — try again in a few seconds."
                        )
                    except Exception:
                        pass
                return

            await func(*args, **kwargs)

        return wrapper

    return decorator


# leave chat if cannot write
def leavemute(func):
    @wraps(func)
    async def capture(client, message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except ChatWriteForbidden:
            await client.leave_chat(message.chat.id)
            return

    return capture


callback_registry = {}


def _remove_callback_handler(client, registered_handler):
    if registered_handler is None:
        return
    try:
        client.remove_handler(*registered_handler)
    except Exception:
        pass


async def _expire_callback_handler(
    client, callback_name, registered_handler, delay=300
):
    await asyncio.sleep(delay)
    if callback_registry.pop(callback_name, None) is not None:
        _remove_callback_handler(client, registered_handler)


def register_callback(func, message, client, owner_only: bool = False):
    callback_name = f"anon:{secrets.token_urlsafe(8)}"
    registered_handler = None

    async def callback_handler(_: Client, callback_query: CallbackQuery):
        user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id
        if chat_id != message.chat.id:
            await callback_query.answer(
                "This confirmation belongs to another chat.", show_alert=True
            )
            return

        if await anon_admin_checker(chat_id, user_id, client, owner_only=owner_only):
            if callback_registry.pop(callback_name, None) is None:
                await callback_query.answer(
                    "This confirmation has expired.", show_alert=True
                )
                return
            _remove_callback_handler(client, registered_handler)
            message._emilia_verified_user_id = user_id
            await func(_, message)
            try:
                await callback_query.message.delete()
            except Exception:
                pass
        else:
            if owner_only:
                await callback_query.answer(
                    "You are not the group owner", show_alert=True
                )
            else:
                await callback_query.answer("You are not an admin", show_alert=True)

    registered_handler = client.add_handler(
        CallbackQueryHandler(
            callback_handler,
            filters.create(lambda _, __, query: query.data == callback_name),
        )
    )
    callback_registry[callback_name] = True
    from Emilia.utils.tasks import spawn

    spawn(
        _expire_callback_handler(client, callback_name, registered_handler),
        name=f"expire_callback:{callback_name}",
    )

    return callback_name


def anonadmin_checker(func=None, *, owner_only: bool = False):
    def decorator(inner_func):
        @wraps(inner_func)
        async def wrapper(client, message):
            from_user = getattr(message, "from_user", None)
            if message.sender_chat or (
                message.sender_chat is None
                and from_user is not None
                and from_user.id == 1087968824
            ):
                if not owner_only and await get_anon_setting_cached(message.chat.id):
                    return await inner_func(client, message)

                button_text = (
                    "Click to prove owner" if owner_only else "Click to prove admin"
                )
                button = [
                    [
                        InlineKeyboardButton(
                            text=button_text,
                            callback_data=register_callback(
                                inner_func, message, client, owner_only=owner_only
                            ),
                        )
                    ]
                ]
                await message.reply(
                    text="You are anonymous. Tap this button to confirm your identity.",
                    reply_markup=InlineKeyboardMarkup(button),
                )

                return
            else:
                return await inner_func(client, message)

        return wrapper

    if func is None:
        return decorator
    return decorator(func)

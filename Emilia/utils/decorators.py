import time
from datetime import datetime
from functools import wraps
import asyncio

from pyrogram import Client, enums, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden
from pyrogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pyrogram.handlers import CallbackQueryHandler
from telethon import errors
from telethon.errors.rpcerrorlist import PersistentTimestampOutdatedError

from Emilia import BOT_ID, LOGGER, db, telethn
from Emilia.helper.chat_status import anon_admin_checker
from Emilia.helper.get_data import GetChat
from Emilia.mongo.connection_mongo import GetConnectedChat
from Emilia.mongo.chats_settings_mongo import get_anon_setting_cached
from Emilia.strings import error_messages

# Rate Limit Constants
# (requests, window_seconds)
# Telegram Global Limit: ~30 msgs/sec
# Per Chat/User Limit: ~1 msg/sec (sustained) or burst of ~20
# We want to be safe but not annoying.
RATE_LIMIT_GENERAL = (3, 5)   # 3 commands per 5 seconds (Standard)
RATE_LIMIT_HEAVY = (1, 5)     # 1 command per 5 seconds (Heavy ops like mass actions)
RATE_LIMIT_SUPER_HEAVY = (1, 30) # 1 command per 30 seconds (Very heavy ops)

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
        except PersistentTimestampOutdatedError as e:
            # Telegram occasionally returns this when local state is behind; treat as transient
            chat_ctx = None
            try:
                if args and hasattr(args[0], "chat_id"):
                    chat_ctx = getattr(args[0], "chat_id", None)
                elif len(args) >= 2 and hasattr(args[1], "chat"):
                    chat_ctx = getattr(args[1].chat, "id", None)
            except Exception:
                pass
            LOGGER.debug(
                f"PersistentTimestampOutdatedError encountered in {func.__name__} (chat={chat_ctx}). Will ignore and continue. Details: {e}"
            )
            # brief backoff to let client resync
            await asyncio.sleep(0.5)
            return
        except Exception as e:
            error_message = error_messages.get(type(e), str(e))

            if (
                isinstance(e, errors.RPCError)
                and getattr(e, "code", None) == 403
                and "CHAT_SEND_DOCS_FORBIDDEN" in getattr(e, "message", "")
            ):
                error_message = (
                    "I am not allowed to send documents in this chat. Please make me an admin to do so."
                )

            # Determine the appropriate reply target for Telethon or Pyrogram
            reply_target = None
            # Telethon handler signatures typically pass only the event as first arg
            if args and args and args[0] and args[0].__class__.__module__.startswith("telethon"):
                reply_target = args[0]
            # Pyrogram handler signatures pass (client, message)
            elif len(args) >= 2:
                reply_target = args[1]

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


async def get_telegram_info_telethon(event):
    id_ = None
    # Prefer explicit private check to determine connection-based routing
    try:
        is_private = event.is_private
    except AttributeError:
        is_private = False

    if not is_private:
        try:
            id_ = event.message.id
        except AttributeError:
            id_ = "meow"

    try:
        first_name = event.sender.first_name if event.sender else None
        admin_id = event.sender_id if event.sender else None
    except AttributeError:
        first_name = None
        admin_id = None

    chat_id = event.chat_id if hasattr(event, "chat_id") else None

    # When in PM, try connected chat; otherwise don't force connection logic
    if is_private:
        connected = await GetConnectedChat(admin_id) if admin_id else None
        if connected:
            chat_id = connected
            # mark that this is a connected/virtual context, so link-building is skipped
            id_ = "connected"
            # Safe title resolution for connected chats
            title = await GetChat(chat_id) or (getattr(event.chat, "title", None) or "Chat")
        else:
            # No connected chat – keep chat_id None and avoid DB lookups
            title = getattr(event.chat, "title", None) or "Private Chat"
            chat_id = None
            id_ = "manual"
    else:
        # Group/supergroup/channel: resolve title via DB cache when available
        title = await GetChat(chat_id) or (getattr(event.chat, "title", None) or "Chat")

    return (chat_id, title, first_name, admin_id, id_)


async def get_telegram_info_pyrogram(client, event):
    id_ = "connected"
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
            title = await GetChat(chat_id) or (event.chat.title if hasattr(event.chat, "title") else "Chat")
        else:
            # PM with no connection
            title = event.chat.title if hasattr(event.chat, "title") else "Private Chat"
            chat_id = None
            id_ = "manual"
    else:
        title = await GetChat(chat_id) or (event.chat.title if hasattr(event.chat, "title") else "Chat")

    return (chat_id, title, first_name, admin_id, id_)


def is_telethon_client(client):
    return client.__module__.startswith("telethon")


async def get_telegram_info(client, event):
    if is_telethon_client(client):
        return await get_telegram_info_telethon(event)
    else:
        return await get_telegram_info_pyrogram(client, event)


def logging(func):
    async def wrapper(*args, **kwargs):
        log_message = " "
        client = args[0]
        event = (
            args[0]
            if is_telethon_client(client)
            else args[1] if args[1] is not None else args[0]
        )

        chat_id, chat_title, admin_name, admin_id, message_id = await get_telegram_info(
            client, event
        )

        # If we don't have a valid chat to log against, just run the handler
        if chat_id is None:
            return await func(*args, **kwargs)

        chat_data = await mongo_collection.find_one({"chat_id": chat_id})
        if not (chat_data and "channel_id" in chat_data):
            return await func(*args, **kwargs)
        try:

            result = await func(*args, **kwargs)
            # Only proceed with logging when the handler returns a structured tuple
            if not isinstance(result, tuple):
                return result

            result_tuple = result
            if len(result_tuple) == 3:
                event_type, user_id, user_name = result_tuple
            else:
                event_type, user_id, user_name, adminid, adminname = result_tuple
                admin_id = adminid
                admin_name = adminname
        except Exception as e:
            LOGGER.error(e)
            return

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
            f"\n**Event Stamp**: `{datetime.utcnow().strftime(datetime_fmt)}`"
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

        await telethn.send_message(
            chat_data["channel_id"], log_message, link_preview=False
        )

    return wrapper


@Client.on_chat_member_updated(filters.group)
@logging
async def NewMemer(client: Client, message: ChatMemberUpdated):

    if message.new_chat_member and not message.old_chat_member:
        if (message.from_user and message.new_chat_member.user):
            if (message.new_chat_member.user.id != message.from_user.id):
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
            admin_title = message.new_chat_member.promoted_by.first_name
            admin_id = message.new_chat_member.promoted_by.id
            if admin_id == BOT_ID:
                return
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
        return (
            "UNBAN",
            message.old_chat_member.user.id,
            message.old_chat_member.user.first_name,
            admin_id,
            admin_title,
        )


message_history = {}


# Redis Rate Limiting
from Emilia import db
redis_client = db.redis_client

def rate_limit(limit_config=RATE_LIMIT_GENERAL):
    """
    Decorator that limits the rate at which a function can be called using Redis.
    limit_config: Tuple of (messages_per_window, window_seconds)
    """
    messages_per_window, window_seconds = limit_config

    def decorator(func):
        async def wrapper(*args, **kwargs):
            client = args[0]
            if is_telethon_client(client):
                user_id = args[0].sender_id
            else:
                user_id = (
                    args[1].from_user.id
                    if args[1] is not None
                    else args[0].from_user.id
                )

            current_time = time.time()
            key = f"rate_limit:{BOT_ID}:{user_id}:{func.__name__}"

            # Redis Pipeline for atomic operations
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, current_time - window_seconds)
            pipe.zrange(key, 0, -1)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.expire(key, window_seconds + 1)
            results = await pipe.execute()
            
            # results[1] is the list of timestamps in the window (before adding current)
            request_count = len(results[1])

            if request_count >= messages_per_window:
                LOGGER.warning(
                    f"Rate limit exceeded for user {user_id}. Allowed {messages_per_window} updates in {window_seconds} seconds for {func.__name__}"
                )
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


def register_callback(func, message, client):
    callback_name = f"check_admin_callback_{func.__name__}_{message.id}"

    async def callback_handler(_: Client, callback_query: CallbackQuery):
        user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id

        if await anon_admin_checker(chat_id, user_id, client):
            await func(_, message)
            await callback_query.message.delete()
        else:
            await callback_query.answer("You are not an admin", show_alert=True)

    client.add_handler(
        CallbackQueryHandler(
            callback_handler,
            filters.create(lambda _, __, query: query.data == callback_name)
        )
    )

    return callback_name


def anonadmin_checker(func):
    @wraps(func)
    async def wrapper(client, message):
        if message.sender_chat or (
            message.sender_chat is None and message.from_user.id == 1087968824
        ):
            # Check if anon admin is enabled in this chat
            if await get_anon_setting_cached(message.chat.id):
                return await func(client, message)

            button = [
                [
                    InlineKeyboardButton(
                        text="Click to prove admin",
                        callback_data=register_callback(func, message, client),
                    )
                ]
            ]
            await message.reply(
                text="You are anonymous. Tap this button to confirm your identity.",
                reply_markup=InlineKeyboardMarkup(button),
            )

            return
        else:
            return await func(client, message)

    return wrapper
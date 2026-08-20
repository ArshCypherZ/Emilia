import time
from asyncio import sleep
from datetime import datetime, timezone

from pyrogram.enums import ChatMemberStatus, ChatType, MessageEntityType
from pyrogram.errors import FloodWait, UserNotParticipant

import Emilia.strings as strings
from Emilia import DEV_USERS, db
from Emilia.helper.get_data import GetChat
from Emilia.utils.decorators import *
from Emilia.helper.chat_status import get_chat_member_cached, _status, _priv

cache_collection = db.admincache


def ctypeof(text):
    try:
        return int(text)
    except BaseException:
        return text


def _get_client(event):
    client = getattr(event, "_client", None)
    if client is None:
        from Emilia import pgram

        client = pgram
    return client


async def find_instance(items, class_or_tuple):
    for item in items:
        if isinstance(item, class_or_tuple):
            return item
    return None


async def get_user_reason(event):
    text = event.text or event.caption or ""
    client = _get_client(event)

    # Default return values
    user_input = None
    extra = None

    # If replying to a user, use the replied sender as target. Optional extra
    # is the rest of the command text
    if event.reply_to_message:
        user_input = event.reply_to_message.from_user
        # Extra is anything after the command itself
        parts = text.split(None, 1)
        extra = parts[1] if len(parts) >= 2 else None
        return user_input, extra

    # Not a reply: try to resolve using entities first (supports mentions with
    # spaces)
    entities = event.entities or event.caption_entities
    if entities:
        ent = None
        for item in entities:
            if item.type in (
                MessageEntityType.TEXT_MENTION,
                MessageEntityType.MENTION,
                MessageEntityType.TEXT_LINK,
            ):
                ent = item
                break
        if ent:
            users = None
            if ent.type == MessageEntityType.TEXT_MENTION:
                user_input = ent.user
            elif ent.type == MessageEntityType.MENTION:
                users = text[ent.offset : ent.offset + ent.length]
            elif ent.type == MessageEntityType.TEXT_LINK:
                if ent.url and ent.url.startswith("tg://user?id="):
                    users = int(ent.url.split("=")[1])

            if user_input is None and users is not None:
                try:
                    user_input = await client.get_users(ctypeof(users))
                except (TypeError, ValueError):
                    user_input = None
                except FloodWait as e:
                    await sleep(e.value)
                except Exception:
                    user_input = None

            if user_input is not None:
                after_idx = ent.offset + ent.length
                extra_text = text[after_idx:].strip()
                extra = extra_text if extra_text else None
                return user_input, extra

    parts = text.split(None, 2)
    if len(parts) > 1:
        user_token = parts[1]
        extra = parts[2] if len(parts) > 2 else None

        try:
            if user_token.isnumeric():
                user_input = await client.get_users(int(user_token))
            else:
                user_input = await client.get_users(user_token)
        except (TypeError, ValueError):
            return None, None
        except FloodWait as e:
            await sleep(e.value)
        except Exception:
            # get_entity resolved chats too; fall back to get_chat
            try:
                user_input = await client.get_chat(ctypeof(user_token))
            except Exception:
                return None, None
        return user_input, extra

    return None, None


async def get_extra_args(event):
    try:
        args = (event.text or event.caption or "").split(None, 1)[1].strip()
    except IndexError:
        args = None
    if event.reply_to_message:
        return event.reply_to_message.text
    elif args:
        return args


async def extract_time(message, time_val):
    if any(time_val.endswith(unit) for unit in ("m", "h", "d")):
        unit = time_val[-1]
        time_num = time_val[:-1]  # type: str
        if not time_num.isdigit():
            await message.reply_text("Invalid time amount specified.")
            return None
        if unit == "m":
            bantime = int(time.time() + int(time_num) * 60)
        elif unit == "h":
            bantime = int(time.time() + int(time_num) * 60 * 60)
        elif unit == "d":
            bantime = int(time.time() + int(time_num) * 24 * 60 * 60)
        else:
            return
        return bantime
    else:
        return None


async def get_time(time: int):
    """Return a human-readable duration string.
    Tolerates None/invalid values by treating them as 0 seconds.
    """
    try:
        t = int(time)
    except Exception:
        t = 0
    if t < 0:
        t = 0

    if t < 60:
        return f"{t} second{'s' if t != 1 else ''}"

    time_units = [("day", 86400), ("hour", 3600), ("minute", 60)]
    time_parts = []

    for unit, divisor in time_units:
        if t >= divisor:
            count = t // divisor
            t %= divisor
            time_parts.append(f"{count} {unit}{'s' if count != 1 else ''}")

    if t > 0:
        time_parts.append(f"{t} second{'s' if t != 1 else ''}")

    return " ".join(time_parts)


async def can_add_admins(event, user_id, chat_id=None):
    client = _get_client(event)
    try:
        target_chat = chat_id if chat_id is not None else event.chat.id
        member = await get_chat_member_cached(client, target_chat, user_id)
    except UserNotParticipant:
        return False

    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True

    elif _status(member) == "ADMINISTRATOR":
        if not _priv(member, "can_promote_members"):
            await event.reply_text(strings.CAN_PROMOTE)
            return False
        return True

    else:
        await event.reply_text(strings.NOT_ADMIN)
        return False


async def cb_can_add_admins(event, user_id):
    client = _get_client(event)
    try:
        member = await get_chat_member_cached(client, event.message.chat.id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    elif _status(member) == "ADMINISTRATOR":
        if not _priv(member, "can_promote_members"):
            await event.answer(strings.CAN_PROMOTE, show_alert=True)
            return False
        return True
    else:
        await event.answer(strings.NOT_ADMIN)
        return False


@exception
async def can_ban_users(event, user_id, chat_id=None):
    client = _get_client(event)
    if chat_id is not None:
        chat_id = chat_id
    else:
        chat_id = event.chat.id
    try:
        member = await get_chat_member_cached(client, chat_id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    elif _status(member) == "ADMINISTRATOR":
        if not _priv(member, "can_restrict_members"):
            await event.reply_text(strings.CAN_BAN)
            return False
        return True
    else:
        await event.reply_text(strings.NOT_ADMIN)
        return False


async def cb_can_ban_users(event, user_id):
    client = _get_client(event)
    try:
        member = await get_chat_member_cached(client, event.message.chat.id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    elif _status(member) == "ADMINISTRATOR":
        if not _priv(member, "can_restrict_members"):
            await event.answer(strings.CAN_BAN, show_alert=True)
            return False
        return True
    else:
        await event.answer(strings.NOT_ADMIN, show_alert=True)
        return False


@exception
async def can_change_info(event, user_id, chat_id=None):
    client = _get_client(event)
    if chat_id is not None:
        chat_id = chat_id
    else:
        chat_id = event.chat.id

    try:
        member = await get_chat_member_cached(client, chat_id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    elif _status(member) == "ADMINISTRATOR":
        if not _priv(member, "can_change_info"):
            await event.reply_text(strings.CAN_CHANGE_INFO)
            return False
        return True
    else:
        await event.reply_text(strings.NOT_ADMIN)
        return False


async def cb_can_change_info(event, user_id):
    client = _get_client(event)
    try:
        member = await get_chat_member_cached(client, event.message.chat.id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    elif _status(member) == "ADMINISTRATOR":
        if not _priv(member, "can_change_info"):
            await event.answer(strings.CAN_CHANGE_INFO, show_alert=True)
            return False
        return True
    else:
        await event.answer(strings.NOT_ADMIN, show_alert=True)
        return False


@exception
async def is_owner(event, user_id, chat_id=None):
    client = _get_client(event)
    if chat_id is not None:
        chat_id = chat_id
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat.id
        title = event.chat.title
    try:
        member = await get_chat_member_cached(client, chat_id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    else:
        await event.reply_text(f"You need to be the chat owner of {title} to do this.")
        return False


async def cb_is_owner(event, user_id):
    client = _get_client(event)
    try:
        member = await get_chat_member_cached(client, event.message.chat.id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    else:
        await event.answer(
            f"You need to be the chat owner of {event.message.chat.title} to do this.",
            show_alert=True,
        )
        return False


async def can_delete_msg(event, user_id):
    client = _get_client(event)
    try:
        member = await get_chat_member_cached(client, event.chat.id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    elif _status(member) == "ADMINISTRATOR":
        if not _priv(member, "can_delete_messages"):
            await event.reply_text(strings.CAN_DELETE)
            return False
        return True
    else:
        await event.reply_text(strings.NOT_ADMIN)
        return False


@exception
async def is_admin(event, user_id, pm_mode: bool = False, chat_id=None):
    client = _get_client(event)

    # Determine target chat context
    target_chat = chat_id if chat_id is not None else event.chat.id

    # Preserve legacy behavior: in PM and no explicit chat provided, treat as
    # admin unless pm_mode is True
    if not pm_mode and event.chat.type == ChatType.PRIVATE and chat_id is None:
        return True

    try:
        member = await get_chat_member_cached(client, target_chat, user_id)
    except UserNotParticipant:
        return False

    is_admin_flag = _status(member) in ("ADMINISTRATOR", "OWNER")

    return is_admin_flag


async def get_admin_cache(event, user_id):
    # projection to reduce payload; normalize chat_id/user_id types
    cache_data = await cache_collection.find_one(
        {"chat_id": int(event.chat.id), "user_id": int(user_id)},
        {"is_admin": 1, "last_updated": 1},
    )
    if cache_data:
        lu = cache_data.get("last_updated")
        if lu is not None:
            # Mongo hands datetimes back naive-UTC; compare on the same basis.
            if lu.tzinfo is None:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                now = datetime.now(timezone.utc)
            if (now - lu).total_seconds() < 600:
                return cache_data["is_admin"]
    return None


async def update_admin_cache(chat_id, user_id, is_admin):
    await cache_collection.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"is_admin": is_admin, "last_updated": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def cb_is_admin(event, user_id):
    client = _get_client(event)
    try:
        member = await get_chat_member_cached(client, event.message.chat.id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) in ("ADMINISTRATOR", "OWNER"):
        return True
    else:
        await event.answer(strings.NOT_ADMIN, show_alert=True)
        return False


async def can_manage_topics(event, user_id):
    client = _get_client(event)
    try:
        member = await get_chat_member_cached(client, event.chat.id, user_id)
    except UserNotParticipant:
        return False
    if _status(member) == "OWNER" or user_id in DEV_USERS:
        return True
    elif _status(member) == "ADMINISTRATOR":
        if not _priv(member, "can_manage_topics"):
            await event.reply_text(strings.NOT_TOPIC)
            return False
        return True
    else:
        await event.reply_text(strings.NOT_ADMIN)
        return False


# The full-collection admin-cache refresher was removed (B4). Staleness is now
# handled lazily in get_admin_cache (10-minute TTL) plus a Mongo TTL index that
# self-deletes dead entries, so admin status is re-fetched on demand per active
# (chat,user) instead of eagerly for every pair ever seen.

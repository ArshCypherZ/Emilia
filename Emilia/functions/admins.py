import asyncio
import time
from asyncio import sleep
from datetime import datetime

from telethon import errors, types
from telethon.errors.rpcerrorlist import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import MessageEntityMention, MessageEntityMentionName

import Emilia.strings as strings
from Emilia import DEV_USERS, db
from Emilia import telethn as meow
from Emilia.utils.decorators import *

cache_collection = db.admincache


def ctypeof(text):
    try:
        return int(text)
    except BaseException:
        return text


async def find_instance(items, class_or_tuple):
    for item in items:
        if isinstance(item, class_or_tuple):
            return item
    return None


async def get_user_reason(event):
    # Prefer raw_text to preserve exact spacing/entity offsets
    text = getattr(event, "raw_text", event.text)

    # Default return values
    user_input = None
    extra = None

    # If replying to a user, use the replied sender as target. Optional extra is the rest of the command text
    if event.reply_to_msg_id:
        previous_message = await event.get_reply_message()
        try:
            user_input = await meow.get_entity(previous_message.sender_id)
        except errors.FloodWaitError as e:
            await sleep(e.seconds)
        # Extra is anything after the command itself
        parts = text.split(None, 1)
        extra = parts[1] if len(parts) >= 2 else None
        return user_input, extra

    # Not a reply: try to resolve using entities first (supports mentions with spaces)
    entities = getattr(getattr(event, "message", event), "entities", None) or event.entities
    if entities:
        ent = await find_instance(entities, (MessageEntityMentionName, MessageEntityMention))
        if ent:
            users = None
            if isinstance(ent, MessageEntityMentionName):
                users = ent.user_id
            elif isinstance(ent, MessageEntityMention):
                token = text[ent.offset : ent.offset + ent.length]
                users = token
            if users is not None:
                try:
                    user_input = await meow.get_entity(ctypeof(users))
                except (TypeError, ValueError):
                    user_input = None
                except errors.FloodWaitError as e:
                    await sleep(e.seconds)

                after_idx = ent.offset + ent.length
                extra_text = text[after_idx:].strip()
                extra = extra_text if extra_text else None

                if user_input is not None:
                    return user_input, extra

    parts = text.split(None, 2)
    if len(parts) > 1:
        user_token = parts[1]
        extra = parts[2] if len(parts) > 2 else None

        try:
            if user_token.isnumeric():
                user_input = await meow.get_entity(int(user_token))
            else:
                user_input = await meow.get_entity(user_token)
        except (TypeError, ValueError):
            return None, None
        except errors.FloodWaitError as e:
            await sleep(e.seconds)
        except Exception:
            return None, None
        return user_input, extra

    return None, None


async def get_extra_args(event):
    try:
        args = event.text.split(None, 1)[1].strip()
    except IndexError:
        args = None
    if event.reply_to_msg_id:
        previous_message = await event.get_reply_message()
        return previous_message.text
    elif args:
        return args


async def extract_time(message, time_val):
    if any(time_val.endswith(unit) for unit in ("m", "h", "d")):
        unit = time_val[-1]
        time_num = time_val[:-1]  # type: str
        if not time_num.isdigit():
            await message.reply("Invalid time amount specified.")
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
    try:
        target_chat = chat_id if chat_id is not None else event.chat_id
        p = await meow(GetParticipantRequest(target_chat, user_id))
    except UserNotParticipantError:
        return False

    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True

    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.add_admins:
            await event.reply(strings.CAN_PROMOTE)
            return False
        return True

    else:
        await event.reply(strings.NOT_ADMIN)
        return False


async def cb_can_add_admins(event, user_id):
    try:
        p = await meow(GetParticipantRequest(event.chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.add_admins:
            await event.answer(strings.CAN_PROMOTE, alert=True)
            return False
        return True
    else:
        await event.answer(strings.NOT_ADMIN)
        return False


@exception
async def can_ban_users(event, user_id, chat_id=None):
    if chat_id is not None:
        chat_id = chat_id
    else:
        chat_id = event.chat_id
    try:
        p = await meow(GetParticipantRequest(chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.ban_users:
            await event.reply(strings.CAN_BAN)
            return False
        return True
    else:
        await event.reply(strings.NOT_ADMIN)
        return False


async def cb_can_ban_users(event, user_id):
    try:
        p = await meow(GetParticipantRequest(event.chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.ban_users:
            await event.answer(strings.CAN_BAN, alert=True)
            return False
        return True
    else:
        await event.answer(strings.NOT_ADMIN, alert=True)
        return False


@exception
async def can_change_info(event, user_id, chat_id=None):
    if chat_id is not None:
        chat_id = chat_id
    else:
        chat_id = event.chat_id

    try:
        p = await meow(GetParticipantRequest(chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.change_info:
            await event.reply(strings.CAN_CHANGE_INFO)
            return False
        return True
    else:
        await event.reply(strings.NOT_ADMIN)
        return False


async def cb_can_change_info(event, user_id):
    try:
        p = await meow(GetParticipantRequest(event.chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.change_info:
            await event.answer(strings.CAN_CHANGE_INFO, alert=True)
            return False
        return True
    else:
        await event.answer(strings.NOT_ADMIN, alert=True)
        return False


@exception
async def is_owner(event, user_id, chat_id=None):
    if chat_id is not None:
        chat_id = chat_id
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    try:
        p = await meow(GetParticipantRequest(chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    else:
        await event.reply(f"You need to be the chat owner of {title} to do this.")
        return False


async def cb_is_owner(event, user_id):
    try:
        p = await meow(GetParticipantRequest(event.chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    else:
        await event.answer(
            f"You need to be the chat owner of {event.chat.title} to do this.",
            alert=True,
        )
        return False


async def can_delete_msg(event, user_id):
    try:
        p = await meow(GetParticipantRequest(event.chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.delete_messages:
            await event.reply(strings.CAN_DELETE)
            return False
        return True
    else:
        await event.reply(strings.NOT_ADMIN)
        return False


@exception
async def is_admin(event, user_id, pm_mode: bool = False, chat_id=None):

    # Determine target chat context
    target_chat = chat_id if chat_id is not None else event.chat_id

    # Preserve legacy behavior: in PM and no explicit chat provided, treat as admin unless pm_mode is True
    if not pm_mode and getattr(event, "is_private", False) and chat_id is None:
        return True

    cached_admin_status = await get_admin_cache(event, user_id)
    if cached_admin_status is not None and chat_id is None:
        # Only use cache when operating on event.chat_id
        return cached_admin_status

    try:
        p = await meow(GetParticipantRequest(target_chat, user_id))
    except UserNotParticipantError:
        return False

    is_admin_flag = isinstance(
        p.participant, types.ChannelParticipantAdmin
    ) or isinstance(p.participant, types.ChannelParticipantCreator)

    if chat_id is None:
        await update_admin_cache(target_chat, user_id, is_admin_flag)

    return is_admin_flag


async def get_admin_cache(event, user_id):
    # projection to reduce payload; normalize chat_id/user_id types
    cache_data = await cache_collection.find_one(
        {"chat_id": int(event.chat_id), "user_id": int(user_id)}, {"is_admin": 1}
    )
    if cache_data:
        return cache_data["is_admin"]
    return None


async def update_admin_cache(chat_id, user_id, is_admin):
    await cache_collection.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"is_admin": is_admin, "last_updated": datetime.now()}},
        upsert=True,
    )


async def cb_is_admin(event, user_id):
    try:
        p = await meow(GetParticipantRequest(event.chat_id, user_id))
    except UserNotParticipantError:
        return False
    if isinstance(p.participant, types.ChannelParticipantAdmin) or isinstance(
        p.participant, types.ChannelParticipantCreator
    ):
        return True
    else:
        await event.answer(strings.NOT_ADMIN, alert=True)
        return False


async def can_manage_topics(event, user_id):
    try:
        p = await meow(GetParticipantRequest(event.chat_id, user_id))
    except UserNotParticipantError:
        return False
    if (
        isinstance(p.participant, types.ChannelParticipantCreator)
        or user_id in DEV_USERS
    ):
        return True
    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.manage_topics:
            await event.reply(strings.NOT_TOPIC)
            return False
        return True
    else:
        await event.reply(strings.NOT_ADMIN)
        return False


async def update_cache_periodically():
    """Periodically update admin cache - runs as a background task"""
    while True:
        try:
            # Process in batches to avoid blocking the event loop
            batch_size = 200
            cursor = cache_collection.find({}, {"chat_id": 1, "user_id": 1}, batch_size=500)
            batch = []
            
            async for entry in cursor:
                batch.append(entry)
                
                if len(batch) >= batch_size:
                    # Process batch
                    await process_admin_cache_batch(batch)
                    batch = []
                    # Yield control to event loop between batches
                    try:
                        await asyncio.sleep(0.1)
                    except asyncio.CancelledError:
                        LOGGER.info("Admin cache update task cancelled.")
                        return
            
            # Process remaining entries
            if batch:
                await process_admin_cache_batch(batch)
                
        except asyncio.CancelledError:
            LOGGER.info("Admin cache update task cancelled.")
            break
        except Exception as e:
            LOGGER.error(f"Error in admin cache update periodic task: {e}")
            
        try:
            await asyncio.sleep(600)  # 10 minutes
        except asyncio.CancelledError:
            LOGGER.info("Admin cache update task cancelled during sleep.")
            break


async def process_admin_cache_batch(batch):
    """Process a batch of admin cache entries"""
    for entry in batch:
        chat_id = entry["chat_id"]
        user_id = int(entry["user_id"])

        try:
            p = await meow(GetParticipantRequest(chat_id, user_id))
            is_admin = isinstance(
                p.participant, types.ChannelParticipantAdmin
            ) or isinstance(p.participant, types.ChannelParticipantCreator)
            await update_admin_cache(chat_id, user_id, is_admin)
        except UserNotParticipantError:
            pass
        except ValueError:
            pass
        except errors.ChatAdminRequiredError:
            pass
        except errors.ChannelPrivateError:
            pass
        except asyncio.CancelledError:
            # Task was cancelled, stop processing
            break
        except Exception as e:
            LOGGER.error(f"Error updating admin cache for {user_id}: {e}")
            
        # Small delay between each user to avoid rate limits
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            break


async def start_admin_cache_task():
    """Start the admin cache update task - should be called during startup"""
    try:
        asyncio.create_task(update_cache_periodically())
        LOGGER.info("Admin cache update task started successfully.")
    except Exception as e:
        LOGGER.error(f"Failed to start admin cache update task: {e}")


# Don't start the task at import time - it will be started in main()
# This prevents the "asyncio event loop must not change after connection" error

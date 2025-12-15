from asyncio import sleep
from datetime import datetime, timedelta

from pyrogram import Client, enums, filters
from pyrogram.types import ChatPermissions, Message

import Emilia.strings as strings
from Emilia import custom_filter, db, LOGGER
from Emilia.helper.chat_status import isBotCan, isUserAdmin
from Emilia.helper.time_checker import *
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *
from Emilia.utils.cache import SimpleCache, approvals_cache

DB = db.antiflood_chats
# collection = db.flood_msgs # Deprecated: Using Redis
FLOOD_LOCK = set()
redis_client = db.redis_client

# Caches
_flood_status_cache = SimpleCache(default_ttl=60)
# Antiflood Settings Cache: L1 (Memory) -> L2 (Redis) -> L3 (Mongo)
_settings_cache = SimpleCache(default_ttl=300)

async def flood_limits(chat_id: int):
    """
    Fetch flood limits with 3-level caching (Memory -> Redis -> Mongo).
    Returns: (limit, timed_limit, timed_duration, action, clear_flood, time, timed_on)
    """
    cache_key = f"antiflood_settings:{chat_id}"
    
    # Try Cache (L1 + L2)
    cached_data = await _settings_cache.get(cache_key)
    if cached_data:
        return cached_data

    # Fetch from Mongo (L3)
    limit = await DB.find_one({"chat_id": chat_id})
    if not limit:
        # Default values. timed_on is False by default if not set.
        result = (10, 10, 10, "ban", "yes", None, False)
    else:
        chat_limit = int(limit.get("limit", 10))
        timed_limit = int(limit.get("timed_limit", 10))
        timed_duration = int(limit.get("timed_duration", 10))
        action = limit.get("action", "ban")
        clear_flood = limit.get("clear", "yes")
        timed_on = limit.get("timed_status", "off") == "on"
        
        if action in ["tban", "tmute"]:
            time = limit.get("time", None)
            result = (chat_limit, timed_limit, timed_duration, action, clear_flood, time, timed_on)
        else:
            result = (chat_limit, timed_limit, timed_duration, action, clear_flood, None, timed_on)

    # Set Cache
    await _settings_cache.set(cache_key, result, ttl=300)
    return result

async def _check_flood_on_cached(chat_id: int) -> bool:
    k = f"flood_on:{chat_id}"
    v = await _flood_status_cache.get(k)
    if v is not None:
        return v
    meow = await DB.find_one({"chat_id": chat_id})
    on = bool(meow and "status" in meow and meow["status"] != "off")
    await _flood_status_cache.set(k, on, ttl=60)
    return on

async def _is_approved_cached(chat_id: int, user_id: int) -> bool:
    key = f"appr:{chat_id}:{user_id}"
    val = await approvals_cache.get(key)
    if val is not None:
        return val
    is_approved = await db["approve_d"].find_one({"user_id": user_id, "chat_id": chat_id}) is not None
    await approvals_cache.set(key, is_approved, ttl=180)
    return is_approved

async def check_flood_on(chat_id: int):
    meow = await DB.find_one({"chat_id": chat_id})
    if meow and "status" in meow and meow["status"] != "off":
        return True
    else:
        return False


@usage("/setfloodtimer [count] [duration]")
@description(
    "Set the number of messages and time required for timed antiflood to take action on a user. Set to just 'off' or 'no' to disable."
)
@example("/setfloodtimer 10 10")
@Client.on_message(custom_filter.command("setfloodtimer"))
@logging
async def setfloodtimer(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserAdmin(message, pm_mode=True):
        return

    if len(message.text.split()) < 2:
        return await usage_string(message, setfloodtimer)

    if not (
        (
            await isBotCan(
                message, chat_id=chat_id, privileges="can_restrict_members", silent=True
            )
        )
        and (
            await isBotCan(
                message, chat_id=chat_id, privileges="can_delete_messages", silent=True
            )
        )
    ):
        await DB.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "off"}}, upsert=True
        )
        # Invalidate Settings Cache
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)
        
        await_msg = await message.reply(
            "I need permission to delete messages and restrict users to enable antiflood. So I am disabling it in this chat."
        )
        return

    count, duration = message.text.split()[1:]

    if count == "off" or count == "no":
        await DB.update_one(
            {"chat_id": chat_id},
            {"$set": {"timed_status": "off"}},
            upsert=True,
        )
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        
        await message.reply("Timed antiflood is now disabled.")
        return "DISABLED_TIMED_ANTIFLOOD", None, None

    if not count.isdigit() or not duration.isdigit():
        return await message.reply("Usage: /setfloodtimer [count] [duration]")

    await DB.update_one(
        {"chat_id": chat_id},
        {"$set": {"timed_limit": int(count), "timed_duration": int(duration), "timed_status": "on"}},
        upsert=True,
    )
    await _settings_cache.delete(f"antiflood_settings:{chat_id}")

    await message.reply(
        f"Timed antiflood is now set to trigger after {count} messages in {duration} seconds."
    )
    return "SET_TIMED_ANTIFLOOD", None, None


@Client.on_message(custom_filter.command("flood"))
async def flood_func(client, message: Message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await check_flood_on(chat_id):
        await message.reply_text("Antiflood is disabled in this chat.")
    else:
        limit, timed_limit, timed_duration, action, clear_flood, time, timed_on = (
            await flood_limits(chat_id)
        )
        if time:
            return await message.reply_text(
                f"Antiflood will trigger after {limit} messages.\nAction to take: {action} for {time}\nClear flood messages: {clear_flood}\nTimed antiflood: {timed_limit} messages in {timed_duration} seconds."
            )
        await message.reply_text(
            f"Antiflood will trigger after {limit} messages.\nAction to take: {action}\nClear flood messages: {clear_flood}\nTimed antiflood: {timed_limit} messages in {timed_duration} seconds."
        )


@usage("/antiflood [on/off/limit]")
@description(
    "By turning it on inside a group chat, bot will automatically mute users that send a specific amount of messages to avoid spam. Default limit is 10."
)
@example("/antiflood 15")
@Client.on_message(custom_filter.command(commands=["antiflood", "setflood"]))
@logging
async def antiflood_func(client, message: Message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserAdmin(message, pm_mode=True):
        return

    if len(message.text.split()) < 2:
        return await usage_string(message, antiflood_func)

    if not (
        (
            await isBotCan(
                message, chat_id=chat_id, privileges="can_restrict_members", silent=True
            )
        )
        and (
            await isBotCan(
                message, chat_id=chat_id, privileges="can_delete_messages", silent=True
            )
        )
    ):
        await DB.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "off"}}, upsert=True
        )
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)

        await message.reply(
            "I need permission to delete messages and restrict users to enable antiflood. So it will remain disabled until then."
        )
        return

    status = message.text.split(None, 1)[1].strip()

    if status == "on":
        await DB.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "on"}}, upsert=True
        )
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", True, ttl=60)
        await message.reply(
            "Antiflood is now enabled in this chat. Default limit is 10."
        )
        return "ENABLED_ANTIFLOOD", None, None
    elif status == "off" or status == "no":
        await DB.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "off"}}, upsert=True
        )
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)
        await message.reply("Antiflood is now disabled in this chat.")
        return "DISABLED_ANTIFLOOD", None, None
    elif status.isdigit():
        status = int(status)
        if status < 1 or status > 50:
            await message.reply("Flood value should be between 1 and 50.")
        else:
            await DB.update_one(
                {"chat_id": chat_id},
                {"$set": {"limit": status, "status": "on"}},
                upsert=True,
            )
            await _settings_cache.delete(f"antiflood_settings:{chat_id}")
            await _flood_status_cache.set(f"flood_on:{chat_id}", True, ttl=60)
            await message.reply(f"Antiflood limit is now set to {status} in this chat.")
            return "NEW_FLOOD_LIMIT", None, None
    else:
        await message.reply("Usage: /antiflood [on/off]")


@usage("/floodmode [action type]")
@description(
    "Choose which action to take on a user who has been flooding. Possible actions: ban/mute/kick/tban/tmute"
)
@example("/floodmode ban")
@Client.on_message(custom_filter.command(commands=["floodmode", "setfloodmode"]))
@logging
async def floodmode(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserAdmin(message, pm_mode=True):
        return

    if len(message.text.split()) < 2:
        return await usage_string(message, floodmode)

    if not (
        (
            await isBotCan(
                message, chat_id=chat_id, privileges="can_restrict_members", silent=True
            )
        )
        and (
            await isBotCan(
                message, chat_id=chat_id, privileges="can_delete_messages", silent=True
            )
        )
    ):
        await DB.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "off"}}, upsert=True
        )
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)
        
        await message.reply(
            "I need permission to delete messages and restrict users to enable antiflood. So I am disabling it in this chat."
        )
        return

    action = message.text.split()[1]
    if action not in ["ban", "mute", "kick", "tban", "tmute"]:
        return await message.reply(
            "Invalid action type. Choose from ban/mute/kick/tban/tmute."
        )
    if action in ["tban", "tmute"]:
        try:
            time = message.text.split()[2]
        except IndexError:
            time = message.text.split()[-1]
        if await check_time(message, time):
            await DB.update_one(
                {"chat_id": chat_id},
                {"$set": {"action": action, "time": time}},
                upsert=True,
            )
            await _settings_cache.delete(f"antiflood_settings:{chat_id}")

            await message.reply(
                f"Action to take on flooding users is now set to {action} for {time}."
            )
            return "SET_FLOOD_ACTION", None, None
        else:
            return

    await DB.update_one(
        {"chat_id": chat_id},
        {"$set": {"action": action}},
        upsert=True,
    )
    await _settings_cache.delete(f"antiflood_settings:{chat_id}")

    await message.reply(f"Action to take on flooding users is now set to {action}.")
    return "SET_FLOOD_ACTION", None, None


@usage("/clearflood [yes/no/on/off]")
@description("Whether to delete the messages that triggered the flood.")
@example("/clearflood yes")
@Client.on_message(custom_filter.command("clearflood"))
@logging
async def clearflood(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserAdmin(message, pm_mode=True):
        return

    if len(message.text.split()) < 2:
        return await usage_string(message, clearflood)

    if not (
        (
            await isBotCan(
                message, chat_id=chat_id, privileges="can_restrict_members", silent=True
            )
        )
        and (
            await isBotCan(
                message, chat_id=chat_id, privileges="can_delete_messages", silent=True
            )
        )
    ):
        await DB.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "off"}}, upsert=True
        )
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)

        await message.reply(
            "I need permission to delete messages and restrict users to enable antiflood. So I am disabling it in this chat."
        )
        return

    action = message.text.split()[1]
    if action not in ["yes", "no", "on", "off"]:
        return await message.reply("Invalid action type. Choose from yes/no/on/off.")

    await DB.update_one(
        {"chat_id": chat_id},
        {"$set": {"clear": action}},
        upsert=True,
    )
    await _settings_cache.delete(f"antiflood_settings:{chat_id}")

    await message.reply(f"Clear flood messages is now set to {action}.")
    return f"SET_CLEAR_FLOOD", None, None



approve_collection = db["approve_d"]

@Client.on_message(
    filters.group
    & ~filters.new_chat_members
    & ~filters.left_chat_member
    & ~filters.service
    & ~filters.bot,
    group=11,
)
async def handle_message(client, message):
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    msg_id = message.id

    # Fast path check
    if not await _check_flood_on_cached(chat_id):
        return
    # GLOBAL STATE TRACKING (Crucial for resetting consecutive counts)
    # We must track "Last User" change BEFORE ignoring admins.
    last_user_key = f"flood:last_user:{chat_id}"
    last_user_id = await redis_client.get(last_user_key)
    
    # Check if user changed
    if last_user_id and int(last_user_id) != user_id:
        # User changed! Reset the *consecutive* flood counter for the PREVIOUS user.
        # This prevents the bot from thinking the previous user is still spamming
        # if they resume after an interruption.
        pass

    # Update Last User to Current
    await redis_client.set(last_user_key, user_id)
    # Check approval
    if await _is_approved_cached(chat_id, user_id):
        if last_user_id and int(last_user_id) != user_id:
             # Regular user -> Approved User.
             # Clear Regular User's ZSET to be lenient (reset their strict consecutive count).
             await redis_client.delete(f"flood:zset:{chat_id}:{int(last_user_id)}")
        return

    if await isUserAdmin(message, silent=True):
        if last_user_id and int(last_user_id) != user_id:
             # Regular user -> Admin.
             # Clear Regular User's ZSET.
             await redis_client.delete(f"flood:zset:{chat_id}:{int(last_user_id)}")
        return
    # If we are regular user:
    # Clear PREVIOUS user if different
    if last_user_id and int(last_user_id) != user_id:
        await redis_client.delete(f"flood:zset:{chat_id}:{int(last_user_id)}")

    # Fetch settings
    (limit, timed_limit, timed_duration, action, clear_flood, time, timed_on) = await flood_limits(chat_id)
    limit = int(limit)
    timed_limit = int(timed_limit)
    timed_duration = int(timed_duration)
    
    current_time = datetime.now().timestamp()
    zkey = f"flood:zset:{chat_id}:{user_id}"

    # Add message to ZSET
    await redis_client.zadd(zkey, {str(msg_id): current_time})
    await redis_client.expire(zkey, max(timed_duration, 60) + 10)

    should_punish = False
    
    if timed_on:
        # Count messages within last 'timed_duration' seconds
        min_score = current_time - timed_duration
        count = await redis_client.zcount(zkey, min_score, "+inf")
        if count >= timed_limit:
            should_punish = True
    else:
        # Consecutive count
        # By clearing the ZSET on user switch, ZCARD is effectively consecutive count
        count = await redis_client.zcard(zkey)
        if count >= limit:
            should_punish = True

    if should_punish:
        if user_id in FLOOD_LOCK:
            return
        FLOOD_LOCK.add(user_id)
        try:
            firstname = message.from_user.first_name
            
            # Exec Punishment
            if action == "ban":
                await client.ban_chat_member(chat_id, user_id)
                await client.send_message(chat_id, f"{firstname} has been banned for spamming.")
            elif action == "mute":
                await client.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
                await client.send_message(chat_id, f"{firstname} has been muted for spamming.")
            elif action == "kick":
                await client.ban_chat_member(chat_id, user_id)
                await client.unban_chat_member(chat_id, user_id)
                await client.send_message(chat_id, f"{firstname} has been kicked for spamming.")
            elif action in ["tban", "tmute"]:
                time_str = time
                time_value = await time_converter(message, time_str)
                if action == "tban":
                    await client.ban_chat_member(chat_id, user_id, until_date=time_value)
                    await client.send_message(chat_id, f"{firstname} has been temporarily banned ({time_str}) for spamming.")
                else:
                    await client.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False), until_date=time_value)
                    await client.send_message(chat_id, f"{firstname} has been temporarily muted ({time_str}) for spamming.")
            
            # Clear messages
            if clear_flood in ["yes", "on"]:
                # Get all msg_ids from ZSET
                msg_ids_raw = await redis_client.zrange(zkey, 0, -1)
                msg_ids = [int(m) for m in msg_ids_raw]
                if msg_ids:
                    try:
                        await client.delete_messages(chat_id, msg_ids)
                    except Exception:
                        pass
            
            # Clear Redis state
            await redis_client.delete(zkey)
            
        finally:
            FLOOD_LOCK.discard(user_id)

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
collection = db.flood_msgs
FLOOD_LOCK = set()

async def flood_limits(chat_id: int):
    limit = await DB.find_one({"chat_id": chat_id})
    chat_limit = int(limit.get("limit", 10))
    timed_limit = int(limit.get("timed_limit", 10))
    timed_duration = int(limit.get("timed_duration", 10))
    action = limit.get("action", "ban")
    clear_flood = limit.get("clear", "yes")
    if action in ["tban", "tmute"]:
        time = limit.get("time", None)
        if time:
            return chat_limit, timed_limit, timed_duration, action, clear_flood, time

    return chat_limit, timed_limit, timed_duration, action, clear_flood, None

# Small TTL caches
_flood_status_cache = SimpleCache(default_ttl=60)

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
        await message.reply(
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
        await message.reply("Timed antiflood is now disabled.")
        return "DISABLED_TIMED_ANTIFLOOD", None, None

    if not count.isdigit() or not duration.isdigit():
        return await message.reply("Usage: /setfloodtimer [count] [duration]")

    await DB.update_one(
        {"chat_id": chat_id},
        {"$set": {"timed_limit": int(count), "timed_duration": int(duration), "timed_status": "on"}},
        upsert=True,
    )
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
        limit, timed_limit, timed_duration, action, clear_flood, time = (
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
        await message.reply(
            "I need permission to delete messages and restrict users to enable antiflood. So it will remain disabled until then."
        )
        return

    status = message.text.split(None, 1)[1].strip()

    if status == "on":
        await DB.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "on"}}, upsert=True
        )
        await _flood_status_cache.set(f"flood_on:{chat_id}", True, ttl=60)
        await message.reply(
            "Antiflood is now enabled in this chat. Default limit is 10."
        )
        return "ENABLED_ANTIFLOOD", None, None
    elif status == "off" or status == "no":
        await DB.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "off"}}, upsert=True
        )
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
    await message.reply(f"Clear flood messages is now set to {action}.")
    return f"SET_CLEAR_FLOOD", None, None


async def handle_flood(client, message, user_id: int, chat_id: int):
    if user_id in FLOOD_LOCK:
        return
    
    settings = await DB.find_one({"chat_id": chat_id})
    if not settings:
        return
    limit = settings.get("limit", 10)
    timed_limit = settings.get("timed_limit", 10)
    timed_duration = settings.get("timed_duration", 10)
    action = settings.get("action", "ban")
    clear_flood = settings.get("clear", "yes")
    firstname = (
        message.from_user.first_name if message.from_user else message.sender_chat.title
    )

    if settings.get("timed_status", "off") == "on":
        start_time = datetime.now() - timedelta(seconds=timed_duration)
        count = await collection.count_documents(
            {
                "user_id": user_id,
                "chat_id": chat_id,
                "timestamp": {"$gte": start_time.timestamp()},
            }
        )
        if count == timed_limit:
            FLOOD_LOCK.add(user_id)
            try:
                if action == "ban":
                    await client.ban_chat_member(chat_id, user_id)
                    await client.send_message(
                        chat_id, f"{firstname} has been banned for spamming."
                    )
                elif action == "mute":
                    await client.restrict_chat_member(
                        chat_id,
                        user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                    )
                    await client.send_message(
                        chat_id, f"{firstname} has been muted for spamming."
                    )
                elif action == "kick":
                    await client.ban_chat_member(chat_id, user_id)
                    await client.unban_chat_member(chat_id, user_id)
                    await client.send_message(
                        chat_id, f"{firstname} has been kicked for spamming."
                    )
                elif action == "tban":
                    time = settings.get("time")
                    time_value = await time_converter(message, time)
                    await client.ban_chat_member(chat_id, user_id, until_date=time_value)
                    await client.send_message(
                        chat_id,
                        f"{firstname} has been temporarily banned ({time}) for spamming.",
                    )
                elif action == "tmute":
                    time = settings.get("time")
                    time_value = await time_converter(message, time)
                    await client.restrict_chat_member(
                        chat_id,
                        user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=time_value,
                    )
                    await client.send_message(
                        chat_id,
                        f"{firstname} has been temporarily muted ({time}) for spamming.",
                    )

                if clear_flood in ["yes", "on"]:
                    msg_ids = []
                    async for doc in collection.find({"user_id": user_id, "chat_id": chat_id}):
                        mid = doc["msg_id"]
                        if isinstance(mid, int):
                            msg_ids.append(mid)
                    if msg_ids:
                        try:
                            await client.delete_messages(chat_id, msg_ids)
                        except Exception as e:
                            LOGGER.warning(f"antiflood: failed to delete flood msgs in {chat_id}: {e}")
                    await collection.delete_many({"user_id": user_id, "chat_id": chat_id})
            finally:
                FLOOD_LOCK.discard(user_id)
    else:
        counter = await collection.count_documents(
            {"user_id": user_id, "chat_id": chat_id}
        )
        if counter == limit:
            FLOOD_LOCK.add(user_id)
            try:
                if action == "ban":
                    await client.ban_chat_member(chat_id, user_id)
                    await client.send_message(
                        chat_id, f"{firstname} has been banned for spamming."
                    )
                elif action == "mute":
                    await client.restrict_chat_member(
                        chat_id,
                        user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                    )
                    await client.send_message(
                        chat_id, f"{firstname} has been muted for spamming."
                    )
                elif action == "kick":
                    await client.ban_chat_member(chat_id, user_id)
                    await client.unban_chat_member(chat_id, user_id)
                    await client.send_message(
                        chat_id, f"{firstname} has been kicked for spamming."
                    )
                elif action == "tban":
                    time = settings.get("time")
                    time_value = await time_converter(message, time)
                    await client.ban_chat_member(chat_id, user_id, until_date=time_value)
                    await client.send_message(
                        chat_id,
                        f"{firstname} has been temporarily banned ({time}) for spamming.",
                    )
                elif action == "tmute":
                    time = settings.get("time")
                    time_value = await time_converter(message, time)
                    await client.restrict_chat_member(
                        chat_id,
                        user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=time_value,
                    )
                    await client.send_message(
                        chat_id,
                        f"{firstname} has been temporarily muted ({time}) for spamming.",
                    )
                await sleep(5)

                if clear_flood in ["yes", "on"]:
                    msg_ids = []
                    async for doc in collection.find({"user_id": user_id, "chat_id": chat_id}):
                        mid = doc["msg_id"]
                        if isinstance(mid, int):
                            msg_ids.append(mid)
                    if msg_ids:
                        try:
                            await client.delete_messages(chat_id, msg_ids)
                        except Exception as e:
                            LOGGER.warning(f"antiflood: failed to delete flood msgs in {chat_id}: {e}")
                    await collection.delete_many({"user_id": user_id, "chat_id": chat_id})
            finally:
                FLOOD_LOCK.discard(user_id)

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
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else message.sender_chat.id
    msg_id = message.id

    if not await _check_flood_on_cached(chat_id):
        return
    
    chat_settings = await DB.find_one({"chat_id": chat_id})
    last_user = chat_settings.get("last_user_id") if chat_settings else None
    
    if await _is_approved_cached(chat_id, user_id):
        if last_user and last_user != user_id:
            await collection.delete_many({"user_id": last_user, "chat_id": chat_id})
        await DB.update_one(
            {"chat_id": chat_id},
            {"$set": {"last_user_id": user_id}},
            upsert=True
        )
        return

    if await isUserAdmin(message, silent=True):
        if last_user and last_user != user_id:
            await collection.delete_many({"user_id": last_user, "chat_id": chat_id})
        await DB.update_one(
            {"chat_id": chat_id},
            {"$set": {"last_user_id": user_id}},
            upsert=True
        )
        return

    if last_user and last_user != user_id:
        await collection.delete_many({"user_id": last_user, "chat_id": chat_id})
    
    await DB.update_one(
        {"chat_id": chat_id},
        {"$set": {"last_user_id": user_id}},
        upsert=True
    )

    await collection.insert_one(
        {"user_id": user_id, "chat_id": chat_id, "msg_id": msg_id, "timestamp": datetime.now().timestamp(), "date": datetime.utcnow()}
    )
    await handle_flood(client, message, user_id, chat_id)
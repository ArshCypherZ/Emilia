# DONE: Antiraid

from datetime import datetime, timedelta

from pyrogram import filters as pyrofilters
from pyrogram.enums import ChatType
from pyrogram.errors import ChatAdminRequired

import Emilia.strings as strings
from Emilia import LOGGER, db
from Emilia.custom_filter import listen, register
from Emilia.helper.admins import can_change_info
from Emilia.helper.get_data import GetChat
from Emilia.modules.plugins.connection.connection import connection
from Emilia.utils.decorators import *
from Emilia.utils.decorators import anonadmin_checker

# Configurable default values
DEFAULT_ANTIRAID_DURATION = 6
DEFAULT_RAID_ACTION_TIME = 1
DEFAULT_AUTO_ANTIRAID_THRESHOLD = 20

collection = db.antiraid_data
join_times_collection = db.join_times

# Command names and usage messages
COMMANDS = {
    "antiraid": "Toggle antiraid system.",
    "raidtime": "Set the antiraid duration (in hours).",
    "raidactiontime": "Set the raid action time (in hours).",
    "autoantiraid": "Set the auto antiraid threshold (use 'off' or 'no' to disable).",
}


@listen(filters=pyrofilters.new_chat_members)
async def on_chat_action(client, message):
    if not message.new_chat_members:
        return

    chat_id = message.chat.id

    # Check if antiraid is enabled for the chat
    antiraid_data = await collection.find_one({"_id": chat_id})
    if (
        antiraid_data
        and antiraid_data.get("expiry_time", datetime.now()) > datetime.now()
    ):
        # Ban the new member if antiraid is enabled
        for new_member in message.new_chat_members:
            try:
                await client.ban_chat_member(
                    chat_id,
                    new_member.id,
                    until_date=datetime.now()
                    + timedelta(
                        hours=antiraid_data.get(
                            "raid_action_time", DEFAULT_RAID_ACTION_TIME
                        )
                    ),
                )
            except ChatAdminRequired:
                LOGGER.warning(
                    f"antiraid: lost admin rights in {chat_id}, disabling raid mode"
                )
                await collection.delete_one({"_id": chat_id})
                break
            except Exception as exc:
                LOGGER.warning(
                    f"antiraid: failed to ban {new_member.id} in {chat_id}: {exc}"
                )
                continue

    elif antiraid_data:
        # Check for automatic antiraid
        auto_antiraid_threshold = antiraid_data.get(
            "auto_antiraid_threshold", DEFAULT_AUTO_ANTIRAID_THRESHOLD
        )
        current_time = datetime.now()
        one_minute_ago = current_time - timedelta(minutes=1)

        # Drop stale entries before pushing new ones, so this document can't
        # grow without bound in a busy/long-lived chat.
        await join_times_collection.update_one(
            {"chat_id": chat_id},
            {"$pull": {"join_times": {"$lt": one_minute_ago}}},
        )
        await join_times_collection.update_one(
            {"chat_id": chat_id},
            {
                "$push": {
                    "join_times": {
                        "$each": [current_time] * len(message.new_chat_members)
                    }
                }
            },
            upsert=True,
        )

        # Get the join times for the chat
        join_times_data = await join_times_collection.find_one({"chat_id": chat_id})
        if join_times_data:
            recent_join_times = join_times_data.get("join_times", [])

            # If the number of recent join times exceeds the threshold, enable
            # antiraid
            if len(recent_join_times) >= auto_antiraid_threshold:
                # Enable antiraid, honoring an admin-configured duration if set
                duration = antiraid_data.get(
                    "antiraid_duration", DEFAULT_ANTIRAID_DURATION
                )
                expiry_time = current_time + timedelta(hours=duration)
                await collection.update_one(
                    {"_id": chat_id},
                    {"$set": {"expiry_time": expiry_time}},
                    upsert=True,
                )
                await message.reply_text(
                    f"Auto anti-raid enabled since {len(recent_join_times)} users joined the chat within one minute."
                )


@register(pattern="antiraid")
@log_to_channel
@anonadmin_checker
async def toggle_antiraid(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title
    sender_id = message.from_user.id if message.from_user else None
    if not await can_change_info(message, sender_id, chat_id=chat_id):
        return
    antiraid_data = await collection.find_one({"_id": chat_id})
    if (
        antiraid_data
        and antiraid_data.get("expiry_time", datetime.now()) > datetime.now()
    ):
        # Disable antiraid
        await collection.delete_one({"_id": chat_id})
        await message.reply_text(f"Antiraid has been disabled in {title}.")
        return "ANTIRAID_DISABLE", None, None
    else:
        # Enable antiraid, honoring an admin-configured duration if set
        duration = (antiraid_data or {}).get(
            "antiraid_duration", DEFAULT_ANTIRAID_DURATION
        )
        expiry_time = datetime.now() + timedelta(hours=duration)
        await collection.update_one(
            {"_id": chat_id}, {"$set": {"expiry_time": expiry_time}}, upsert=True
        )
        await message.reply_text(f"Antiraid has been enabled in {title}.")
        return "ANTIRAID_ENABLE", None, None


@register(pattern="raidtime")
@log_to_channel
@anonadmin_checker
async def set_antiraid_duration(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title
    sender_id = message.from_user.id if message.from_user else None
    if not await can_change_info(message, sender_id, chat_id=chat_id):
        return
    try:
        # Extract the duration from the command arguments
        duration = int((message.text or "").split(" ")[1])
        if duration <= 0:
            return await message.reply_text(
                "Invalid Duration. Make sure it is positive."
            )
        await collection.update_one(
            {"_id": chat_id},
            {"$set": {"antiraid_duration": duration}},
            upsert=True,
        )
        await message.reply_text(
            f"Antiraid duration set to {duration} hours in {title}."
        )
        return "ANTIRAID_DURATION", None, None
    except (ValueError, IndexError):
        # Invalid or no duration provided, use the default antiraid duration
        await message.reply_text(f"Invalid duration. Usage: /raidtime <hours>")


@register(pattern="raidactiontime")
@log_to_channel
@anonadmin_checker
async def set_raid_action_time(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title
    sender_id = message.from_user.id if message.from_user else None
    if not await can_change_info(message, sender_id, chat_id=chat_id):
        return

    try:
        # Extract the time from the command arguments
        time = int((message.text or "").split(" ")[1])
        if time <= 0:
            return await message.reply_text(
                "Invalid Duration. Make sure it is positive."
            )
        await collection.update_one(
            {"_id": chat_id},
            {"$set": {"raid_action_time": time}},
            upsert=True,
        )
        await message.reply_text(f"Raid action time set to {time} hours in {title}.")
        return "RAID_ACTION_TIME", None, None
    except (ValueError, IndexError):
        # Invalid or no time provided, use the default raid action time
        await message.reply_text(f"Invalid time. Usage: /raidactiontime <hours>")


@register(pattern="autoantiraid")
@log_to_channel
@anonadmin_checker
async def set_auto_antiraid(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title
    sender_id = message.from_user.id if message.from_user else None
    if not await can_change_info(message, sender_id, chat_id=chat_id):
        return
    try:
        # Extract the threshold from the command arguments
        threshold = (message.text or "").split(" ")[1]
        if threshold.lower() in ["off", "no"]:
            auto_antiraid_threshold = 0
        else:
            auto_antiraid_threshold = int(threshold)
            if auto_antiraid_threshold <= 0:
                await message.reply_text(
                    "Threshold must be a positive integer or 'off' to disable."
                )
                return
    except (ValueError, IndexError):
        # Invalid or no threshold provided, use the default auto antiraid
        # threshold
        auto_antiraid_threshold = DEFAULT_AUTO_ANTIRAID_THRESHOLD

    await collection.update_one(
        {"_id": chat_id},
        {"$set": {"auto_antiraid_threshold": auto_antiraid_threshold}},
        upsert=True,
    )
    await message.reply_text(
        f"Auto antiraid threshold set to {auto_antiraid_threshold} in {title}."
    )
    return "AUTO_ANTIRAID", None, None

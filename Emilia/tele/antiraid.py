# DONE: Antiraid

from datetime import datetime, timedelta

from telethon import errors, events

import Emilia.strings as strings
from Emilia import db, telethn
from Emilia.custom_filter import register
from Emilia.functions.admins import can_change_info
from Emilia.helper.get_data import GetChat
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *

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


@telethn.on(events.ChatAction(func=lambda e: e.user_joined))
async def on_chat_action(event):
    if not event.user_joined:
        return

    user_id = event.user_id
    chat_id = event.chat_id

    # Check if antiraid is enabled for the chat
    antiraid_data = await collection.find_one({"_id": chat_id})
    if (
        antiraid_data
        and antiraid_data.get("expiry_time", datetime.now()) > datetime.now()
    ):
        # Ban the new member if antiraid is enabled
        try:
            await telethn.edit_permissions(
                chat_id,
                user_id,
                until_date=datetime.now()
                + timedelta(hours=antiraid_data["raid_action_time"]),
            )
        except errors.ChatAdminRequiredError:
            return

    elif antiraid_data:
        # Check for automatic antiraid
        auto_antiraid_threshold = antiraid_data.get(
            "auto_antiraid_threshold", DEFAULT_AUTO_ANTIRAID_THRESHOLD
        )
        current_time = datetime.now()

        # Insert the current time in the MongoDB collection for join times
        await join_times_collection.update_one(
            {"chat_id": chat_id}, {"$push": {"join_times": current_time}}, upsert=True
        )

        # Get the join times for the chat
        join_times_data = await join_times_collection.find_one({"chat_id": chat_id})
        if join_times_data:
            join_times = join_times_data.get("join_times", [])

            # Filter join times that occurred within the last minute
            one_minute_ago = current_time - timedelta(minutes=1)
            recent_join_times = [t for t in join_times if t >= one_minute_ago]

            # If the number of recent join times exceeds the threshold, enable
            # antiraid
            if len(recent_join_times) >= auto_antiraid_threshold:
                # Enable antiraid
                expiry_time = current_time + timedelta(hours=DEFAULT_ANTIRAID_DURATION)
                await collection.update_one(
                    {"_id": chat_id},
                    {"$set": {"expiry_time": expiry_time}},
                    upsert=True,
                )
                await event.reply(
                    f"Auto anti-raid enabled since {len(recent_join_times)} users joined the chat within one minute."
                )


@register(pattern="antiraid")
@logging
async def toggle_antiraid(event):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    if not await can_change_info(event, event.sender_id):
        return
    antiraid_data = await collection.find_one({"_id": chat_id})
    if (
        antiraid_data
        and antiraid_data.get("expiry_time", datetime.now()) > datetime.now()
    ):
        # Disable antiraid
        await collection.delete_one({"_id": chat_id})
        await event.reply(f"Antiraid has been disabled in {title}.")
        return "ANTIRAID_DISABLE", None, None
    else:
        # Enable antiraid
        expiry_time = datetime.now() + timedelta(hours=DEFAULT_ANTIRAID_DURATION)
        await collection.update_one(
            {"_id": chat_id}, {"$set": {"expiry_time": expiry_time}}, upsert=True
        )
        await event.reply(f"Antiraid has been enabled in {title}.")
        return "ANTIRAID_ENABLE", None, None


@register(pattern="raidtime")
@logging
async def set_antiraid_duration(event):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    if not await can_change_info(event, event.sender_id):
        return
    try:
        # Extract the duration from the command arguments
        duration = int(event.raw_text.split(" ")[1])
        if duration <= 0:
            return await event.reply("Invalid Duration. Make sure it is positive.")
        await collection.update_one(
            {"_id": chat_id},
            {"$set": {"antiraid_duration": duration}},
            upsert=True,
        )
        await event.reply(f"Antiraid duration set to {duration} hours in {title}.")
        return "ANTIRAID_DURATION", None, None
    except (ValueError, IndexError):
        # Invalid or no duration provided, use the default antiraid duration
        await event.reply(f"Invalid duration. Usage: /raidtime <hours>")


@register(pattern="raidactiontime")
@logging
async def set_raid_action_time(event):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    if not await can_change_info(event, event.sender_id):
        return

    try:
        # Extract the time from the command arguments
        time = int(event.raw_text.split(" ")[1])
        if time <= 0:
            return await event.reply("Invalid Duration. Make sure it is positive.")
        await collection.update_one(
            {"_id": chat_id},
            {"$set": {"raid_action_time": time}},
            upsert=True,
        )
        await event.reply(f"Raid action time set to {time} hours in {title}.")
        return "RAID_ACTION_TIME", None, None
    except (ValueError, IndexError):
        # Invalid or no time provided, use the default raid action time
        await event.reply(f"Invalid time. Usage: /raidactiontime <hours>")


@register(pattern="autoantiraid")
@logging
async def set_auto_antiraid(event):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    if not await can_change_info(event, event.sender_id):
        return
    chat_id = event.chat_id
    try:
        # Extract the threshold from the command arguments
        threshold = event.raw_text.split(" ")[1]
        if threshold.lower() in ["off", "no"]:
            auto_antiraid_threshold = 0
        else:
            auto_antiraid_threshold = int(threshold)
            if auto_antiraid_threshold <= 0:
                await event.reply(
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
    await event.reply(
        f"Auto antiraid threshold set to {auto_antiraid_threshold} in {title}."
    )
    return "AUTO_ANTIRAID", None, None

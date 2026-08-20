# DONE: AFK

import random
import time

from pyrogram.enums import ChatType, MessageEntityType
from pyrogram.errors import (
    FloodWait,
    PeerIdInvalid,
    UsernameInvalid,
    UsernameNotOccupied,
)

from Emilia import BOT_ID
from Emilia.custom_filter import listen
from Emilia.helper.admins import get_time as get_readable_time
from Emilia.mongo import afk_mongo as db

options = [
    "**{}** is here! Was afk for {}",
    "**{}** is back! Been away for {}",
    "**{}** is now in the chat! Back after {}",
    "**{}** is awake! Was afk for {}",
    "**{}** is back online! Been away for {}",
    "**{}** is finally here! Was afk for {}",
    "Welcome back! **{}**, Was afk for {}",
    "Where is **{}**?\nIn the chat! Was afk for {}",
    "Pro **{}**, is back alive! Was afk for {}",
]


@listen()
async def afk(client, message):
    if message.chat.id == 777000:
        return
    if not message.from_user:
        return
    text = message.text or ""
    for x in ["+afk", "/afk", "!afk", "?afk", ".afk", "brb", "i go away"]:
        if text.lower().startswith(x):
            try:
                reason = text.split(None, 1)[1]
            except IndexError:
                reason = ""
            if text.lower().startswith("i go away"):
                reason = reason.replace("go away", "")
            _x = await message.reply_text(
                f"**{message.from_user.first_name}** is now away from keyboard!",
            )
            await db.set_afk(message.from_user.id, message.from_user.first_name, reason)
            return

    afk_data = await db.get_afk_user(message.from_user.id)
    if afk_data and "time" in afk_data:
        xp = await get_readable_time(int(time.time()) - int(afk_data.get("time")))
        await db.unset_afk(message.from_user.id)
        await message.reply_text(
            random.choice(options).format(message.from_user.first_name, xp)
        )
        return


@listen()
async def afk_check(client, message):
    if (
        message.chat.type == ChatType.PRIVATE
        or not message.from_user
        or message.from_user.id == BOT_ID
    ):
        return

    user_id = None
    r = message.reply_to_message
    if r and r.from_user:
        user_id = r.from_user.id
    else:
        text = message.text or message.caption or ""
        for ent in message.entities or message.caption_entities or []:
            if ent.offset != 0:
                break
            if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
                user_id = ent.user.id
                break
            if ent.type == MessageEntityType.MENTION:
                mention = text[ent.offset : ent.offset + ent.length]
                try:
                    user_id = (await client.get_users(mention.split()[0])).id
                except AttributeError:
                    user_id = None
                except ValueError:
                    user_id = None
                except FloodWait:
                    user_id = None
                except (
                    PeerIdInvalid,
                    UsernameInvalid,
                    UsernameNotOccupied,
                    IndexError,
                ):
                    # pyrogram raises these instead of ValueError for bad
                    # usernames
                    user_id = None
                break

    if not user_id:
        return

    afk_data = await db.get_afk_user(user_id)
    if afk_data and afk_data["time"]:
        time_seen = await get_readable_time(int(time.time()) - int(afk_data["time"]))
        reason = f"**Reason**: `{afk_data['reason']}`" if afk_data["reason"] else ""
        await message.reply_text(
            f"**{afk_data['first_name']} is away from keyboard!**\n"
            f"**Last seen**: {time_seen} ago.\n\n{reason}",
        )

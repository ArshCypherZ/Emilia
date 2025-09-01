# DONE: AFK

import random
import time

from telethon import events
from telethon.errors import FloodWaitError
from telethon.tl.types import MessageEntityMention, MessageEntityMentionName, User

from Emilia import BOT_ID, telethn
from Emilia.functions.admins import get_time as get_readable_time
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


@telethn.on(events.NewMessage(pattern=r"(.*?)", blacklist_chats=[777000]))
async def afk(e: events.NewMessage.Event):
    if not e.sender:
        return
    for x in ["+afk", "/afk", "!afk", "?afk", ".afk", "brb", "i go away"]:
        if e.text.lower().startswith(x):
            try:
                reason = e.text.split(None, 1)[1]
            except IndexError:
                reason = ""
            if e.text.lower().startswith("i go away"):
                reason = reason.replace("go away", "")
            _x = await e.reply(
                f"**{e.sender.first_name}** is now away from keyboard!",
                parse_mode="markdown",
            )
            await db.set_afk(e.sender_id, e.sender.first_name, reason)
            return

    afk_data = await db.get_afk_user(e.sender_id)
    if afk_data and "time" in afk_data:
        xp = await get_readable_time(int(time.time()) - int(afk_data.get("time")))
        await db.unset_afk(e.sender_id)
        await e.reply(random.choice(options).format(e.sender.first_name, xp))
        return


@telethn.on(events.NewMessage(pattern=r"(.*?)"))
async def afk_check(e: events.NewMessage.Event):
    if e.is_private or not e.from_id or e.sender_id == BOT_ID:
        return

    user_id = None
    r = await e.get_reply_message()
    if r and r.sender and isinstance(r.sender, User):
        user_id = r.sender_id
    else:
        for ent, txt in e.get_entities_text():
            if ent.offset != 0:
                break
            if isinstance(ent, (MessageEntityMention, MessageEntityMentionName)):
                try:
                    user_id = (await telethn.get_input_entity(txt.split()[0])).user_id
                except AttributeError:
                    user_id = None
                except ValueError:
                    user_id = None
                except FloodWaitError:
                    user_id = None
                break

    if not user_id:
        return

    afk_data = await db.get_afk_user(user_id)
    if afk_data and afk_data["time"]:
        time_seen = await get_readable_time(int(time.time()) - int(afk_data["time"]))
        reason = f"**Reason**: `{afk_data['reason']}`" if afk_data["reason"] else ""
        await e.reply(
            f"**{afk_data['first_name']} is away from keyboard!**\n"
            f"**Last seen**: {time_seen} ago.\n\n{reason}",
            parse_mode="markdown",
        )

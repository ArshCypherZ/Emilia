import asyncio
from telethon import events
import Emilia.strings as strings
from Emilia import telethn
from Emilia.custom_filter import register
from Emilia.functions.admins import is_admin


@register(pattern="all")
@telethn.on(events.NewMessage(pattern=r"@all"))
async def mentionall(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)

    if not await is_admin(event, event.sender_id):
        return await event.reply(strings.NOT_ADMIN)
    
    text = " "
    reply = await event.get_reply_message()

    if reply:
        text = reply.text or reply.caption or " "

    elif event.pattern_match and event.pattern_match.group(1):
        text = event.text.split(None, 1)[1]

    usrnum = 0
    usrtxt = ""
    async for usr in telethn.iter_participants(event.chat_id):
        usrnum += 1
        first_name = (usr.first_name).replace("[", "").replace("]", "")
        usrtxt += f"[{first_name}](tg://user?id={usr.id}) "
        if usrnum == 5:
            await telethn.send_message(event.chat_id, f"{usrtxt}\n\n{text}")
            await asyncio.sleep(3)
            usrnum = 0
            usrtxt = ""

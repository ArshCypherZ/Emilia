import asyncio

from pyrogram.enums import ChatType

import Emilia.strings as strings
from Emilia.custom_filter import listen, register
from Emilia.helper.admins import is_admin


async def _mentionall(client, message):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return await message.reply_text(strings.is_pvt)

    if not await is_admin(message, message.from_user.id if message.from_user else None):
        return await message.reply_text(strings.NOT_ADMIN)

    text = " "
    reply = message.reply_to_message

    if reply:
        text = reply.text or reply.caption or " "

    elif getattr(message, "pattern_match", None) and message.pattern_match.group(1):
        text = message.text.split(None, 1)[1]

    usrnum = 0
    usrtxt = ""
    async for member in client.get_chat_members(message.chat.id):
        usr = member.user
        usrnum += 1
        first_name = (usr.first_name).replace("[", "").replace("]", "")
        usrtxt += f"[{first_name}](tg://user?id={usr.id}) "
        if usrnum == 5:
            await client.send_message(message.chat.id, f"{usrtxt}\n\n{text}")
            await asyncio.sleep(3)
            usrnum = 0
            usrtxt = ""

    # flush the final partial batch (member count not a multiple of 5)
    if usrtxt:
        await client.send_message(message.chat.id, f"{usrtxt}\n\n{text}")


@register(pattern="all")
async def mentionall(client, message):
    await _mentionall(client, message)


@listen()
async def mentionall_watcher(client, message):
    if not message.text or not message.text.startswith("@all"):
        return
    await _mentionall(client, message)

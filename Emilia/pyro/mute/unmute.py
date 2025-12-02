from pyrogram import Client
from pyrogram.types import ChatPermissions

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAllAdminsStuffs
from Emilia.helper.get_user import get_user_id
from Emilia.utils.decorators import *
from Emilia.utils.decorators import logging

UNMUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_send_polls=True,
)


@Client.on_message(custom_filter.command(commands="unmute"))
@logging
@anonadmin_checker
async def ban(client, message):
    chat_id = message.chat.id

    if not await CheckAllAdminsStuffs(message, privileges="can_restrict_members"):
        return

    user_info = await get_user_id(message)
    user_id = user_info.id

    await client.restrict_chat_member(chat_id, user_id, UNMUTE_PERMISSIONS)

    await message.reply("Alright, they can speak again.")
    return "UNMUTE", user_id, user_info.first_name

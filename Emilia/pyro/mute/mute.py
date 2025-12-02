import html

from pyrogram import Client
from pyrogram.errors import BadRequest
from pyrogram.types import ChatPermissions

from Emilia import BOT_ID, custom_filter
from Emilia.helper.chat_status import can_restrict_member, isBotAdmin, isUserAdmin
from Emilia.helper.get_user import get_text, get_user_id
from Emilia.utils.decorators import *
from Emilia.utils.decorators import logging

MUTE_PERMISSIONS = ChatPermissions(can_send_messages=False)


@Client.on_message(custom_filter.command(commands=["mute", "dmute", "smute"]))
@logging
@anonadmin_checker
async def mute(client, message):
    chat_id = message.chat.id
    chat_title = message.chat.title
    message_id = None
    if not await isUserAdmin(message):
        return

    user_info = await get_user_id(message)
    user_id = user_info.id

    if user_id == BOT_ID:
        await message.reply("Yup! Let me just ban myself. Yay!")
        return

    if not await isBotAdmin(message):
        return

    if not await can_restrict_member(message, user_id):
        await message.reply("Surely I don't plan to mute an admin.")
        return

    try:
        await client.restrict_chat_member(chat_id, user_id, MUTE_PERMISSIONS)
    except BadRequest:
        return await message.reply("Give me `ban_user` rights to perform this command.")

    if message.text.split()[0].find("dmute") >= 0:
        if message.reply_to_message:
            message_id = message.reply_to_message.id

    elif message.text.split()[0].find("smute") >= 0:
        message_id = message.id

    if not message.text.split()[0].find("smute") >= 0:
        text = f"{user_info.mention} is muted now in {html.escape(chat_title)}.\n"

        reason = await get_text(message)
        if reason:
            text += f"Reason: {reason}"

        await message.reply(text)

    # Deletaion of message according to user admin command
    if message_id is not None:
        await client.delete_messages(chat_id=chat_id, message_ids=message_id)

    return "MUTE", user_info.id, user_info.first_name

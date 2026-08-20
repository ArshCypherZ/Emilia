import html

from pyrogram import Client
from pyrogram.errors import BadRequest
from pyrogram.enums import ParseMode
from pyrogram.types import ChatPermissions

from Emilia import BOT_ID, custom_filter
from Emilia.helper.chat_status import can_restrict_member, isBotAdmin, isUserAdmin
from Emilia.helper.get_user import get_text, get_user_id
from Emilia.helper.telegram_api import restrict_member_no_reactions
from Emilia.utils.decorators import *
from Emilia.utils.decorators import log_to_channel

MUTE_PERMISSIONS = ChatPermissions(can_send_messages=False)


@Client.on_message(custom_filter.command(commands=["mute", "dmute", "smute"]))
@log_to_channel
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
        if not await restrict_member_no_reactions(chat_id, user_id):
            await client.restrict_chat_member(chat_id, user_id, MUTE_PERMISSIONS)
    except BadRequest:
        return await message.reply("Give me `ban_user` rights to perform this command.")

    if message.text.split()[0].find("dmute") >= 0:
        if message.reply_to_message:
            message_id = message.reply_to_message.id

    elif message.text.split()[0].find("smute") >= 0:
        message_id = message.id

    if not message.text.split()[0].find("smute") >= 0:
        actor_html = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>"
        target_html = f"<a href='tg://user?id={user_info.id}'>{user_info.first_name}</a>"
        text = f"Yep! {target_html} has been muted by {actor_html}!"

        reason = await get_text(message)
        if reason:
            text += f"\n\n<blockquote expandable>{html.escape(reason)}</blockquote>"

        await message.reply(text, parse_mode=ParseMode.HTML)

    # Deletaion of message according to user admin command
    if message_id is not None:
        await client.delete_messages(chat_id=chat_id, message_ids=message_id)

    return "MUTE", user_info.id, user_info.first_name

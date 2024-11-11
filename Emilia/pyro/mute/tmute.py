from pyrogram import Client
from pyrogram.errors import BadRequest
from pyrogram.types import ChatPermissions, Message

from Emilia import BOT_ID, custom_filter
from Emilia.helper.chat_status import can_restrict_member, isBotAdmin, isUserAdmin
from Emilia.helper.text_reason import *
from Emilia.helper.time_checker import time_converter
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands=["tmute", "tempmute"]))
@anonadmin_checker
async def mute(_, message: Message):
    if not await isUserAdmin(message):
        return
    if not await isBotAdmin(message):
        return

    user_id, reason = await extract_user_and_reason(message)

    if not user_id:
        await message.reply("I can't find that user.")
        return

    if user_id == BOT_ID:
        await message.reply("Yup! Let me just mute myself. Yay!")
        return

    if not await can_restrict_member(message, user_id):
        await message.reply("Surely I don't plan to mute an admin.")
        return

    if not reason:
        await message.reply(
            "Please give me some time interval to mute the user for!\n**Example**: /tmute @user 1m <reason>"
        )
        return

    split = reason.split(None, 1)
    time_value = split[0]
    temp_reason = split[1] if len(split) > 1 else ""
    temp_mute = await time_converter(message, time_value)
    msg = f"**Muted For:** {time_value}\n"
    if temp_reason:
        msg += f"**Reason:** {temp_reason}"
    try:
        await message.chat.restrict_member(
            user_id,
            permissions=ChatPermissions(),
            until_date=temp_mute,
        )
        await message.reply_text(msg)
    except AttributeError:
        pass
    except BadRequest:
        return await message.reply("Give me `ban_user` rights to perform this command!")

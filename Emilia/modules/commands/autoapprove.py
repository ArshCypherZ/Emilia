import Emilia.strings as strings
from Emilia.custom_filter import register as command
from Emilia.helper.chat_status import isBotCan, isUserCan
from Emilia.modules.plugins.connection.connection import connection
from pyrogram import enums
from Emilia.mongo.autoapprove_mongo import get_autoapprove_mode, set_autoapprove_mode
from Emilia.utils.decorators import *


@command(pattern="autoapprove")
@exception
@log_to_channel
async def autoapprove_cmd(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id
        if message.chat.type == enums.ChatType.PRIVATE:
            return await message.reply(strings.is_pvt)

    if not await isBotCan(message, privileges="can_invite_users", silent=True):
        return await message.reply(
            "I need to be admin with the right to **invite users** to manage join requests."
        )

    if not await isUserCan(message, privileges="can_restrict_members", silent=True):
        return await message.reply(
            "You need to be admin with the right to restrict members to configure autoapprove."
        )

    args = message.text.split()
    if len(args) == 1:
        current_mode = await get_autoapprove_mode(chat_id)
        return await message.reply(
            f"**Current Autoapprove Mode:** `{current_mode}`"
        )

    mode = args[1].lower()
    valid_modes = ["off", "on", "antispam", "rules", "captcha"]

    if mode not in valid_modes:
        return await message.reply(
            f"Invalid mode: `{mode}`.\nValid modes are: `{'`, `'.join(valid_modes)}`."
        )

    await set_autoapprove_mode(chat_id, mode)
    await message.reply(f"Successfully set Autoapprove mode to `{mode}`.")

    # Return standard event tuple for logging
    return ("AUTOAPPROVE", message.from_user.id, message.from_user.first_name)

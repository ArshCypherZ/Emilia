from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.disable_mongo import get_disabled


@Client.on_message(custom_filter.command(commands="disabled"))
async def disable(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserAdmin(message, pm_mode=True):
        return

    DISABLE_LIST = await get_disabled(chat_id)

    if len(DISABLE_LIST) == 0:
        await message.reply("There are no disabled commands in this chat.")
        return

    text = "The following commands are disabled in this chat:\n"
    for item in DISABLE_LIST:
        text += f"- `{item}`\n"

    await message.reply(text)

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.modules.plugins.connection.connection import connection
from Emilia.modules.plugins.locks import lock_map
from Emilia.mongo.locks_mongo import get_locks


@Client.on_message(custom_filter.command(commands="locks"))
async def locks(client, message):
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

    LOCKS_LIST = await get_locks(chat_id)

    if len(LOCKS_LIST) == 0:
        return await message.reply("No items locked in this chat.")

    if 1 in LOCKS_LIST:
        return await message.reply("Jokes on you, everything's locked.")

    text = "These are the currently locked items:\n"
    for item in LOCKS_LIST:
        lock_name = lock_map.LocksMap(item).name
        text += f"• `{lock_name}`\n"

    await message.reply(text)

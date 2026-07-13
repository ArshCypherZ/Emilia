from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.filters_mongo import get_filters_list, stop_db
from Emilia.utils.decorators import *


@usage("/stop [filter name]")
@example("/stop meow")
@description("Use this command to stop the active filter in chat.")
@Client.on_message(custom_filter.command("stop"))
async def stop(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if not await isUserAdmin(message):
        return

    if not (len(message.text.split()) >= 2):
        await usage_string(message, stop)
        return

    filter_name = message.text.split()[1]
    if filter_name not in (await get_filters_list(chat_id)):
        await message.reply("You haven't saved any filters on this word yet!")
        return

    await stop_db(chat_id, filter_name)
    await message.reply(f"I've stopped `{filter_name}`.")

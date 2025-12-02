import html

from pyrogram import Client
from pyrogram.enums import ChatType

from Emilia import custom_filter
from Emilia.helper.get_data import GetChat
from Emilia.mongo.filters_mongo import get_filters_list
from Emilia.pyro.connection.connection import connection


@Client.on_message(custom_filter.command("filters"))
async def filters(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

        if message.chat.type == ChatType.PRIVATE:
            chat_title = "local"
    FILTERS = await get_filters_list(chat_id)

    if len(FILTERS) == 0:
        await message.reply(f"No filters in {html.escape(chat_title)}.")
        return

    filters_list = f"List of filters in {html.escape(chat_title)}:\n"

    for filter_ in FILTERS:
        filters_list += f"• `{filter_}`\n"

    await message.reply(filters_list)

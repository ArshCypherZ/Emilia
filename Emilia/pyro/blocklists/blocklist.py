import html

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.helper.get_data import GetChat
from Emilia.mongo.blocklists_mongo import get_blocklist
from Emilia.pyro.connection.connection import connection


@Client.on_message(custom_filter.command(commands=["blocklist", "blacklist"]))
async def blocklist(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)
    if not await isUserAdmin(message, pm_mode=True):
        return

    BLOCKLIST_DATA = await get_blocklist(chat_id)
    if BLOCKLIST_DATA is None or len(BLOCKLIST_DATA) == 0:
        await message.reply(
            f"No blocklist filters are active in {html.escape(chat_title)}!"
        )
        return

    BLOCKLIST_ITMES = []
    for blocklist_array in BLOCKLIST_DATA:
        BLOCKLIST_ITMES.append(blocklist_array["blocklist_text"])

    blocklist_header = f"The following blocklist filters are currently active in {html.escape(chat_title)}:\n"
    for block_itmes in BLOCKLIST_ITMES:
        blocklist_name = f"• `{block_itmes}`\n"
        blocklist_header += blocklist_name

    await message.reply(blocklist_header, quote=True)

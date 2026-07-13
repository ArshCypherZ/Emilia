from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.blocklists_mongo import get_blocklist, rmblocklist_db


@Client.on_message(
    custom_filter.command(
        commands=["rmblocklist", "rmblacklist", "unblocklist", "unblacklist"]
    )
)
async def add_blocklist(client, message):
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

    if not (len(message.text.split()) >= 2):
        await message.reply("You need to specify the blocklist filter to remove")
        return

    blocklist_word = " ".join(message.text.split()[1:])

    BLOCKLIST_DATA = await get_blocklist(chat_id)
    if BLOCKLIST_DATA is None or len(BLOCKLIST_DATA) == 0:
        return

    BLOCKLIST_ITMES = []
    for blocklist_array in BLOCKLIST_DATA:
        BLOCKLIST_ITMES.append(blocklist_array["blocklist_text"])

    if blocklist_word in BLOCKLIST_ITMES:
        await rmblocklist_db(chat_id, blocklist_word)
        await message.reply(f"I will no longer blocklist '`{blocklist_word}`'.")
    else:
        await message.reply(
            f"`{blocklist_word}` hasn't been blocklisted, and so couldn't be stopped. Use the /blocklist command to see the current blocklist."
        )

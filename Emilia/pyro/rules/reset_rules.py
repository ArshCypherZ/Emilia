import html

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.helper.get_data import GetChat
from Emilia.mongo.rules_mongo import set_rules_db
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands=["resetrules", "clearrules"]))
@anonadmin_checker
async def reset_rules(client, message):
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

    if not await isUserCan(message, privileges="can_change_info"):
        return

    await set_rules_db(chat_id, None)
    await message.reply(
        f"Rules for {html.escape(chat_title)} were successfully cleared!"
    )
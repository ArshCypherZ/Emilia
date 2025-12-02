import html

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.helper.get_data import GetChat
from Emilia.mongo.rules_mongo import set_rules_db
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


@usage("/setrules [rules]")
@example("/setrules No promotion allowed.")
@description("Use this command to set rules for users in a group chat.")
@Client.on_message(custom_filter.command(commands="setrules"))
@anonadmin_checker
@logging
async def set_rules(client, message):
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

    command = message.text.split(" ")
    if len(command) == 1:
        await usage_string(message, set_rules)
        return

    get_rules = message.text.markdown[len(message.text.split()[0]) + 2 :]
    await set_rules_db(chat_id, get_rules)
    await message.reply(
        f"New rules for {html.escape(chat_title)} set successfully!", quote=True
    )
    return "NEW_RULES", None, None
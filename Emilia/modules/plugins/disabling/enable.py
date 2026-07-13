from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.custom_filter import DISABLE_COMMANDS
from Emilia.helper.chat_status import check_user
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.disable_mongo import enable_db
from Emilia.utils.decorators import *


@usage("/enable [command]")
@example("/enable notes")
@description("Use this command to enable already disabled command for users.")
@Client.on_message(custom_filter.command(commands="enable"))
async def enable(client, message):
    connected_chat = await connection(message)
    chat_id = connected_chat if connected_chat is not None else message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await check_user(
        message, privileges="can_change_info", chat_id=chat_id, pm_mode=True
    ):
        return

    if not (len(message.text.split()) >= 2):
        await usage_string(message, enable)
        return

    enable_args = message.text.split()[1:]

    ENABLE_ITMES = []
    INCORRECT_ITEMS = []

    for enable_arg in enable_args:
        if enable_arg not in DISABLE_COMMANDS:
            INCORRECT_ITEMS.append(enable_arg)
        else:
            ENABLE_ITMES.append(enable_arg)

    if len(INCORRECT_ITEMS) != 0:
        text = "Unknown command to enable:\n"
        for item in INCORRECT_ITEMS:
            text += f"- `{item}`\n"
        text += "Check /disableable!"
        await message.reply(text)
        return

    for items in ENABLE_ITMES:
        await enable_db(chat_id, items)

    text = "Enabled:\n"
    for enable_arg in ENABLE_ITMES:
        if len(ENABLE_ITMES) != 1:
            text += f"- `{enable_arg}`\n"
        else:
            text = f"Enabled `{enable_arg}`."

    await message.reply(text)

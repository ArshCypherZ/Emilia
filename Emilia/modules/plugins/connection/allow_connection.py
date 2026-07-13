from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.connection_mongo import allow_collection, get_allow_connection
from Emilia.utils.decorators import *

ALLOW_CONNECTION_TRUE = ["on", "yes", "true"]
ALLOW_CONNECTION_FALSE = ["off", "no", "false"]


@Client.on_message(custom_filter.command(commands=("allowconnection")))
async def allow_connection(client, message):

    connected_chat = await connection(message)
    if connected_chat is not None:
        chat_id = connected_chat
        chat_title = None
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserAdmin(message, chat_id=chat_id, pm_mode=True):
        return

    if len(message.text.split()) >= 2:
        get_arg = message.text.split()[1]

        if get_arg in ALLOW_CONNECTION_TRUE:
            await allow_collection(chat_id, chat_title, allow_collection=True)
            await message.reply("Allowed all users in connection.")
        elif get_arg in ALLOW_CONNECTION_FALSE:
            await allow_collection(chat_id, chat_title, allow_collection=False)
            await message.reply("Disallowed all users in connection.")
        else:
            await message.reply(f"I got {get_arg}, need on/off/yes/no/true/false.")
    else:
        if await get_allow_connection(chat_id):
            t_message = "Users are allowed to connect chat to PM."
        else:
            t_message = "Users are not allowed to connect chat to PM."

        await message.reply(t_message)

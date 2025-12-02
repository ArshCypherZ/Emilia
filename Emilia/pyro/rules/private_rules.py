import html

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.helper.get_data import GetChat
from Emilia.mongo.rules_mongo import get_private_note, set_private_rule
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *

PRIVATE_RULES_TRUE = ["yes", "on"]
PRIVATE_RULES_FALSE = ["no", "off"]


@Client.on_message(custom_filter.command(commands="privaterules"))
@anonadmin_checker
async def private_rules(client, message):
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
    if not (len(command) == 1):
        args = command[1]

        if args in PRIVATE_RULES_TRUE:
            await message.reply(
                "Use of /rules will send the rules to the user's PM.", quote=True
            )
            await set_private_rule(chat_id, True)

        elif args in PRIVATE_RULES_FALSE:
            await message.reply(
                f"All /rules commands will send the rules to {html.escape(chat_title)}.",
                quote=True,
            )
            await set_private_rule(chat_id, False)

        else:
            await message.reply(
                "I only understand the following: yes/no/on/off", quote=True
            )
    else:
        if await get_private_note(chat_id):
            await message.reply("Use of /rules will send the rules to the user's PM.")
        else:
            await message.reply(
                f"All /rules commands will send the rules to {html.escape(chat_title)}."
            )
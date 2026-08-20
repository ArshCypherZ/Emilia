from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.rules_mongo import get_rules_button, set_rule_button
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands="setrulesbutton"))
@anonadmin_checker
async def set_rules(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserCan(message, privileges="can_change_info"):
        return

    command = message.text.split(" ")
    if len(command) == 1:
        current_rules_button = await get_rules_button(chat_id)
        return await message.reply(
            f"The rules button will be called:\n `{current_rules_button}`\n\nTo change the button name, try this command again followed by the new name",
        )

    rules_button = " ".join(command[1:])

    await set_rule_button(chat_id, rules_button)
    await message.reply("Updated the rules button name!")

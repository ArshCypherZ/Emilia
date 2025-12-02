import html

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.helper.get_data import GetChat
from Emilia.mongo.warnings_mongo import set_warn_limit_db
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


@usage("/warnlimit [integer]")
@example("/warnlimit 4")
@description(
    "Use this command to set on how many warns a user should be allowed to receive before acted upon."
)
@Client.on_message(custom_filter.command(commands=["warnlimit", "setwarnlimit"]))
@anonadmin_checker
async def setWarnLimit(client, message):
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

    if not len(message.text.split()) >= 2:
        await usage_string(message, setWarnLimit)
        return

    warn_limit_arg = message.text.split()[1]
    if not warn_limit_arg.isdigit():
        return await message.reply(
            f"{warn_limit_arg} is not a valid integer.", quote=True
        )

    if int(warn_limit_arg) > 50:
        return await message.reply("The maximum warning limit is 50.", quote=True)

    if int(warn_limit_arg) == 0:
        return await message.reply(
            "The warning limit has to be set to a number bigger than 0.", quote=True
        )

    await message.reply(
        f"Warn limit settings for {html.escape(chat_title)} has been updated to {warn_limit_arg}.",
        quote=True,
    )
    await set_warn_limit_db(chat_id, int(warn_limit_arg))
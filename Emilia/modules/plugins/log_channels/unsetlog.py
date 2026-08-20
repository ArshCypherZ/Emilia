from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.log_channels_mongo import unset_log_db
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands=("unsetlog")))
@anonadmin_checker
async def unset_log(client, message):

    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserCan(message, chat_id=chat_id, privileges="can_change_info"):
        return

    await unset_log_db(chat_id)

    await message.reply(
        "Successfully unset log channel. Admin actions will no longer be logged.",
    )

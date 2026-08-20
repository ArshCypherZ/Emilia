from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import check_bot, check_user
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.disable_mongo import disabledel_db
from Emilia.utils.decorators import *

DISABLEDEL_TRUE = ["on", "yes"]
DISABLEDEL_FALSE = ["off", "no"]


@usage("/disabledel [on/off | yes/no]")
@example("/disabledel on")
@description(
    "By turning it on, bot will automatically delete the commands that are disabled in a chat for non-admins."
)
@Client.on_message(custom_filter.command(commands="disabledel"))
async def disabledel(client, message):
    connected_chat = await connection(message)
    chat_id = connected_chat if connected_chat is not None else message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await check_bot(message, privileges="can_delete_messages", chat_id=chat_id):
        return

    if not await check_user(
        message, privileges="can_change_info", chat_id=chat_id, pm_mode=True
    ):
        return

    if len(message.text.split()) >= 2:
        arg = message.text.split()[1]
        if arg in DISABLEDEL_TRUE:
            await disabledel_db(chat_id, True)
            await message.reply("Disabled messages will now be deleted.")

        elif arg in DISABLEDEL_FALSE:
            await disabledel_db(chat_id, False)
            await message.reply("Disabled messages will no longer be deleted.")

        else:
            await message.reply(strings.YES_NO_ON_OFF)
    else:
        await usage_string(message, disabledel)
        return

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isBotCan, isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.blocklists_mongo import (
    blocklistMessageDelete,
    getblocklistMessageDelete,
)
from Emilia.utils.decorators import *

BLOCKLIST_DELETE_TRUE = ["on", "yes"]
BLOCKLIST_DELETE_FALSE = ["off", "no"]


@usage("/blocklistdelete [on/off]")
@description(
    "Use this command to enable/disable blocklist deletes in your chat. When enabled, I will delete all blocklisted messages."
)
@example("/blocklistdelete on")
@Client.on_message(custom_filter.command(commands="blocklistdelete"))
@anonadmin_checker
async def blocklistdelete(client, message):
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

    if not await isBotCan(message, chat_id=chat_id, privileges="can_delete_messages"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]

        if args in BLOCKLIST_DELETE_TRUE:
            await blocklistMessageDelete(chat_id, True)
            await message.reply(
                "Blocklist deletes have now been **enabled**. I will be deleting all blocklisted messages from now on."
            )

        elif args in BLOCKLIST_DELETE_FALSE:
            await blocklistMessageDelete(chat_id, False)
            await message.reply(
                "Blocklist deletes have now been **disabled**. I will no longer be deleting any blocklisted messages. However, I will still take actions; such as warnings, or bans."
            )

        else:
            await usage_string(message, blocklistdelete)
    else:
        if getblocklistMessageDelete:
            await message.reply("I am currently deleting all blocklisted messages.")
        else:
            await message.reply("I am currently **not** deleting blocklisted messages.")

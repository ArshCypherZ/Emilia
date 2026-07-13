from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.blocklists_mongo import getblocklistmode, setblocklistreason_db
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands="setblocklistreason"))
@anonadmin_checker
async def setblocklistreason(client, message):
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

    blocklist_mode, blocklist_time, blocklist_default_reason = await getblocklistmode(
        chat_id
    )

    if len(message.text.split()) >= 2:
        set_reason = message.text.markdown[len(message.text.split()[0]) + 2 :]
        await setblocklistreason_db(chat_id, set_reason)
        await message.reply(
            f"The default blocklist reason has been set to:\n{set_reason}"
        )
    else:
        if blocklist_default_reason is None:
            await message.reply(
                (
                    "No default blocklist message has been set. I will reply with:\n"
                    "Automated blocklist action, due to a match on: TriggeredFilter"
                )
            )
        else:
            await message.reply(
                f"The current blocklist reason is: \n{blocklist_default_reason}"
            )

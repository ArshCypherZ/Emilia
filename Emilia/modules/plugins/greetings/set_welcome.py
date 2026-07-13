from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.helper.welcome_helper.get_welcome_message import GetWelcomeMessage
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.welcome_mongo import SetWelcome
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands="setwelcome"))
@anonadmin_checker
async def set_welcome(client, message):
    if await connection(message) is not None:
        ChatID = await connection(message)
    else:
        ChatID = message.chat.id

    if (
        not str(ChatID).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserCan(message, chat_id=ChatID, privileges="can_change_info"):
        return

    if not message.reply_to_message or len(message.text.split()) > 1:
        return await message.reply("You need to give the welcome message some content!")

    CONTENT, TEXT, DATATYPE = GetWelcomeMessage(message)
    await SetWelcome(ChatID, CONTENT, TEXT, DATATYPE)
    await message.reply("The new welcome message has been saved!")

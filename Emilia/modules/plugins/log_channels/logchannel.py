import html

from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.log_channels_mongo import get_set_channel
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands=("logchannel")))
@anonadmin_checker
async def logcategories(client, message):

    connected_chat = await connection(message)
    chat_id = connected_chat if connected_chat is not None else message.chat.id

    if not await isUserAdmin(message, chat_id=chat_id, pm_mode=True):
        return

    if await get_set_channel(chat_id) is not None:
        channel_title = await get_set_channel(chat_id)
        await message.reply(
            f"I am currently logging admin actions in '{html.escape(channel_title)}'.",
            )
    else:
        await message.reply(
            "There are no log channels assigned to this chat."
        )

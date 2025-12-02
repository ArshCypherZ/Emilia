import html

from pyrogram import Client
from pyrogram.enums import ChatType

from Emilia import custom_filter
from Emilia.helper.get_data import GetChat
from Emilia.mongo.connection_mongo import GetConnectedChat, reconnectChat
from Emilia.pyro.connection.connection import connection


@Client.on_message(custom_filter.command(commands=("reconnect")))
async def reconnectC(client, message):
    user_id = message.from_user.id
    if not (message.chat.type == ChatType.PRIVATE):
        await message.reply("You need to be in PM to use this.")
        return
    if await GetConnectedChat(user_id) is not None:
        chat_id = await GetConnectedChat(user_id)
        chat_title = await GetChat(chat_id, client)
        chat_title = html.escape(chat_title)
        if await connection(message) is None:
            await reconnectChat(user_id)
            await message.reply(f"You're now reconnected to {chat_title}.", quote=True)
    else:
        await message.reply(
            "You haven't made a connection to any chats yet.", quote=True
        )

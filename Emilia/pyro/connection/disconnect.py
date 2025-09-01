from pyrogram import Client
from pyrogram.enums import ChatType

from Emilia import custom_filter
from Emilia.mongo.connection_mongo import disconnectChat
from Emilia.pyro.connection.connection import connection


@Client.on_message(custom_filter.command(commands=("disconnect")))
async def diconnectChat(client, message):
    user_id = message.from_user.id
    if not (message.chat.type == ChatType.PRIVATE):
        await message.reply("You need to be in PM to use this.")
        return
    if await connection(message) is not None:
        await disconnectChat(user_id)
        await message.reply("Disconnected from chat.", quote=True)
    else:
        await message.reply("You aren't connected to any chats :)", quote=True)

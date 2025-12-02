from pyrogram import Client
from pyrogram.enums import ChatType

from Emilia import custom_filter
from Emilia.helper.chat_status import *
from Emilia.mongo.connection_mongo import (
    GetConnectedChat,
    get_allow_connection,
    isChatConnected,
)
from Emilia.pyro.connection.connect import connect_button


@Client.on_message(custom_filter.command(commands=("connection")))
async def ConnectionChat(client, message):
    if not (message.chat.type == ChatType.PRIVATE):
        await message.reply("You need to be in PM to use this.")
        return
    if await connection(message) is not None:
        chat_id = await connection(message)
        await connect_button(message, chat_id)
    else:
        await message.reply("You aren't connected to any chat :)", quote=True)


async def connection(message):
    try:
        if not message.chat.type == ChatType.PRIVATE:
            return None
    except AttributeError:
        if not message.is_private:  # for telethon
            return None

    try:
        user_id = message.from_user.id
    except AttributeError:
        user_id = message.sender_id

    connected_chat = await GetConnectedChat(user_id)
    if await isChatConnected(user_id):
        if connected_chat is not None:
            if await get_allow_connection(connected_chat):
                bot_admin = False
                try:
                    bot_admin = await isUserBanned(connected_chat, user_id, message._client)
                except BaseException:
                    return None

                if not bot_admin:
                    return connected_chat
                else:
                    await message.reply(f"You are banned user of {message.chat.title}")
                    return None

            else:
                if await isUserAdmin(message, chat_id=connected_chat, user_id=user_id, pm_mode=True):
                    return connected_chat
                return None
        else:
            return None
    else:
        return None

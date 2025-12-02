import html

from pyrogram import Client
from pyrogram.enums import ChatType

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAdmins
from Emilia.helper.get_data import GetChat
from Emilia.helper.note_helper.get_note_message import GetNoteMessage
from Emilia.mongo.notes_mongo import SaveNote
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


@usage("/save [trigger/reply to content] or [trigger content]")
@example("/save meow nya")
@description("Bot will reply with content when someone mentions #trigger in a chat")
@Client.on_message(custom_filter.command(commands="save"))
async def saveNote(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
        chat_title = html.escape(chat_title)
    else:
        chat_id = message.chat.id
        chat_title = html.escape(message.chat.title)

        if message.chat.type == ChatType.PRIVATE:
            chat_title = "local"

    if not await CheckAdmins(message, silent=True):
        return await message.reply("You need to be an admin to do this.", quote=True)

    command = message.text.split(" ")
    if message.reply_to_message and len(command) == 1:
        await usage_string(message, saveNote)
        return

    if not message.reply_to_message and len(command) == 2:
        await usage_string(message, saveNote)
        return

    try:
        NoteName = command[1]
    except IndexError:
        await usage_string(message, saveNote)
        return

    await message.reply(f"I've saved note `{NoteName}` in {chat_title}.", quote=True)
    Content, Text, DataType = GetNoteMessage(message)
    await SaveNote(chat_id, NoteName, Content, Text, DataType)

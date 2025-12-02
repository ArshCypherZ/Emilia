import html

from pyrogram import Client
from pyrogram.enums import ChatType

from Emilia import custom_filter
from Emilia.helper.disable import disable
from Emilia.helper.get_data import GetChat
from Emilia.mongo.notes_mongo import NoteList
from Emilia.pyro.connection.connection import connection


@Client.on_message(custom_filter.command(commands=(["notes", "saved"]), disable=True))
@disable
async def Notes(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

        if message.chat.type == ChatType.PRIVATE:
            chat_title = "local"

    Notes_list = await NoteList(chat_id)

    NoteHeader = f"List of notes  in {html.escape(chat_title)}:\n"
    if len(Notes_list) != 0:
        for notes in Notes_list:
            NoteName = f" • `{notes}`\n"
            NoteHeader += NoteName
        await message.reply(
            f"{NoteHeader}\nYou can retrieve these notes by using `/get notename`, or `#notename`",
            quote=True,
        )

    else:
        await message.reply(f"No notes in {chat_title}.", quote=True)

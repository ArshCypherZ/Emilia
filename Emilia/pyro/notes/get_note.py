from pyrogram import Client, filters
from pyrogram.types import Message

from Emilia import custom_filter
from Emilia.helper.note_helper.note_misc_helper import privateNote_and_admin_checker
from Emilia.helper.note_helper.note_send_message import exceNoteMessageSender
from Emilia.mongo.notes_mongo import GetNote, is_pnote_on, isNoteExist
from Emilia.pyro.connection.connection import connection
from Emilia.pyro.notes.private_notes import PrivateNoteButton


@Client.on_message(custom_filter.command(commands="get"))
async def getNote(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id
    if not len(message.text.split()) >= 2:
        return await message.reply("You need to give the note a name!")

    note_name = message.text.split()[1]
    if not (await isNoteExist(chat_id, note_name)):
        return await message.reply("Note not found!")

    await send_note(client, message, note_name)


@Client.on_message(filters.regex(pattern=(r"^#[^\s]+")))
async def regex_get_note(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id
    if message.from_user and message.text is not None:
        note_name = message.text.split()[0].replace("#", "")
        if await isNoteExist(chat_id, note_name):
            await send_note(client, message, note_name)


async def send_note(client, message: Message, note_name: str):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id
    content, text, data_type = await GetNote(chat_id, note_name)
    privateNote, allow = await privateNote_and_admin_checker(message, text)

    if allow:
        if privateNote is None:
            if await is_pnote_on(chat_id):
                await PrivateNoteButton(message, chat_id, note_name)
            else:
                await exceNoteMessageSender(client, message, note_name)

        elif privateNote is not None:
            if await is_pnote_on(chat_id):
                if privateNote:
                    await PrivateNoteButton(message, chat_id, note_name)
                else:
                    await exceNoteMessageSender(client, message, note_name)
            else:
                if privateNote:
                    await PrivateNoteButton(message, chat_id, note_name)
                else:
                    await exceNoteMessageSender(client, message, note_name)

import html

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAdmins, isUserCreator
from Emilia.helper.get_data import GetChat
from Emilia.mongo.notes_mongo import ClearAllNotes, ClearNote, NoteList, isNoteExist
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


@usage("/clear [note name]")
@example("/clear meow")
@description("Use this command to stop the active note in chat.")
@Client.on_message(custom_filter.command(commands="clear"))
async def Clear_Note(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if not await CheckAdmins(message):
        return

    command = message.text.split(" ")
    if len(command) == 1:
        await usage_string(message, Clear_Note)
        return

    note_name = command[1].lower()

    if await isNoteExist(chat_id, note_name):
        await message.reply(f"I've removed the note `{note_name}`!.", quote=True)
        await ClearNote(chat_id, note_name)

    else:
        await message.reply("You haven't saved a note with this name yet!", quote=True)


@Client.on_message(custom_filter.command(commands="clearall"))
@anonadmin_checker
async def ClearAll_Note(client, message):
    owner_id = message.from_user.id
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
        chat_title = html.escape(chat_title)
    else:
        chat_id = message.chat.id
        chat_title = html.escape(message.chat.title)
        if message.chat.type == ChatType.PRIVATE:
            chat_title = "local"

    if not await isUserCreator(message):
        return await message.reply(
            f"You need to be the chat owner of {chat_title} to do this.", quote=True
        )

    note_list = await NoteList(chat_id)
    if note_list == 0:
        await message.reply(f"No notes in {chat_title}", quote=True)

    keyboard = InlineKeyboardMarkup(
        [
            InlineKeyboardButton(
                text="Delete all notes",
                callback_data=f"clearallnotes_clear_{owner_id}_{chat_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="Cancel", callback_data=f"clearallnotes_cancel_{owner_id}"
            )
        ],
    )

    await message.reply(
        f"Are you sure you want to clear **ALL** notes in {chat_title}? This action is irreversible.",
        reply_markup=keyboard,
        quote=True,
    )


@Client.on_callback_query(
    filters.create(lambda _, __, query: "clearallnotes_" in query.data)
)
async def ClearAllCallback(client: Client, callback_query: CallbackQuery):
    query_data = callback_query.data.split("_")[1]
    owner_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    if owner_id == user_id:
        if query_data == "clear":
            chat_id = int(callback_query.data.split("_")[3])
            await ClearAllNotes(chat_id)
            await callback_query.message.reply("Deleted all chat notes.")
            await callback_query.message.delete()
            return

        elif query_data == "cancel":
            await callback_query.message.reply("Cancelled.")
            await callback_query.message.delete()
    else:
        await callback_query.answer("Only owner can execute this command!")

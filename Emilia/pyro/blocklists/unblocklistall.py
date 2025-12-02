import html

from pyrogram import Client, enums, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCreator
from Emilia.helper.get_data import GetChat
from Emilia.mongo.blocklists_mongo import get_blocklist, unblocklistall_db
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands=["unblocklistall", "unblacklistall"]))
@anonadmin_checker
async def removeblocklistall(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserCreator(message):
        return

    BLOCKLIST_DATA = await get_blocklist(chat_id)
    if BLOCKLIST_DATA is None or len(BLOCKLIST_DATA) == 0:
        await message.reply(
            f"No blocklist filters active in {html.escape(chat_title)}!"
        )
        return

    button = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="Delete blocklist", callback_data="blocklist_confirm"
                )
            ],
            [InlineKeyboardButton(text="Cancel", callback_data="blocklist_cancel")],
        ]
    )

    await message.reply(
        text=f"Are you sure you would like to stop **ALL** of the blocklist in {html.escape(chat_title)}? This action cannot be undone.",
        reply_markup=button,
        quote=True,
    )


@Client.on_callback_query(
    filters.create(lambda _, __, query: "blocklist_" in query.data)
)
async def removeblocklistall_callback(client: Client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id

    query_data = callback_query.data.split("_")[1]
    if not await isUserCreator(
        callback_query,
        chat_id=callback_query.message.chat.id,
        user_id=callback_query.from_user.id,
    ):
        await callback_query.answer(text="You're not owner of this chat.")
        return

    if query_data == "confirm":
        await unblocklistall_db(chat_id)
        await callback_query.message.reply(text="Deleted chat blocklist.")
        await callback_query.message.delete()
    elif query_data == "cancel":
        await callback_query.message.reply(
            text="Removal of the blocklist has been cancelled."
        )
        await callback_query.message.delete()

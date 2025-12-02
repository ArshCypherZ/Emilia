import html

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCreator
from Emilia.helper.get_data import GetChat
from Emilia.mongo.filters_mongo import stop_all_db
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command("stopall"))
@anonadmin_checker
async def stopall(_, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title
    
    if message.chat.type == ChatType.PRIVATE:
        chat_title = "local"
    if not await isUserCreator(message):
        await message.reply("You're not the creator of this chat.")
        return

    KEYBOARD = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="Delete all filters", callback_data="filters_stopall"
                )
            ],
            [InlineKeyboardButton(text="Cancel", callback_data="filters_cancel")],
        ]
    )

    await message.reply(
        text=(
            f"Are you sure you want to stop **ALL** filters in {html.escape(chat_title)}? This action is irreversible."
        ),
        reply_markup=KEYBOARD,
    )


@Client.on_callback_query(filters.create(lambda _, __, query: "filters_" in query.data))
async def stopall_callback(client: Client, callback_query: CallbackQuery):
    message = callback_query.message
    
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id
    
    query_data = callback_query.data.split("_")[1]

    if not await isUserCreator(
        message,
        chat_id=chat_id,
        user_id=callback_query.from_user.id,
    ):
        await callback_query.answer(text="You're not owner of this chat.", show_alert=True)
        return

    if query_data == "stopall":
        await stop_all_db(chat_id)
        await message.edit_text(text="I've deleted all chat filters.")

    elif query_data == "cancel":
        await message.edit_text(text="Cancelled.")

import html

from pyrogram import Client, enums, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCreator
from Emilia.helper.get_data import GetChat
from Emilia.mongo.warnings_mongo import reset_all_warns_db
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands="resetallwarns"))
@anonadmin_checker
async def reset_all_warns(client, message, do=False):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title
    if do:
        return chat_id
    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserCreator(message):
        return await message.reply(
            f"You need to be the chat owner of {html.escape(chat_title)} to do this."
        )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="Reset all warnings", callback_data="resetwarns_confirm"
                )
            ],
            [InlineKeyboardButton(text="Cancel", callback_data="resetwarns_cancel")],
        ]
    )
    await message.reply(
        text=(
            f"Are you sure you want to reset **ALL** warnings in {html.escape(chat_title)}? This action cannot be undone."
        ),
        reply_markup=buttons,
        quote=True,
    )


@Client.on_callback_query(
    filters.create(lambda _, __, query: "resetwarns_" in query.data)
)
async def resetwarns_callback(client: Client, callback_query: CallbackQuery):
    query_data = callback_query.data.split("_")[1]
    chat_id = await reset_all_warns(client, callback_query.message, do=True)
    if not await isUserCreator(
        callback_query,
        chat_id=chat_id,
        user_id=callback_query.from_user.id,
    ):
        return await callback_query.answer(text="You're not the owner of this chat.")

    if query_data == "confirm":
        await reset_all_warns_db(chat_id)
        await callback_query.message.reply(text="Reset all chat warnings.")
        await callback_query.message.delete()

    else:
        await callback_query.message.reply(
            text="Resetting of all warnings has been cancelled."
        )
        await callback_query.message.delete()
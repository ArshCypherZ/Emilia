from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAllAdminsStuffs, isUserCan
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands="unpinall"))
@anonadmin_checker
async def unpinall(client, message):
    if not await CheckAllAdminsStuffs(message, privileges="can_pin_messages"):
        return

    button = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text="Yes", callback_data="unpin_yes"),
                InlineKeyboardButton(text="No", callback_data="unpin_no"),
            ]
        ]
    )

    await message.reply(
        text="Are you sure you want to unpin all messages?", reply_markup=button
    )


@Client.on_callback_query(filters.create(lambda _, __, query: "unpin_" in query.data))
async def unpinall_callback(client: Client, callback_query: CallbackQuery):
    query_data = callback_query.data.split("_")[1]
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id
    if not await isUserCan(
        callback_query,
        user_id=user_id,
        chat_id=chat_id,
        privileges="can_pin_messages",
        silent=True,
    ):
        return await callback_query.answer(
            text="you don't have permission to use this button."
        )

    if query_data == "yes":
        await client.unpin_all_chat_messages(chat_id=chat_id)
        await callback_query.message.reply("All pinned messages have been unpinned.")
        await callback_query.message.delete()

    elif query_data == "no":
        await callback_query.message.reply(
            "Unpin of all pinned messages has been cancelled."
        )
        await callback_query.message.delete()

from pyrogram.types import ChatPermissions, InlineKeyboardMarkup

from Emilia import pgram
from Emilia.helper.button_gen import button_markdown_parser
from Emilia.mongo.welcome_mongo import (
    AppendVerifiedUsers,
    DeleteUsercaptchaData,
    GetWelcome,
    isWelcome,
)


async def passedAction(chat_id: int, user_id: int, message_id: int):
    await pgram.restrict_chat_member(
        chat_id,
        user_id,
        ChatPermissions(can_send_messages=True, can_add_web_page_previews=True),
    )

    if await isWelcome(chat_id):
        Content, Text, DataType = await GetWelcome(chat_id)
        Text, buttons = button_markdown_parser(Text)
        reply_markup = None
        if len(buttons) > 0:
            reply_markup = InlineKeyboardMarkup(buttons)
    else:
        reply_markup = None

    await pgram.edit_message_reply_markup(
        chat_id=chat_id, message_id=message_id, reply_markup=reply_markup
    )

    await DeleteUsercaptchaData(chat_id, user_id)
    await AppendVerifiedUsers(chat_id, user_id)


async def failedAction(message, user_id: int, chat_id: int, message_id: int):
    await pgram.ban_chat_member(chat_id=chat_id, user_id=user_id)

    await pgram.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(f"User {message.from_user.mention} has failed the CAPTCHAs!"),
    )
    await pgram.unban_chat_member(chat_id=chat_id, user_id=user_id)

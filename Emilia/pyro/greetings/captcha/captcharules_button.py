import html
from typing import Union

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


from Emilia.helper.get_data import GetChat
from Emilia.mongo.rules_mongo import get_rules
from Emilia.pyro.greetings.utils.actions import passedAction


async def ruleCaptchaButton(
    client, message: Union[Message, CallbackQuery], chat_id: int, message_id: int
) -> bool:
    user_id = message.from_user.id
    KEYBOARD = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="I have read and accept the rules",
                    callback_data=f"captcharule_{chat_id}_{message_id}",
                )
            ]
        ]
    )

    RULES = await get_rules(chat_id=chat_id)
    if RULES is None:
        chat_title = await GetChat(chat_id, client)
        RULES = f"{html.escape(chat_title)} haven't any rules yet."

    await client.send_message(
        chat_id=user_id,
        text=RULES,
        reply_markup=KEYBOARD,
        reply_to_message_id=message.id,
    )


@Client.on_callback_query(
    filters.create(lambda _, __, query: "captcharule_" in query.data)
)
async def captchaRules(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = int(callback_query.data.split("_")[1])
    message_id = int(callback_query.data.split("_")[2])

    await callback_query.answer(text=("You have passed the CAPTCHA."))

    str_chat_id = str(chat_id).replace("-100", "")
    passedButton = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="Go Back to the chat",
                    url=f"http://t.me/c/{str_chat_id}/{message_id}",
                )
            ]
        ]
    )

    await callback_query.edit_message_text(
        text="You have passed the CAPTCHA.", reply_markup=passedButton
    )

    await passedAction(client, chat_id=chat_id, user_id=user_id, message_id=message_id)

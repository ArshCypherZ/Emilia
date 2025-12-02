from Emilia import BOT_USERNAME
from Emilia.helper.note_helper.note_misc_helper import preview_text_replace
from Emilia.helper.welcome_helper.welcome_fillings import Welcomefillings
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


async def SendWelcomeMessage(
    client, message, NewUserJson, content, text, data_type, reply_markup
):
    chat_id = message.chat.id
    text = await Welcomefillings(message, text, NewUserJson)

    preview, text = await preview_text_replace(text)

    if "{rules}" in text:
        text = text.replace("{rules}", "")
        button = [
            [
                InlineKeyboardButton(
                    text="Rules",
                    url=f"http://t.me/{BOT_USERNAME}?start=rules_{chat_id}",
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(button)

    SentMessage = None

    if data_type == 1:
        SentMessage = await client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            disable_web_page_preview=preview,
        )

    elif data_type == 2:
        SentMessage = await client.send_sticker(
            chat_id=chat_id,
            sticker=content,
            reply_markup=reply_markup,
        )

    elif data_type == 3:
        SentMessage = await client.send_animation(
            chat_id=chat_id,
            animation=content,
            caption=text,
            reply_markup=reply_markup,
        )

    elif data_type == 4:
        SentMessage = await client.send_document(
            chat_id=chat_id,
            document=content,
            caption=text,
            reply_markup=reply_markup,
        )

    elif data_type == 5:
        SentMessage = await client.send_photo(
            chat_id=chat_id,
            photo=content,
            caption=text,
            reply_markup=reply_markup,
        )

    elif data_type == 6:
        SentMessage = await client.send_audio(
            chat_id=chat_id,
            audio=content,
            caption=text,
            reply_markup=reply_markup,
        )
    elif data_type == 7:
        SentMessage = await client.send_voice(
            chat_id=chat_id,
            voice=content,
            caption=text,
            reply_markup=reply_markup,
        )

    elif data_type == 8:
        SentMessage = await client.send_video(
            chat_id=chat_id,
            video=content,
            caption=text,
            reply_markup=reply_markup,
        )

    elif data_type == 9:
        SentMessage = await client.send_video_note(
            chat_id=chat_id,
            video_note=content,
            reply_markup=reply_markup,
        )

    return SentMessage

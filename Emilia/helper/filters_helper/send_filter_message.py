from asyncio import sleep
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.errors import FloodWait

from Emilia import BOT_USERNAME
from Emilia.helper.button_gen import button_markdown_parser
from Emilia.helper.note_helper.note_fillings import NoteFillings
from Emilia.helper.note_helper.note_misc_helper import preview_text_replace
from Emilia.utils.decorators import rate_limit

@rate_limit((10, 5))
async def SendFilterMessage(
    client, message: Message, filter_name: str, content: str, text: str, data_type: int, reply_to_sender: bool = False
):
    chat_id = message.chat.id
    message_id = message.reply_to_message.id if reply_to_sender and message.reply_to_message else message.id
    text, buttons = button_markdown_parser(text)

    text = await NoteFillings(message, text)
    preview, text = await preview_text_replace(text)

    reply_markup = None
    if len(buttons) > 0:
        reply_markup = InlineKeyboardMarkup(buttons)
    elif "{rules}" in text:
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
    else:
        reply_markup = None

    if data_type == 1:
        try:
            await client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
            disable_web_page_preview=preview,
        )
        except FloodWait as e:
            await sleep(e.value)

    elif data_type == 2:
        await client.send_sticker(
            chat_id=chat_id,
            sticker=content,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
        )

    elif data_type == 3:
        await client.send_animation(
            chat_id=chat_id,
            caption=text,
            animation=content,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
        )

    elif data_type == 4:
        await client.send_document(
            chat_id=chat_id,
            document=content,
            caption=text,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
        )

    elif data_type == 5:
        await client.send_photo(
            chat_id=chat_id,
            photo=content,
            caption=text,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
        )

    elif data_type == 6:
        await client.send_audio(
            chat_id=chat_id,
            audio=content,
            caption=text,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
        )

    elif data_type == 7:
        await client.send_voice(
            chat_id=chat_id,
            voice=content,
            caption=text,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
        )

    elif data_type == 8:
        await client.send_video(
            chat_id=chat_id,
            video=content,
            caption=text,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
        )

    elif data_type == 9:
        await client.send_video_note(
            chat_id=chat_id,
            video_note=content,
            reply_markup=reply_markup,
            reply_to_message_id=message_id,
        )

import html

from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import Emilia.strings as strings
from Emilia import BOT_USERNAME, custom_filter
from Emilia.helper.button_gen import button_markdown_parser
from Emilia.helper.disable import disable
from Emilia.helper.get_data import GetChat
from Emilia.helper.note_helper.note_fillings import NoteFillings as rules_filler
from Emilia.mongo.rules_mongo import get_private_note, get_rules, get_rules_button
from Emilia.pyro.connection.connection import connection


@Client.on_message(custom_filter.command(commands="rules", disable=True))
@disable
async def rules(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if not str(chat_id).startswith("-100"):
        return await message.reply(strings.is_pvt)

    rules_text = await get_rules(chat_id)
    if rules_text is None:
        return await message.reply(
            "This chat doesn't seem to have had any rules set yet... I wouldn't take that as an invitation though.",
            quote=True,
        )

    if not (await get_private_note(chat_id)):
        rules_text, buttons = button_markdown_parser(rules_text)
        button_markdown = None
        if len(buttons) > 0:
            button_markdown = InlineKeyboardMarkup(buttons)

        rules_text = await rules_filler(message, rules_text)

        await message.reply(
            (f"The rules for `{html.escape(chat_title)}` are:\n\n" f"{rules_text}"),
            reply_markup=button_markdown,
            quote=True,
        )
    else:
        button_text = await get_rules_button(chat_id)
        button = [
            [
                InlineKeyboardButton(
                    text=button_text,
                    url=f"http://t.me/{BOT_USERNAME}?start=rules_{chat_id}",
                )
            ]
        ]

        await message.reply(
            "Click on the button to see the chat rules!",
            reply_markup=InlineKeyboardMarkup(button),
            quote=True,
        )


async def rulesRedirect(message, client):
    chat_id = int(message.text.split()[1].split("_")[1])
    chat_title = await GetChat(chat_id, client)
    rules_text = await get_rules(chat_id)

    rules_text, buttons = button_markdown_parser(rules_text)
    button_markdown = None
    if len(buttons) > 0:
        button_markdown = InlineKeyboardMarkup(buttons)

    rules_text = await rules_filler(message, rules_text)
    await message.reply(
        (f"The rules for `{html.escape(chat_title)}` are:\n\n" f"{rules_text}"),
        reply_markup=button_markdown,
        quote=True,
    )
from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAllAdminsStuffs
from Emilia.utils.decorators import *
from Emilia.utils.decorators import logging


@Client.on_message(custom_filter.command(commands="pin"))
@anonadmin_checker
@logging
async def pin(client, message):
    chat_id = message.chat.id
    if not await CheckAllAdminsStuffs(message, privileges="can_pin_messages"):
        return

    if not message.reply_to_message:
        return await message.reply("You need to reply to a message to pin it!")

    pin_message_id = message.reply_to_message.id
    message_link = (
        f"http://t.me/c/{str(chat_id).replace(str(-100), '')}/{pin_message_id}"
    )

    if len(message.text.split()) == 1 or (
        len(message.text.split()) >= 2
        and message.text.split()[1] in ("silent", "quiet")
    ):
        await message.reply(f"I have pinned [this message]({message_link}).")
        await client.pin_chat_message(
            chat_id=chat_id, message_id=pin_message_id, disable_notification=True
        )
        return "PIN", None, None

    elif len(message.text.split()) >= 2 and message.text.split()[1] in (
        "loud",
        "notify",
        "violent",
    ):
        await message.reply(
            f"I have pinned [this message]({message_link}) and notified all members."
        )
        await client.pin_chat_message(
            chat_id=chat_id, message_id=pin_message_id, disable_notification=False
        )
        return "LOUD_PIN", None, None

    elif len(message.text.split()) >= 2:
        await message.reply(
            f"'{message.text.split()[1]}' was not recognised as a valid pin option. Please use one of: loud/violent/notify/silent/quiet"
        )

from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAllAdminsStuffs
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands="unpin"))
@anonadmin_checker
async def unpin(client, message):
    chat_id = message.chat.id
    if not await CheckAllAdminsStuffs(message, privileges="can_pin_messages"):
        return

    if message.reply_to_message:
        pinned_message_id = message.reply_to_message.id
        message_link = (
            f"http://t.me/c/{str(chat_id).replace(str(-100), '')}/{pinned_message_id}"
        )
        await message.reply(f"Unpinned [this message]({message_link}).")
        await client.unpin_chat_message(chat_id=chat_id, message_id=pinned_message_id)

    else:
        chat_data = await client.get_chat(chat_id=chat_id)
        if chat_data.pinned_message:
            pinned_message_id = chat_data.pinned_message.id
            await message.reply(f"Unpinned the last pinned message.")
            await client.unpin_chat_message(
                chat_id=chat_id, message_id=pinned_message_id
            )
        else:
            await message.reply(
                "There are no pinned messages. What are you trying to unpin?"
            )

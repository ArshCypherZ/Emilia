from pyrogram import Client

from Emilia import custom_filter
from Emilia.custom_filter import DISABLE_COMMANDS
from Emilia.helper.chat_status import isUserAdmin


@Client.on_message(custom_filter.command(commands="disableable"))
async def disable_list(client, message):
    if not await isUserAdmin(message):
        return

    text_header = "The following commands can be disabled:\n"
    for diable in DISABLE_COMMANDS:
        text_header += f"- `{diable}`\n"

    await message.reply(text_header)

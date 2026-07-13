from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin


@Client.on_message(custom_filter.command(commands="pininfo"))
async def pininfo(client, message):
    if not await isUserAdmin(message):
        return

    await message.reply(
        "`/antichannelpin` and `/cleanlinked` can't be enabled at the same time because there's no point in doing so.\n\nAs `/cleanlinked` automatically deletes messages sent by the linked channel and it's removed from the pin."
    )

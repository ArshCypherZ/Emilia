from pyrogram import Client
from pyrogram.errors import WebpageCurlFailed
from pyrogram.types import Message

from Emilia import custom_filter
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *


@usage("/webss [website link]")
@example("/webss google.com")
@description("Screenshots given website.")
@Client.on_message(custom_filter.command(commands="webss", disable=True))
@disable
@rate_limit(RATE_LIMIT_HEAVY)
async def take_ss(_, message: Message):
    try:
        if len(message.text.split()) != 2:
            await usage_string(message, take_ss)
            return
        url = message.text.split(None, 1)[1]
        try:
            await message.reply_photo(
                photo=f"https://service.headless-render-api.com/screenshot/{url}",
                quote=False,
            )
        except WebpageCurlFailed:
            url = "https://" + url
            await message.reply_photo(
                photo=f"https://service.headless-render-api.com/screenshot/{url}",
                quote=False,
            )
        except TypeError:
            return await message.reply("No Such Website.")
    except Exception as e:
        await message.reply_text(str(e))
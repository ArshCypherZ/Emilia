import asyncio

from pyrogram import Client
from pyrogram.errors import WebpageCurlFailed
from pyrogram.types import Message

from Emilia import custom_filter
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *
from Emilia.utils.net_guard import is_safe_url


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
        if "://" not in url:
            url = "https://" + url
        if not await asyncio.to_thread(is_safe_url, url):
            return await message.reply_text("That URL isn't allowed.")
        try:
            await message.reply_photo(
                photo=f"https://service.headless-render-api.com/screenshot/{url}",
                reply_parameters=None,
            )
        except WebpageCurlFailed:
            return await message.reply("No Such Website.")
        except TypeError:
            return await message.reply("No Such Website.")
    except Exception as e:
        await message.reply_text(str(e))

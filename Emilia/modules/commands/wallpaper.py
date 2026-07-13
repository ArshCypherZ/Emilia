import asyncio
import random

from pyrogram.types import ReplyParameters

from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get
from Emilia.utils.decorators import *


@usage("/wall [query]")
@example("/wall naruto")
@description("This will send desired wallpaper.")
@register(pattern="wall", disable=True)
@disable
@rate_limit(RATE_LIMIT_HEAVY)
async def some1(client, message):
    try:
        inpt: str = (
            message.text.split(None, 1)[1]
            if len(message.text) < 3
            else message.text.split(None, 1)[1].replace(" ", "%20")
        )
    except IndexError:
        return await usage_string(message, some1)

    Emievent = await message.reply_text("Sending please wait...")
    try:
        r = await get(
            f"https://bakufuapi.vercel.app/api/wall/wallhaven?query={inpt}&page=1"
        )
        r_json = r.json()

        list_id = [
            r_json["response"][i]["path"] for i in range(len(r_json["response"]))
        ]
        item = (random.sample(list_id, 1))[0]
    except BaseException:
        await message.reply_text("Try again later or enter correct query.")
        await Emievent.delete()
        return

    await client.send_photo(
        message.chat.id,
        item,
        caption="Preview",
        reply_parameters=ReplyParameters(message_id=message.id),
    )
    await client.send_document(
        message.chat.id,
        item,
        caption="wall",
        reply_parameters=ReplyParameters(message_id=message.id),
    )
    await Emievent.delete()
    await asyncio.sleep(5)

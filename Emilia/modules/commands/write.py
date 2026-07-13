import os

from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get
from Emilia.utils.decorators import *


@register(pattern="write", disable=True)
@disable
@rate_limit(RATE_LIMIT_HEAVY)
async def writer(client, m):
    async def process_text(text):
        encoded_text = text.replace(" ", "%20")
        r = await get(f"https://apis.xditya.me/write?text={encoded_text}")
        if r.status_code == 200:
            image_data = r.content
            with open("write_image.png", "wb") as f:
                f.write(image_data)
            return "done"
        return None

    if not m.reply_to_message_id:
        try:
            text = m.text.split(None, 1)[1]
        except IndexError:
            return await m.reply_text("What should I write? Give me some text.")
        var = await m.reply_text("`Waitoo...`")
        image_data = await process_text(text)
        if image_data:
            await m.reply_photo("write_image.png")
            os.remove("write_image.png")
        await var.delete()

    else:
        reply = m.reply_to_message
        if reply and not reply.text:
            return await m.reply_text("Reply to a text.")
        text = reply.text
        var = await m.reply_text("`Waitoo...`")
        image_data = await process_text(text)
        if image_data:
            await m.reply_photo("write_image.png")
            os.remove("write_image.png")
        await var.delete()

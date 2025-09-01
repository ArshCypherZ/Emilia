import os
import random

import carbon
from telethon import types

from Emilia import LOGGER, SUPPORT_CHAT, telethn
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *


@usage("/carbon [text/reply to text]")
@example("/carbon meow")
@description("Generates carbon image, try for yourself.")
@register(pattern="carbon", disable=True)
@disable
async def cba(event):
    if not event.reply_to and not event.pattern_match.group(1):
        return await usage_string(event, cba)
    elif event.reply_to:
        msg = await event.get_reply_message()
        if msg.media:
            if isinstance(msg.media, types.MessageMediaDocument):
                file = await telethn.download_media(msg)
                f = open(file)
                try:
                    code = f.read()
                except Exception as ef:
                    LOGGER.error(ef)
                    return await event.reply("Reply to some readable document!")
                f.close()
                os.remove(file)
            else:
                if msg.text:
                    code = msg.raw_text
                else:
                    return await event.reply("Reply to a text or a document file!")
        else:
            code = msg.raw_text
    elif event.pattern_match.group(1):
        code = event.text.split(None, 1)[1]
    res = await event.reply("`Processing...`")
    options = carbon.CarbonOptions(
        code,
        language="python",
        background_color=random.choice(
            [
                (255, 0, 0, 1),
                (171, 184, 195, 1),
                (255, 255, 0, 1),
                (0, 0, 128, 1),
                (255, 255, 255, 1),
            ]
        ),
        font_family=random.choice(["Iosevka", "IBM Plex Mono", "hack", "Fira Code"]),
        adjust_width=True,
        theme=random.choice(["seti", "Night Owl", "One Dark"]),
    )
    cb = carbon.Carbon()
    try:
        img = await cb.generate(options)
    except Exception as e:
        LOGGER.error(e)
        await event.reply(f"Some error occured! Please report to @{SUPPORT_CHAT}")
    await img.save("carbon")
    await event.respond(file="carbon.png")
    await res.delete()

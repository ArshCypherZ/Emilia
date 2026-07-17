import os
import random

import carbon

from Emilia import LOGGER, SUPPORT_CHAT
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *


@usage("/carbon [text/reply to text]")
@example("/carbon meow")
@description("Generates carbon image, try for yourself.")
@register(pattern="carbon", disable=True)
@disable
async def cba(client, message):
    if not message.reply_to_message and not message.pattern_match.group(1):
        return await usage_string(message, cba)
    elif message.reply_to_message:
        msg = message.reply_to_message
        if msg.media:
            if msg.document:
                file = await msg.download(in_memory=False)
                f = open(file)
                try:
                    code = f.read()
                except Exception as ef:
                    LOGGER.error(ef)
                    return await message.reply_text("Reply to some readable document!")
                f.close()
                os.remove(file)
            else:
                if msg.text:
                    code = msg.text
                else:
                    return await message.reply_text(
                        "Reply to a text or a document file!"
                    )
        else:
            code = msg.text
    elif message.pattern_match.group(1):
        code = message.text.split(None, 1)[1]
    res = await message.reply_text("`Processing...`")
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
    import uuid
    unique_id = uuid.uuid4().hex
    base_name = f"carbon_{unique_id}"
    full_name = f"{base_name}.png"

    cb = carbon.Carbon()
    try:
        img = await cb.generate(options)
        await img.save(base_name)
        await message.reply_photo(full_name, reply_parameters=None)
    except Exception as e:
        LOGGER.error(e)
        await message.reply_text(
            f"Some error occured! Please report to @{SUPPORT_CHAT}"
        )
    finally:
        try:
            await res.delete()
        except Exception:
            pass
        if os.path.exists(full_name):
            try:
                os.remove(full_name)
            except Exception:
                pass


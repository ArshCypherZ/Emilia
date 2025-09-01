# DONE: Memify

import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

from Emilia import LOGGER
from Emilia import telethn as bot
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *


@usage("/mmf [text/reply to sticker]")
@example("/mmf meow ; cat")
@description("Write text on stickers. (The sticker should not be animated)")
@register(pattern="mmf", disable=True)
@disable
async def handler(event):
    if event.fwd_from:
        return
    if not event.reply_to_msg_id:
        return await usage_string(event, handler)
    reply_message = await event.get_reply_message()
    if not reply_message.media:
        return await event.reply("```Reply to a image/sticker.```")
    file = await bot.download_media(reply_message)
    msg = await event.reply("```Memifying this image!```")
    parts = event.text.split(None, 1)
    text = parts[1] if len(parts) > 1 else ""
    if len(text) < 1:
        await msg.edit("You might want to try `/mmf text`")
        return
    try:
        meme = await drawText(file, text)
        await bot.send_file(event.chat_id, file=meme, force_document=False)
        os.remove(meme)
    except Exception as e:
        LOGGER.error(e)
        await usage_string(event, handler)
    await msg.delete()


async def drawText(image_path, text):
    img = Image.open(image_path)
    os.remove(image_path)
    i_width, i_height = img.size
    fnt = "./Emilia/utils/Logo/Roboto-Medium.ttf"
    m_font = ImageFont.truetype(fnt, int((70 / 640) * i_width))

    if ";" in text:
        upper_text, lower_text = text.split(";")
    else:
        upper_text = text
        lower_text = ""
    draw = ImageDraw.Draw(img)
    current_h, pad = 10, 5
    if upper_text:
        for u_text in textwrap.wrap(upper_text, width=15):
            # textsize deprecated in Pillow 10+; use textbbox to measure
            u_bbox = draw.textbbox((0, 0), u_text, font=m_font)
            u_width, u_height = (u_bbox[2] - u_bbox[0], u_bbox[3] - u_bbox[1])
            draw.text(
                xy=(((i_width - u_width) / 2) - 2, int((current_h / 640) * i_width)),
                text=u_text,
                font=m_font,
                fill=(0, 0, 0),
            )
            draw.text(
                xy=(((i_width - u_width) / 2) + 2, int((current_h / 640) * i_width)),
                text=u_text,
                font=m_font,
                fill=(0, 0, 0),
            )
            draw.text(
                xy=((i_width - u_width) / 2, int(((current_h / 640) * i_width)) - 2),
                text=u_text,
                font=m_font,
                fill=(0, 0, 0),
            )
            draw.text(
                xy=(((i_width - u_width) / 2), int(((current_h / 640) * i_width)) + 2),
                text=u_text,
                font=m_font,
                fill=(0, 0, 0),
            )

            draw.text(
                xy=((i_width - u_width) / 2, int((current_h / 640) * i_width)),
                text=u_text,
                font=m_font,
                fill=(255, 255, 255),
            )
            current_h += u_height + pad
    if lower_text:
        for l_text in textwrap.wrap(lower_text, width=15):
            l_bbox = draw.textbbox((0, 0), l_text, font=m_font)
            u_width, u_height = (l_bbox[2] - l_bbox[0], l_bbox[3] - l_bbox[1])
            draw.text(
                xy=(
                    ((i_width - u_width) / 2) - 2,
                    i_height - u_height - int((20 / 640) * i_width),
                ),
                text=l_text,
                font=m_font,
                fill=(0, 0, 0),
            )
            draw.text(
                xy=(
                    ((i_width - u_width) / 2) + 2,
                    i_height - u_height - int((20 / 640) * i_width),
                ),
                text=l_text,
                font=m_font,
                fill=(0, 0, 0),
            )
            draw.text(
                xy=(
                    (i_width - u_width) / 2,
                    (i_height - u_height - int((20 / 640) * i_width)) - 2,
                ),
                text=l_text,
                font=m_font,
                fill=(0, 0, 0),
            )
            draw.text(
                xy=(
                    (i_width - u_width) / 2,
                    (i_height - u_height - int((20 / 640) * i_width)) + 2,
                ),
                text=l_text,
                font=m_font,
                fill=(0, 0, 0),
            )

            draw.text(
                xy=(
                    (i_width - u_width) / 2,
                    i_height - u_height - int((20 / 640) * i_width),
                ),
                text=l_text,
                font=m_font,
                fill=(255, 255, 255),
            )
            current_h += u_height + pad
    image_name = "memify.webp"
    webp_file = os.path.join(image_name)
    img.save(webp_file, "webp")
    return webp_file

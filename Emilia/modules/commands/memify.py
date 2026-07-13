# DONE: Memify

import asyncio
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

from Emilia import LOGGER
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.helper.forward_origin import fwd_date
from Emilia.utils.decorators import *


@usage("/mmf [text/reply to sticker]")
@example("/mmf meow ; cat")
@description("Write text on stickers. (The sticker should not be animated)")
@register(pattern="mmf", disable=True)
@disable
async def handler(client, message):
    if fwd_date(message):
        return
    if not message.reply_to_message_id:
        return await usage_string(message, handler)
    reply_message = message.reply_to_message
    if not reply_message.media:
        return await message.reply_text("```Reply to a image/sticker.```")
    file = await reply_message.download(in_memory=False)
    msg = await message.reply_text("```Memifying this image!```")
    parts = (message.text or "").split(None, 1)
    text = parts[1] if len(parts) > 1 else ""
    if len(text) < 1:
        await msg.edit_text("You might want to try `/mmf text`")
        return
    try:
        meme = await asyncio.to_thread(drawText, file, text)
        # Telethon sent the .webp with force_document=False, i.e. as a sticker
        await client.send_sticker(message.chat.id, meme)
        os.remove(meme)
    except Exception as e:
        LOGGER.error(e)
        await usage_string(message, handler)
    await msg.delete()


def drawText(image_path, text):
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

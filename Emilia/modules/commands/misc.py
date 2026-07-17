# DONE: Misc

import asyncio
import os
import random

from gtts import gTTS
from mutagen.mp3 import MP3
from pyrogram.enums import ChatAction
from pyrogram.types import ReplyParameters

from Emilia import BOT_NAME
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get
from Emilia.utils.decorators import *


def _synthesize_tts(text, lang, filename):
    gTTS(text, tld="com", lang=lang).save(filename)


@register(pattern="(count|gstat)")
async def ___stat_chat__(client, message):
    __stats_format = "**Total Messages in {}:** `{}`"
    await message.reply_text(__stats_format.format(message.chat.title, message.id))


@usage("/tts [LanguageCode] <text>")
@example("/tts en Hello")
@description("This will convert the given text to speech.")
@register(pattern="tts", disable=True)
@disable
@exception
async def tts(client, message):
    if not message.reply_to_message_id and message.text.split(None, 1)[1]:
        text = message.text.split(None, 1)[1]
        _total = text.split(None, 1)
        if len(_total) == 2:
            lang = (_total[0]).lower()
            text = _total[1]
        else:
            lang = "en"
            text = _total[0]
    elif message.reply_to_message_id:
        text = message.reply_to_message.text
        if message.pattern_match.group(1):
            lang = (message.text.split(None, 1)[1]).lower()
        else:
            lang = "en"
    else:
        return await usage_string(message, tts)
    import uuid
    filename = f"stt_{uuid.uuid4().hex}.mp3"
    try:
        await asyncio.to_thread(_synthesize_tts, text, lang, filename)
        aud_len = int((MP3(filename)).info.length)
        if aud_len == 0:
            aud_len = 1
        await client.send_chat_action(message.chat.id, ChatAction.RECORD_AUDIO)
        await message.reply_audio(
            filename,
            reply_parameters=None,
            duration=aud_len,
            title=f"stt_{lang}",
            performer=f"{BOT_NAME}",
        )
    except BaseException as e:
        return await message.reply_text(str(e))
    finally:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                pass


# DONE: GIFs
@usage("/gif [query]")
@example("/gif cats ; 5")
@description(
    "This will send desired GIF, if you need multiple GIFs look at the example."
)
@register(pattern="gif", disable=True)
@disable
@exception
async def some(client, message):
    # Parse input safely
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await usage_string(message, some)
    inpt = parts[1].strip()
    if not inpt:
        return await usage_string(message, some)

    # Support ';' to specify count, e.g. "cats ; 5"
    count = 1
    if ";" in inpt:
        left, right = inpt.split(";", 1)
        inpt = left.strip()
        try:
            count = int(right.strip())
        except Exception:
            count = 1

    # Validate count
    if not (1 <= int(count) <= 20):
        return await message.reply_text("Give number of GIFs between 1-20.")

    # Query GIPHY search
    try:
        r = await get(
            f"https://api.giphy.com/v1/gifs/search?q={inpt}&api_key=mwEesEFclDVHEbtYzI3hw2AEIhEMCIxM&limit=50"
        )
        if r.status_code >= 400:
            return await message.reply_text("Failed to fetch GIFs. Try again later.")
        js = r.json() or {}
        data = js.get("data", [])
        if not isinstance(data, list) or not data:
            return await message.reply_text("No GIFs found for your query.")
        gif_urls = []
        for it in data:
            gid = (it or {}).get("id")
            if gid:
                gif_urls.append(f"https://media.giphy.com/media/{gid}/giphy.gif")
    except Exception:
        return await message.reply_text("Failed to fetch GIFs. Try again later.")

    if not gif_urls:
        return await message.reply_text("No GIFs found for your query.")

    # Randomly select up to requested count
    try:
        chosen = random.sample(gif_urls, min(count, len(gif_urls)))
    except ValueError:
        chosen = gif_urls[:count]

    for url in chosen:
        await client.send_animation(
            message.chat.id,
            url,
            reply_parameters=ReplyParameters(message_id=message.id),
        )

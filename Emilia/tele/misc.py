# DONE: Misc

import os
import random
import re

from gtts import gTTS
from mutagen.mp3 import MP3
from telethon.tl.types import DocumentAttributeAudio

from Emilia import telethn as meow, BOT_NAME
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *
from Emilia.utils.async_http import get 


@register(pattern="(count|gstat)")
async def ___stat_chat__(e):
    __stats_format = "**Total Messages in {}:** `{}`"
    await e.reply(__stats_format.format(e.chat.title, e.id))


@usage("/tts [LanguageCode] <text>")
@example("/tts en Hello")
@description("This will convert the given text to speech.")
@register(pattern="tts", disable=True)
@disable
@exception
async def tts(event):
    if not event.reply_to_msg_id and event.text.split(None, 1)[1]:
        text = event.text.split(None, 1)[1]
        _total = text.split(None, 1)
        if len(_total) == 2:
            lang = (_total[0]).lower()
            text = _total[1]
        else:
            lang = "en"
            text = _total[0]
    elif event.reply_to_msg_id:
        text = (await event.get_reply_message()).text
        if event.pattern_match.group(1):
            lang = (event.text.split(None, 1)[1]).lower()
        else:
            lang = "en"
    else:
        return await usage_string(event, tts)
    try:
        tts = gTTS(text, tld="com", lang=lang)
        tts.save("stt.mp3")
    except BaseException as e:
        return await event.reply(str(e))
    aud_len = int((MP3("stt.mp3")).info.length)
    if aud_len == 0:
        aud_len = 1
    async with meow.action(event.chat_id, "record-voice"):
        await event.respond(
            file="stt.mp3",
            attributes=[
                DocumentAttributeAudio(
                    duration=aud_len,
                    title=f"stt_{lang}",
                    performer=f"{BOT_NAME}",
                    waveform="320",
                )
            ],
        )
        os.remove("stt.mp3")


# DONE: GIFs
@usage("/gif [query]")
@example("/gif cats ; 5")
@description(
    "This will send desired GIF, if you need multiple GIFs look at the example."
)
@register(pattern="gif", disable=True)
@disable
@exception
async def some(event):
    # Parse input safely
    parts = event.text.split(None, 1)
    if len(parts) < 2:
        return await usage_string(event, some)
    inpt = parts[1].strip()
    if not inpt:
        return await usage_string(event, some)

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
        return await event.reply("Give number of GIFs between 1-20.")

    # Query GIPHY search
    try:
        r = await get(
            f"https://api.giphy.com/v1/gifs/search?q={inpt}&api_key=mwEesEFclDVHEbtYzI3hw2AEIhEMCIxM&limit=50"
        )
        if r.status_code >= 400:
            return await event.reply("Failed to fetch GIFs. Try again later.")
        js = r.json() or {}
        data = js.get("data", [])
        if not isinstance(data, list) or not data:
            return await event.reply("No GIFs found for your query.")
        gif_urls = []
        for it in data:
            gid = (it or {}).get("id")
            if gid:
                gif_urls.append(f"https://media.giphy.com/media/{gid}/giphy.gif")
    except Exception:
        return await event.reply("Failed to fetch GIFs. Try again later.")

    if not gif_urls:
        return await event.reply("No GIFs found for your query.")

    # Randomly select up to requested count
    try:
        chosen = random.sample(gif_urls, min(count, len(gif_urls)))
    except ValueError:
        chosen = gif_urls[:count]

    for url in chosen:
        await event.client.send_file(
            event.chat_id,
            url,
            reply_to=event,
        )

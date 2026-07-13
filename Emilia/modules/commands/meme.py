# DONE: Memes

import random

from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get
from Emilia.utils.decorators import exception

MemesReddit = [
    "Animemes",
    "lostpause",
    "LoliMemes",
    "cleananimemes",
    "animememes",
    "goodanimemes",
    "AnimeFunny",
    "dankmemes",
    "teenagers",
    "shitposting",
    "Hornyjail",
    "wholesomememes",
    "cursedcomments",
]


@register(pattern="memes", disable=True)
@disable
@exception
async def mimi(client, message):
    memereddit = random.choice(MemesReddit)
    meme_link = f"https://meme-api.com/gimme/{memereddit}"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="dank", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/dankmemes"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="lolimeme", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/LoliMemes"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="hornyjail", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/Hornyjail"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="wmeme", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/wholesomememes"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="pewds", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/PewdiepieSubmissions"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="hmeme", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/hornyresistance"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="teen", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/teenagers"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="fbi", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/FBI_Memes"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="shitposting", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/shitposting"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@register(pattern="cursed", disable=True)
@disable
@exception
async def mimi(client, message):
    meme_link = "https://meme-api.com/gimme/cursedcomments"
    q = await get(meme_link)
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])

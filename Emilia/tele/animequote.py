# DONE: Anime Quotes


import random

from telethon import Button

from Emilia import telethn as meow
from Emilia.custom_filter import callbackquery, register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get


async def anime_quote(anime):
    if anime is None:
        url = "https://animechan.xyz/api/random"
    else:
        url = f"https://animechan.xyz/api/random/anime?title={anime}"

    r = await get(url)
    try:
        dic = r.json()
        quote = dic["quote"]
        character = dic["character"]
        animes = dic["anime"]
        return quote, character, animes
    except BaseException:
        return None, None, None


@register(pattern="quote", disable=True)
@disable
async def quotes(event):
    try:
        anim: str = event.text.split(None, 1)[1]
        quote, character, anime = await anime_quote(anime=anim)
    except IndexError:
        quote, character, anime = await anime_quote(anime=None)
    if not quote:
        await event.reply("No quote found!")
        return
    msg = f"__❝ {quote}❞__\n\n**{character} from {anime}**"
    keyboard = [Button.inline("Change 🔁", data="change_quote")]
    await event.reply(msg, buttons=keyboard)


@callbackquery(pattern=r"change_.*")
@callbackquery(pattern=r"quote_.*")
async def change_quote(event):
    quote, character, anime = await anime_quote(anime=None)
    msg = f"__❝ {quote}❞__\n\n**{character} from {anime}**"
    keyboard = [Button.inline("Change 🔁", data="quote_change")]
    await event.edit(msg, buttons=keyboard)


@register(pattern="animequotes", disable=True)
@disable
async def animequotes(event):
    keyboard = [Button.inline("Change 🔁", data="changek_quote")]
    await meow.send_file(event.chat_id, random.choice(QUOTES_IMG), buttons=keyboard)


@callbackquery(pattern=r"changek_.*")
@callbackquery(pattern=r"quotek_.*")
async def changek_quote(event):
    keyboard = [Button.inline("Change 🔁", data="quotek_change")]
    await event.edit(file=random.choice(QUOTES_IMG), buttons=keyboard)


QUOTES_IMG = (
    "https://i.imgur.com/Iub4RYj.jpg",
    "https://i.imgur.com/uvNMdIl.jpg",
    "https://i.imgur.com/YOBOntg.jpg",
    "https://i.imgur.com/fFpO2ZQ.jpg",
    "https://i.imgur.com/f0xZceK.jpg",
    "https://i.imgur.com/RlVcCip.jpg",
    "https://i.imgur.com/CjpqLRF.jpg",
    "https://i.imgur.com/8BHZDk6.jpg",
    "https://i.imgur.com/8bHeMgy.jpg",
    "https://i.imgur.com/5K3lMvr.jpg",
    "https://i.imgur.com/NTzw4RN.jpg",
    "https://i.imgur.com/wJxryAn.jpg",
    "https://i.imgur.com/9L0DWzC.jpg",
    "https://i.imgur.com/sBe8TTs.jpg",
    "https://i.imgur.com/1Au8gdf.jpg",
    "https://i.imgur.com/28hFQeU.jpg",
    "https://i.imgur.com/Qvc03JY.jpg",
    "https://i.imgur.com/gSX6Xlf.jpg",
    "https://i.imgur.com/iP26Hwa.jpg",
    "https://i.imgur.com/uSsJoX8.jpg",
    "https://i.imgur.com/OvX3oHB.jpg",
    "https://i.imgur.com/JMWuksm.jpg",
    "https://i.imgur.com/lhM3fib.jpg",
    "https://i.imgur.com/64IYKkw.jpg",
    "https://i.imgur.com/nMbyA3J.jpg",
    "https://i.imgur.com/7KFQhY3.jpg",
    "https://i.imgur.com/mlKb7zt.jpg",
    "https://i.imgur.com/JCQGJVw.jpg",
    "https://i.imgur.com/hSFYDEz.jpg",
    "https://i.imgur.com/PQRjAgl.jpg",
    "https://i.imgur.com/ot9624U.jpg",
    "https://i.imgur.com/iXmqN9y.jpg",
    "https://i.imgur.com/RhNBeGr.jpg",
    "https://i.imgur.com/tcMVNa8.jpg",
    "https://i.imgur.com/LrVg810.jpg",
    "https://i.imgur.com/TcWfQlz.jpg",
    "https://i.imgur.com/muAUdvJ.jpg",
    "https://i.imgur.com/AtC7ZRV.jpg",
    "https://i.imgur.com/sCObQCQ.jpg",
    "https://i.imgur.com/AJFDI1r.jpg",
    "https://i.imgur.com/TCgmRrH.jpg",
    "https://i.imgur.com/LMdmhJU.jpg",
    "https://i.imgur.com/eyyax0N.jpg",
    "https://i.imgur.com/YtYxV66.jpg",
    "https://i.imgur.com/292w4ye.jpg",
    "https://i.imgur.com/6Fm1vdw.jpg",
    "https://i.imgur.com/2vnBOZd.jpg",
    "https://i.imgur.com/j5hI9Eb.jpg",
    "https://i.imgur.com/cAv7pJB.jpg",
    "https://i.imgur.com/jvI7Vil.jpg",
    "https://i.imgur.com/fANpjsg.jpg",
    "https://i.imgur.com/5o1SJyo.jpg",
    "https://i.imgur.com/dSVxmh8.jpg",
    "https://i.imgur.com/02dXlAD.jpg",
    "https://i.imgur.com/htvIoGY.jpg",
    "https://i.imgur.com/hy6BXOj.jpg",
    "https://i.imgur.com/OuwzNYu.jpg",
    "https://i.imgur.com/L8vwvc2.jpg",
    "https://i.imgur.com/3VMVF9y.jpg",
    "https://i.imgur.com/yzjq2n2.jpg",
    "https://i.imgur.com/0qK7TAN.jpg",
    "https://i.imgur.com/zvcxSOX.jpg",
    "https://i.imgur.com/FO7bApW.jpg",
    "https://i.imgur.com/KK06gwg.jpg",
    "https://i.imgur.com/6lG4tsO.jpg",
)
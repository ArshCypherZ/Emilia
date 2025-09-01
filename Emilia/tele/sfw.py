# DONE: SFW

import nekos
from Emilia.utils.async_http import get

from Emilia import telethn as meow
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.decorators import exception

url_sfw = "https://api.waifu.pics/sfw/"


@exception
async def send_media(event, img):
    if event.reply_to:
        replied_message = await event.get_reply_message()
        if replied_message:
            return await meow.send_file(event.chat_id, img, reply_to=replied_message.id)
        else:
            return await event.reply(file=img)
    return await event.reply(file=img)


@register(pattern="waifu", disable=True)
@disable
async def waifu(event):
    url = f"{url_sfw}waifu"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="cosplay", disable=True)
@disable
async def waifu(event):
    r = await get("https://waifu-api.vercel.app")
    r_json = r.json()
    await send_media(event, r_json)


@register(pattern="neko", disable=True)
@disable
async def neko(event):
    url = f"{url_sfw}neko"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="shinobu", disable=True)
@disable
async def shinobu(event):
    url = f"{url_sfw}shinobu"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="megumin", disable=True)
@disable
async def megumin(event):
    url = f"{url_sfw}megumin"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="bully", disable=True)
@disable
async def bully(event):
    url = f"{url_sfw}bully"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="cuddle", disable=True)
@disable
async def cuddle(event):
    url = f"{url_sfw}cuddle"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="cry", disable=True)
@disable
async def cry(event):
    url = f"{url_sfw}cry"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="hug", disable=True)
@disable
async def hug(event):
    url = f"{url_sfw}hug"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="awoo", disable=True)
@disable
async def awoo(event):
    url = f"{url_sfw}awoo"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="kiss", disable=True)
@disable
async def kiss(event):
    url = f"{url_sfw}kiss"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="lick", disable=True)
@disable
async def lick(event):
    url = f"{url_sfw}lick"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="pat", disable=True)
@disable
async def pat(event):
    url = f"{url_sfw}pat"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="smug", disable=True)
@disable
async def smug(event):
    url = f"{url_sfw}smug"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="bonk", disable=True)
@disable
async def bonk(event):
    url = f"{url_sfw}bonk"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="yeet", disable=True)
@disable
async def yeet(event):
    url = f"{url_sfw}yeet"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="blush", disable=True)
@disable
async def blush(event):
    url = f"{url_sfw}blush"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="smile", disable=True)
@disable
async def smile(event):
    url = f"{url_sfw}smile"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="wave", disable=True)
@disable
async def wave(event):
    url = f"{url_sfw}wave"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="highfive", disable=True)
@disable
async def highfive(event):
    url = f"{url_sfw}highfive"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="handhold", disable=True)
@disable
async def handhold(event):
    url = f"{url_sfw}handhold"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="nom", disable=True)
@disable
async def nom(event):
    url = f"{url_sfw}nom"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="bite", disable=True)
@disable
async def bite(event):
    url = f"{url_sfw}bite"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="glomp", disable=True)
@disable
async def glomp(event):
    url = f"{url_sfw}glomp"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="slap", disable=True)
@disable
async def slap(event):
    url = f"{url_sfw}slap"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="kill", disable=True)
@disable
async def killgif(event):
    url = f"{url_sfw}kill"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="kicks", disable=True)
@disable
async def kickgif(event):
    url = f"{url_sfw}kick"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="happy", disable=True)
@disable
async def happy(event):
    url = f"{url_sfw}happy"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="wink", disable=True)
@disable
async def wink(event):
    url = f"{url_sfw}wink"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="poke", disable=True)
@disable
async def poke(event):
    url = f"{url_sfw}poke"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="dance", disable=True)
@disable
async def dance(event):
    url = f"{url_sfw}dance"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="cringe", disable=True)
@disable
async def cringe(event):
    url = f"{url_sfw}cringe"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    await send_media(event, img)


@register(pattern="wallpaper", disable=True)
@disable
async def wallpaper(event):
    target = "wallpaper"
    await send_media(event, (nekos.img(target)))


@register(pattern="tickle", disable=True)
@disable
async def tickle(event):
    target = "tickle"
    await send_media(event, (nekos.img(target)))


@register(pattern="ngif", disable=True)
@disable
async def ngif(event):
    target = "ngif"
    await send_media(event, (nekos.img(target)))


@register(pattern="feed", disable=True)
@disable
async def feed(event):
    target = "feed"
    await send_media(event, (nekos.img(target)))


@register(pattern="gasm", disable=True)
@disable
async def gasm(event):
    target = "gasm"
    await send_media(event, (nekos.img(target)))


@register(pattern="avatar", disable=True)
@disable
async def avatar(event):
    target = "avatar"
    await send_media(event, (nekos.img(target)))


@register(pattern="foxgirl", disable=True)
@disable
async def foxgirl(event):
    target = "fox_girl"
    await send_media(event, (nekos.img(target)))


@register(pattern="gecg", disable=True)
@disable
async def gecg(event):
    target = "gecg"
    await send_media(event, (nekos.img(target)))


@register(pattern="lizard", disable=True)
@disable
async def lizard(event):
    target = "lizard"
    await send_media(event, (nekos.img(target)))


@register(pattern="goose", disable=True)
@disable
async def goose(event):
    target = "goose"
    await send_media(event, (nekos.img(target)))


@register(pattern="woof", disable=True)
@disable
async def woof(event):
    target = "woof"
    await send_media(event, (nekos.img(target)))

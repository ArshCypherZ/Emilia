# DONE: NSFW

from Emilia.utils.async_http import get

import Emilia.strings as strings
from Emilia import telethn as meow
from Emilia.custom_filter import register
from Emilia.functions.admins import is_admin
from Emilia.mongo.nsfw_mongo import is_nsfw_on, nsfw_off, nsfw_on
from Emilia.utils.decorators import *

url_nsfw = "https://api.waifu.pics/nsfw/"


@register(pattern="addnsfw")
@logging
async def add_nsfw(event):
    if not await is_admin(event, event.sender_id):
        return await event.reply(strings.NOT_ADMIN)

    is_nsfw = await is_nsfw_on(event.chat_id)
    if not is_nsfw:
        await nsfw_on(event.chat_id)
        await event.reply("Activated NSFW Mode!")
        return "NSFW_ACTIVE", None, None
    else:
        return await event.reply("NSFW Mode is already Activated for this chat!")


@register(pattern="rmnsfw")
@logging
async def rem_nsfw(event):
    if not await is_admin(event, event.sender_id):
        return await event.reply(strings.NOT_ADMIN)

    is_nsfw = await is_nsfw_on(event.chat_id)
    if not is_nsfw:
        return await event.reply("NSFW Mode is already Deactivated")
    else:
        await nsfw_off(event.chat_id)
        await event.reply("Rolled Back to SFW Mode!")
        return "NSFW_DEACTIVE", None, None


@register(pattern="blowjob|bj")
async def blowjob(event):
    if event.is_group:
        is_nsfw = await is_nsfw_on(event.chat_id)
        if not is_nsfw:
            return await event.reply("NSFW is not activated")
    url = f"{url_nsfw}blowjob"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    if event.reply_to_msg_id:
        await meow.send_file(event.chat_id, img, reply_to=event.reply_to_msg_id)
    await meow.send_file(event.chat_id, img)


@register(pattern="trap")
async def trap(event):
    if event.is_group:
        is_nsfw = await is_nsfw_on(event.chat_id)
        if not is_nsfw:
            return await event.reply("NSFW is not activated")
    url = f"{url_nsfw}trap"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    if event.reply_to_msg_id:
        await meow.send_file(event.chat_id, img, reply_to=event.reply_to_msg_id)
    await meow.send_file(event.chat_id, img)


@register(pattern="(nsfwwaifu|nwaifu)")
async def nsfwwaifu(event):
    if event.is_group:
        is_nsfw = await is_nsfw_on(event.chat_id)
        if not is_nsfw:
            return await event.reply("NSFW is not activated")
    url = f"{url_nsfw}waifu"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    if event.reply_to_msg_id:
        await meow.send_file(event.chat_id, img, reply_to=event.reply_to_msg_id)
    await meow.send_file(event.chat_id, img)


@register(pattern="(nsfwneko|nneko)")
async def nsfwneko(event):
    if event.is_group:
        is_nsfw = await is_nsfw_on(event.chat_id)
        if not is_nsfw:
            return await event.reply("NSFW is not activated")
    url = f"{url_nsfw}neko"
    result = await get(url)
    result_json = result.json()
    img = result_json["url"]
    if event.reply_to_msg_id:
        await meow.send_file(event.chat_id, img, reply_to=event.reply_to_msg_id)
    await meow.send_file(event.chat_id, img)


@register(pattern="lewd")
async def lewd(event):    
    if event.is_group:
        is_nsfw = await is_nsfw_on(event.chat_id)
        if not is_nsfw:
            return await event.reply("NSFW is not activated")
    r = await get("https://waifu-api.vercel.app/items/1")
    r_json = r.json()
    if event.reply_to_msg_id:
        await meow.send_file(event.chat_id, r_json, reply_to=event.reply_to_msg_id)
    await meow.send_file(event.chat_id, r_json)

# DONE: NSFW

from pyrogram.enums import ChatType
from pyrogram.types import ReplyParameters

import Emilia.strings as strings
from Emilia.custom_filter import register
from Emilia.helper.admins import is_admin
from Emilia.mongo.nsfw_mongo import is_nsfw_on, nsfw_off, nsfw_on
from Emilia.utils.async_http import get
from Emilia.utils.decorators import *

url_nsfw = "https://api.purrbot.site/v2/img/nsfw"
_HEADERS = {"User-Agent": "Emilia/1.0 (https://github.com/ArshCypherZ/Emilia)"}


@exception
async def send_nsfw_media(client, message, img):
    reply_id = message.reply_to_message_id or message.id
    reply_parameters = ReplyParameters(message_id=reply_id)
    if str(img).lower().split("?")[0].endswith(".gif"):
        return await client.send_animation(message.chat.id, img, reply_parameters=reply_parameters)
    return await client.send_photo(message.chat.id, img, reply_parameters=reply_parameters)


@register(pattern="addnsfw")
@log_to_channel
async def add_nsfw(client, message):
    if not await is_admin(message, message.from_user.id):
        return await message.reply_text(strings.NOT_ADMIN)

    is_nsfw = await is_nsfw_on(message.chat.id)
    if not is_nsfw:
        await nsfw_on(message.chat.id)
        await message.reply_text("Activated NSFW Mode!")
        return "NSFW_ACTIVE", None, None
    else:
        return await message.reply_text("NSFW Mode is already Activated for this chat!")


@register(pattern="rmnsfw")
@log_to_channel
async def rem_nsfw(client, message):
    if not await is_admin(message, message.from_user.id):
        return await message.reply_text(strings.NOT_ADMIN)

    is_nsfw = await is_nsfw_on(message.chat.id)
    if not is_nsfw:
        return await message.reply_text("NSFW Mode is already Deactivated")
    else:
        await nsfw_off(message.chat.id)
        await message.reply_text("Rolled Back to SFW Mode!")
        return "NSFW_DEACTIVE", None, None


async def send_nsfw_category(client, message, category, kind="gif"):
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        is_nsfw = await is_nsfw_on(message.chat.id)
        if not is_nsfw:
            return await message.reply_text(strings.NSFW_NOT_ACTIVE)

    result = await get(f"{url_nsfw}/{category}/{kind}", headers=_HEADERS)
    try:
        result_json = result.json() or {}
    except Exception:
        return
    if result_json.get("error"):
        return
    img = result_json.get("link")
    if not img:
        return

    await send_nsfw_media(client, message, img)


def _register_nsfw(pattern, category, kind="gif"):
    @register(pattern=pattern)
    async def handler(client, message):
        await send_nsfw_category(client, message, category, kind)

    return handler


blowjob = _register_nsfw("blowjob|bj", "blowjob")
anal = _register_nsfw("anal", "anal")
cum = _register_nsfw("cum", "cum")
fuck = _register_nsfw("fuck", "fuck")
nsfwneko = _register_nsfw("(nsfwneko|nneko)", "neko", "gif")
pussylick = _register_nsfw("pussylick", "pussylick")
solo = _register_nsfw("solo", "solo")
solomale = _register_nsfw("solomale", "solo_male")
threesomefff = _register_nsfw("threesomefff", "threesome_fff")
threesomeffm = _register_nsfw("threesomeffm", "threesome_ffm")
threesomemmf = _register_nsfw("threesomemmf", "threesome_mmf")
yaoi = _register_nsfw("yaoi", "yaoi")
yuri = _register_nsfw("yuri", "yuri")

import os
import io
import aiofiles
from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.disable import disable
from Emilia.utils.async_http import post

REMOVE_BG_API_KEY = "vBTqsW1weqiNraoa8L33QNt8"


async def check_filename(filroid):
    if not os.path.exists(filroid):
        return filroid

    no = 1
    while True:
        ult = f"{os.path.splitext(filroid)[0]}_{no}{os.path.splitext(filroid)[1]}"
        if not os.path.exists(ult):
            return ult
        no += 1


async def remove_background(input_bytes):
    headers = {"X-API-Key": REMOVE_BG_API_KEY}
    
    files = {"image_file": ("image.png", input_bytes, "image/png")}

    resp = await post("https://api.remove.bg/v1.0/removebg", headers=headers, data=None, files=files)

    status = resp.status_code
    if status == 200:
        name = await check_filename("rmbg.png")
        async with aiofiles.open(name, "wb") as file:
            await file.write(resp.content)
        return True, name

    try:
        j = resp.json()
    except Exception:
        j = {"errors": [{"title": "Unknown", "detail": "Unexpected response"}]}
    return False, j


@Client.on_message(custom_filter.command(commands="rmbg", disable=True))
@disable
async def remove_bg_command_handler(client, message):
    replied = message.reply_to_message
    if not replied or not replied.photo:
        return await message.reply(
            "Reply to a photo in order for me to remove its background."
        )
    
    # Download to memory to avoid disk I/O blocking
    photo_bytes = await client.download_media(replied, in_memory=True)
    
    success, result_file = await remove_background(photo_bytes)

    if success:
        await message.reply_photo(photo=result_file)
        await message.reply_document(document=result_file)

        try:
            os.remove(result_file)
        except Exception:
            pass
    else:
        error_title = result_file["errors"][0].get("title", "Unknown Error")
        error_detail = result_file["errors"][0].get("detail", "")
        await message.reply(f"**ERROR Occurred**\n\n`{error_title}`\n`{error_detail}`")

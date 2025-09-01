import os

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


async def remove_background(input_file_name):
    headers = {"X-API-Key": REMOVE_BG_API_KEY}
    files = {"image_file": open(input_file_name, "rb")}

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
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    photo_path = await client.download_media(replied)
    success, result_file = await remove_background(photo_path)
    os.remove(photo_path)

    if success:
        async with aiofiles.open(result_file, "rb") as result:
            result_data = await result.read()

        result_temp_file = "temp_result.png"
        async with aiofiles.open(result_temp_file, "wb") as temp_file:
            await temp_file.write(result_data)

        await message.reply_photo(photo=result_temp_file),
        await message.reply_document(document=result_temp_file),

        os.remove(result_temp_file)
        os.remove(result_file)
    else:
        error_title = result_file["errors"][0].get("title", "Unknown Error")
        error_detail = result_file["errors"][0].get("detail", "")
        await message.reply(f"**ERROR Occurred**\n\n`{error_title}`\n`{error_detail}`")

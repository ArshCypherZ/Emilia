# DONE: Telegraph

import os
from datetime import datetime

from PIL import Image
from Emilia import telethn
from Emilia.custom_filter import register

from catbox import CatboxUploader


uploader = CatboxUploader()
TMP_DOWNLOAD_DIRECTORY = "catbox/"


@register(pattern="t(gm|gt)")
async def _(event):
    if event.fwd_from:
        return
    if event.reply_to_msg_id:
        start = datetime.now()
        r_message = await event.get_reply_message()
        downloaded_file_name = await telethn.download_media(
                r_message, TMP_DOWNLOAD_DIRECTORY
            )
        end = datetime.now()
        ms = (end - start).seconds
        h = await event.reply(
            f"Downloaded to {downloaded_file_name} in {ms} seconds."
        )
        if downloaded_file_name.endswith((".webp")):
            resize_image(downloaded_file_name)
        try:
            start = datetime.now()
            media_urls = uploader.upload_file(downloaded_file_name)
        except:
            os.remove(downloaded_file_name)
        else:                
            end = datetime.now()
            ms_two = (end - start).seconds
            os.remove(downloaded_file_name)
            await h.edit(
                f"Uploaded to [Catbox]({media_urls}) in {ms + ms_two} seconds.",
                link_preview=True,
            )       
    else:
        await event.reply("Reply to a message to get a permanent catbox link.")


def resize_image(image):
    im = Image.open(image)
    im.save(image, "PNG")

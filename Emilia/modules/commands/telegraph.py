# DONE: Telegraph

import os
from datetime import datetime

from pyrogram.types import LinkPreviewOptions

from Emilia import LOGGER
from Emilia.custom_filter import register
from Emilia.helper.forward_origin import fwd_date
from Emilia.uploader import TMP_DOWNLOAD_DIRECTORY, upload_local_file


@register(pattern="t(gm|gt)")
async def _(client, message):
    if fwd_date(message):
        return
    if message.reply_to_message_id:
        r_message = message.reply_to_message
        if r_message is None:
            await message.reply_text(
                "Can't access the replied message (it may have been deleted)."
            )
            return

        text_content = r_message.text or r_message.caption
        start = datetime.now()

        if not r_message.media:
            if not text_content:
                await message.reply_text(
                    "Reply to a message containing media or text to upload."
                )
                return
            os.makedirs(TMP_DOWNLOAD_DIRECTORY, exist_ok=True)
            downloaded_file_name = os.path.join(
                TMP_DOWNLOAD_DIRECTORY, f"text_{message.chat.id}_{r_message.id}.txt"
            )
            with open(downloaded_file_name, "w", encoding="utf-8") as text_file:
                text_file.write(text_content)
        else:
            try:
                downloaded_file_name = await r_message.download(
                    file_name=TMP_DOWNLOAD_DIRECTORY
                )
            except ValueError:
                await message.reply_text(
                    "Reply to a message containing media or text to upload."
                )
                return

        end = datetime.now()
        ms = (end - start).seconds
        h = await message.reply_text(
            f"Downloaded to {downloaded_file_name} in {ms} seconds."
        )
        try:
            start = datetime.now()
            media_urls = await upload_local_file(downloaded_file_name)
        except Exception as exc:
            LOGGER.exception(
                f"tgm: upload_local_file failed for {downloaded_file_name}"
            )
            await h.edit_text(f"Upload failed: `{exc}`")
        else:
            end = datetime.now()
            ms_two = (end - start).seconds
            await h.edit_text(
                f"Uploaded to [Zipline]({media_urls}) in {ms + ms_two} seconds.",
                link_preview_options=LinkPreviewOptions(is_disabled=False),
            )
    else:
        await message.reply_text("Reply to a message to get a permanent upload link.")

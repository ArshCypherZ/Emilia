# DONE: Zipping

import os
import time
import zipfile
from datetime import datetime

from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from telethon.tl.types import DocumentAttributeVideo

import Emilia.strings as strings
from Emilia import TEMP_DOWNLOAD_DIRECTORY, telethn
from Emilia.custom_filter import register
from Emilia.functions.admins import *
from Emilia.utils.decorators import *


@usage("/zip [reply to file]")
@description("Zips/Compresses a replied file and sends it as a document.")
@example("/zip [reply to file]")
@register(pattern="zip")
@exception
@rate_limit(RATE_LIMIT_HEAVY)
async def _(event):
    if event.fwd_from:
        return

    if not event.is_reply:
        return await usage_string(event, _)
    if event.is_group:
        if not (await is_admin(event, event.sender_id)):
            return await event.reply(strings.NOT_ADMIN)

    mone = await event.reply("⏳️ Please wait...")
    if not os.path.isdir(TEMP_DOWNLOAD_DIRECTORY):
        os.makedirs(TEMP_DOWNLOAD_DIRECTORY)
    if event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
        try:
            time.time()
            downloaded_file_name = await telethn.download_media(
                reply_message, TEMP_DOWNLOAD_DIRECTORY
            )
            directory_name = downloaded_file_name
        except Exception as e:
            return await mone.reply(str(e))
    zipfile.ZipFile(directory_name + ".zip", "w", zipfile.ZIP_DEFLATED).write(
        directory_name
    )
    await telethn.send_file(
        event.chat_id,
        directory_name + ".zip",
        force_document=True,
        allow_cache=False,
        reply_to=event.message.id,
    )


def zipdir(path, ziph):
    # ziph is zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))
            os.remove(os.path.join(root, file))


extracted = TEMP_DOWNLOAD_DIRECTORY + "extracted/"
thumb_image_path = TEMP_DOWNLOAD_DIRECTORY + "/thumb_image.jpg"
if not os.path.isdir(extracted):
    os.makedirs(extracted)


@usage("/unzip [reply to zip file]")
@description("Unzips/Decompresses a replied zip file and sends it as a document.")
@example("/unzip [reply to zip file]")
@register(pattern="unzip")
@exception
@rate_limit(RATE_LIMIT_HEAVY)
async def _(event):
    if event.fwd_from:
        return

    if not event.is_reply:
        return await usage_string(event, _)
    if event.is_group:
        if not (await is_admin(event, event.sender_id)):
            return await event.reply(strings.NOT_ADMIN)

    mone = await event.reply("Processing...")
    if not os.path.isdir(TEMP_DOWNLOAD_DIRECTORY):
        os.makedirs(TEMP_DOWNLOAD_DIRECTORY)
    if event.reply_to_msg_id:
        start = datetime.now()
        reply_message = await event.get_reply_message()
        try:
            time.time()
            downloaded_file_name = await telethn.download_media(
                reply_message, TEMP_DOWNLOAD_DIRECTORY
            )
        except Exception as e:
            await mone.reply(str(e))
        else:
            end = datetime.now()
            (end - start).seconds

        with zipfile.ZipFile(downloaded_file_name, "r") as zip_ref:
            zip_ref.extractall(extracted)
        filename = sorted(get_lst_of_files(extracted, []))
        await event.reply("Unzipping now, please wait!")
        for single_file in filename:
            if os.path.exists(single_file):
                caption_rts = os.path.basename(single_file)
                force_document = True
                supports_streaming = False
                document_attributes = []
                if single_file.endswith((".mp4", ".mp3", ".flac", ".webm")):
                    metadata = extractMetadata(createParser(single_file))
                    duration = 0
                    width = 0
                    height = 0
                    if metadata.has("duration"):
                        duration = metadata.get("duration").seconds
                    if os.path.exists(thumb_image_path):
                        metadata = extractMetadata(createParser(thumb_image_path))
                        if metadata.has("width"):
                            width = metadata.get("width")
                        if metadata.has("height"):
                            height = metadata.get("height")
                    document_attributes = [
                        DocumentAttributeVideo(
                            duration=duration,
                            w=width,
                            h=height,
                            round_message=False,
                            supports_streaming=True,
                        )
                    ]
                try:
                    await telethn.send_file(
                        event.chat_id,
                        single_file,
                        force_document=force_document,
                        supports_streaming=supports_streaming,
                        allow_cache=False,
                        reply_to=event.message.id,
                        attributes=document_attributes,
                    )
                except Exception as e:
                    await telethn.send_message(
                        event.chat_id,
                        "{} caused `{}`".format(caption_rts, str(e)),
                        reply_to=event.message.id,
                    )
                    continue
                os.remove(single_file)
        os.remove(downloaded_file_name)


def get_lst_of_files(input_directory, output_lst):
    filesinfolder = os.listdir(input_directory)
    for file_name in filesinfolder:
        current_file_name = os.path.join(input_directory, file_name)
        if os.path.isdir(current_file_name):
            return get_lst_of_files(current_file_name, output_lst)
        output_lst.append(current_file_name)
    return output_lst
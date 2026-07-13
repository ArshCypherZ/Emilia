# DONE: Zipping

import os
import time
import zipfile
from datetime import datetime

from pyrogram.enums import ChatType
from pyrogram.types import ReplyParameters

import Emilia.strings as strings
from Emilia import TEMP_DOWNLOAD_DIRECTORY
from Emilia.custom_filter import register
from Emilia.helper.forward_origin import fwd_date
from Emilia.helper.admins import *
from Emilia.utils.decorators import *


@usage("/zip [reply to file]")
@description("Zips/Compresses a replied file and sends it as a document.")
@example("/zip [reply to file]")
@register(pattern="zip")
@exception
@rate_limit(RATE_LIMIT_HEAVY)
async def _(client, message):
    if fwd_date(message):
        return

    if not message.reply_to_message:
        return await usage_string(message, _)
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        sender_id = message.from_user.id if message.from_user else None
        if not (await is_admin(message, sender_id)):
            return await message.reply_text(strings.NOT_ADMIN)

    mone = await message.reply_text("⏳️ Please wait...")
    if not os.path.isdir(TEMP_DOWNLOAD_DIRECTORY):
        os.makedirs(TEMP_DOWNLOAD_DIRECTORY)
    if message.reply_to_message_id:
        reply_message = message.reply_to_message
        try:
            time.time()
            downloaded_file_name = await reply_message.download(
                file_name=TEMP_DOWNLOAD_DIRECTORY
            )
            directory_name = downloaded_file_name
        except Exception as e:
            return await mone.reply_text(str(e))
    zipfile.ZipFile(directory_name + ".zip", "w", zipfile.ZIP_DEFLATED).write(
        directory_name
    )
    await client.send_document(
        message.chat.id,
        directory_name + ".zip",
        reply_parameters=ReplyParameters(message_id=message.id),
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
async def _(client, message):
    if fwd_date(message):
        return

    if not message.reply_to_message:
        return await usage_string(message, _)
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        sender_id = message.from_user.id if message.from_user else None
        if not (await is_admin(message, sender_id)):
            return await message.reply_text(strings.NOT_ADMIN)

    mone = await message.reply_text("Processing...")
    if not os.path.isdir(TEMP_DOWNLOAD_DIRECTORY):
        os.makedirs(TEMP_DOWNLOAD_DIRECTORY)
    if message.reply_to_message_id:
        start = datetime.now()
        reply_message = message.reply_to_message
        try:
            time.time()
            downloaded_file_name = await reply_message.download(
                file_name=TEMP_DOWNLOAD_DIRECTORY
            )
        except Exception as e:
            await mone.reply_text(str(e))
        else:
            end = datetime.now()
            (end - start).seconds

        with zipfile.ZipFile(downloaded_file_name, "r") as zip_ref:
            zip_ref.extractall(extracted)
        filename = sorted(get_lst_of_files(extracted, []))
        await message.reply_text("Unzipping now, please wait!")
        for single_file in filename:
            if os.path.exists(single_file):
                caption_rts = os.path.basename(single_file)
                # files were always sent with force_document=True, so the
                # Telethon DocumentAttributeVideo/hachoir metadata had no
                # effect; dropped.
                try:
                    await client.send_document(
                        message.chat.id,
                        single_file,
                        reply_parameters=ReplyParameters(message_id=message.id),
                    )
                except Exception as e:
                    await client.send_message(
                        message.chat.id,
                        "{} caused `{}`".format(caption_rts, str(e)),
                        reply_parameters=ReplyParameters(message_id=message.id),
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

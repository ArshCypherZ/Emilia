from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isBotAdmin, isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.welcome_mongo import GetCaptchaSettings, SetCaptchaText
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands="setcaptchatext"))
@anonadmin_checker
async def SetCaptchatext(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserCan(message, chat_id=chat_id, privileges="can_change_info"):
        return

    if not await isBotAdmin(message, silent=True):
        await message.reply(
            "I need to be admin with the right to restrict to enable CAPTCHAs.",
            )
        return

    CaptchaText = " ".join(message.text.split()[1:])
    if CaptchaText:
        await message.reply("Updated the CAPTCHA button text!")
        await SetCaptchaText(chat_id, CaptchaText)

    else:
        captcha_mode, captcha_text, captcha_kick_time = await GetCaptchaSettings(
            chat_id
        )

        await message.reply(
            (
                "Users will be welcomed with a button containing the following:\n"
                f"`{captcha_text}`\n\n"
                "To change the text, try this command again followed by your new text"
            ),
            )

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isBotAdmin, isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.welcome_mongo import GetCaptchaSettings, SetCaptchaMode
from Emilia.utils.decorators import *

CAPTCHA_MODE_MAP = {
    "text": "Text CAPTCHAs require the user to answer a CAPTCHA containing letters and numbers.",
    "math": "Math CAPTCHAs require the user to solve a basic maths question. Please note that this may discriminate against users with little maths knowledge.",
    "button": "Button CAPTCHAs simply require a user to press a button in their welcome message to confirm they're human.",
}


@Client.on_message(custom_filter.command(commands="captchamode"))
@anonadmin_checker
async def CaptchaMode(client, message):
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
            "I need to be admin with the right to restrict to enable CAPTCHAs."
        )
        return

    command = message.text.split(" ")
    if not (len(command) == 1):
        GetArgs = command[1]
        if GetArgs == "text":
            await message.reply(
                "CAPTCHA set to **text**.\n\n" f"{CAPTCHA_MODE_MAP['text']}"
            )
            await SetCaptchaMode(chat_id, "text")

        elif GetArgs == "math":
            await message.reply(
                "CAPTCHA set to **math**.\n\n" f"{CAPTCHA_MODE_MAP['math']}"
            )
            await SetCaptchaMode(chat_id, "math")

        elif GetArgs == "button":
            await message.reply(
                "CAPTCHA set to **button**.\n\n" f"{CAPTCHA_MODE_MAP['button']}"
            )
            await SetCaptchaMode(chat_id, "button")

        else:
            await message.reply(
                f"'{GetArgs}' is not a recognised CAPTCHA mode! Try one of: button/math/text"
            )
    else:
        captcha_mode, captcha_text, captcha_kick_time = await GetCaptchaSettings(
            chat_id
        )

        if captcha_mode is None:
            captcha_mode = "button"

        await message.reply(
            (
                f"The current CAPTCHA mode is: {captcha_mode}\n"
                f"{CAPTCHA_MODE_MAP[captcha_mode]}\n\n"
                "Available CAPTCHA modes are: button/math/text"
            )
        )

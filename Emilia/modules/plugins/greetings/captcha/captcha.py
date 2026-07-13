from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isBotCan, isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.welcome_mongo import SetCaptcha, isGetCaptcha
from Emilia.utils.decorators import *

CAPTCHA_WELCOME_TRUE = ["on", "yes"]
CAPTCHA_WELCOME_FALSE = ["off", "no"]


@Client.on_message(custom_filter.command(commands="captcha"))
@anonadmin_checker
async def Captcha(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isBotCan(message, privileges="can_restrict_members", silent=True):
        await message.reply(
            "I need to be admin with the right to restrict to enable CAPTCHAs.",
            )
        return

    if not await isUserCan(message, privileges="can_restrict_members", silent=True):
        await message.reply(
            "You need to be admin with the right to restrict to enable CAPTCHAs.",
            )
        return

    if len(message.text.split()) >= 2:
        get_args = message.text.split()[1]

        if get_args in CAPTCHA_WELCOME_TRUE:
            await message.reply(
                "CAPTCHAs have been enabled. I will now mute people when they join.",
                )
            captcha = True
            await SetCaptcha(chat_id, captcha)

        elif get_args in CAPTCHA_WELCOME_FALSE:
            await message.reply(
                "CAPTCHAs have been disabled. Users can join normally."
            )
            captcha = False
            await SetCaptcha(chat_id, captcha)

    elif len(message.text.split()) == 1:
        if await isGetCaptcha(chat_id):
            CaptchaSetting = "Users will be asked to complete a CAPTCHA before being allowed to speak in the chat."
        else:
            CaptchaSetting = "Users will NOT be muted when joining the chat."

        await message.reply(
            (
                f"{CaptchaSetting}\n\n"
                "To change this setting, try this command again followed by one of yes/no/on/off"
            ),
            )

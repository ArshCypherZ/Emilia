from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.welcome_mongo import isReCaptcha, setReCaptcha

RECAPTCHA_TRUE = ["on", "yes"]
RECAPTCHA_FALSE = ["off", "no"]


@Client.on_message(custom_filter.command("recaptcha"))
async def reCaptcha(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserAdmin(message, pm_mode=True):
        return

    if len(message.text.split()) >= 2:
        command_arg = message.text.split()[1]

        if command_arg in RECAPTCHA_TRUE:
            await message.reply(
                "From now on, I'll ask the CAPTCHA to every new user; regardless of whether they'd joined the chat before and verified themselves."
            )
            await setReCaptcha(chat_id=chat_id, reCaptcha=True)

        elif command_arg in RECAPTCHA_FALSE:
            await message.reply(
                "I won't ask the CAPTCHA to users that have joined the chat before and already verified themselves."
            )
            await setReCaptcha(chat_id=chat_id, reCaptcha=False)

        else:
            await message.reply(
                f"This isn't a boolean - excpected one of yes/on or no/off: got: {command_arg}"
            )

    else:
        if await isReCaptcha(chat_id=chat_id):
            await message.reply(
                "reCAPTCHA: **enabled**; I'm asking the CAPTCHA to every new user, be it someone who has joined before and verified already - they'll have to pass the CAPTCHA again.\n\n"
                "To chnage this setting, try this command again followed by one of yes/no/on/off"
            )
        else:
            await message.reply(
                "reCAPTCHA: **disabled**; I'm not asking the CAPTCHA to people who have joined before and verified themselves.\n\n"
                "To chnage this setting, try this command again followed by one of yes/no/on/off"
            )

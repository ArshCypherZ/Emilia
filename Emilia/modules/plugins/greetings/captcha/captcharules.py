from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.welcome_mongo import isRuleCaptcha, setRuleCaptcha

CAPTCHARULE_TRUE = ["on", "yes"]
CAPTCHARULE_FALSE = ["off", "no"]


@Client.on_message(custom_filter.command("captcharules"))
async def rulecaptcha(client, message):
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

    if len(message.text.split()) >= 2:
        command_arg = message.text.split()[1]
        if command_arg in CAPTCHARULE_TRUE:
            await message.reply(
                "CAPTCHA rules have been enable. Users now need to accept rules as part of the CAPTCHA."
            )
            await setRuleCaptcha(chat_id=chat_id, rule_captcha=True)

        elif command_arg in CAPTCHARULE_FALSE:
            await message.reply(
                "CAPTCHA rules have been disabled. Users will not need to accept rules as part of the CAPTCHA."
            )
            await setRuleCaptcha(chat_id=chat_id, rule_captcha=False)

        else:
            await message.reply(
                f"That isn't a boolean - excpected one of /yes/on or no/off; got: {command_arg}"
            )

    else:
        if await isRuleCaptcha(chat_id=chat_id):
            text = "CAPTCHA rules are currently enabled. Users will be asked to accept the rules while completing the CAPTCHA."
        else:
            text = "CAPTCHA rules are currently disabled."

        await message.reply(
            (
                f"{text}\n\n"
                "To change this setting, try this command agin followed by on of yes/no/no/off"
            )
        )

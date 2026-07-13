from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin, isUserCan
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.report_mongo import get_report, reports_db
from Emilia.utils.decorators import *

REPORTS_TRUE = ["yes", "on"]
REPORTS_FALSE = ["no", "off"]


@Client.on_message(custom_filter.command(commands="reports"))
@anonadmin_checker
async def reports(client, message):
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

    if not await isUserCan(message, chat_id=chat_id, privileges="can_change_info"):
        return

    if len(message.text.split()) >= 2:
        report_args = message.text.split()[1]

        if report_args in REPORTS_TRUE:
            await message.reply("Users will now be able to report messages.")
            await reports_db(chat_id, True)

        elif report_args in REPORTS_FALSE:
            await message.reply(
                "Users will no longer be able to report via @admin or /report."
            )
            await reports_db(chat_id, False)

        else:
            await message.reply(strings.YES_NO_ON_OFF)
    else:
        if await get_report(chat_id):
            text = (
                "Reports are currently enabled in this chat.\n"
                "Users can use the /report command, or mention @admin, to tag all admins.\n\n"
            )
        else:
            text = "Reports are currently disabled in this chat.\n\n"

        await message.reply(
            f"{text} To change this setting, try this command again, with one of the following args: yes/no/on/off"
        )

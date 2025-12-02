from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import isBotCan, isUserCan
from Emilia.helper.get_user import get_text
from Emilia.pyro.warnings.warn import warn
from Emilia.utils.decorators import *


@Client.on_message(custom_filter.command(commands=["warn", "swarn", "dwarn"]))
@anonadmin_checker
@logging
async def addwarn(client, message):
    chat_id = message.chat.id
    message_id = None
    silent = False

    if not await isUserCan(message, privileges="can_restrict_members"):
        return

    if not await isBotCan(message, privileges="can_restrict_members"):
        return

    reason = await get_text(message)
    if not reason:
        reason = None

    if message.text.split()[0].find("dwarn") >= 0:
        if message.reply_to_message:
            message_id = message.reply_to_message.id

    elif message.text.split()[0].find("swarn") >= 0:
        message_id = message.id
        silent = True

    warn_r, log_msg, info = await warn(client, message, reason, silent, warn_user=None)

    if warn_r:
        if message_id is not None:
            await client.delete_messages(chat_id=chat_id, message_ids=message_id)
    return log_msg, info.id, info.first_name
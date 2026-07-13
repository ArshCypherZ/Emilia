from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import check_user
from Emilia.helper.custom_emoji import (
    emojipack_token,
    is_emojipack_token,
    normalize_emojipack_name,
)
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.locks_mongo import get_allowlist, rmallow_db


@Client.on_message(custom_filter.command(commands="rmallowlist"))
async def rmallow(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await check_user(message, privileges="can_change_info", pm_mode=True):
        return

    if not (len(message.text.split()) >= 2):
        return await message.reply(
            "You haven't given me any items to remove from the allowlist!"
        )

    RMALLOW_LIST = message.text.split()[1:]
    ALLOW_LIST = await get_allowlist(chat_id)

    CORRECT_LIST = []
    INCORRECT_LIST = []

    for rmallow in RMALLOW_LIST:
        if is_emojipack_token(rmallow):
            token = emojipack_token(normalize_emojipack_name(rmallow))
            if token:
                rmallow = token
        if rmallow in ALLOW_LIST:
            CORRECT_LIST.append(rmallow)
        else:
            INCORRECT_LIST.append(rmallow)

    if len(INCORRECT_LIST) != 0:
        text = "The following items are not currently allowlisted, and so can't be removed from the allowlist:\n"
        for item in INCORRECT_LIST:
            text += f"• `{item}`\n"

        return await message.reply(text)

    text = "These items are has been successfully removed from the allowlist:\n"
    for item in CORRECT_LIST:
        await rmallow_db(chat_id, item)
        if len(CORRECT_LIST) == 1:
            text = f"'{item}' removed from the allowlist."
        else:
            text += f"• `{item}`\n"

    await message.reply(text)

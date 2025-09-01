from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.helper.disable import disable
from Emilia.helper.get_user import get_user_id
from Emilia.mongo.warnings_mongo import count_user_warn, get_all_warn_reason, warn_limit
from Emilia.pyro.connection.connection import connection


@Client.on_message(custom_filter.command(commands="warns", disable=True))
@disable
async def warns(client, message):
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

    user_info = await get_user_id(message)
    user_id = user_info.id

    user_warn_num = await count_user_warn(chat_id, user_id)
    if user_warn_num is None or user_warn_num == 0:
        return await message.reply(f"User {user_info.mention} has no warnings!")

    chat_warn_limit = await warn_limit(chat_id)
    REASONS = await get_all_warn_reason(chat_id, user_id)

    await message.reply(
        f"User {user_info.mention} has {user_warn_num}/{chat_warn_limit} warnings. Reasons are:\n{''.join(REASONS)}"
    )

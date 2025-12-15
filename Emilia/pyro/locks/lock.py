from pyrogram import Client, enums
from pyrogram.errors import BadRequest
from pyrogram.types import ChatPermissions

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import check_bot, check_user
from Emilia.mongo.locks_mongo import lock_db
from Emilia.pyro.connection.connection import connection
from Emilia.pyro.locks import lock_map


@Client.on_message(custom_filter.command(commands="lock"))
async def lock(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await check_bot(
        message, privileges=["can_delete_messages", "can_restrict_members"]
    ):
        return

    if not await check_user(message, privileges="can_change_info"):
        return

    if not (len(message.text.split()) >= 2):
        return await message.reply("You haven't specified a type to lock.")

    LOCKS_LIST = lock_map.LocksMap.list()

    lock_args = message.text.split()[1:]

    LOCK_ITMES = []
    INCORRECT_ITEMS = []

    for lock in lock_args:
        if lock not in LOCKS_LIST:
            INCORRECT_ITEMS.append(lock)
        else:
            LOCK_ITMES.append(lock)

    if len(INCORRECT_ITEMS) != 0:
        text = "Unknown lock types:\n"
        for item in INCORRECT_ITEMS:
            text += f"• {item}\n"
        text += "Check /locktypes!"
        return await message.reply(text)

    for item in LOCK_ITMES:
        lock_value = lock_map.LocksMap[item].value
        await lock_db(chat_id, lock_value)

    text = "Locked:\n"
    for lock_arg in LOCK_ITMES:
        if len(LOCK_ITMES) != 1:
            text += f"• `{lock_arg}`\n"
        else:
            text = f"Locked `{lock_arg}`."

    if "all" in LOCK_ITMES:
        try:
            await client.set_chat_permissions(chat_id, ChatPermissions())
        except BadRequest:
            return await message.reply(
                "Non-admins already can't send messages. What are you even trying to do m8?"
            )

    await message.reply(text)

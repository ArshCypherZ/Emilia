from pyrogram import Client, enums
from pyrogram.types import ChatPermissions

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import check_bot, check_user
from Emilia.mongo.locks_mongo import unlock_db
from Emilia.pyro.connection.connection import connection
from Emilia.pyro.locks import lock_map


@Client.on_message(custom_filter.command(commands="unlock"))
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

    if not await check_bot(message, privileges="can_restrict_members"):
        return

    if not await check_user(message, privileges="can_change_info"):
        return

    if not len(message.text.split()) >= 2:
        return await message.reply("You haven't specified a type to unlock.")

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
        text = "Unknown unlock types:\n"

        for item in INCORRECT_ITEMS:
            text += f"• {item}\n"
        text += "Check /locktypes!"
        return await message.reply(text)

    for item in LOCK_ITMES:
        lock_value = lock_map.LocksMap[item].value
        await unlock_db(chat_id, lock_value)

    text = "Unlocked:\n"
    for unlock_arg in LOCK_ITMES:
        if len(LOCK_ITMES) != 1:
            text += f"• `{unlock_arg}`\n"
        else:
            text = f"Unlocked `{unlock_arg}`."

    if "all" in LOCK_ITMES:
        try:
            await client.set_chat_permissions(
                chat_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                ),
            )
        except BaseException:
            return await message.reply("All items are **already** unlocked.")

    await message.reply(text)

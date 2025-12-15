import html

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCan
from Emilia.helper.get_data import GetChat
from Emilia.mongo.locks_mongo import lockwarns_db, set_lockwarn_db
from Emilia.pyro.connection.connection import connection

LOCKWARN_TRUE = ["on", "yes"]
LOCKWARN_FALSE = ["off", "no"]


@Client.on_message(custom_filter.command(commands="lockwarns"))
async def lockwarns(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await isUserCan(message, chat_id=chat_id, privileges="can_change_info"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]
        if args in LOCKWARN_TRUE:
            await message.reply(
                "Lock warns have been enabled. Any user using locked messages will be warned, as well has have their message deleted."
            )
            await set_lockwarn_db(chat_id, True)

        elif args in LOCKWARN_FALSE:
            await message.reply(
                "Lock warns have been disabled. Any user using locked messages will no longer be warned, and will only have their message deleted."
            )
            await set_lockwarn_db(chat_id, False)

        else:
            await message.reply(
                "Your input was not recognised as one of: yes/no/on/off"
            )

    else:
        if await lockwarns_db(chat_id):
            await message.reply(
                f"I am currently warning all users who try to use locked message types in {html.escape(chat_title)}."
            )
        else:
            await message.reply(
                f"I am NOT warning all users who try to use locked message types in {html.escape(chat_title)}. I will simply delete the messages."
            )

import html

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserCreator
from Emilia.helper.get_data import GetChat
from Emilia.mongo.chats_settings_mongo import anonadmin_db, get_anon_setting
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *

ANONADMIN_TRUE = ["yes", "on"]
ANONADMIN_FALSE = ["no", "off"]


@Client.on_message(custom_filter.command(commands="anonadmin"))
@anonadmin_checker
async def anon_admin(client, message):
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

    if not await isUserCreator(message, chat_id=chat_id):
        await message.reply("Only the group creator can execute this command")
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]

        if args in ANONADMIN_TRUE:
            await anonadmin_db(chat_id, True)
            await message.reply(
                f"The anon admin setting for {html.escape(chat_title)} has been updated to true."
            )
        elif args in ANONADMIN_FALSE:
            await anonadmin_db(chat_id, False)
            await message.reply(
                f"The anon admin setting for {html.escape(chat_title)} has been updated to false."
            )
        else:
            await message.reply(
                f"failed to get boolean from input: expected one of y/yes/on or n/no/off; got: {args}"
            )

    else:
        if await get_anon_setting(chat_id):
            await message.reply(
                f"{html.escape(chat_title)} currently allows all anonymous admins to use any admin command without restriction."
            )
        else:
            await message.reply(
                f"{html.escape(chat_title)} currently requires anonymous admins to press a button to confirm their permissions."
            )
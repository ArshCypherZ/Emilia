import html

from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAllAdminsStuffs
from Emilia.helper.get_data import GetChat
from Emilia.mongo.pin_mongo import (
    antichannelpin_db,
    cleanlinked_db,
    get_antichannelpin,
    get_cleanlinked,
)
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *

CLEAN_LINKED_TRUE = ["on", "yes"]
CLEAN_LINKED_FALSE = ["off", "no"]


@Client.on_message(custom_filter.command(commands="cleanlinked"))
@anonadmin_checker
async def cleanlinked(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if not await CheckAllAdminsStuffs(message, privileges="can_delete_messages"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]
        if args in CLEAN_LINKED_TRUE:
            ANTICHANNEL_PIN = await get_antichannelpin(chat_id)
            if ANTICHANNEL_PIN:
                await message.reply(
                    "I've disabled `/antichannelpin`. Do /pininfo to know why or you can also read the `/help`."
                )
                await antichannelpin_db(chat_id, False)

            await message.reply(
                f"**Enabled** linked channel post deletion in {html.escape(chat_title)}. Messages sent from the linked channel will be deleted."
            )
            await cleanlinked_db(chat_id, True)

        elif args in CLEAN_LINKED_FALSE:
            await message.reply(
                f"**Disabled** linked channel post deletion in {html.escape(chat_title)}."
            )
            await cleanlinked_db(chat_id, False)

        else:
            await message.reply(
                "Your input was not recognised as one of: yes/no/on/off"
            )

    else:
        IS_CLEAN_LINK = await get_cleanlinked(chat_id)
        if IS_CLEAN_LINK:
            await message.reply(
                f"Linked channel post deletion is currently **enabled** in {html.escape(chat_title)}. Messages sent from the linked channel will be deleted."
            )

        else:
            await message.reply(
                f"Linked channel post deletion is currently **disabled** in {html.escape(chat_title)}."
            )

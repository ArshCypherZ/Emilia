import html

from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAllAdminsStuffs
from Emilia.helper.get_data import GetChat
from Emilia.mongo.pin_mongo import (
    antichannelpin_db,
    get_antichannelpin,
    get_cleanlinked,
)
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *

ANTICHANNELPIN_TRUE = ["on", "yes"]
ANTICHANNELPIN_FALSE = ["off", "no"]


@Client.on_message(custom_filter.command(commands="antichannelpin"))
@anonadmin_checker
async def antichannelpin(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if not await CheckAllAdminsStuffs(message, privileges="can_pin_messages"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]
        if args in ANTICHANNELPIN_TRUE:
            CLEAN_LINKED = await get_cleanlinked(chat_id)
            if not CLEAN_LINKED:
                await message.reply(
                    f"**Enabled** anti channel pins. Automatic pins from a channel will now be replaced with the previous pin."
                )
                await antichannelpin_db(chat_id, True)

            else:
                await message.reply(
                    "`/antichannelpin` and `/cleanlinked` can't be enabled at the same time because there's no point in doing so.\n\nAs `/cleanlinked` automatically deletes messages sent by the linked channel and it's removed from the pin."
                )

        elif args in ANTICHANNELPIN_FALSE:
            await message.reply(
                f"**Disabled** anti channel pins. Automatic pins from a channel will not be removed."
            )
            await antichannelpin_db(chat_id, False)
        else:
            await message.reply(
                "Your input was not recognised as one of: yes/no/on/off"
            )

    else:
        IS_ANITICHANNEL = await get_antichannelpin(chat_id)
        if IS_ANITICHANNEL:
            await message.reply(
                f"Anti channel pins are currently **enabled** in {html.escape(chat_title)}. All channel posts that get auto-pinned by telegram will be replaced with the previous pin."
            )

        else:
            await message.reply(
                f"Anti channel pins are currently **disabled** in {html.escape(chat_title)}."
            )

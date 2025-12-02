import html

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.helper.disable import disable
from Emilia.helper.get_data import GetChat
from Emilia.mongo.warnings_mongo import get_warn_mode, warn_limit
from Emilia.pyro.connection.connection import connection
from Emilia.pyro.warnings.set_warn_mode import WarnModeMap


def warn_mode_map(warn_mode_in):
    warn_mode_raw = WarnModeMap(warn_mode_in)
    warn_mode_out = warn_mode_raw.name
    return warn_mode_out


@Client.on_message(custom_filter.command(commands="warnings", disable=True))
@disable
async def warnings(client, message):
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

    if not await isUserAdmin(message, pm_mode=True):
        return

    warn_chat_limit = await warn_limit(chat_id)
    text = f"There is a {warn_chat_limit} warning limit in {html.escape(chat_title)}. "
    warn_mode_in, warn_mode_time = await get_warn_mode(chat_id)
    warn_mode = warn_mode_map(warn_mode_in)
    if warn_mode == "Ban":
        text += "When that limit has been exceeded, the user will be banned."
    elif warn_mode == "Kick":
        text += "When that limit has been exceeded, the user will be kicked."
    elif warn_mode == "Mute":
        text += "When that limit has been exceeded, the user will be muted."
    elif warn_mode == "Tmute":
        text += "When that limit has been exceeded, the user will be temporarily muted."
    elif warn_mode == "Tban":
        text += (
            "When that limit has been exceeded, the user will be temporarily banned."
        )

    await message.reply(text, quote=True)
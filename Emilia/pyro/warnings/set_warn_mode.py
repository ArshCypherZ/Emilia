import html
from enum import Enum, auto

from pyrogram import Client, enums

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import isBotAdmin, isUserCan
from Emilia.helper.convert import convert_time
from Emilia.helper.get_data import GetChat
from Emilia.helper.time_checker import get_time, time_string_helper
from Emilia.mongo.warnings_mongo import set_warn_mode_db
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


class WarnModeMap(Enum):
    Ban = auto()
    Kick = auto()
    Mute = auto()
    Tban = auto()
    Tmute = auto()


@usage("/warnmode [ban/kick/mute/tmute/tban]")
@example("/warnmode mute")
@description(
    "Use this command to set what action to take when a user exceeds warn limit"
)
@Client.on_message(custom_filter.command(commands=["setwarnmode", "warnmode"]))
@anonadmin_checker
async def set_warn_mode(client, message):
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

    if not await isUserCan(message, privileges="can_restrict_members", silent=True):
        return await message.reply("You need to be an admin to do this.")

    if not await isBotAdmin(message, silent=True):
        return await message.reply(
            f"I am not admin in {html.escape(chat_title)}\nin which you want me to set different warn modes, I need to be admin."
        )

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]

        if args == "ban":
            warn_mode_map = WarnModeMap.Ban.value
            await set_warn_mode_db(chat_id, warn_mode_map, time=None)
            await message.reply("Updated warning mode to: `banned`")

        elif args == "kick":
            warn_mode_map = WarnModeMap.Kick.value
            await set_warn_mode_db(chat_id, warn_mode_map, time=None)
            await message.reply("Updated warning mode to: `kicked`")

        elif args == "mute":
            warn_mode_map = WarnModeMap.Mute.value
            await set_warn_mode_db(chat_id, warn_mode_map, time=None)
            await message.reply("Updated warning mode to: `muted`")

        elif args == "tban":
            warn_mode_map = WarnModeMap.Tban.value
            time_args = await get_time(message)
            cal_time = await convert_time(int(time_args[:-1]), time_args[-1])
            time_limit, time_format = await time_string_helper(time_args)
            await set_warn_mode_db(chat_id, warn_mode_map, time=cal_time)
            await message.reply(
                f"Updated warning mode to: `temporarily banned for {time_limit} {time_format}`"
            )

        elif args == "tmute":
            warn_mode_map = WarnModeMap.Tmute.value
            time_args = await get_time(message)
            cal_time = await convert_time(int(time_args[:-1]), time_args[-1])
            time_limit, time_format = await time_string_helper(time_args)
            await set_warn_mode_db(chat_id, warn_mode_map, time=cal_time)
            await message.reply(
                f"Updated warning mode to: `temporarily muted for {time_limit} {time_format}`"
            )

        else:
            await message.reply(
                f"I don't recognize this argument: '{args}'. Please use one of: ban/kick/mute/tban/tmute"
            )
    else:
        await usage_string(message, set_warn_mode)
        return
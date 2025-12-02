import html
from enum import Enum, auto

from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAllAdminsStuffs
from Emilia.helper.convert import convert_time
from Emilia.helper.get_data import GetChat
from Emilia.helper.time_checker import get_time, time_string_helper
from Emilia.mongo.blocklists_mongo import getblocklistmode, setblocklistmode
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *


class BlocklistModeMap(Enum):
    nothing = auto()
    ban = auto()
    mute = auto()
    kick = auto()
    warn = auto()
    tban = auto()
    tmute = auto()


@Client.on_message(custom_filter.command(commands=["blocklistmode", "blacklistmode"]))
@anonadmin_checker
async def blocklistmode(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if not await CheckAllAdminsStuffs(message, privileges="can_restrict_members"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]

        if args == "nothing":
            blocklist_mode = BlocklistModeMap.nothing.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                f"I've updated blocklist action in {html.escape(chat_title)} to: nothing. Users who say any blocklisted words will now have their message deleted, and then be nothing"
            )

        elif args == "ban":
            blocklist_mode = BlocklistModeMap.ban.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                f"I've updated blocklist action in {html.escape(chat_title)} to: ban. Users who say any blocklisted words will now have their message deleted, and then be banned"
            )

        elif args == "mute":
            blocklist_mode = BlocklistModeMap.mute.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                f"I've updated blocklist aaction in {html.escape(chat_title)} to: mute. Users who say any blocklisted words will now have their message deleted, and then be muted"
            )

        elif args == "kick":
            blocklist_mode = BlocklistModeMap.kick.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                f"I've updated blocklist action in {html.escape(chat_title)} to: kick. Users who say any blocklisted words will now have their message deleted, and then be kicked"
            )

        elif args == "warn":
            blocklist_mode = BlocklistModeMap.warn.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                f"I've updated blocklist action in {html.escape(chat_title)} to: warn. Users who say any blocklisted words will now have their message deleted, and then be warned"
            )

        elif args == "tban":
            blocklist_mode = BlocklistModeMap.tban.value
            time_args = await get_time(message)
            cal_time = await convert_time(int(time_args[:-1]), time_args[-1])
            time_limit, time_format = await time_string_helper(time_args)
            await setblocklistmode(chat_id, blocklist_mode, blocklist_time=cal_time)
            await message.reply(
                f"I've updated blocklist action in {html.escape(chat_title)} to: tban for {time_limit} {time_format}. Users who say any blocklisted words will now have their message deleted, and then be temporarily banned for {time_limit} {time_format}"
            )

        elif args == "tmute":
            blocklist_mode = BlocklistModeMap.tmute.value
            time_args = await get_time(message)
            cal_time = await convert_time(int(time_args[:-1]), time_args[-1])
            time_limit, time_format = await time_string_helper(time_args)
            await setblocklistmode(chat_id, blocklist_mode, blocklist_time=cal_time)
            await message.reply(
                f"I've updated blocklist action in {html.escape(chat_title)} to: tmute for {time_limit} {time_format}. Users who say any blocklisted words will now have their message deleted, and then be temporarily muted for {time_limit} {time_format}"
            )

        else:
            await message.reply(
                f"I son't recognize this argument: `{args}``. Please use one of: nothing/ban/mute/kick/warn/tban/tmute"
            )
    else:
        (
            blocklist_mode,
            blocklist_time,
            blocklist_default_reason,
        ) = await getblocklistmode(chat_id)

        if blocklist_mode == 1:
            text = "Your current blocklist preference is just to delete messages with blocklisted words.\n\n"

        elif blocklist_mode == 2:
            text = "Your current blocklist preference is to ban users on messages containing blocklisted words, and delete the message.\n\n"

        elif blocklist_mode == 3:
            text = "Your current blocklist preference is to mute users on messages containing blocklisted words, and delete the message.\n\n"

        elif blocklist_mode == 4:
            text = "Your current blocklist preference is to kick users on messages containing blocklisted words, and delete the message.\n\n"

        elif blocklist_mode == 5:
            text = "Your current blocklist preference is to warn users on messages containing blocklisted words, and delete the message.\n\n"

        elif blocklist_mode == 6:
            text = "Your current blocklist preference is to tban users on messages containing blocklisted words, and delete the message.\n\n"

        elif blocklist_mode == 7:
            text = "Your current blocklist preference is to tmute users on messages containing blocklisted words, and delete the message.\n\n"

        await message.reply(
            f"{text}"
            "If you want to change this setting, you will need to specify an action to take on blocklisted words. Possible modes are: nothing/ban/mute/kick/warn/tban/tmute"
        )

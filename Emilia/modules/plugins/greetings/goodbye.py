from pyrogram import Client, enums
from pyrogram.types import InlineKeyboardMarkup

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.button_gen import button_markdown_parser
from Emilia.helper.chat_status import isUserCan
from Emilia.helper.welcome_helper.welcome_send_message import SendWelcomeMessage
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.welcome_mongo import (
    DEFAUT_GOODBYE,
    GetCleanService,
    GetGoobye,
    GetGoodbyemessageOnOff,
    SetGoodbyeMessageOnOff,
    isGoodbye,
)
from Emilia.utils.decorators import *

GOODBYE_TRUE = ["on", "yes"]
GOODBYE_FALSE = ["off", "no"]


@Client.on_message(custom_filter.command(commands="goodbye"))
@anonadmin_checker
async def Welcome(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)
    if not await isUserCan(message, chat_id=chat_id, privileges="can_change_info"):
        return

    command = message.text.split(" ")
    if not (len(command) == 1):
        GetWelcomeArg = command[1]
        if GetWelcomeArg in GOODBYE_TRUE:
            await SetGoodbyeMessageOnOff(chat_id, goodbye_message=True)
            await message.reply("I'll be saying goodbye to any leavers from now on!")

        elif GetWelcomeArg in GOODBYE_FALSE:
            await SetGoodbyeMessageOnOff(chat_id, goodbye_message=False)
            await message.reply("I'll stay quiet when people leave.")

        else:
            await message.reply(strings.YES_NO_ON_OFF)

    elif len(command) == 1:
        if await GetGoodbyemessageOnOff(chat_id):
            GoodByeMessage = "true"
        else:
            GoodByeMessage = "false"

        if await GetCleanService(chat_id):
            CleanService = "true"
        else:
            CleanService = "false"

        GOODBYE_MESSAGE = (
            f"I am currently saying goodbye to users: `{GoodByeMessage}`\n"
            f"I am currently deleting service messages: `{CleanService}`\n"
            "NOTE: If your group has more than 50 members, it is possible that Emilia will stop wishing users goodbye - this is a Telegram restriction.\n\n"
            "Members are currently bidden farewell with:"
        )

        GoodByeSentMessage = await message.reply(GOODBYE_MESSAGE)

        if await isGoodbye(chat_id):
            Content, Text, DataType = await GetGoobye(chat_id)
            Text, buttons = button_markdown_parser(Text)

            reply_markup = None
            if len(buttons) > 0:
                reply_markup = InlineKeyboardMarkup(buttons)
            GoodByeSentMessage = await SendWelcomeMessage(
                GoodByeSentMessage,
                None,
                Content,
                Text,
                DataType,
                reply_markup=reply_markup,
            )
        else:
            await GoodByeSentMessage.reply(DEFAUT_GOODBYE)

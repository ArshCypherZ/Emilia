from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatMemberUpdated, InlineKeyboardMarkup, Message


from Emilia.helper.button_gen import button_markdown_parser
from Emilia.helper.welcome_helper.welcome_fillings import Welcomefillings
from Emilia.helper.welcome_helper.welcome_send_message import SendWelcomeMessage
from Emilia.mongo.welcome_mongo import (
    DEFAUT_GOODBYE,
    GetCleanService,
    GetGoobye,
    GetGoodbyemessageOnOff,
    isGoodbye,
)
from Emilia.utils.decorators import *


@Client.on_message(filters.service & filters.group, group=59)
async def cleannnnn(_, message: Message):
    if await GetCleanService(message.chat.id):
        try:
            await message.delete()
        except BaseException:
            pass


@Client.on_chat_member_updated(filters.group, group=790)
@leavemute
async def goodbye_member(client: Client, message: ChatMemberUpdated):
    if (
        not message.new_chat_member
        and message.old_chat_member.status
        not in {ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED}
        and message.old_chat_member
    ):
        pass
    else:
        return

    chat_id = message.chat.id
    user = (
        message.old_chat_member.user if message.old_chat_member else message.from_user
    )
    if not await GetGoodbyemessageOnOff(chat_id):
        return
    # If user set goodbye
    if await isGoodbye(chat_id):

        Content, Text, DataType = await GetGoobye(chat_id)
        Text, buttons = button_markdown_parser(Text)

        # If Goodbye message has button greater than 0
        reply_markup = None
        if len(buttons) > 0:
            reply_markup = InlineKeyboardMarkup(buttons)

        GoodByeMessageSet = await SendWelcomeMessage(
            message,
            user,
            Content,
            Text,
            DataType,
            reply_markup=reply_markup,
        )
    else:
        # If Goodbye has No any messages set
        Text = await Welcomefillings(message, DEFAUT_GOODBYE, user)
        reply_markup = None
        GoodByeMessageSet = await client.send_message(
            chat_id=chat_id,
            text=Text,
            reply_markup=reply_markup,
        )

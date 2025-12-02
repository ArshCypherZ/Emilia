import html

from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import BOT_USERNAME, custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.helper.get_data import GetChat
from Emilia.mongo.connection_mongo import connectDB, get_allow_connection
from Emilia.utils.decorators import *


@usage("/connect [chat id]")
@description("Connect to a chat using its id in PM")
@example("/connect -1001234567890")
@Client.on_message(custom_filter.command(commands=("connect")))
async def Connect(client, message):
    if message.chat.type == ChatType.PRIVATE:
        if not (len(message.text.split()) >= 2):
            await usage_string(message, Connect)
            return
        chat_id = message.text.split()[1]
        if not (chat_id.startswith("-100")):
            await message.reply(
                "I was expecting a chat id, but this isn't a valid integer", quote=True
            )
            return

        chat_title = await GetChat(int(chat_id), client)
        if chat_title is None:
            await message.reply(
                "failed to connect to chat!\nError: `chat not found`", quote=True
            )
        else:
            await connect_button(client, message, int(chat_id))
    else:
        chat_id = message.chat.id
        await message.reply(
            "Tap the following button to connect to this chat in PM",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="Connect to chat",
                            url=f"http://t.me/{BOT_USERNAME}?start=connect_{chat_id}",
                        )
                    ]
                ]
            ),
        )


async def connectRedirect(client, message):
    chat_id = int(message.text.split("_")[1])
    await connect_button(client, message, chat_id)


async def connect_button(client, message, chat_id):

    user_id = message.from_user.id
    if await isUserAdmin(
        message, user_id=user_id, chat_id=chat_id, silent=True, pm_mode=True
    ):
        keyboard = [
            [InlineKeyboardButton(text="Admin commands", callback_data="connect_admin")]
        ]
        keyboard += [
            [InlineKeyboardButton(text="User commands", callback_data="connect_user")]
        ]

    else:
        if await get_allow_connection(chat_id):
            keyboard = [
                [
                    InlineKeyboardButton(
                        text="User commands", callback_data="connect_user"
                    )
                ]
            ]
        else:
            keyboard = []

    chat_title = await GetChat(chat_id, client)

    reply_markup = None
    text = f"Users are **not** allowed to connect in {html.escape(chat_title)}."
    if len(keyboard) > 0:
        await connectDB(user_id, chat_id)
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = f"You have been connected to {html.escape(chat_title)}!"

    await client.send_message(
        text=text,
        chat_id=message.from_user.id,
        reply_markup=reply_markup,
        reply_to_message_id=message.id,
    )


@Client.on_callback_query(filters.regex("connect_admin"))
async def mam(_, message):
    user_command = """Admin commands available:
- /antiraid
- /raidmode
- /raidtime
- /raidactiontime
- /autoantiraid
- /setautoantiraid
- /quietfed
- /joinfed
- /leavefed
- /chatfed
- /lock
- /unlock
- /allowlist
- /rmallowlist
- /lockwarns
- /locks
- /addblocklist
- /unblocklist
- /unblocklistall
- /blocklist
- /blocklistmode
- /blocklistdelete
- /setblocklistreason
- /resetblocklistreason
- /flood
- /clearflood
- /floodmode
- /setflood
- /setfloodtimer
- /welcome
- /goodbye
- /setwelcome
- /resetwelcome
- /setgoodbye
- /resetgoodbye
- /cleanwelcome
- /captcha
- /captchatime
- /captchamode
- /captchakick
- /captchakicktime
- /setcaptchatext
- /resetcaptchatext
- /captcharules
- /filter
- /stop
- /stopall
- /reports
- /antichannelpin
- /cleanlinked
- /cleanlinkedchannel
- /logchannel
- /log
- /nolog
- /cleanservice
- /keepservice
- /nocleanservice
- /cleancommand
- /keepcommand
- /nocleancommand
- /save
- /clear
- /clearall
- /privatenotes
- /admincache
- /legacyadmin
- /anonadmin
- /adminerror
- /resetallwarns
- /warnings
- /setwarnmode
- /warnmode
- /setwarnlimit
- /warnlimit
- /setwarntime
- /warntime
- /setrules
- /resetrules
- /clearrules
- /setrulesbutton
- /resetrulesbutton
- /privaterules
- /disable
- /enable
- /disabled
- /disabledel
- /disableadmin
- /approve
- /unapprove
- /unapproveall
- /approved
- /export
- /import
- /chatreset
- /silentactions
- /actiontopic"""
    keyboard = [
                [
                    InlineKeyboardButton(
                        text="User Commands", callback_data="connect_user"
                    )
                ]
            ]
    buttons = InlineKeyboardMarkup(keyboard)
    await message.message.reply(user_command, reply_markup=buttons)
    await message.message.delete()


@Client.on_callback_query(filters.regex("connect_user"))
async def ma(_, message):
    user_command = """User commands available:
- /filters
- /get
- /notes
- /saved
- /adminlist
- /info
- /warns
- /rules
- /approval"""
    keyboard = [
                [
                    InlineKeyboardButton(
                        text="Admin Commands", callback_data="connect_admin"
                    )
                ]
            ]
    buttons = InlineKeyboardMarkup(keyboard)
    await message.message.reply(user_command, reply_markup=buttons)
    await message.message.delete()


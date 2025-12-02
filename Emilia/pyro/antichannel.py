from pyrogram import Client, enums, filters
from pyrogram.raw import functions, types

import Emilia.strings as strings
from Emilia import custom_filter, db
from Emilia.helper.chat_status import check_user
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *
from Emilia.pyro.pin.cleanlinked_checker import GetLinkedChannel

# db
antichanneldb = db.antichannel


async def antichannelmode_on(chat_id: int):
    return await antichanneldb.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id}}, upsert=True)


async def antichannelmode_off(chat_id: int):
    return await antichanneldb.delete_one({"chat_id": chat_id})


async def isModOn(chat_id: int) -> bool:
    return bool(await antichanneldb.find_one({"chat_id": chat_id}))


@usage("/antichannelmode [on/off]")
@example("/antichannelmode on")
@description(
    "By turning it on inside a group chat, bot will automatically ban and delete users that send message through channels."
)
@Client.on_message(custom_filter.command(commands=["antichannel", "antichannelmode"]) & filters.group)
@logging
@anonadmin_checker
async def _antichannelmode(_, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await check_user(message, privileges="can_change_info", pm_mode=True):
        return

    args = message.text.split()
    mm = await isModOn(chat_id)
    if len(args) < 2:
        await usage_string(message, _antichannelmode)
    if "on" in args:
        if not mm:
            await antichannelmode_on(chat_id)
            await message.reply_text("Antichannel is enabled in this group.")
            return "ENABLED_ANTICHANNEL", None, None
        return await message.reply_text("Antichannel is already enabled in this group.")
    elif "off" in args:
        if not mm:
            return await message.reply_text(
                "Antichannel is already disabled in this group."
            )
        await antichannelmode_off(chat_id)
        await message.reply_text("Disabled Antichannel successfully in this chat.")
        return "DISABLED_ANTICHANNEL", None, None


@Client.on_message(filters.group, group=110)
async def _message_handler(client, message):
    if not (await isModOn(message.chat.id)):
        return
    chat_id = message.chat.id
    if (
        message.sender_chat
        and message.sender_chat.type == enums.ChatType.CHANNEL
    ):  
        
        try:
            linked_channel = await GetLinkedChannel(client, chat_id)
            if linked_channel:
                if message.forward_from_chat.id == linked_channel:
                    return
            await message.delete()
            channel_id = message.sender_chat.id
            await client.invoke(
                functions.channels.EditBanned(
                    channel=await client.resolve_peer(chat_id),
                    participant=await client.resolve_peer(channel_id),
                    banned_rights=types.ChatBannedRights(
                        until_date=0,
                        view_messages=True,
                        send_messages=True,
                        send_media=True,
                        send_stickers=True,
                        send_gifs=True,
                        send_games=True,
                        send_polls=True,
                    ),
                )
            )
        except Exception:
            await message.reply_text(
                "Give me ban/delete permissions to ban channels who are sending messages! If already given, report to support chat!"
            )
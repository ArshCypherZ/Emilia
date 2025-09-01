from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType

from Emilia import custom_filter, db
from Emilia.helper.chat_status import check_user
from Emilia.utils.decorators import *

# db
cleanerdb = db.cleaner


async def cleanblue_on(chat_id: int):
    return await cleanerdb.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id}}, upsert=True)


async def cleanblue_off(chat_id: int):
    return await cleanerdb.delete_one({"chat_id": chat_id})


async def isOn(chat_id: int) -> bool:
    return bool(await cleanerdb.find_one({"chat_id": chat_id}))


@usage("/cleanblue [on/off]")
@example("/cleanblue on")
@description("This will delete incoming blue texts from the chat (i.e, bot commands)")
@Client.on_message(custom_filter.command(commands="cleanblue") & filters.group)
@logging
async def _cleanblue(_, message):
    if not await check_user(message, privileges="can_delete_messages"):
        return
    args = message.text.split()
    chat_id = message.chat.id
    check = await isOn(chat_id)
    if "on" in args:
        if not check:
            await cleanblue_on(chat_id)
            await message.reply_text("Bluetext cleaning enabled!")
            return "ENABLED_BLUETEXT_CLEANING", None, None
        return await message.reply_text(
            "Bluetext cleaning has been already enabled in this chat!"
        )
    elif "off" in args:
        if not check:
            return await message.reply_text(
                "Bluetext cleaning has been already disabled in this chat!"
            )
        await cleanblue_off(chat_id)
        await message.reply_text("Disabled Bluetext cleaning successfully!")
        return "DISABLED_BLUETEXT_CLEANING", None, None
    else:
        await usage_string(message, _cleanblue)
        return


@Client.on_message(filters.group, group=16)
async def _delmessage(_, message):
    chat_id = message.chat.id
    check = await isOn(chat_id)
    if not check:
        return
    try:
        type = message.entities[0].type
        if type == MessageEntityType.BOT_COMMAND:
            await message.delete()
    except BaseException:
        pass

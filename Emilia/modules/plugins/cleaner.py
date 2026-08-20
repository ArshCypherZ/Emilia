from pyrogram import Client, filters
from pyrogram.enums import ChatType, MessageEntityType
from pyrogram.errors import MessageDeleteForbidden, RPCError

from Emilia import custom_filter
from Emilia.helper.chat_status import check_user
from Emilia.mongo.cleaner_mongo import get_cleancommand_cached, set_cleancommand
from Emilia.mongo.connection_mongo import GetConnectedChat
from Emilia.utils.decorators import (
    description,
    example,
    exception,
    log_to_channel,
    rate_limit,
    usage,
    usage_string,
)


@usage("/cleancommand [on/off]")
@example("/cleancommand on")
@description("This will delete incoming bot commands from the chat to prevent spam.")
@Client.on_message(
    custom_filter.command(
        commands=[
            "cleancommand",
            "cleancommands",
            "cleancmd",
            "cleanblue",
            "nocleancommand",
            "keepcommand",
        ]
    )
)
@rate_limit()
@exception
@log_to_channel
async def _cleancommand(_, message):
    chat_id = message.chat.id
    if message.chat.type == ChatType.PRIVATE:
        user_id = message.from_user.id if message.from_user else None
        connected = await GetConnectedChat(user_id) if user_id else None
        if connected:
            chat_id = connected
            if not await check_user(
                message, privileges="can_delete_messages", pm_mode=True, chat_id=chat_id
            ):
                return
    else:
        if not await check_user(message, privileges="can_delete_messages"):
            return

    cmd = message.text.split()[0].lower()
    if "@" in cmd:
        cmd = cmd.split("@")[0]
    if cmd.startswith(("/", "!", ".")):
        cmd = cmd[1:]

    args = [x.lower() for x in message.text.split()[1:]]
    check = await get_cleancommand_cached(chat_id)

    if cmd in ("nocleancommand", "keepcommand"):
        if not check:
            await message.reply_text(
                "Command cleaning has been already disabled in this chat!"
            )
            return
        await set_cleancommand(chat_id, False)
        await message.reply_text("Disabled command cleaning successfully!")
        return "DISABLED_COMMAND_CLEANING", None, None

    if not args:
        status_text = "enabled" if check else "disabled"
        await message.reply_text(
            f"Command cleaning is currently **{status_text}** in this chat."
        )
        return

    first_arg = args[0]
    if first_arg in ("on", "yes", "true", "enable"):
        if not check:
            await set_cleancommand(chat_id, True)
            await message.reply_text("Command cleaning enabled!")
            return "ENABLED_COMMAND_CLEANING", None, None
        return await message.reply_text(
            "Command cleaning has been already enabled in this chat!"
        )
    elif first_arg in ("off", "no", "false", "disable"):
        if not check:
            return await message.reply_text(
                "Command cleaning has been already disabled in this chat!"
            )
        await set_cleancommand(chat_id, False)
        await message.reply_text("Disabled command cleaning successfully!")
        return "DISABLED_COMMAND_CLEANING", None, None
    else:
        await usage_string(message, _cleancommand)
        return


@Client.on_message(filters.group | filters.private, group=16)
async def _delmessage(_, message):
    if not message.chat:
        return
    chat_id = message.chat.id
    if not await get_cleancommand_cached(chat_id):
        return
    entities = message.entities or message.caption_entities
    if not entities:
        return
    try:
        first_entity = entities[0]
        if first_entity.offset == 0 and first_entity.type == MessageEntityType.BOT_COMMAND:
            await message.delete()
    except MessageDeleteForbidden:
        pass
    except RPCError:
        pass
    except Exception:
        pass

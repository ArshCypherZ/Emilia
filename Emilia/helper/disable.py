from telethon import types

from Emilia import LOGGER
from Emilia.functions.admins import is_admin
from Emilia.helper.chat_status import isBotCan, isUserAdmin
from Emilia.mongo.disable_mongo import get_disabled, get_disabledel


def disable(func):
    async def wrapper(*args, **kwargs):
        if len(args) == 2:
            LOGGER.error("meow")
            client, message = args  # for pyrogram
            if not message.text.split():
                return
            if not await isUserAdmin(message, silent=True):
                LOGGER.error("gay")
                chat_id = message.chat.id
                command = (message.text.split()[0])[1:]
                DISABLED_LIST = await get_disabled(chat_id)
                if any(command in key.split("|") for key in DISABLED_LIST):
                    if await get_disabledel(chat_id) and not await isBotCan(
                        message, privileges="can_delete_messages"
                    ):
                        await message.delete()
                        return
                    else:
                        return
                else:
                    await func(client, message)
            else:
                await func(client, message)
        elif len(args) == 1:
            message = args[0]  # for telethon
            if message.entities:
                if not isinstance(message.entities[0], types.MessageEntityBotCommand):
                    return
            elif not message.text.startswith("!"):
                return
            if not await is_admin(message, message.sender_id):
                chat_id = message.chat_id
                command = (message.text.split()[0])[1:]
                DISABLED_LIST = await get_disabled(chat_id)
                if any(command in key.split("|") for key in DISABLED_LIST):
                    if (
                        await get_disabledel(chat_id)
                        and message.chat.admin_rights
                        and not message.chat.admin_rights.delete_messages
                    ):
                        await message.delete()
                        return
                    else:
                        return
                else:
                    await func(message)
            else:
                await func(message)
        else:
            LOGGER.error("3")
            raise TypeError("Invalid number of arguments for the disable function")

    return wrapper

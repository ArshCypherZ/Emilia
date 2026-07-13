from Emilia import LOGGER
from Emilia.helper.chat_status import isBotCan, isUserAdmin
from Emilia.mongo.disable_mongo import get_disabled, get_disabledel


def disable(func):
    async def wrapper(*args, **kwargs):
        if len(args) != 2:
            raise TypeError("Invalid number of arguments for the disable function")
        client, message = args  # for pyrogram
        if not message.text.split():
            return
        if not await isUserAdmin(message, silent=True):
            chat_id = message.chat.id
            # Strip the trigger char and any "@BotUsername" suffix, and
            # lowercase to match the case-insensitive command filter.
            command = message.text.split()[0][1:].split("@", 1)[0].lower()
            DISABLED_LIST = await get_disabled(chat_id)
            if command in DISABLED_LIST:
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

    return wrapper

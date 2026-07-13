from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import CheckAdmins
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.welcome_mongo import GetCleanWelcome, SetCleanWelcome

CLEAN_WELCOME_TRUE = ["on", "yes"]
CLEAN_WELCOME_FALSE = ["off", "no"]


@Client.on_message(custom_filter.command(commands="cleanwelcome"))
async def CleanWelcome(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if not await CheckAdmins(message):
        return

    command = message.text.split(" ")
    if not (len(command) == 1):
        get_args = command[1]
        if get_args in CLEAN_WELCOME_TRUE:
            clean_welcome = True
            await SetCleanWelcome(chat_id, clean_welcome)
            await message.reply(
                "I'll be deleting all old welcome/goodbye messages from now on!",
                )

        elif get_args in CLEAN_WELCOME_FALSE:
            clean_welcome = False
            await SetCleanWelcome(chat_id, clean_welcome)
            await message.reply("I'll leave old welcome/goodbye messages.")

    elif len(command) == 1:
        if await GetCleanWelcome(chat_id):
            CleanMessage = (
                "I am currently deleting old welcome messages when new members join."
            )
        else:
            CleanMessage = "I am not currently deleting old welcome messages when new members join."

        await message.reply(
            (
                f"{CleanMessage}\n\n"
                "To change this setting, try this command again followed by one of yes/no/on/off"
            ),
            )

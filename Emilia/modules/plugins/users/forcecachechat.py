from pyrogram import Client, enums

from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.mongo.users_mongo import add_chat


@Client.on_message(custom_filter.command(commands="forcecachechat"))
async def forcecachechat(client, message):
    chat_id = message.chat.id
    chat_title = message.chat.title

    if message.chat.type == enums.ChatType.PRIVATE:
        await message.reply(
            "This command is made to be used in group chats, not in pm!"
        )
        return

    if not await isUserAdmin(message):
        return

    await add_chat(chat_id, chat_title)
    await message.reply("I've exported your chat's data to my database.")

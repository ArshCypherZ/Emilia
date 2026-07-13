from pyrogram import Client, enums, filters

from Emilia.helper.forward_origin import fwd_user
from Emilia.mongo.users_mongo import add_chat, add_user


@Client.on_message(filters.all & filters.group & ~filters.user(777000), group=1)
async def logger(client, message):
    chat_id = message.chat.id
    chat_title = message.chat.title
    await add_chat(chat_id, chat_title)

    if message.from_user:
        user_id = message.from_user.id
        username = message.from_user.username
        await add_user(user_id, username, chat_id, chat_title)

    if message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
        username = message.reply_to_message.from_user.username

        await add_user(user_id, username, chat_id, chat_title)

    fwd = fwd_user(message)
    if fwd:
        await add_user(fwd.id, fwd.username, forwarded=True)


@Client.on_message(filters.all & ~filters.group & ~filters.user(777000))
async def pvtlogger(client, message):
    if message.chat.type == enums.ChatType.PRIVATE:
        username = message.from_user.username or None
        await add_user(message.from_user.id, username, forwarded=True)

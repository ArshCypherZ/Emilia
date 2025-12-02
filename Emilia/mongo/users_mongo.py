import datetime

from Emilia import db
from Emilia.utils.write_buffer import WriteBuffer

users = db.users
chats = db.chats

WRITE_BUFFER = WriteBuffer()


async def add_user(
    user_id, username=None, chat_id=None, chat_title=None, Forwared=False, bot_id=None
):
    await WRITE_BUFFER.add_user(
        user_id, username, chat_id, chat_title, forwarded=Forwared, bot_id=bot_id
    )


async def add_chat(chat_id, chat_title, bot_id=None):
    await WRITE_BUFFER.add_chat(chat_id, chat_title, bot_id)


async def GetChatName(chat_id):
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "chat_title": 1})
    return doc.get("chat_title") if doc else None

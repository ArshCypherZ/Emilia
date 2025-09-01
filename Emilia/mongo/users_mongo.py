import datetime

from Emilia import db

users = db.users
chats = db.chats

first_found_date = datetime.datetime.now()


async def add_user(
    user_id, username=None, chat_id=None, chat_title=None, Forwared=False
):
    # Upsert basic user and optionally add chat via $addToSet
    update_doc = {
        "$set": {"username": username},
        "$setOnInsert": {"first_found_date": first_found_date},
    }

    if not Forwared and chat_id is not None:
        # Avoid path conflict by not setting 'chats' in $setOnInsert when using $addToSet
        update_doc["$addToSet"] = {
            "chats": {"chat_id": chat_id, "chat_title": chat_title}
        }

    await users.update_one({"user_id": user_id}, update_doc, upsert=True)


async def add_chat(chat_id, chat_title):
    await chats.update_one(
        {"chat_id": chat_id},
        {
            "$set": {"chat_title": chat_title},
            "$setOnInsert": {"first_found_date": first_found_date},
        },
        upsert=True,
    )


async def GetChatName(chat_id):
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "chat_title": 1})
    return doc.get("chat_title") if doc else None

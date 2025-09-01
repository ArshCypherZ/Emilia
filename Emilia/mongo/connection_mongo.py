import datetime

from Emilia import db

connection = db.connection
chats = db.chats

first_found_date = datetime.datetime.now()


async def connectDB(user_id, chat_id):
    await connection.update_one(
        {"user_id": user_id},
        {"$set": {"connection": True, "connected_chat": chat_id}},
        upsert=True,
    )


async def GetConnectedChat(user_id):
    doc = await connection.find_one({"user_id": user_id}, {"_id": 0, "connected_chat": 1})
    return doc.get("connected_chat") if doc else None


async def isChatConnected(user_id) -> bool:
    doc = await connection.find_one({"user_id": user_id}, {"_id": 0, "connection": 1})
    return doc.get("connection", False) if doc else False


async def disconnectChat(user_id):
    await connection.update_one({"user_id": user_id}, {"$set": {"connection": False}}, upsert=True)


async def reconnectChat(user_id):
    await connection.update_one({"user_id": user_id}, {"$set": {"connection": True}}, upsert=True)


async def allow_collection(chat_id, chat_title, allow_collection):
    await chats.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "chat_title": chat_title,
                "allow_collection": allow_collection,
            },
            "$setOnInsert": {"first_found_date": first_found_date},
        },
        upsert=True,
    )


async def get_allow_connection(chat_id) -> bool:
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "allow_collection": 1})
    return doc.get("allow_collection", False) if doc else False

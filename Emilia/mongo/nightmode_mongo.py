from Emilia import db

nightdb = db.nightmode


async def nightmode_on(chat_id: int):
    return nightdb.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id}}, upsert=True)


async def nightmode_off(chat_id: int):
    return nightdb.delete_one({"chat_id": chat_id})


async def get_nightchats() -> list:
    cursor = nightdb.find({"chat_id": {"$lt": 0}}, {"_id": 0, "chat_id": 1})
    chats_list = []
    async for doc in cursor:
        chats_list.append(doc)
    return chats_list

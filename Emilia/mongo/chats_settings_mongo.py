from Emilia import db

chats = db.chats


async def anonadmin_db(chat_id, arg):
    await chats.update_one({"chat_id": chat_id}, {"$set": {"anon_admin": arg}}, upsert=True)


async def get_anon_setting(chat_id) -> bool:
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "anon_admin": 1})
    return doc.get("anon_admin", False) if doc else False

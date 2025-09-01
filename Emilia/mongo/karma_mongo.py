from Emilia import db

karmadb = db.karma


async def get_karmas_count() -> dict:
    chats_count = 0
    karmas_count = 0
    async for chat in karmadb.find({"chat_id": {"$lt": 0}}, {"_id": 0, "karma": 1}):
        karma_map = chat.get("karma", {}) or {}
        for i in karma_map:
            karma_ = karma_map[i].get("karma", 0) or 0
            if karma_ > 0:
                karmas_count += karma_
        chats_count += 1
    return {"chats_count": chats_count, "karmas_count": karmas_count}


m = db.chatlevels


async def user_global_karma(user_id) -> int:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$chat_id", "highest_points": {"$max": "$points"}}},
        {"$sort": {"highest_points": -1}},
        {"$limit": 1},
    ]
    result = await m.aggregate(pipeline).to_list(1)
    return result[0]["highest_points"] if result else 0


async def is_karma_on(chat_id: int) -> bool:
    doc = await karmadb.find_one({"chat_id_toggle": chat_id}, {"_id": 0, "chat_id_toggle": 1})
    return bool(doc)


async def karma_on(chat_id: int):
    await karmadb.update_one({"chat_id_toggle": chat_id}, {"$set": {"chat_id_toggle": chat_id}}, upsert=True)


async def karma_off(chat_id: int):
    await karmadb.delete_one({"chat_id_toggle": chat_id})

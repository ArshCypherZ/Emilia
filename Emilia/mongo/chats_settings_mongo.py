from Emilia import db
from Emilia.utils.cache import anonymous_admin_cache

chats = db.chats


async def anonadmin_db(chat_id, arg):
    await chats.update_one({"chat_id": chat_id}, {"$set": {"anon_admin": arg}}, upsert=True)
    # Update cache
    key = f"anon_admin:{chat_id}"
    await anonymous_admin_cache.set(key, arg)


async def get_anon_setting(chat_id) -> bool:
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "anon_admin": 1})
    return doc.get("anon_admin", False) if doc else False


async def get_anon_setting_cached(chat_id) -> bool:
    key = f"anon_admin:{chat_id}"
    cached = await anonymous_admin_cache.get(key)
    if cached is not None:
        return cached
    
    val = await get_anon_setting(chat_id)
    await anonymous_admin_cache.set(key, val)
    return val

from Emilia import db
from Emilia.utils.cache import SimpleCache

collection = db.autoapprove
cache = SimpleCache(default_ttl=3600, namespace="autoapprove")


async def get_autoapprove_mode(chat_id: int) -> str:
    cached = await cache.get(chat_id)
    if cached is not None:
        return cached

    result = await collection.find_one({"chat_id": chat_id})
    mode = result["mode"] if result else "off"
    
    await cache.set(chat_id, mode)
    return mode


async def set_autoapprove_mode(chat_id: int, mode: str):
    await collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"mode": mode}},
        upsert=True,
    )
    await cache.set(chat_id, mode)

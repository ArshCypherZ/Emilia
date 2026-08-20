from Emilia import db
from Emilia.utils.cache import SimpleCache

cleanerdb = db.cleaner
cleancommand_cache = SimpleCache(default_ttl=600, namespace="cleancommand")


async def set_cleancommand(chat_id: int, enable: bool):
    if enable:
        await cleanerdb.update_one(
            {"chat_id": chat_id}, {"$set": {"clean_command": True}}, upsert=True
        )
    else:
        await cleanerdb.delete_one({"chat_id": chat_id})
    await cleancommand_cache.set(f"cleancommand:{chat_id}", enable)


async def get_cleancommand(chat_id: int) -> bool:
    doc = await cleanerdb.find_one({"chat_id": chat_id})
    if not doc:
        return False
    return bool(doc.get("clean_command", True))


async def get_cleancommand_cached(chat_id: int) -> bool:
    key = f"cleancommand:{chat_id}"
    cached = await cleancommand_cache.get(key)
    if cached is not None:
        return cached

    val = await get_cleancommand(chat_id)
    await cleancommand_cache.set(key, val)
    return val

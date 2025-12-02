from Emilia import db
from Emilia.utils.cache import cached_db_call, locks_cache

locks = db.locks


async def lock_db(chat_id, lock_item):
    # Add item to locked set atomically; create doc if missing
    # First ensure the document exists
    await locks.update_one(
        {"chat_id": chat_id},
        {"$setOnInsert": {"chat_id": chat_id, "lockwarns": True, "allow_list": [], "locked": []}},
        upsert=True,
    )
    # Then add the lock item to the existing document
    await locks.update_one(
        {"chat_id": chat_id},
        {"$addToSet": {"locked": lock_item}},
    )
    # Clear cache after modification
    await locks_cache.delete(f"get_locks:({chat_id},):{{}}")


@cached_db_call(locks_cache, ttl=120)
async def get_locks(chat_id) -> list:
    doc = await locks.find_one({"chat_id": chat_id}, {"_id": 0, "locked": 1})
    return doc.get("locked", []) if doc else []


async def unlock_db(chat_id, locked_item):
    await locks.update_one({"chat_id": chat_id}, {"$pull": {"locked": locked_item}})
    # Clear cache after modification
    await locks_cache.delete(f"get_locks:({chat_id},):{{}}")


async def lockwarns_db(chat_id) -> bool:
    doc = await locks.find_one({"chat_id": chat_id}, {"_id": 0, "lockwarns": 1})
    return doc.get("lockwarns", True) if doc else True


async def set_lockwarn_db(chat_id, warn_args):
    await locks.update_one(
        {"chat_id": chat_id},
        {"$set": {"lockwarns": warn_args}, "$setOnInsert": {"locked": [], "allow_list": []}},
        upsert=True,
    )


async def allowlist_db(chat_id, allowlist_arg):
    # First ensure the document exists
    await locks.update_one(
        {"chat_id": chat_id},
        {"$setOnInsert": {"chat_id": chat_id, "locked": [], "lockwarns": True, "allow_list": []}},
        upsert=True,
    )
    # Then add the allowlist item to the existing document
    await locks.update_one(
        {"chat_id": chat_id},
        {"$addToSet": {"allow_list": allowlist_arg}},
    )


async def rmallow_db(chat_id, allow_arg):
    await locks.update_one({"chat_id": chat_id}, {"$pull": {"allow_list": allow_arg}}, upsert=True)


async def rmallowall_db(chat_id):
    await locks.update_one({"chat_id": chat_id}, {"$set": {"allow_list": []}}, upsert=True)


async def get_allowlist(chat_id) -> list:
    doc = await locks.find_one({"chat_id": chat_id}, {"_id": 0, "allow_list": 1})
    return doc.get("allow_list", []) if doc else []

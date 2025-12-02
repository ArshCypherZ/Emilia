from Emilia import db
from Emilia.utils.cache import cached_db_call, blocklist_cache

blocklists = db.blocklists


async def add_blocklist_db(chat_id, blocklist_text, blocklist_reason):
    # First ensure the document exists
    await blocklists.update_one(
        {"chat_id": chat_id},
        {
            "$setOnInsert": {
                "chat_id": chat_id,
                "blocklist_text": [],
                "blocklist_mode": {"blocklist_mode": 1, "blocklist_time": None},
                "blocklistdelete": True,
                "blocklist_default_reason": None,
            }
        },
        upsert=True,
    )
    # Then add the blocklist entry to the existing document
    await blocklists.update_one(
        {"chat_id": chat_id},
        {
            "$addToSet": {
                "blocklist_text": {
                    "blocklist_text": blocklist_text,
                    "blocklist_reason": blocklist_reason,
                }
            }
        },
    )
    # If an entry with same text exists but different reason, update reason
    await blocklists.update_one(
        {"chat_id": chat_id, "blocklist_text.blocklist_text": blocklist_text},
        {"$set": {"blocklist_text.$.blocklist_reason": blocklist_reason}},
    )
    # Invalidate cache
    await blocklist_cache.delete(f"bl:{chat_id}")


async def rmblocklist_db(chat_id, blocklist_name):
    await blocklists.update_one(
        {"chat_id": chat_id}, {"$pull": {"blocklist_text": {"blocklist_text": blocklist_name}}}
    )
    # Invalidate cache
    await blocklist_cache.delete(f"bl:{chat_id}")


async def unblocklistall_db(chat_id):
    await blocklists.update_one({"chat_id": chat_id}, {"$set": {"blocklist_text": []}}, upsert=True)
    # Invalidate cache
    await blocklist_cache.delete(f"bl:{chat_id}")


async def get_blocklist(chat_id) -> list:
    key = f"bl:{chat_id}"
    cached = await blocklist_cache.get(key)
    if cached is not None:
        return cached

    doc = await blocklists.find_one({"chat_id": chat_id}, {"_id": 0, "blocklist_text": 1})
    data = doc.get("blocklist_text", []) if doc else []
    
    await blocklist_cache.set(key, data, ttl=180)
    return data


async def get_blocklist_reason(chat_id, blocklist_text):
    doc = await blocklists.find_one(
        {"chat_id": chat_id},
        {"_id": 0, "blocklist_text": {"$elemMatch": {"blocklist_text": blocklist_text}}},
    )
    arr = (doc or {}).get("blocklist_text", [])
    if arr:
        return arr[0].get("blocklist_reason")
    return None


async def blocklistMessageDelete(chat_id, blocklistdelete):
    await blocklists.update_one(
        {"chat_id": chat_id},
        {"$set": {"blocklistdelete": blocklistdelete}, "$setOnInsert": {"blocklist_text": [], "blocklist_mode": {"blocklist_mode": 1, "blocklist_time": None}, "blocklist_default_reason": None}},
        upsert=True,
    )


async def getblocklistMessageDelete(chat_id) -> bool:
    doc = await blocklists.find_one({"chat_id": chat_id}, {"_id": 0, "blocklistdelete": 1})
    return doc.get("blocklistdelete", True) if doc else True


async def setblocklistmode(chat_id, blocklist_mode, blocklist_time=None):
    await blocklists.update_one(
        {"chat_id": chat_id},
        {"$set": {"blocklist_mode": {"blocklist_mode": blocklist_mode, "blocklist_time": blocklist_time}}},
        upsert=True,
    )


async def getblocklistmode(chat_id):
    doc = await blocklists.find_one({"chat_id": chat_id}, {"_id": 0, "blocklist_mode": 1, "blocklist_default_reason": 1})
    if doc is not None:
        blocklist_mode = (doc.get("blocklist_mode") or {}).get("blocklist_mode", 1)
        blocklist_time = (doc.get("blocklist_mode") or {}).get("blocklist_time")
        blocklist_default_reason = doc.get("blocklist_default_reason")
        return (blocklist_mode, blocklist_time, blocklist_default_reason)
    else:
        return (1, None, None)


async def setblocklistreason_db(chat_id, reason):
    await blocklists.update_one(
        {"chat_id": chat_id},
        {"$set": {"blocklist_default_reason": reason}, "$setOnInsert": {"blocklist_text": [], "blocklist_mode": {"blocklist_mode": 1, "blocklist_time": None}, "blocklistdelete": True}},
        upsert=True,
    )

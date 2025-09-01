from Emilia import db

nsfwdb = db.nsfw

"""NSFW System"""


async def is_nsfw_on(chat_id: int) -> bool:
    doc = await nsfwdb.find_one({"chat_id": chat_id}, {"_id": 0, "chat_id": 1})
    return not bool(doc)


async def nsfw_on(chat_id: int):
    if await is_nsfw_on(chat_id):
        return
    return await nsfwdb.delete_one({"chat_id": chat_id})


async def nsfw_off(chat_id: int):
    if not await is_nsfw_on(chat_id):
        return
    # Idempotent create; relies on unique index on chat_id
    return await nsfwdb.update_one({"chat_id": chat_id}, {"$setOnInsert": {"chat_id": chat_id}}, upsert=True)

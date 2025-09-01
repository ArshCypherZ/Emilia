from Emilia import db

disable = db.disable


async def disable_db(chat_id, disable_arg):
    await disable.update_one(
        {"chat_id": chat_id}, {"$addToSet": {"disabled_items": disable_arg}}, upsert=True
    )


async def enable_db(chat_id, enable_arg):
    await disable.update_one(
        {"chat_id": chat_id}, {"$pull": {"disabled_items": enable_arg}}, upsert=True
    )


async def get_disabled(chat_id) -> list:
    doc = await disable.find_one({"chat_id": chat_id}, {"disabled_items": 1})
    return doc.get("disabled_items", []) if doc else []


async def disabledel_db(chat_id, disabledel):
    await disable.update_one(
        {"chat_id": chat_id}, {"$set": {"disabledel": bool(disabledel)}}, upsert=True
    )


async def get_disabledel(chat_id) -> bool:
    doc = await disable.find_one({"chat_id": chat_id}, {"disabledel": 1})
    return bool(doc.get("disabledel")) if doc else False

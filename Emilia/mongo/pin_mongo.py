from Emilia import db

pin = db.pin


async def cleanlinked_db(chat_id: int, cleanlinked: bool) -> None:
    # Upsert directly
    await pin.update_one(
        {"chat_id": chat_id}, {"$set": {"cleanlinked": bool(cleanlinked)}}, upsert=True
    )


async def get_cleanlinked(chat_id: int) -> bool:
    doc = await pin.find_one({"chat_id": chat_id}, {"cleanlinked": 1})
    return bool(doc.get("cleanlinked")) if doc else False


async def antichannelpin_db(chat_id: int, antichannelpin: bool) -> None:
    await pin.update_one(
        {"chat_id": chat_id}, {"$set": {"antichannelpin": bool(antichannelpin)}}, upsert=True
    )


async def get_antichannelpin(chat_id: int) -> bool:
    doc = await pin.find_one({"chat_id": chat_id}, {"antichannelpin": 1})
    return bool(doc.get("antichannelpin")) if doc else False

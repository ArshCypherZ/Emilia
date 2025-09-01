import time

from Emilia import db

afk_collection = db.afk


async def set_afk(user_id: int, first_name="User", reason=None):
    await afk_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "first_name": first_name,
                "reason": reason,
                "time": time.time(),
            }
        },
        upsert=True,
    )


async def unset_afk(user_id):
    await afk_collection.delete_one({"user_id": user_id})


async def is_afk(user_id):
    _afk = await afk_collection.count_documents({"user_id": user_id})
    return _afk > 0


async def get_afk_user(user_id):
    _afk = await afk_collection.find_one({"user_id": user_id})
    return _afk if _afk else None

from Emilia import db

birthday_collection = db.birthday


async def set_birthday(user_id: int, day: int, month: int, chat_id: int = None):
    operation = {
        "$set": {
            "day": day,
            "month": month,
        }
    }
    if chat_id:
        operation["$addToSet"] = {"chats": chat_id}

    await birthday_collection.update_one(
        {"user_id": user_id},
        operation,
        upsert=True,
    )


async def get_birthday(user_id: int):
    return await birthday_collection.find_one({"user_id": user_id})


async def delete_birthday(user_id: int):
    await birthday_collection.delete_one({"user_id": user_id})


def get_birthdays_by_date(day: int, month: int):
    """Return a cursor of birthdays on this date; stream it with `async for`
    rather than materializing the whole day's list."""
    return birthday_collection.find({"day": day, "month": month})

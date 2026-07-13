from datetime import datetime, timedelta, timezone

from Emilia import db

settings = db.bot2bot_settings
pending = db.bot2bot_pending


async def get_bot2bot_settings(chat_id: int):
    doc = await settings.find_one({"chat_id": chat_id}, {"_id": 0})
    if not doc:
        return {"mode": "off", "skip_review": False}
    return {
        "mode": doc.get("mode", "off"),
        "skip_review": bool(doc.get("skip_review", False)),
    }


async def set_bot2bot_mode(chat_id: int, mode: str):
    await settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"mode": mode}, "$setOnInsert": {"skip_review": False}},
        upsert=True,
    )


async def set_bot2bot_skip_review(chat_id: int, skip_review: bool):
    await settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"skip_review": skip_review}, "$setOnInsert": {"mode": "off"}},
        upsert=True,
    )


async def add_pending_bot_command(
    token: str,
    chat_id: int,
    message_id: int,
    bot_id: int,
    client_type: str = "pyrogram",
    command_name: str = None,
):
    await pending.update_one(
        {"token": token},
        {
            "$set": {
                "token": token,
                "chat_id": chat_id,
                "message_id": message_id,
                "bot_id": bot_id,
                "client_type": client_type,
                "command_name": command_name,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            }
        },
        upsert=True,
    )


async def get_pending_bot_command(token: str):
    doc = await pending.find_one({"token": token}, {"_id": 0})
    if not doc:
        return None
    if doc.get("expires_at") and doc["expires_at"] < datetime.now(timezone.utc).replace(
        tzinfo=None
    ):
        await pending.delete_one({"token": token})
        return None
    return doc


async def delete_pending_bot_command(token: str):
    await pending.delete_one({"token": token})

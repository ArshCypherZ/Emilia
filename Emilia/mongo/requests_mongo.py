import re
import time
from datetime import datetime, timezone
from typing import Any
from pymongo import ReturnDocument
from Emilia import db

requests_coll = db.requests
settings_coll = db.request_settings
limits_coll = db.request_limits


async def get_settings(chat_id: int) -> dict[str, Any]:
    return await settings_coll.find_one({"_id": chat_id}) or {}


async def update_settings(chat_id: int, updates: dict[str, Any]):
    return await settings_coll.update_one({"_id": chat_id}, {"$set": updates}, upsert=True)


async def add_channel(chat_id: int, ch_id: int, title: str, username: str | None = None) -> bool:
    channel_obj = {"id": ch_id, "title": title, "username": username}
    await settings_coll.update_one(
        {"_id": chat_id},
        {"$pull": {"channels": {"id": ch_id}}},
        upsert=True,
    )
    await settings_coll.update_one(
        {"_id": chat_id},
        {"$push": {"channels": channel_obj}},
        upsert=True,
    )
    return True


async def remove_channel(chat_id: int, ident: str | int) -> bool:
    clean = str(ident).lstrip("@").strip().lower()
    ch_id = int(clean) if (clean.isdigit() or (clean.startswith("-") and clean[1:].isdigit())) else None

    pull_query = [{"username": {"$regex": f"^{re.escape(clean)}$", "$options": "i"}}]
    if ch_id is not None:
        pull_query.append({"id": ch_id})

    res = await settings_coll.update_one(
        {"_id": chat_id},
        {"$pull": {"channels": {"$or": pull_query}}},
    )
    return res.modified_count > 0


async def set_req_limit(chat_id: int, limit: int):
    return await update_settings(chat_id, {"daily_limit": max(0, limit)})


async def get_req_limit(chat_id: int) -> int:
    doc = await get_settings(chat_id)
    return int(doc.get("daily_limit", 0))


async def check_and_increment_daily_limit(chat_id: int, user_id: int, max_limit: int) -> tuple[bool, int]:
    if max_limit <= 0:
        return True, 0

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    limit_id = f"{chat_id}_{user_id}_{today}"

    await limits_coll.update_one(
        {"_id": limit_id},
        {"$setOnInsert": {"count": 0, "chat_id": chat_id, "user_id": user_id, "date": today, "created_at": now}},
        upsert=True,
    )

    doc = await limits_coll.find_one_and_update(
        {"_id": limit_id, "count": {"$lt": max_limit}},
        {"$inc": {"count": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if doc:
        return True, doc.get("count", 1)

    existing = await limits_coll.find_one({"_id": limit_id})
    return False, existing.get("count", max_limit) if existing else max_limit


async def create_request(
    chat_id: int,
    user_id: int,
    user_name: str,
    query: str,
    req_channel: int | None = None,
) -> dict[str, Any]:
    counter = await db.counters.find_one_and_update(
        {"_id": "req"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    num = counter.get("seq", 1)
    doc = {
        "_id": f"req_{num}",
        "num": num,
        "user_id": user_id,
        "user_name": user_name,
        "query": query.strip(),
        "norm_query": query.strip().lower(),
        "chat_id": chat_id,
        "req_channel": req_channel,
        "status": "pending",
        "subscribers": [user_id],
        "created_at": time.time(),
        "post_url": None,
        "reason": None,
    }
    await requests_coll.insert_one(doc)
    return doc


async def find_active_request(query: str, chat_id: int | None = None) -> dict[str, Any] | None:
    q: dict[str, Any] = {"norm_query": query.strip().lower(), "status": "pending"}
    if chat_id:
        q["chat_id"] = chat_id
    return await requests_coll.find_one(q)


async def add_subscriber(req_id: str | int, user_id: int) -> bool:
    target_id = req_id if str(req_id).startswith("req_") else f"req_{req_id}"
    res = await requests_coll.update_one({"_id": target_id}, {"$addToSet": {"subscribers": user_id}})
    return res.modified_count > 0


async def update_request_status(
    req_id: str | int,
    status: str,
    post_url: str | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    target_id = req_id if str(req_id).startswith("req_") else f"req_{req_id}"
    return await requests_coll.find_one_and_update(
        {"_id": target_id},
        {"$set": {"status": status, "post_url": post_url, "reason": reason, "updated_at": time.time()}},
        return_document=ReturnDocument.AFTER,
    )


async def get_user_requests(user_id: int, limit: int = 8) -> list[dict[str, Any]]:
    return await requests_coll.find({"subscribers": user_id}).sort("created_at", -1).limit(limit).to_list(length=limit)


async def get_request(req_id: str | int) -> dict[str, Any] | None:
    clean = str(req_id).lstrip("#").lower().replace("req-", "").replace("req_", "").strip()
    if clean.isdigit():
        doc = await requests_coll.find_one({"num": int(clean)})
        if doc:
            return doc
    return await requests_coll.find_one({"_id": f"req_{clean}"}) or await requests_coll.find_one({"_id": str(req_id)})


async def create_request_indexes():
    await requests_coll.create_index([("num", 1)], unique=True)
    await requests_coll.create_index([("norm_query", 1), ("status", 1)])
    await requests_coll.create_index([("subscribers", 1)])
    await requests_coll.create_index([("chat_id", 1), ("status", 1)])
    await limits_coll.create_index([("created_at", 1)], expireAfterSeconds=86400 * 2)

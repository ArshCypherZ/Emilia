from Emilia import db

filters = db.filters


async def add_filter_db(
    chat_id: int, filter_name: str, content: str, text: str, data_type: int, reply_to_sender: bool = False
):
    # Try to update existing filter by name
    res = await filters.update_one(
        {"chat_id": chat_id, "filters.filter_name": filter_name},
        {
            "$set": {
                "filters.$.filter_name": filter_name,
                "filters.$.content": content,
                "filters.$.text": text,
                "filters.$.data_type": data_type,
                "filters.$.reply_to_sender": reply_to_sender,
            }
        },
    )
    if res.matched_count == 0:
        # First ensure the document exists with an empty filters array
        await filters.update_one(
            {"chat_id": chat_id},
            {"$setOnInsert": {"chat_id": chat_id, "filters": []}},
            upsert=True,
        )
        # Then add the new filter to the existing document
        await filters.update_one(
            {"chat_id": chat_id},
            {
                "$addToSet": {
                    "filters": {
                        "filter_name": filter_name,
                        "content": content,
                        "text": text,
                        "data_type": data_type,
                        "reply_to_sender": reply_to_sender,
                    }
                }
            },
        )


async def stop_db(chat_id: int, filter_name: str):
    await filters.update_one(
        {"chat_id": chat_id}, {"$pull": {"filters": {"filter_name": filter_name}}}
    )


async def stop_all_db(chat_id: id):
    await filters.update_one(
        {"chat_id": chat_id}, {"$set": {"filters": []}}, upsert=True
    )


async def get_filter(chat_id: int, filter_name: str):
    doc = await filters.find_one(
        {"chat_id": chat_id},
        {"_id": 0, "filters": {"$elemMatch": {"filter_name": filter_name}}},
    )
    if doc and doc.get("filters"):
        f = doc["filters"][0]
        return (f.get("filter_name"), f.get("content"), f.get("text"), f.get("data_type"), f.get("reply_to_sender", False))


async def get_filters_list(chat_id: int):
    doc = await filters.find_one({"chat_id": chat_id}, {"_id": 0, "filters.filter_name": 1})
    if doc and doc.get("filters"):
        return [f.get("filter_name") for f in doc["filters"] if f.get("filter_name")]
    else:
        return []

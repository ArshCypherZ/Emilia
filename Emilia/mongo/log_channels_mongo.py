from Emilia import db

log_channels = db.logchannels


async def set_log_db(chat_id, channel_id, channel_title):
    await log_channels.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "channel_id": channel_id,
                "channel_title": channel_title,
                "categories": {
                    "settings": True,
                    "admin": True,
                    "user": True,
                    "automated": True,
                    "reports": True,
                    "other": True,
                },
            }
        },
        upsert=True,
    )


async def unset_log_db(chat_id):
    await log_channels.delete_one({"chat_id": chat_id})


async def get_set_channel(chat_id):
    doc = await log_channels.find_one({"chat_id": chat_id}, {"_id": 0, "channel_title": 1})
    return doc.get("channel_title") if doc else None

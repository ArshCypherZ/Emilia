from Emilia import db

warn_settings = db.warn_settings
user_warnings = db.user_warnings


async def warn_db(chat_id, admin_id, user_id, reason):
    # Determine next warn_id per (chat_id,user_id) by counting existing docs
    # Use retry-on-duplicate to handle concurrent inserts safely under unique index
    attempts = 0
    while attempts < 5:
        attempts += 1
        warn_count = await user_warnings.count_documents({"chat_id": chat_id, "user_id": user_id})
        new_warn_id = warn_count + 1
        try:
            await user_warnings.insert_one(
                {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "admin_id": admin_id,
                    "reason": reason,
                    "warn_id": new_warn_id,
                }
            )
            break
        except Exception as e:
            # Retry on duplicate key error from unique index (code 11000)
            if "E11000" in str(e) or getattr(e, "code", None) == 11000:
                continue
            raise
    # Initialize settings lazily and idempotently
    await warn_settings.update_one(
        {"chat_id": chat_id},
        {
            "$setOnInsert": {
                "chat_id": chat_id,
                "warn_limit": 3,
                "warn_mode": {"warn_mode": 1, "warn_time": None},
            }
        },
        upsert=True,
    )


async def warn_limit(chat_id):
    warn_data = await warn_settings.find_one({"chat_id": chat_id}, {"warn_limit": 1})

    if warn_data is not None:
        return warn_data.get("warn_limit", 3)
    else:
        return 3


async def count_user_warn(chat_id, user_id):
    warn_count = await user_warnings.count_documents({"chat_id": chat_id, "user_id": user_id})
    return warn_count


async def remove_warn(chat_id, user_id, warn_id):
    await user_warnings.delete_one(
        {"chat_id": chat_id, "user_id": user_id, "warn_id": warn_id}
    )


async def set_warn_mode_db(chat_id, warn_mode, time=None):
    await warn_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"warn_mode": {"warn_mode": warn_mode, "warn_time": time}}},
        upsert=True,
    )


async def get_warn_mode(chat_id):
    warn_data = await warn_settings.find_one({"chat_id": chat_id}, {"warn_mode": 1})

    if warn_data is not None and warn_data.get("warn_mode"):
        warn_mode_data = warn_data["warn_mode"]
        warn_mode = warn_mode_data.get("warn_mode", 1)
        warn_mode_time = warn_mode_data.get("warn_time")
        return (warn_mode, warn_mode_time)
    else:
        return (1, None)


async def get_all_warn_reason(chat_id, user_id) -> list:
    warns = user_warnings.find({"chat_id": chat_id, "user_id": user_id}, {"warn_id": 1, "reason": 1})
    REASONS = []
    async for warn in warns:
        warn_id = warn.get("warn_id")
        reason = warn.get("reason") or "Reason wasn't given"
        REASONS.append(f"{warn_id}. {reason}\n")
    return REASONS


async def reset_user_warns(chat_id, user_id):
    await user_warnings.delete_many({"chat_id": chat_id, "user_id": user_id})


async def reset_all_warns_db(chat_id):
    await user_warnings.delete_many({"chat_id": chat_id})


async def set_warn_limit_db(chat_id, warn_limit):
    await warn_settings.update_one(
        {"chat_id": chat_id}, {"$set": {"warn_limit": warn_limit}}, upsert=True
    )

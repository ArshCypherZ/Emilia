"""Migrate the `clone` collection from one-doc-per-user to one-doc-per-bot.

Old shape: {_id: user_id, token, bot_id, bot_username, bot_name}
New shape: {_id: bot_id, owner_id, token, bot_username, bot_name, created_at, status}

Idempotent: docs already carrying `owner_id` are skipped. Run once before
deploying the multi-bot clone system.

    ./venv/bin/python -m scripts.migrate_clone_schema
"""

import asyncio
from datetime import datetime, timezone

from Emilia import db


async def main():
    docs = await db.clone.find({}).to_list(length=None)
    migrated = 0
    for d in docs:
        if "owner_id" in d:
            continue  # already migrated

        bot_id = d.get("bot_id")
        if not bot_id:
            # Recover bot_id from the token if the old doc lacked it.
            try:
                bot_id = int(str(d["token"]).split(":")[0])
            except (KeyError, ValueError, IndexError):
                continue

        new = {
            "_id": bot_id,
            "owner_id": d["_id"],
            "token": d.get("token"),
            "bot_username": d.get("bot_username"),
            "bot_name": d.get("bot_name"),
            "created_at": datetime.now(timezone.utc),
            "status": "running",
        }
        await db.clone.delete_one({"_id": d["_id"]})
        await db.clone.replace_one({"_id": new["_id"]}, new, upsert=True)
        migrated += 1

    total = await db.clone.count_documents({})
    print(f"migrated {migrated} docs; clone collection now holds {total} docs")


if __name__ == "__main__":
    asyncio.run(main())

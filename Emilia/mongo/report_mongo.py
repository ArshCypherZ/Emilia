from Emilia import db

reports = db.reports


async def reports_db(chat_id: int, report_arg: bool):
    await reports.update_one(
        {"chat_id": chat_id}, {"$set": {"reports": report_arg}}, upsert=True
    )


async def get_report(chat_id: int) -> bool:
    doc = await reports.find_one({"chat_id": chat_id}, {"_id": 0, "reports": 1})
    return doc.get("reports", True) if doc else True

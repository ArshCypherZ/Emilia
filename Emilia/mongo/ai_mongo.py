from Emilia import db

chatbotdb1 = db.ai


async def addchat_bot1(chat_id: int):
    await chatbotdb1.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id}}, upsert=True)


async def rmchat_bot1(chat_id: int):
    await chatbotdb1.delete_one({"chat_id": chat_id})

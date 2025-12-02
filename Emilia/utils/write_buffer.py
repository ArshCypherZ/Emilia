import asyncio
import datetime
from pymongo import UpdateOne
from Emilia import db, LOGGER

class WriteBuffer:
    def __init__(self, flush_interval=5):
        self.flush_interval = flush_interval
        self.users_buffer = {}
        self.chats_buffer = {}
        self.lock = asyncio.Lock()
        self.running = False
        self.task = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._loop())
        LOGGER.info("WriteBuffer started.")

    async def stop(self):
        if not self.running:
            return
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self._flush()
        LOGGER.info("WriteBuffer stopped and flushed.")

    async def add_user(self, user_id, username=None, chat_id=None, chat_title=None, forwarded=False, bot_id=None):
        async with self.lock:
            if user_id not in self.users_buffer:
                self.users_buffer[user_id] = {
                    "username": username,
                    "chats": {},
                    "bot_ids": set(),
                }
            
            entry = self.users_buffer[user_id]
            if username:
                entry["username"] = username
            
            if not forwarded and chat_id is not None:
                if chat_id not in entry["chats"]:
                    entry["chats"][chat_id] = {"chat_id": chat_id, "chat_title": chat_title}
                else:
                    if chat_title:
                        entry["chats"][chat_id]["chat_title"] = chat_title
            
            if bot_id:
                entry["bot_ids"].add(bot_id)

    async def add_chat(self, chat_id, chat_title, bot_id=None):
        async with self.lock:
            if chat_id not in self.chats_buffer:
                self.chats_buffer[chat_id] = {
                    "chat_title": chat_title,
                    "bot_ids": set()
                }
            
            entry = self.chats_buffer[chat_id]
            if chat_title:
                entry["chat_title"] = chat_title
            
            if bot_id:
                entry["bot_ids"].add(bot_id)

    async def _loop(self):
        while self.running:
            await asyncio.sleep(self.flush_interval)
            await self._flush()

    async def _flush(self):
        async with self.lock:
            if not self.users_buffer and not self.chats_buffer:
                return
            
            users_to_write = self.users_buffer
            chats_to_write = self.chats_buffer
            self.users_buffer = {}
            self.chats_buffer = {}

        if users_to_write:
            requests = []
            current_time = datetime.datetime.now()

            for user_id, data in users_to_write.items():
                update_doc = {
                    "$set": {"username": data["username"]},
                    "$setOnInsert": {"first_found_date": current_time},
                }
                
                unique_chats = list(data["chats"].values())
                if unique_chats:
                    update_doc["$addToSet"] = {
                        "chats": {"$each": unique_chats}
                    }
                
                if data["bot_ids"]:
                     if "$addToSet" not in update_doc:
                         update_doc["$addToSet"] = {}
                     update_doc["$addToSet"]["bot_ids"] = {"$each": list(data["bot_ids"])}

                requests.append(UpdateOne({"user_id": user_id}, update_doc, upsert=True))
            
            if requests:
                try:
                    await db.users.bulk_write(requests, ordered=False)
                    LOGGER.info(f"Flushed {len(requests)} users to DB.")
                except Exception as e:
                    LOGGER.error(f"Error flushing users buffer: {e}")

        if chats_to_write:
            requests = []
            current_time = datetime.datetime.now()
            for chat_id, data in chats_to_write.items():
                update_doc = {
                    "$set": {"chat_title": data["chat_title"]},
                    "$setOnInsert": {"first_found_date": current_time},
                }
                
                if data["bot_ids"]:
                    update_doc["$addToSet"] = {"bot_ids": {"$each": list(data["bot_ids"])}}
                
                requests.append(UpdateOne({"chat_id": chat_id}, update_doc, upsert=True))

            if requests:
                try:
                    await db.chats.bulk_write(requests, ordered=False)
                    LOGGER.info(f"Flushed {len(requests)} chats to DB.")
                except Exception as e:
                    LOGGER.error(f"Error flushing chats buffer: {e}")
import asyncio
import logging
from pyrogram import Client
from telethon import TelegramClient
from Emilia import API_ID, API_HASH, LOGGER
from Emilia.custom_filter import apply_handlers

class CloneManager:
    def __init__(self):
        self.clones = {}  # {user_id: {'pgram': Client, 'telethn': TelegramClient, 'bot_token': str}}
        self._lock = asyncio.Lock()

    async def start_clone(self, user_id, bot_token, bot_id=None):
        async with self._lock:
            if user_id in self.clones:
                LOGGER.warning(f"Clone for user {user_id} already running.")
                return True, self.clones[user_id]['bot_username'], self.clones[user_id]['bot_name']

            LOGGER.info(f"Starting clone for user {user_id}...")
            
            # Initialize Pyrogram Client
            session_name = f"emilia_clone_{user_id}"
            pgram_client = Client(
                name=session_name,
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=bot_token,
                plugins=dict(root="Emilia/pyro"), # Load same plugins
                sleep_threshold=0
            )
            
            # Initialize Telethon Client
            tele_session_name = f"emilia_clone_{user_id}_tele"
            telethn_client = TelegramClient(tele_session_name, API_ID, API_HASH)

            try:
                # Start Pyrogram
                await pgram_client.start()
                me = pgram_client.me
                bot_username = me.username
                bot_name = me.first_name
                
                # Attach metadata to client instance
                pgram_client.is_clone = True
                pgram_client.owner_id = user_id
                pgram_client.bot_id = me.id

                # Start Telethon
                apply_handlers(telethn_client)
                await telethn_client.start(bot_token=bot_token)
                # Attach metadata to telethon client if needed
                telethn_client.is_clone = True
                telethn_client.owner_id = user_id

                self.clones[user_id] = {
                    'pgram': pgram_client,
                    'telethn': telethn_client,
                    'bot_token': bot_token,
                    'bot_username': bot_username,
                    'bot_name': bot_name,
                    'bot_id': me.id
                }
                
                LOGGER.info(f"Clone started for user {user_id} (@{bot_username})")
                return True, bot_username, bot_name

            except Exception as e:
                LOGGER.error(f"Failed to start clone for user {user_id}: {e}")
                # Cleanup if failed
                try:
                    if pgram_client.is_connected:
                        await pgram_client.stop()
                except: pass
                try:
                    if telethn_client.is_connected():
                        await telethn_client.disconnect()
                except: pass
                return False, None, None

    async def stop_clone(self, user_id):
        async with self._lock:
            if user_id not in self.clones:
                return False
            
            clone_data = self.clones[user_id]
            pgram_client = clone_data['pgram']
            telethn_client = clone_data['telethn']

            LOGGER.info(f"Stopping clone for user {user_id}...")
            try:
                if pgram_client.is_connected:
                    await pgram_client.stop()
                if telethn_client.is_connected():
                    await telethn_client.disconnect()
            except Exception as e:
                LOGGER.error(f"Error stopping clone clients for {user_id}: {e}")
            
            del self.clones[user_id]
            return True

    async def stop_all_clones(self):
        LOGGER.info(f"Stopping all {len(self.clones)} clones...")
        users = list(self.clones.keys())
        for user_id in users:
            await self.stop_clone(user_id)

# Global instance
clone_manager = CloneManager()
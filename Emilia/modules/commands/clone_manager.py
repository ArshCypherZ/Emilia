import asyncio
import os

from pyrogram import Client

from Emilia import API_HASH, API_ID, LOGGER
from Emilia.custom_filter import register_expired_callback_catchall


def _remove_session_files(bot_id):
    """Delete on-disk session files for a clone so the next start is clean.

    A revoked/regenerated token invalidates the stored MTProto session; the
    stale `emilia_clone_<bot_id>.session` then makes `client.start()` fail with
    SESSION_REVOKED forever. Removing it lets a retry re-handshake from scratch.
    """
    name = f"emilia_clone_{bot_id}"
    for suffix in (".session", ".session-journal"):
        path = f"{name}{suffix}"
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            LOGGER.warning(f"Could not remove {path}: {e}")


class CloneManager:
    def __init__(self):
        self.clones = {}  # {bot_id: {'client': Client, 'bot_token': str, ...}}
        self._lock = asyncio.Lock()

    async def start_clone(self, owner_id, bot_token, bot_id):
        async with self._lock:
            if bot_id in self.clones:
                LOGGER.warning(f"Clone {bot_id} already running.")
                return (
                    True,
                    self.clones[bot_id]["bot_username"],
                    self.clones[bot_id]["bot_name"],
                )

            LOGGER.info(f"Starting clone {bot_id} for owner {owner_id}...")

            client = Client(
                name=f"emilia_clone_{bot_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=bot_token,
                plugins=dict(root="Emilia/modules"),
                sleep_threshold=10,
            )

            try:
                # modules/commands/ handlers attach via func.handlers, so
                # smart-plugin discovery (root="Emilia/modules") picks them
                # up automatically; only the expired-callback catchall needs
                # explicit per-client wiring.
                register_expired_callback_catchall(client)
                await client.start()
                me = client.me
                bot_username = me.username
                bot_name = me.first_name

                client.is_clone = True
                client.owner_id = owner_id
                client.bot_id = me.id

                self.clones[bot_id] = {
                    "client": client,
                    "bot_token": bot_token,
                    "owner_id": owner_id,
                    "bot_username": bot_username,
                    "bot_name": bot_name,
                    "bot_id": me.id,
                }

                LOGGER.info(f"Clone {bot_id} started (@{bot_username})")
                return True, bot_username, bot_name

            except Exception as e:
                LOGGER.error(f"Failed to start clone {bot_id}: {e}")
                try:
                    if client.is_connected:
                        await client.stop()
                except Exception:
                    pass
                # Drop the stale session so a later retry starts clean.
                _remove_session_files(bot_id)
                return False, None, None

    async def stop_clone(self, bot_id):
        async with self._lock:
            if bot_id not in self.clones:
                return False

            client = self.clones[bot_id]["client"]
            LOGGER.info(f"Stopping clone {bot_id}...")
            try:
                if client.is_connected:
                    await client.stop()
            except Exception as e:
                LOGGER.error(f"Error stopping clone client {bot_id}: {e}")

            del self.clones[bot_id]
            return True

    async def stop_all_clones(self):
        LOGGER.info(f"Stopping all {len(self.clones)} clones...")
        for bot_id in list(self.clones.keys()):
            await self.stop_clone(bot_id)


# Global instance
clone_manager = CloneManager()

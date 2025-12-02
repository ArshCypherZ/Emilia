import asyncio
import importlib
import traceback
from os.path import dirname
from sys import platform
import os
import signal
import time


from pyrogram import idle
from Emilia import LOGGER, anibot, create_indexes, pgram, telethn, TOKEN

from Emilia.data import HELPABLE, IMPORTED, SUB_MODE, HIDDEN_MOD, USER_INFO
from Emilia.info import ALL_MODULES
from Emilia.pyro.nightmode import start_nightmode_scheduler
from Emilia.utils.helper import j1 as helper_scheduler
from Emilia.tele.clone import clone_start_up, shutdown_all_clones
from Emilia.tele.backup import send as send_backup
from Emilia.helper.http import close_http_clients
from Emilia.mongo.users_mongo import WRITE_BUFFER


HELP_MSG = "Click the button below to get help menu in your pm ~"
START_MSG = "**Hie Senpai ~ UwU** I am well and alive ;)"

HELP_IMG = "https://images-cdn.9gag.com/photo/aXvvrdz_700b.jpg"
START_IMG = "https://image.myanimelist.net/ui/5LYzTBVoS196gvYvw3zjwNzKv3dEGU_pTR8jQb-vfgTLHxH8jxREmQF_Ct58ke7N"

def import_modules():
    cdir = dirname(__file__)
    path_dirSec = "/" if platform in ["linux", "linux2"] else "\\"

    LOGGER.info("Importing modules... length: {}".format(len(ALL_MODULES)))
    
    for mode in ALL_MODULES:
        module = mode.replace(cdir, "").replace(path_dirSec, ".")
        try:
            if module not in IMPORTED:
                LOGGER.info(f"Importing module: {module}")
                imported_module = importlib.import_module("Emilia" + module)

                if not hasattr(imported_module, "__mod_name__"):
                    imported_module.__mod_name__ = imported_module.__name__

                if imported_module.__mod_name__.lower() not in IMPORTED:
                    IMPORTED[imported_module.__mod_name__.lower()] = imported_module
                else:
                    raise Exception("Can't have two modules with the same name!")

                if hasattr(imported_module, "__help__") and imported_module.__help__:
                    HELPABLE[imported_module.__mod_name__.lower()] = imported_module
                    LOGGER.info(f"Module {imported_module.__mod_name__} added to HELPABLE.")
                if hasattr(imported_module, "__sub_mod__") and imported_module.__sub_mod__:
                    SUB_MODE[imported_module.__mod_name__.lower()] = imported_module
                    LOGGER.info(f"Module {imported_module.__mod_name__} added to SUB_MODE.")
                if hasattr(imported_module, "__hidden__") and imported_module.__hidden__:
                    HIDDEN_MOD[imported_module.__mod_name__.lower()] = imported_module
                    LOGGER.info(f"Module {imported_module.__mod_name__} added to HIDDEN_MOD.")
                if hasattr(imported_module, "__user_info__") and imported_module.__user_info__:
                    USER_INFO.append(imported_module.__user_info__)
                    LOGGER.info(f"User info from {imported_module.__mod_name__} added to USER_INFO.")
                
                LOGGER.info(f"Module {imported_module.__mod_name__} imported successfully.")
            

        except Exception as e:
            LOGGER.error(f"Failed to import {module}: {e}")
            traceback.print_exc()
        
    LOGGER.info("All modules imported successfully.")

async def start_anibot():
    try:
        await anibot.start()
        LOGGER.info("Anibot client started successfully.")
    except Exception as e:
        LOGGER.error(f"Failed to start anibot client: {e}")

async def start_pgram():
    try:
        await pgram.start()
        LOGGER.info("Pgram client started successfully.")
        await idle()
        LOGGER.info("Pgram client stopped.")
    except Exception as e:
        LOGGER.error(f"Failed to start pgram client: {e}")

async def stop_telethon():
    try:
        if telethn and telethn.is_connected():
            LOGGER.info("Stopping Telethon client...")
            await telethn.disconnect()
            await asyncio.sleep(0.1)
            LOGGER.info("Telethon client stopped.")
    except Exception as e:
        LOGGER.error(f"Error during Telethon shutdown: {e}")


def stop_telethon_sync():
    try:
        if not telethn:
            return
        connected = False
        try:
            connected = telethn.is_connected()
        except Exception:
            connected = True
        if not connected:
            return
        LOGGER.info("Stopping Telethon client...")
        loop = getattr(telethn, "_loop", None) or asyncio.get_event_loop()
        fut = asyncio.run_coroutine_threadsafe(telethn.disconnect(), loop)
        try:
            fut.result(timeout=5)
        except Exception as e:
            LOGGER.error(f"Error during Telethon shutdown: {e}")
        else:
            LOGGER.info("Telethon client stopped.")
    except Exception as e:
        LOGGER.error(f"Error stopping Telethon client: {e}")


async def main():

    await create_indexes()

    import_modules()
    LOGGER.info("All modules loaded.")

    start_nightmode_scheduler(pgram)
    helper_scheduler.start()
    LOGGER.info("Schedulers started successfully.")

    from Emilia.utils.cache import start_cache_cleanup

    async def _delayed_backup():
        try:
            await asyncio.sleep(10)
            await send_backup()
            LOGGER.info("Startup backup completed.")
        except asyncio.CancelledError:
            LOGGER.info("Startup backup task cancelled during shutdown.")
        except Exception:
            LOGGER.error("Startup backup failed")
    
    asyncio.create_task(start_cache_cleanup())

    try:
        from Emilia.functions.admins import start_admin_cache_task
        asyncio.create_task(start_admin_cache_task())
        LOGGER.info("Started admin cache update task.")
    except Exception as e:
        LOGGER.error(f"Failed to start admin cache task: {e}")

    try:
        from Emilia.tele.levels import start_levels_flush_task
        asyncio.create_task(start_levels_flush_task(5.0))
        LOGGER.info("Started periodic levels buffer flusher.")
    except Exception as e:
        LOGGER.error(f"Failed to start levels flusher: {e}")

    asyncio.create_task(_delayed_backup())
    
    asyncio.create_task(WRITE_BUFFER.start())



    LOGGER.info("Background tasks have been started.")
    LOGGER.info("Bot is now online and ready!")
    LOGGER.info("Starting Pyrogram clients...")
    
    clone_task = None
    async def delayed_clone_start():
        try:
            await asyncio.sleep(10)
            await clone_start_up()
        except asyncio.CancelledError:
            LOGGER.info("Clone startup task cancelled during shutdown")
            raise
        except Exception as e:
            LOGGER.error(f"Clone startup failed: {e}")
    
    clone_task = asyncio.create_task(delayed_clone_start())
    
    
    await asyncio.gather(start_pgram(), start_anibot())
    LOGGER.info("Pyrogram clients exited.")

    try:
        from Emilia.tele.levels import flush_levels_buffers_now as _flush_levels
        await _flush_levels()
    except Exception as e:
        LOGGER.error(f"Error flushing levels buffers on shutdown: {e}")

    try:
        await WRITE_BUFFER.stop()
    except Exception as e:
        LOGGER.error(f"Error flushing WriteBuffer on shutdown: {e}")


if __name__ == "__main__":
    loop = None
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        LOGGER.info(f"Received signal {sig}, initiating shutdown...")
        if loop and loop.is_running():
            loop.call_soon_threadsafe(shutdown_event.set)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped via KeyboardInterrupt.")
    except Exception:
        err = traceback.format_exc()
        LOGGER.error(err)
    finally:
        if loop and not loop.is_closed():
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(asyncio.sleep(0.1))
        
        try:
            asyncio.run(shutdown_all_clones())
        except Exception as e:
            LOGGER.error(f"Error shutting down clone clients: {e}")
        try:
            from Emilia.tele.chatbot import shutdown_chatbot
            asyncio.run(shutdown_chatbot())
        except Exception as e:
            LOGGER.error(f"Error shutting down chatbot: {e}")
        stop_telethon_sync()
        try:
            asyncio.run(close_http_clients())
        except Exception as e:
            LOGGER.error(f"Error closing helper HTTP clients: {e}")
        
        try:
            from Emilia.utils.cache import locks_cache, admin_cache, blocklist_cache, anonymous_admin_cache, approvals_cache
            async def stop_caches():
                await locks_cache.stop()
                await admin_cache.stop()
                await blocklist_cache.stop()
                await anonymous_admin_cache.stop()
                await approvals_cache.stop()
            
            loop.run_until_complete(stop_caches())
        except Exception as e:
             LOGGER.error(f"Error stopping caches: {e}")

        LOGGER.info("Stopped Services.")
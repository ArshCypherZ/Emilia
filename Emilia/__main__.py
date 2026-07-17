import asyncio
import importlib
import time
import traceback
from os.path import dirname
from sys import platform

try:
    import uvloop
    has_uvloop = True
except ImportError:
    has_uvloop = False
from pyrogram import idle

from Emilia import LOGGER, create_indexes, pgram
from Emilia.data import HELPABLE, HIDDEN_MOD, IMPORTED, SUB_MODE, USER_INFO
from Emilia.helper.http import close_http_clients
from Emilia.info import ALL_MODULES
from Emilia.modules.commands.backup import send as send_backup
from Emilia.modules.commands.clone import (
    clone_health_loop,
    clone_start_up,
    shutdown_all_clones,
)
from Emilia.modules.plugins.nightmode import start_nightmode_scheduler
from Emilia.mongo.users_mongo import WRITE_BUFFER
from Emilia.utils.helper import j1 as helper_scheduler
from Emilia.utils.tasks import spawn

HELP_MSG = "Click the button below to get help menu in your pm ~"
START_MSG = "**Hie Senpai ~ UwU** I am well and alive ;)"

HELP_IMG = "https://images-cdn.9gag.com/photo/aXvvrdz_700b.jpg"
START_IMG = "https://image.myanimelist.net/ui/5LYzTBVoS196gvYvw3zjwNzKv3dEGU_pTR8jQb-vfgTLHxH8jxREmQF_Ct58ke7N"


def import_modules():
    cdir = dirname(__file__)
    path_dirSec = "/" if platform in ["linux", "linux2"] else "\\"

    LOGGER.debug("Importing modules... length: {}".format(len(ALL_MODULES)))

    for mode in ALL_MODULES:
        module = mode.replace(cdir, "").replace(path_dirSec, ".")
        try:
            if module not in IMPORTED:
                LOGGER.debug(f"Importing module: {module}")
                imported_module = importlib.import_module("Emilia" + module)

                if not hasattr(imported_module, "__mod_name__"):
                    imported_module.__mod_name__ = imported_module.__name__

                if imported_module.__mod_name__.lower() not in IMPORTED:
                    IMPORTED[imported_module.__mod_name__.lower()] = imported_module
                else:
                    raise Exception("Can't have two modules with the same name!")

                if hasattr(imported_module, "__help__") and imported_module.__help__:
                    HELPABLE[imported_module.__mod_name__.lower()] = imported_module
                    LOGGER.debug(
                        f"Module {imported_module.__mod_name__} added to HELPABLE."
                    )
                if (
                    hasattr(imported_module, "__sub_mod__")
                    and imported_module.__sub_mod__
                ):
                    SUB_MODE[imported_module.__mod_name__.lower()] = imported_module
                    LOGGER.debug(
                        f"Module {imported_module.__mod_name__} added to SUB_MODE."
                    )
                if (
                    hasattr(imported_module, "__hidden__")
                    and imported_module.__hidden__
                ):
                    HIDDEN_MOD[imported_module.__mod_name__.lower()] = imported_module
                    LOGGER.debug(
                        f"Module {imported_module.__mod_name__} added to HIDDEN_MOD."
                    )
                if (
                    hasattr(imported_module, "__user_info__")
                    and imported_module.__user_info__
                ):
                    USER_INFO.append(imported_module.__user_info__)
                    LOGGER.debug(
                        f"User info from {imported_module.__mod_name__} added to USER_INFO."
                    )

                LOGGER.debug(
                    f"Module {imported_module.__mod_name__} imported successfully."
                )

        except Exception as e:
            LOGGER.error(f"Failed to import {module}: {e}")
            traceback.print_exc()

    LOGGER.info(
        f"Imported {len(IMPORTED)} modules "
        f"({len(HELPABLE)} helpable) out of {len(ALL_MODULES)}."
    )



async def start_pgram():
    # Bounded retry for transient startup network errors; a persistent failure
    # (bad token, etc.) propagates so main() exits nonzero and the supervisor
    # restarts the container instead of leaving a half-alive process.
    # pgram is constructed at import time (Emilia/__init__.py), before this
    # coroutine's loop exists. Client.loop is normally resolved lazily on first
    # use (pyrogram.utils.get_event_loop()); pinning it explicitly, once, to the
    # loop actually driving this retry loop rules out that lazy resolution ever
    # returning a stale loop on a later attempt (the cause of a
    # "Session.recv_worker() ... attached to a different loop" crash seen here).
    pgram.loop = asyncio.get_running_loop()

    from Emilia.custom_filter import flush_pending_handlers

    flush_pending_handlers()

    for attempt in range(1, 4):
        try:
            await pgram.start()
            break
        except Exception as e:
            LOGGER.error(f"Failed to start pgram client (attempt {attempt}/3): {e}")
            if attempt == 3:
                raise
            await asyncio.sleep(5 * attempt)
    LOGGER.info("Pgram client started successfully.")
    try:
        from Emilia.helper.reaction_updates import start_reaction_update_poller

        spawn(start_reaction_update_poller(pgram), name="reaction_update_poller")
    except Exception as e:
        LOGGER.error(f"Failed to start reaction update poller: {e}")
    await idle()
    LOGGER.info("Pgram client stopped.")


async def stop_caches():
    from Emilia.utils.cache import MultiLevelCache

    for cache in list(MultiLevelCache._instances):
        try:
            await cache.stop()
        except Exception as e:
            LOGGER.error(f"Error stopping cache {cache._namespace}: {e}")


async def ensure_redis_master():
    """Self-heal a Redis instance that was flipped into replica mode (e.g. a
    stray REPLICAOF issued against the exposed host-network port). Without
    this, every write silently fails forever after such a hijack, even across
    container restarts, since the role is persisted in the RDB/AOF state."""
    from Emilia import redis_client

    try:
        info = await redis_client.info("replication")
        if info.get("role") != "master":
            LOGGER.warning(
                f"Redis started as role={info.get('role')!r}, forcing REPLICAOF NO ONE."
            )
            await redis_client.replicaof("NO", "ONE")
    except Exception as e:
        LOGGER.error(f"Failed to verify/fix Redis replication role: {e}")


async def main():

    await ensure_redis_master()
    await create_indexes()

    try:
        from scripts.migrate_clone_schema import main as _migrate_clones

        await _migrate_clones()
    except Exception as e:
        LOGGER.error(f"Clone schema migration failed: {e}")

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

    spawn(start_cache_cleanup(), name="cache_cleanup")

    try:
        from Emilia.modules.commands.levels import start_levels_flush_task

        spawn(start_levels_flush_task(5.0), name="levels_flush")
        LOGGER.info("Started periodic levels buffer flusher.")
    except Exception as e:
        LOGGER.error(f"Failed to start levels flusher: {e}")

    spawn(_delayed_backup(), name="delayed_backup")

    spawn(WRITE_BUFFER.start(), name="write_buffer_start")

    from Emilia.modules.commands.clone_manager import clone_manager

    async def _heartbeat():
        import pathlib

        from Emilia import db, redis_client

        while True:
            try:
                await asyncio.sleep(300)

                probe = {"event": "heartbeat", "clones": len(clone_manager.clones)}

                # Mongo ping latency; a failure is the alertable "invisible"
                # signal.
                try:
                    t0 = time.perf_counter()
                    await db.command("ping")
                    probe["mongo_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                except Exception as e:
                    LOGGER.error(f"Heartbeat: Mongo ping failed: {e}")
                    probe["mongo_ms"] = None

                # Redis ping latency.
                try:
                    t0 = time.perf_counter()
                    await redis_client.ping()
                    probe["redis_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                except Exception as e:
                    LOGGER.error(f"Heartbeat: Redis ping failed: {e}")
                    probe["redis_ms"] = None

                # Buffer depths (backpressure visibility).
                try:
                    probe["users_buffer"] = len(WRITE_BUFFER.users_buffer)
                    probe["chats_buffer"] = len(WRITE_BUFFER.chats_buffer)
                except Exception:
                    pass
                try:
                    from Emilia.modules.commands import levels as _levels

                    probe["levels_buffer"] = len(_levels._points_buffer)
                except Exception:
                    pass

                LOGGER.info("heartbeat", extra={"emilia": probe})

                # Liveness file consumed by the container healthcheck (G1/G2).
                try:
                    pathlib.Path("/tmp/emilia_heartbeat").touch()
                except Exception:
                    pass
            except asyncio.CancelledError:
                break
            except Exception:
                LOGGER.error("Heartbeat task error")

    spawn(_heartbeat(), name="heartbeat")

    LOGGER.info("Background tasks have been started.")
    LOGGER.info("Bot is now online and ready!")
    LOGGER.info("Starting Pyrogram clients...")

    clone_task = None
    health_task = None

    async def delayed_clone_start():
        try:
            await asyncio.sleep(10)
            await clone_start_up()
        except asyncio.CancelledError:
            LOGGER.info("Clone startup task cancelled during shutdown")
            raise
        except Exception as e:
            LOGGER.error(f"Clone startup failed: {e}")

    clone_task = spawn(delayed_clone_start(), name="delayed_clone_start")
    health_task = spawn(clone_health_loop(), name="clone_health")

    await start_pgram()
    LOGGER.info("Pyrogram client exited.")

    # ---- ordered async shutdown, all on this same event loop ----
    # pyrogram.idle() (inside start_pgram) already converts SIGTERM/SIGINT into a
    # clean return, after which these cleanups run on the loop the resources are
    # bound to (no cross-loop asyncio.run()).
    from Emilia.modules.commands.chatbot import shutdown_chatbot
    from Emilia.modules.commands.levels import flush_levels_buffers_now as _flush_levels

    for bg_task in (clone_task, health_task):
        if bg_task is not None:
            bg_task.cancel()

    for step, coro in [
        ("levels flush", _flush_levels()),
        ("write buffer", WRITE_BUFFER.stop()),
        ("clones", shutdown_all_clones()),
        ("chatbot", shutdown_chatbot()),
        ("http clients", close_http_clients()),
        ("caches", stop_caches()),
    ]:
        try:
            await coro
        except Exception as e:
            LOGGER.error(f"Shutdown step {step} failed: {e}")

    # AsyncIOScheduler.shutdown() schedules its teardown via
    # loop.call_soon_threadsafe() on the loop it started on (see
    # apscheduler.schedulers.asyncio.run_in_event_loop), so it must run while
    # that loop is still alive. Doing this in the `finally:` below — after
    # uvloop.run()/asyncio.run() has already closed the loop — always raised
    # "Event loop is closed", so it's done here instead, as the last step
    # before this coroutine (and the loop driving it) returns.
    try:
        helper_scheduler.shutdown(wait=False)
    except Exception as e:
        LOGGER.error(f"Error shutting down scheduler: {e}")

    LOGGER.info("Stopped Services.")


if __name__ == "__main__":
    try:
        if has_uvloop:
            uvloop.run(main())
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("Bot stopped via KeyboardInterrupt.")
    finally:
        try:
            from Emilia import _log_listener

            if _log_listener is not None:
                _log_listener.stop()
        except Exception:
            pass

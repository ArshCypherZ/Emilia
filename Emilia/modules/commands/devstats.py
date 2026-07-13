"""Dev-only runtime dashboard: /devstats.

Aggregates system info (psutil), process/service uptime, MongoDB collection
counts, Redis server info, command usage (from metrics.py), and log-level tallies
into a single message. DEV_USERS-gated via @auth.
"""

import time

import psutil
from pyrogram.enums import ParseMode

from Emilia import LOGGER, db, redis_client
from Emilia.custom_filter import auth
from Emilia.helper.admins import get_time
from Emilia.utils import metrics

# Collections worth counting on the dashboard. (label, attribute)
_COLLECTIONS = [
    ("Users", "users"),
    ("Chats", "chats"),
    ("Notes", "notes"),
    ("Filters", "filters"),
    ("Feds", "feds"),
    ("Fbans", "fbans"),
    ("Warns", "user_warnings"),
    ("Blocklists", "blocklists"),
    ("Welcome", "welcome"),
    ("AFK", "afk"),
]


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


async def _system_section() -> str:
    proc = psutil.Process()
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    try:
        load1, load5, load15 = psutil.getloadavg()
        load = f"{load1:.2f} {load5:.2f} {load15:.2f}"
    except (OSError, AttributeError):
        load = "n/a"
    cpu = psutil.cpu_percent(interval=0.3)
    rss = proc.memory_info().rss
    with proc.oneshot():
        threads = proc.num_threads()
        try:
            fds = proc.num_fds()
        except (AttributeError, psutil.Error):
            fds = "n/a"
    return (
        "<b>🖥 System</b>\n"
        f"• CPU: <code>{cpu:.1f}%</code> ({psutil.cpu_count()} cores)\n"
        f"• Load: <code>{load}</code>\n"
        f"• RAM: <code>{_fmt_bytes(vm.used)}/{_fmt_bytes(vm.total)}</code> ({vm.percent:.0f}%)\n"
        f"• Disk: <code>{_fmt_bytes(disk.used)}/{_fmt_bytes(disk.total)}</code> ({disk.percent:.0f}%)\n"
        f"• Proc RSS: <code>{_fmt_bytes(rss)}</code> | threads <code>{threads}</code> | fds <code>{fds}</code>"
    )


async def _uptime_section() -> str:
    now = int(time.time())
    process = await get_time(now - int(metrics.PROCESS_START))
    sys_boot = await get_time(now - int(psutil.boot_time()))
    return (
        "<b>⏱ Uptime</b>\n"
        f"• Process: <code>{process}</code>\n"
        f"• Host: <code>{sys_boot}</code>"
    )


async def _clones_section() -> str:
    try:
        from Emilia.modules.commands.clone_manager import clone_manager

        n = len(clone_manager.clones)
    except Exception:
        n = "n/a"
    return f"<b>🤖 Clones running:</b> <code>{n}</code>"


async def _db_section() -> str:
    lines = ["<b>🗄 MongoDB</b>"]
    for label, attr in _COLLECTIONS:
        try:
            count = await getattr(db, attr).estimated_document_count()
        except Exception:
            count = "err"
        lines.append(f"• {label}: <code>{count}</code>")
    return "\n".join(lines)


async def _redis_section() -> str:
    try:
        info = await redis_client.info()
        mem = info.get("used_memory_human", "?")
        clients = info.get("connected_clients", "?")
        ops = info.get("instantaneous_ops_per_sec", "?")
        up = info.get("uptime_in_seconds", 0)
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        hitrate = f"{(hits / total * 100):.1f}%" if total else "n/a"
        return (
            "<b>📦 Redis</b>\n"
            f"• Mem: <code>{mem}</code> | clients <code>{clients}</code> | ops/s <code>{ops}</code>\n"
            f"• Hit rate: <code>{hitrate}</code> | uptime <code>{await get_time(up)}</code>"
        )
    except Exception:
        return "<b>📦 Redis</b>\n• <code>unavailable</code>"


async def _usage_section() -> str:
    total = await metrics.total_commands()
    day = await metrics.commands_in_days(1)
    week = await metrics.commands_in_days(7)
    month = await metrics.commands_in_days(30)
    top = await metrics.top_commands(10)
    lines = [
        "<b>📊 Command usage</b>",
        f"• Total: <code>{total}</code>",
        f"• 24h: <code>{day}</code> | 7d: <code>{week}</code> | 30d: <code>{month}</code>",
    ]
    if top:
        lines.append("• Top:")
        for name, cnt in top:
            lines.append(f"  – <code>{name}</code>: {cnt}")
    return "\n".join(lines)


async def _errors_section() -> str:
    allt = await metrics.log_counts()
    week = await metrics.log_counts_days(7)
    day = await metrics.log_counts_days(1)
    return (
        "<b>⚠️ Logs (WARN/ERR/CRIT)</b>\n"
        f"• All: <code>{allt['WARNING']}/{allt['ERROR']}/{allt['CRITICAL']}</code>\n"
        f"• 7d: <code>{week['WARNING']}/{week['ERROR']}/{week['CRITICAL']}</code>\n"
        f"• 24h: <code>{day['WARNING']}/{day['ERROR']}/{day['CRITICAL']}</code>"
    )


@auth(pattern="devstats")
async def devstats(client, message):
    # DEV_USERS-gated by @auth — do not loosen.
    msg = await message.reply_text("Gathering stats…")
    sections = []
    for builder in (
        _uptime_section,
        _system_section,
        _clones_section,
        _usage_section,
        _errors_section,
        _db_section,
        _redis_section,
    ):
        try:
            sections.append(await builder())
        except Exception:
            LOGGER.warning(f"devstats: {builder.__name__} failed", exc_info=True)
            sections.append(f"<i>{builder.__name__} failed</i>")
    text = "\n\n".join(sections)
    try:
        await msg.edit_text(
            text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
    except Exception:
        await msg.edit_text("Stats too long or render failed — check logs.")

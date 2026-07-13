"""Lightweight runtime metrics for dev visibility.

Everything is stored in Redis so numbers are shared across the main bot and any
clone processes. Two write paths:

- Command usage is counted from the async event loop via ``track_command`` using
  the shared async redis client.
- Log levels (WARNING/ERROR/CRITICAL) are counted by ``MetricsLogHandler``,
  which runs inside the logging QueueListener thread (off the event loop), so it
  uses a small dedicated *sync* redis client.

Read helpers used by the ``/devstats`` dashboard aggregate these keys.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from Emilia import redis_client
from Emilia.config import Config

# Process start — used for process uptime independent of psutil.
PROCESS_START = time.time()

_PREFIX = "metrics"
# Keep daily buckets ~40 days so weekly/monthly rollups always have data.
_DAY_TTL = 40 * 86400

_LEVELS = ("WARNING", "ERROR", "CRITICAL")


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _day_keys(n: int) -> list[str]:
    """Return the last ``n`` day keys, most recent first."""
    today = datetime.now(timezone.utc)
    return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]


# --------------------------------------------------------------------------- #
# Command usage (async write path)
# --------------------------------------------------------------------------- #
async def track_command(command: str) -> None:
    """Increment usage counters for ``command``. Best-effort; never raises."""
    if not command:
        return
    day = _today_key()
    try:
        pipe = redis_client.pipeline()
        pipe.incr(f"{_PREFIX}:cmd:total")
        pipe.hincrby(f"{_PREFIX}:cmd:count", command, 1)
        pipe.hincrby(f"{_PREFIX}:cmd:day:{day}", command, 1)
        pipe.expire(f"{_PREFIX}:cmd:day:{day}", _DAY_TTL)
        await pipe.execute()
    except Exception:
        # Metrics must never break command handling.
        pass


# --------------------------------------------------------------------------- #
# Read helpers (async, used by the dashboard)
# --------------------------------------------------------------------------- #
async def total_commands() -> int:
    try:
        val = await redis_client.get(f"{_PREFIX}:cmd:total")
        return int(val) if val else 0
    except Exception:
        return 0


async def top_commands(limit: int = 10) -> list[tuple[str, int]]:
    try:
        data = await redis_client.hgetall(f"{_PREFIX}:cmd:count")
    except Exception:
        return []
    items = sorted(((k, int(v)) for k, v in data.items()), key=lambda x: -x[1])
    return items[:limit]


async def commands_in_days(n: int) -> int:
    """Total commands run across the last ``n`` days."""
    keys = [f"{_PREFIX}:cmd:day:{d}" for d in _day_keys(n)]
    total = 0
    try:
        pipe = redis_client.pipeline()
        for k in keys:
            pipe.hvals(k)
        for vals in await pipe.execute():
            total += sum(int(v) for v in vals)
    except Exception:
        return 0
    return total


async def log_counts() -> dict[str, int]:
    """All-time counts per log level."""
    out = {}
    try:
        pipe = redis_client.pipeline()
        for lvl in _LEVELS:
            pipe.get(f"{_PREFIX}:log:{lvl}")
        for lvl, val in zip(_LEVELS, await pipe.execute()):
            out[lvl] = int(val) if val else 0
    except Exception:
        for lvl in _LEVELS:
            out[lvl] = 0
    return out


async def log_counts_days(n: int) -> dict[str, int]:
    """Counts per log level across the last ``n`` days."""
    out = {lvl: 0 for lvl in _LEVELS}
    keys = [f"{_PREFIX}:log:day:{d}" for d in _day_keys(n)]
    try:
        pipe = redis_client.pipeline()
        for k in keys:
            pipe.hgetall(k)
        for data in await pipe.execute():
            for lvl, val in data.items():
                if lvl in out:
                    out[lvl] += int(val)
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Log-level counting (sync write path, runs in QueueListener thread)
# --------------------------------------------------------------------------- #
_sync_redis = None


def _get_sync_redis():
    global _sync_redis
    if _sync_redis is None:
        import redis as _redis_sync

        _sync_redis = _redis_sync.from_url(
            Config.REDIS_URL,
            password=Config.REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
        )
    return _sync_redis


class MetricsLogHandler(logging.Handler):
    """Counts WARNING/ERROR/CRITICAL records into Redis.

    Attached to the logging QueueListener, so ``emit`` runs on the listener
    thread (not the asyncio loop); a blocking sync redis call is fine here.
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        lvl = record.levelname
        if lvl not in _LEVELS:
            return
        day = _today_key()
        try:
            r = _get_sync_redis()
            pipe = r.pipeline()
            pipe.incr(f"{_PREFIX}:log:{lvl}")
            pipe.hincrby(f"{_PREFIX}:log:day:{day}", lvl, 1)
            pipe.expire(f"{_PREFIX}:log:day:{day}", _DAY_TTL)
            pipe.execute()
        except Exception:
            # Counting failures must never disrupt logging.
            pass

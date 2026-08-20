from Emilia.config import Config
from Emilia.utils.cache import MultiLevelCache

QUEUE_TTL = 7200            # live player state expires if a chat goes idle (2h)
FILE_TTL = 60 * 60 * 24 * 365 * 10  # cached Telegram media (EVENT_LOGS file_id) — permanent
META_TTL = 60 * 60 * 24        # resolved YouTube metadata per query

music_state = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=QUEUE_TTL, namespace="music_q"
)
music_cache = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=FILE_TTL, namespace="music_file_v2"
)
music_meta = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=META_TTL, namespace="music_meta"
)
music_menu = MultiLevelCache(
    Config.REDIS_URL, Config.REDIS_PASSWORD, default_ttl=300, namespace="music_menu"
)


# ---- Queue (upcoming tracks only; now-playing is tracked separately) ----

def _qkey(chat_id) -> str:
    return f"queue:{chat_id}"


def _nkey(chat_id) -> str:
    return f"now:{chat_id}"


async def add_to_queue(chat_id, track):
    q = await music_state.get(_qkey(chat_id)) or []
    q.append(track)
    await music_state.set(_qkey(chat_id), q, ttl=QUEUE_TTL)
    return len(q)


async def add_many_to_queue(chat_id, tracks):
    q = await music_state.get(_qkey(chat_id)) or []
    q.extend(tracks)
    await music_state.set(_qkey(chat_id), q, ttl=QUEUE_TTL)


async def get_queue(chat_id):
    return await music_state.get(_qkey(chat_id)) or []


async def get_now_playing(chat_id):
    return await music_state.get(_nkey(chat_id))


async def set_now_playing(chat_id, track):
    if track is None:
        await music_state.delete(_nkey(chat_id))
    else:
        await music_state.set(_nkey(chat_id), track, ttl=QUEUE_TTL)


async def pop_next(chat_id):
    """Pop the first upcoming track and return it (the next to play)."""
    q = await music_state.get(_qkey(chat_id)) or []
    if not q:
        return None
    nxt = q.pop(0)
    await music_state.set(_qkey(chat_id), q, ttl=QUEUE_TTL)
    return nxt


async def remove_from_queue(chat_id, index: int):
    """Remove an upcoming track by 1-based index. Returns the removed track."""
    q = await music_state.get(_qkey(chat_id)) or []
    if 1 <= index <= len(q):
        removed = q.pop(index - 1)
        await music_state.set(_qkey(chat_id), q, ttl=QUEUE_TTL)
        return removed
    return None


async def clear_queue(chat_id):
    await music_state.set(_qkey(chat_id), [], ttl=QUEUE_TTL)
    await music_state.delete(_nkey(chat_id))


# ---- File-id cache (EVENT_LOGS) ----

async def get_cached_media(video_id, is_video=False):
    return await music_cache.get(f"{video_id}_{is_video}")


async def set_cached_media(video_id, file_id, is_video=False):
    await music_cache.set(f"{video_id}_{is_video}", file_id, ttl=FILE_TTL)




# ---- Query -> metadata cache ----

async def get_cached_meta(norm):
    return await music_meta.get(norm)


async def set_cached_meta(norm, meta):
    await music_meta.set(norm, meta, ttl=META_TTL)


# ---- Chooser menu state (ephemeral, per chat) ----

async def set_menu(chat_id, data):
    await music_menu.set(f"menu:{chat_id}", data, ttl=300)


async def get_menu(chat_id):
    return await music_menu.get(f"menu:{chat_id}")


async def clear_menu(chat_id):
    await music_menu.delete(f"menu:{chat_id}")


async def set_queue_direct(chat_id, queue_list):
    """Directly set the entire queue (used by shuffle)."""
    await music_state.set(f"queue:{chat_id}", queue_list, ttl=QUEUE_TTL)


# ---- Playback message tracking ----

async def set_playback_message_id(chat_id, message_id):
    await music_state.set(f"playback_msg:{chat_id}", message_id, ttl=QUEUE_TTL)


async def get_playback_message_id(chat_id):
    return await music_state.get(f"playback_msg:{chat_id}")


# ---- Loop / Shuffle modes ----

async def set_loop_mode(chat_id, mode: str):
    await music_state.set(f"loop:{chat_id}", mode, ttl=QUEUE_TTL * 4)


async def get_loop_mode(chat_id) -> str:
    val = await music_state.get(f"loop:{chat_id}")
    return val if val in ("off", "one", "all") else "off"


async def set_shuffle_mode(chat_id, enabled: bool):
    await music_state.set(f"shuffle:{chat_id}", bool(enabled), ttl=QUEUE_TTL * 4)


async def get_shuffle_mode(chat_id) -> bool:
    val = await music_state.get(f"shuffle:{chat_id}")
    return bool(val)


# ---- Pause state ----

async def set_paused(chat_id, paused: bool):
    await music_state.set(f"paused:{chat_id}", paused, ttl=QUEUE_TTL)


async def get_paused(chat_id) -> bool:
    val = await music_state.get(f"paused:{chat_id}")
    return bool(val)

import base64
import logging
import sqlite3
import struct
from pathlib import Path

from pyrogram import Client
from pyrogram.storage.storage import Storage
from pyrogram.storage.sqlite_storage import SCHEMA, SQLiteStorage, PROD, TEST
from pytgcalls import PyTgCalls
from pytgcalls.chat_lock import ChatLock

from Emilia import pgram
from Emilia import API_HASH, API_ID, SESSION_STRING

LOGGER = logging.getLogger(__name__)

# A Client built with session_string= is forced onto in-memory peer storage
# (pyrogram's Client picks in_memory=True whenever a session string is given).
# That means the assistant loses every channel access_hash on each restart, so
# pytgcalls can't resolve an already-joined supergroup and Telegram answers
# CHANNEL_INVALID. The auth key lives in the session string; the peer cache
# lives in the storage's `peers` table. By seeding a real .session FILE from
# the string once and then handing pyrogram that file (no session_string), the
# peer cache is written to disk and survives restarts — the cold cache, and the
# CHANNEL_INVALID storm it caused, simply stop happening.
#
# Kept alongside where the app runs so it persists between deploys.
_SESSIONS_DIR = Path(__file__).resolve().parents[5] / "sessions"


def _decode_session_string(session_string: str):
    """Unpack a pyrogram/kurigram session string the same way SQLiteStorage does."""
    n = len(session_string)
    padded = base64.urlsafe_b64decode(session_string + "=" * (-n % 4))
    if n in (Storage.SESSION_STRING_SIZE, Storage.SESSION_STRING_SIZE_64):
        fmt = (
            Storage.OLD_SESSION_STRING_FORMAT
            if n == Storage.SESSION_STRING_SIZE
            else Storage.OLD_SESSION_STRING_FORMAT_64
        )
        dc_id, test_mode, auth_key, user_id, is_bot = struct.unpack(fmt, padded)
        api_id = None
    else:
        dc_id, api_id, test_mode, auth_key, user_id, is_bot = struct.unpack(
            Storage.SESSION_STRING_FORMAT, padded
        )
    return dc_id, api_id, test_mode, auth_key, user_id, is_bot


def _provision_assistant_session(session_string: str, api_id: int) -> str:
    """Seed a persistent .session file from the string; return the client name.

    Idempotent: if a matching file already exists we keep it (and its cached
    peers). If the operator rotated the SESSION_STRING, the auth key won't
    match and we rebuild from the new string. Done synchronously with raw
    sqlite3 so it works even though this module is imported while the event
    loop is already running (the smart-plugin loader pulls it in inside start()).
    """
    dc_id, str_api_id, test_mode, auth_key, user_id, is_bot = _decode_session_string(session_string)
    # Name the file per userbot so distinct assistants never share one file,
    # while the same assistant always maps back to the same (peer-warm) file.
    name = f"music_assistant_{user_id}"
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    db_path = _SESSIONS_DIR / (name + SQLiteStorage.FILE_EXTENSION)

    if db_path.is_file():
        try:
            con = sqlite3.connect(str(db_path))
            row = con.execute("SELECT auth_key, user_id FROM sessions").fetchone()
            con.close()
            if row and row[0] == auth_key and row[1] == user_id:
                return name  # already provisioned; peers on disk are reused
        except Exception:
            pass
        db_path.unlink()  # stale (rotated string) or corrupt → rebuild

    server_address = (TEST if test_mode else PROD)[dc_id]
    port = 80 if test_mode else 443
    con = sqlite3.connect(str(db_path))
    try:
        with con:
            con.executescript(SCHEMA)
            con.execute("INSERT INTO version VALUES (?)", (SQLiteStorage.VERSION,))
            # Column order per SCHEMA: dc_id, server_address, port, api_id,
            # test_mode, auth_key, date, user_id, is_bot.
            con.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    dc_id,
                    server_address,
                    port,
                    str_api_id or api_id,
                    1 if test_mode else 0,
                    auth_key,
                    0,
                    user_id,
                    1 if is_bot else 0,
                ),
            )
    finally:
        con.close()
    LOGGER.info("[Music] Provisioned persistent assistant session at %s", db_path)
    return name


def _build_assistant() -> Client:
    """File-backed assistant with a persistent peer cache.

    There is deliberately no in-memory fallback: the whole point of this module
    is that the peer cache survives restarts, and a silent fallback to the old
    session_string client would quietly bring back the CHANNEL_INVALID bug while
    looking healthy. If we can't provision the persistent session we fail loudly
    at import so the operator fixes the real problem (bad SESSION_STRING, etc.).
    """
    if not SESSION_STRING:
        raise RuntimeError(
            "SESSION_STRING is required for the music assistant but is empty."
        )
    name = _provision_assistant_session(SESSION_STRING, API_ID)
    return Client(name, api_id=API_ID, api_hash=API_HASH, workdir=str(_SESSIONS_DIR))


assistant = _build_assistant()
emilia_call = PyTgCalls(assistant)

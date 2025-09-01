import os
import asyncio
import bson
import shutil
import zipfile
from datetime import datetime
from Emilia import telethn, db, LOGGER, EVENT_LOGS as CHANNEL_ID
from telethon.errors import FloodWaitError

async def dump():
    if not os.path.isdir("backup"):
        os.mkdir("backup")
    path = os.path.join(os.getcwd(), "backup")
    for coll in await db.list_collection_names():
        LOGGER.info(f"Dumping collection: {coll}")
        collection = db[coll]
        file_path = os.path.join(path, f'{coll}.bson')
        # Overwrite each run to avoid unbounded growth
        with open(file_path, 'wb') as f:
            async for doc in collection.find():
                f.write(bson.BSON.encode(doc))
        LOGGER.info(f"Dumped collection to {file_path}")

async def _send_with_retry(path: str, caption: str | None = None, max_retries: int = 5):
    # Use the largest allowed chunk size to minimize RPCs while staying valid
    CHUNK_KB = 512
    for attempt in range(max_retries):
        try:
            await telethn.send_file(
                CHANNEL_ID,
                file=path,
                caption=caption or "",
                force_document=True,
                part_size_kb=CHUNK_KB,
            )
            return True
        except FloodWaitError as e:
            LOGGER.error(f"FloodWait during sending {path}: {e.seconds}s")
            await asyncio.sleep(e.seconds + 2)
        except asyncio.TimeoutError as e:
            LOGGER.error(f"Timeout sending {path} (attempt {attempt+1}/{max_retries}): {e}")
            await asyncio.sleep(5 * (attempt + 1))
        except Exception as e:
            LOGGER.error(f"Attempt {attempt+1}/{max_retries} failed for {path}: {e}")
            await asyncio.sleep(5 * (attempt + 1))
    return False


def _zip_backup_python(backup_dir: str, out_zip: str = "backup.zip") -> bool:
    try:
        try:
            if os.path.exists(out_zip):
                os.remove(out_zip)
        except Exception:
            pass
        # Use deflate with a reasonable compression level
        # compresslevel is supported in Python 3.7+
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, _, files in os.walk(backup_dir):
                for name in files:
                    fpath = os.path.join(root, name)
                    arcname = os.path.relpath(fpath, start=backup_dir)
                    zf.write(fpath, arcname)
        return True
    except Exception as e:
        LOGGER.error(f"Python zip failed: {e}")
        return False

async def send():
    await dump()
    backup_dir = "backup"
    if os.path.isdir(backup_dir):
        LOGGER.info(f"Contents of {backup_dir}: {os.listdir(backup_dir)}")
    else:
        LOGGER.error(f"{backup_dir} directory does not exist")

    out_zip = "backup.zip"
    ok = await asyncio.to_thread(_zip_backup_python, backup_dir, out_zip)
    if not ok:
        LOGGER.error("Failed to create backup archive.")
        return

    try:
        size_mb = os.path.getsize(out_zip) / (1024 * 1024)
    except Exception:
        size_mb = 0
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    caption = f"**Emilia MongoDB Backup**\n**Date**: `{ts}`\n**Size**: `{size_mb:.1f} MB`"

    sent = await _send_with_retry(out_zip, caption)
    if not sent:
        LOGGER.error("Backup upload failed after retries.")

    try:
        if os.path.exists(out_zip):
            os.remove(out_zip)
    except Exception as e:
        LOGGER.error(f"Failed to remove backup zip: {e}")
    try:
        shutil.rmtree("backup")
    except Exception as e:
        LOGGER.error(f"Failed to remove backup directory: {e}")

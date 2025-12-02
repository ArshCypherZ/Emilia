import re

from pyrogram import Client, filters
from urlextract import URLExtract

from Emilia import db
from Emilia.helper.chat_status import isBotAdmin, isUserAdmin
from Emilia.mongo.blocklists_mongo import get_blocklist
from Emilia.pyro.blocklists.checker import blocklist_action
from Emilia.utils.cache import SimpleCache, approvals_cache

collection = db["approve_d"]

# Precompile regex and reuse URL extractor
_WORD_BOUNDARY = r"(?: |^|$|[^\w])"
URL_EXTRACTOR = URLExtract()

# Small caches
# _blocklist_cache removed in favor of centralized Redis cache in get_blocklist

async def _get_blocklist_cached(chat_id: int):
    # Directly call the centralized function which now handles L1/L2 caching + invalidation
    return await get_blocklist(chat_id)

async def _is_approved_cached(chat_id: int, user_id: int) -> bool:
    key = f"appr:{chat_id}:{user_id}"
    val = await approvals_cache.get(key)
    if val is not None:
        return val
    is_approved = await collection.find_one({"user_id": user_id, "chat_id": chat_id}) is not None
    await approvals_cache.set(key, is_approved, ttl=180)
    return is_approved

@Client.on_message(filters.all & filters.group, group=3)
async def blocklist_checker(client, message):
    if not (message.from_user or message.sender_chat):
        return
    chat_id = message.chat.id

    try:
        if not await isBotAdmin(message, silent=True):
            return
        if await isUserAdmin(message, silent=True):
            return
    except BaseException:
        pass

    user_id = message.sender_chat.id if message.sender_chat else message.from_user.id

    if await _is_approved_cached(chat_id, user_id):
        return

    BLOCKLIST_DATA = await _get_blocklist_cached(chat_id)
    if not BLOCKLIST_DATA:
        return

    BLOCKLIST_ITMES = [b["blocklist_text"] for b in BLOCKLIST_DATA]

    message_text = extract_text(message)

    for blitmes in BLOCKLIST_ITMES:
        if "*" in blitmes:
            star_position = blitmes.index("*")
            if star_position > 0 and blitmes[star_position - 1] == "/":
                block_char = blitmes[:star_position]
                URLS = URL_EXTRACTOR.find_urls(message_text or "")
                for url in URLS:
                    if block_char in url:
                        await blocklist_action(client, message, f"{block_char}*")
                        return

            elif star_position + 1 < len(blitmes) and blitmes[star_position + 1] == ".":
                if message.document or message.animation:
                    extensions = blitmes[star_position + 1 :]
                    file_name = None
                    if message.document:
                        file_name = message.document.file_name
                    elif message.animation:
                        file_name = message.animation.file_name
                    if file_name and file_name.endswith(extensions):
                        await blocklist_action(client, message, f"*{extensions}")
                        return
        else:
            if message_text:
                pattern = _WORD_BOUNDARY + re.escape(blitmes) + _WORD_BOUNDARY
                if re.search(pattern, message_text, flags=re.IGNORECASE):
                    await blocklist_action(client, message, blitmes)
                    return


def extract_text(message) -> str:
    return (
        message.text
        or message.caption
        or (message.sticker.emoji if message.sticker else None)
    )

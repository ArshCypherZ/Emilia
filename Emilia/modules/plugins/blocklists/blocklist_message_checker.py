import re
import unicodedata

from pyrogram import Client, filters
from urlextract import URLExtract

from Emilia import LOGGER, db
from Emilia.helper.chat_status import isBotAdmin, isUserAdmin
from Emilia.helper.custom_emoji import extract_emojipack_tokens, is_emojipack_token
from Emilia.modules.plugins.blocklists.checker import blocklist_action
from Emilia.mongo.blocklists_mongo import get_blocklist
from Emilia.utils.cache import approvals_cache

collection = db["approve_d"]

URL_EXTRACTOR = URLExtract()

# Per-chat compiled-pattern cache, invalidated automatically whenever the
# underlying word list changes (keyed by its hash) - avoids recompiling a
# regex per word per message, which doesn't scale with chat count x list size.
_compiled_pattern_cache = {}


def _normalize(text: str) -> str:
    """NFKC-normalize and drop zero-width/format chars so lookalike unicode
    (full-width letters, Cyrillic homoglyphs, zero-width spaces) can't be used
    to sneak a blocklisted word past matching."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _get_compiled_patterns(chat_id: int, items):
    plain_items = tuple(w for w in items if "*" not in w and not is_emojipack_token(w))
    cache_key = hash(plain_items)
    cached = _compiled_pattern_cache.get(chat_id)
    if cached and cached[0] == cache_key:
        return cached[1]

    compiled = [
        (
            word,
            re.compile(
                r"(?<!\w)" + re.escape(_normalize(word)) + r"(?!\w)", re.IGNORECASE
            ),
        )
        for word in plain_items
    ]
    _compiled_pattern_cache[chat_id] = (cache_key, compiled)
    return compiled


async def _get_blocklist_cached(chat_id: int):
    # Directly call the centralized function which now handles L1/L2 caching +
    # invalidation
    return await get_blocklist(chat_id)


async def _is_approved_cached(chat_id: int, user_id: int) -> bool:
    key = f"appr:{chat_id}:{user_id}"
    val = await approvals_cache.get(key)
    if val is not None:
        return val
    is_approved = (
        await collection.find_one({"user_id": user_id, "chat_id": chat_id}) is not None
    )
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
    except Exception as exc:
        LOGGER.warning(f"blocklist_checker admin-check failed in {chat_id}: {exc}")
        return

    user_id = message.sender_chat.id if message.sender_chat else message.from_user.id

    if await _is_approved_cached(chat_id, user_id):
        return

    BLOCKLIST_DATA = await _get_blocklist_cached(chat_id)
    if not BLOCKLIST_DATA:
        return

    BLOCKLIST_ITMES = [b["blocklist_text"] for b in BLOCKLIST_DATA]

    message_text = extract_text(message)
    emojipack_blocklists = {
        item.lower() for item in BLOCKLIST_ITMES if is_emojipack_token(item)
    }
    if emojipack_blocklists:
        message_packs = await extract_emojipack_tokens(client, message)
        for pack in message_packs:
            if pack in emojipack_blocklists:
                await blocklist_action(client, message, pack)
                return

    for blitmes in BLOCKLIST_ITMES:
        if is_emojipack_token(blitmes) or "*" not in blitmes:
            continue
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

    if message_text:
        normalized_text = _normalize(message_text)
        for word, pattern in _get_compiled_patterns(chat_id, BLOCKLIST_ITMES):
            if pattern.search(normalized_text):
                await blocklist_action(client, message, word)
                return


def extract_text(message) -> str:
    return (
        message.text
        or message.caption
        or (message.sticker.emoji if message.sticker else None)
    )

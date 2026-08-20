import re

from pyrogram import Client, enums, filters
from urlextract import URLExtract

from Emilia import db
from Emilia.helper.chat_status import check_bot, isUserAdmin
from Emilia.helper.custom_emoji import extract_emojipack_tokens
from Emilia.helper.forward_origin import fwd_chat, fwd_date, fwd_user
from Emilia.modules.plugins.locks import lock_map
from Emilia.modules.plugins.warnings.warn import warn
from Emilia.mongo.locks_mongo import get_allowlist, get_locks, lockwarns_db
from Emilia.utils.cache import SimpleCache, approvals_cache
from Emilia.modules.plugins.pin.cleanlinked_checker import GetLinkedChannel

collection = db["approve_d"]

# Compile regex patterns once for better performance
PHONE_REGEX = re.compile(r"[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]")
EMAIL_REGEX = re.compile(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+")
# RTL heuristic: any char within known RTL unicode ranges (excluding variation selectors like U+FE0F)
RTL_CHAR_REGEX = re.compile(r"[\u0590-\u08FF\uFB1D-\uFDFD\uFE70-\uFEFC]")

# Cache for URL extractor to avoid recreating it
URL_EXTRACTOR = URLExtract()

# Small TTL caches for locks/allowlist to reduce DB hits per message
_locks_cache = SimpleCache(default_ttl=120, namespace="locks_checker")
_allow_cache = SimpleCache(default_ttl=120, namespace="locks_allow")
_lockwarns_cache = SimpleCache(default_ttl=300, namespace="locks_warns")


async def _get_locks_cached(chat_id: int):
    k = f"locks:{chat_id}"
    v = await _locks_cache.get(k)
    if v is not None:
        return v
    data = await get_locks(chat_id)
    await _locks_cache.set(k, data, ttl=120)
    return data


async def _get_allowlist_cached(chat_id: int):
    k = f"allow:{chat_id}"
    v = await _allow_cache.get(k)
    if v is not None:
        return v
    data = await get_allowlist(chat_id)
    await _allow_cache.set(k, data, ttl=120)
    return data


async def _get_lockwarns(chat_id: int) -> bool:
    k = f"lwarn:{chat_id}"
    v = await _lockwarns_cache.get(k)
    if v is not None:
        return v
    flag = await lockwarns_db(chat_id)
    await _lockwarns_cache.set(k, flag, ttl=300)
    return flag


@Client.on_message(
    filters.all & (filters.group | filters.channel) | filters.new_chat_members, group=4
)
async def locks_checker(client, message):
    chat_id = message.chat.id
    LOCKS_LIST = await _get_locks_cached(chat_id)
    if len(LOCKS_LIST) == 0:
        return

    if 2 in LOCKS_LIST:
        if message.media_group_id:
            await lock_action(client, message, action=2)

    if 3 in LOCKS_LIST:
        if message.audio:
            await lock_action(client, message, action=3)

    if 4 in LOCKS_LIST:
        if message.new_chat_members:
            if await isUserAdmin(message, silent=True):
                return
            for new_member in message.new_chat_members:
                if not await check_bot(
                    message, privileges=["can_delete_messages", "can_restrict_members"]
                ):
                    return
                if await _get_lockwarns(chat_id):
                    reason = "Bot is locked in this chat."
                    await warn(client, message, reason, warn_user=message)

                bot_id = new_member.id
                await client.ban_chat_member(chat_id, bot_id)
                await client.unban_chat_member(chat_id, bot_id)
                await message.delete()

    if 5 in LOCKS_LIST:
        if message.reply_markup:
            await lock_action(client, message, action=5)

    if 6 in LOCKS_LIST:
        if message.text.split():
            await lock_action(client, message, action=6)

    if 7 in LOCKS_LIST:
        reply_fwd_chat = message.reply_to_message and fwd_chat(message.reply_to_message)
        if message.chat and reply_fwd_chat:
            if reply_fwd_chat.type == enums.ChatType.CHANNEL:
                from_user = message.from_user.id
                channel_id = reply_fwd_chat.id
                linked_chat = await GetLinkedChannel(client, chat_id=chat_id)
                if linked_chat == channel_id:
                    chat_member = await client.get_chat_member(
                        chat_id=chat_id, user_id=from_user
                    )
                    if not chat_member.is_member:
                        if not await check_bot(
                            message,
                            privileges=["can_delete_messages", "can_restrict_members"],
                        ):
                            return
                        await message.delete()

    if 8 in LOCKS_LIST:
        if message.contact:
            await lock_action(client, message, action=8)

    if 9 in LOCKS_LIST:
        if message.document:
            await lock_action(client, message, action=9)

    if 10 in LOCKS_LIST:
        if not (message.text or message.caption):
            return

        text = message.text or message.caption
        # Use compiled regex for better performance
        emails = EMAIL_REGEX.findall(text)
        if len(emails) != 0:
            await lock_action(client, message, action=10)

    if 11 in LOCKS_LIST:
        if message.dice:
            await lock_action(client, message, action=11)

    if 12 in LOCKS_LIST:
        if fwd_date(message):
            ALLOW_LIST = await _get_allowlist_cached(chat_id)
            if len(ALLOW_LIST) != 0:
                username = message.from_user.username
                user_id = message.from_user.id

                if not (username in ALLOW_LIST or user_id in ALLOW_LIST):
                    await lock_action(client, message, action=12)
            else:
                await lock_action(client, message, action=12)

    if 13 in LOCKS_LIST:
        fwd_user_13 = fwd_user(message)
        if fwd_user_13 and fwd_user_13.is_bot:
            await lock_action(client, message, action=13)

    if 14 in LOCKS_LIST:
        fwd_chat_14 = fwd_chat(message)
        if fwd_chat_14 and fwd_chat_14.type == enums.ChatType.CHANNEL:
            ALLOW_LIST = await _get_allowlist_cached(chat_id)
            if len(ALLOW_LIST) != 0:
                from_channel_user = fwd_chat_14.username
                from_channel_id = fwd_chat_14.id
                if from_channel_user is None:
                    CHECKER_IN_LIST = from_channel_id in ALLOW_LIST
                else:
                    CHECKER_IN_LIST = (
                        "@" + from_channel_user in ALLOW_LIST
                        or from_channel_id in ALLOW_LIST
                    )

                if not (CHECKER_IN_LIST):
                    await lock_action(client, message, action=14)
            else:
                await lock_action(client, message, action=14)

    if 15 in LOCKS_LIST:
        fwd_user_15 = fwd_user(message)
        if fwd_user_15 and not fwd_user_15.is_bot:
            await lock_action(client, message, action=15)

    if 16 in LOCKS_LIST:
        if message.game:
            await lock_action(client, message, action=16)

    if 17 in LOCKS_LIST:
        if message.animation:
            await lock_action(client, message, action=17)

    if 18 in LOCKS_LIST:
        if message.via_bot:
            ALLOW_LIST = await _get_allowlist_cached(chat_id)
            if len(ALLOW_LIST) != 0:
                via_username = "@" + message.via_bot.username
                via_user_id = message.via_bot.id

                if not (via_username in ALLOW_LIST or via_user_id in ALLOW_LIST):
                    await lock_action(client, message, action=18)
            else:
                await lock_action(client, message, action=18)

    if 19 in LOCKS_LIST:
        if message.text or message.caption:
            text = message.text or message.caption
            # Use cached URL extractor for better performance
            URL_LIST = URL_EXTRACTOR.find_urls(text)
            if len(URL_LIST) == 0:
                return

            TG_INVITELINK = "t.me/joinchat/"
            for link in URL_LIST:
                if TG_INVITELINK in link:
                    await lock_action(client, message, action=19)

    if 20 in LOCKS_LIST:
        if message.location:
            await lock_action(client, message, action=20)

    if 21 in LOCKS_LIST:
        if message.text or message.caption:
            text = message.text or message.caption
            # Use compiled regex for better performance
            PHONE_NOs_LIST = PHONE_REGEX.findall(text)

            if len(PHONE_NOs_LIST) != 0:
                await lock_action(client, message, action=21)

    if 22 in LOCKS_LIST:
        if message.photo:
            await lock_action(client, message, action=22)

    if 23 in LOCKS_LIST:
        if message.poll:
            await lock_action(client, message, action=23)

    if 24 in LOCKS_LIST:
        text = message.text or message.caption

        if text:
            # Lightweight RTL detection via regex on unicode ranges
            if RTL_CHAR_REGEX.search(text) and not text.isdigit():
                await lock_action(client, message, action=24)

    if 25 in LOCKS_LIST:
        if message.sticker:
            await lock_action(client, message, action=25)

    if 26 in LOCKS_LIST:
        if message.text or message.caption:
            await lock_action(client, message, action=26)

    if 27 in LOCKS_LIST:
        text = message.text or message.caption

        if text:
            # Use cached URL extractor for better performance
            URL_LIST = URL_EXTRACTOR.find_urls(text)
            if len(URL_LIST) != 0:
                ALLOW_LIST = await _get_allowlist_cached(chat_id)
                if len(ALLOW_LIST) != 0:
                    for url in URL_LIST:
                        if url not in ALLOW_LIST:
                            await lock_action(client, message, action=27)
                            break
                else:
                    await lock_action(client, message, action=27)

    if 28 in LOCKS_LIST:
        if message.video:
            await lock_action(client, message, action=28)

    if 29 in LOCKS_LIST:
        if message.video_note:
            await lock_action(client, message, action=29)

    if 30 in LOCKS_LIST:
        if message.voice:
            await lock_action(client, message, action=30)

    if lock_map.LocksMap.emojicustom.value in LOCKS_LIST:
        emojipacks = await extract_emojipack_tokens(client, message)
        if emojipacks:
            ALLOW_LIST = set(await _get_allowlist_cached(chat_id))
            if not ALLOW_LIST or any(pack not in ALLOW_LIST for pack in emojipacks):
                await lock_action(
                    client, message, action=lock_map.LocksMap.emojicustom.value
                )

    if lock_map.LocksMap.guestbot.value in LOCKS_LIST:
        if getattr(message, "guest_bot_caller_user", None) or getattr(
            message, "guest_bot_caller_chat", None
        ):
            await lock_action(client, message, action=lock_map.LocksMap.guestbot.value)

    if (
        lock_map.LocksMap.spoiler.value in LOCKS_LIST
        or lock_map.LocksMap.format.value in LOCKS_LIST
        or lock_map.LocksMap.code.value in LOCKS_LIST
    ):
        entities = []
        if message.entities:
            entities.extend(message.entities)
        if message.caption_entities:
            entities.extend(message.caption_entities)
            
        if entities:
            has_spoiler = False
            has_format = False
            has_code = False
            
            for ent in entities:
                if ent.type == enums.MessageEntityType.SPOILER:
                    has_spoiler = True
                elif ent.type in {
                    enums.MessageEntityType.BOLD,
                    enums.MessageEntityType.ITALIC,
                    enums.MessageEntityType.UNDERLINE,
                    enums.MessageEntityType.STRIKETHROUGH,
                    enums.MessageEntityType.BLOCKQUOTE,
                }:
                    has_format = True
                elif ent.type in {enums.MessageEntityType.CODE, enums.MessageEntityType.PRE}:
                    has_code = True
            
            if has_spoiler and lock_map.LocksMap.spoiler.value in LOCKS_LIST:
                await lock_action(client, message, action=lock_map.LocksMap.spoiler.value)
            elif has_format and lock_map.LocksMap.format.value in LOCKS_LIST:
                await lock_action(client, message, action=lock_map.LocksMap.format.value)
            elif has_code and lock_map.LocksMap.code.value in LOCKS_LIST:
                await lock_action(client, message, action=lock_map.LocksMap.code.value)


async def lock_action(client, message, action: int = None, delete: bool = True):
    lock_name = lock_map.LocksMap(action).name
    if await isUserAdmin(message, silent=True):
        return
    # approvals TTL cache
    uid = (
        message.sender_chat.id
        if getattr(message, "sender_chat", None)
        else (message.from_user.id if message.from_user else None)
    )
    if uid is not None:
        key = f"appr:{message.chat.id}:{uid}"
        cached = await approvals_cache.get(key)
        if cached is None:
            cached = (
                await collection.find_one({"user_id": uid, "chat_id": message.chat.id})
                is not None
            )
            await approvals_cache.set(key, cached, ttl=180)
        if cached:
            return
    if not await check_bot(
        message, privileges=["can_delete_messages", "can_restrict_members"]
    ):
        return
    if await _get_lockwarns(message.chat.id):
        reason = f"{lock_name} is locked in this chat."
        await warn(client, message, reason, warn_user=message)
    if delete:
        await message.delete()

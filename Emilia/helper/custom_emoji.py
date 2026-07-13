from typing import Iterable, List, Optional, Set

from pyrogram.enums import MessageEntityType

from Emilia.helper.telegram_api import get_custom_emoji_stickers

EMOJIPACK_PREFIX = "emojipack:"


def normalize_emojipack_name(name: str) -> Optional[str]:
    if not name:
        return None
    name = str(name).strip()
    if not name:
        return None
    if name.lower().startswith(EMOJIPACK_PREFIX):
        name = name.split(":", 1)[1]
    name = name.strip("<> ")
    return name or None


def emojipack_token(name: str) -> Optional[str]:
    normalized = normalize_emojipack_name(name)
    if normalized is None:
        return None
    return f"{EMOJIPACK_PREFIX}{normalized.lower()}"


def is_emojipack_token(value: str) -> bool:
    return bool(value and str(value).lower().startswith(EMOJIPACK_PREFIX))


def extract_custom_emoji_ids_from_message(message) -> List[int]:
    ids = []
    for attr in ("entities", "caption_entities"):
        for entity in getattr(message, attr, None) or []:
            entity_type = getattr(entity, "type", None)
            if entity_type == MessageEntityType.CUSTOM_EMOJI or str(
                entity_type
            ).endswith("CUSTOM_EMOJI"):
                custom_emoji_id = getattr(entity, "custom_emoji_id", None)
                if custom_emoji_id:
                    try:
                        ids.append(int(custom_emoji_id))
                    except (TypeError, ValueError):
                        pass
    return list(dict.fromkeys(ids))


async def get_pack_names_for_custom_emoji_ids(
    client, custom_emoji_ids: Iterable[int]
) -> Set[str]:
    ids = list(dict.fromkeys(int(x) for x in custom_emoji_ids if x))
    if not ids:
        return set()

    stickers = []
    if hasattr(client, "get_custom_emoji_stickers"):
        for i in range(0, len(ids), 200):
            try:
                stickers.extend(
                    await client.get_custom_emoji_stickers(ids[i : i + 200])
                )
            except Exception:
                stickers = []
                break

    if not stickers:
        stickers = await get_custom_emoji_stickers([str(x) for x in ids])

    pack_names = set()
    for sticker in stickers or []:
        if isinstance(sticker, dict):
            set_name = sticker.get("set_name")
        else:
            set_name = getattr(sticker, "set_name", None)
        token = emojipack_token(set_name)
        if token:
            pack_names.add(token)
    return pack_names


async def extract_emojipack_tokens(client, message) -> Set[str]:
    ids = extract_custom_emoji_ids_from_message(message)
    return await get_pack_names_for_custom_emoji_ids(client, ids)


async def extract_emojipack_tokens_from_command_target(client, message) -> Set[str]:
    target = getattr(message, "reply_to_message", None) or message
    return await extract_emojipack_tokens(client, target)

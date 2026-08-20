import asyncio
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Optional

from aiohttp import ClientError

from Emilia import LOGGER, TOKEN
from Emilia.helper.http import get_aiohttp_session

BOT_API_BASE = f"https://api.telegram.org/bot{TOKEN}"


class BotAPIError(RuntimeError):
    pass


async def bot_api_request(
    method: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    timeout: int = 30,
    retries: int = 2,
) -> Any:
    url = f"{BOT_API_BASE}/{method}"
    payload = payload or {}

    last_error = None
    for attempt in range(retries + 1):
        try:
            session = await get_aiohttp_session()
            async with session.post(url, json=payload, timeout=timeout) as resp:
                data = await resp.json(content_type=None)
            if data.get("ok"):
                return data.get("result")

            description = data.get("description", "Unknown Bot API error")
            last_error = BotAPIError(f"{method}: {description}")
            retry_after = (data.get("parameters") or {}).get("retry_after")
            if resp.status == 429 and retry_after is not None and attempt < retries:
                await asyncio.sleep(int(retry_after))
                continue
            if resp.status < 500:
                break
        except (ClientError, asyncio.TimeoutError, BotAPIError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            await asyncio.sleep(0.5 * (attempt + 1))

    LOGGER.warning("Bot API request failed: %s", last_error)
    return None


async def get_updates(
    *,
    offset: Optional[int] = None,
    allowed_updates: Optional[Iterable[str]] = None,
    timeout: int = 50,
    limit: int = 100,
):
    payload: Dict[str, Any] = {"timeout": timeout, "limit": limit}
    if offset is not None:
        payload["offset"] = offset
    if allowed_updates is not None:
        payload["allowed_updates"] = list(allowed_updates)
    return await bot_api_request("getUpdates", payload, timeout=timeout + 10, retries=0)


async def delete_message(chat_id: int, message_id: int) -> bool:
    return bool(
        await bot_api_request(
            "deleteMessage",
            {"chat_id": chat_id, "message_id": message_id},
            retries=1,
        )
    )


async def delete_message_reaction(
    chat_id: int,
    message_id: int,
    *,
    user_id: Optional[int] = None,
    actor_chat_id: Optional[int] = None,
) -> bool:
    payload: Dict[str, Any] = {"chat_id": chat_id, "message_id": message_id}
    if user_id is not None:
        payload["user_id"] = user_id
    if actor_chat_id is not None:
        payload["actor_chat_id"] = actor_chat_id
    return bool(await bot_api_request("deleteMessageReaction", payload, retries=1))


async def delete_all_message_reactions(
    chat_id: int,
    *,
    user_id: Optional[int] = None,
    actor_chat_id: Optional[int] = None,
) -> bool:
    payload: Dict[str, Any] = {"chat_id": chat_id}
    if user_id is not None:
        payload["user_id"] = user_id
    if actor_chat_id is not None:
        payload["actor_chat_id"] = actor_chat_id
    return bool(await bot_api_request("deleteAllMessageReactions", payload, retries=1))


async def get_custom_emoji_stickers(custom_emoji_ids: Iterable[str]):
    ids = [str(x) for x in custom_emoji_ids if x]
    if not ids:
        return []

    result = []
    for i in range(0, len(ids), 200):
        chunk = ids[i : i + 200]
        stickers = await bot_api_request(
            "getCustomEmojiStickers",
            {"custom_emoji_ids": chunk},
            retries=1,
        )
        if stickers:
            result.extend(stickers)
    return result


async def restrict_member_no_reactions(
    chat_id: int,
    user_id: int,
    *,
    can_send_messages: bool = False,
    until_date: Optional[int] = None,
):
    permissions = {
        "can_send_messages": can_send_messages,
        "can_send_media_messages": can_send_messages,
        "can_send_other_messages": can_send_messages,
        "can_send_polls": can_send_messages,
        "can_add_web_page_previews": can_send_messages,
        "can_react_to_messages": can_send_messages,
    }
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "permissions": permissions,
    }
    if until_date is not None:
        payload["until_date"] = int(until_date)
    return await bot_api_request("restrictChatMember", payload, retries=1)


async def send_message(
    chat_id: int,
    text: str,
    *,
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
    link_preview_options: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = None,
):
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_to_message_id is not None:
        payload["reply_parameters"] = {"message_id": reply_to_message_id}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if link_preview_options is not None:
        payload["link_preview_options"] = link_preview_options
    if parse_mode:
        payload["parse_mode"] = parse_mode
    result = await bot_api_request("sendMessage", payload, retries=1)
    if isinstance(result, dict):
        return SimpleNamespace(id=result.get("message_id"), raw=result)
    return result

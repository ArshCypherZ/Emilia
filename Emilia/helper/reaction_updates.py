import asyncio
import re

from Emilia import LOGGER, db
from Emilia.helper.chat_status import _perm, _status, get_chat_member_cached
from Emilia.helper.telegram_api import (
    delete_all_message_reactions,
    delete_message,
    delete_message_reaction,
    get_updates,
)
from Emilia.modules.plugins.locks import lock_map
from Emilia.mongo.blocklists_mongo import get_blocklist
from Emilia.mongo.feds_db import get_chat_fed, get_fban_user
from Emilia.mongo.locks_mongo import get_allowlist, get_locks

REACTION_ALLOWED_UPDATES = ("message_reaction", "guest_message")
_approved = db["approve_d"]
REACTION_LOCK = lock_map.LocksMap.reaction.value
OUTSIDE_REACTION_LOCK = lock_map.LocksMap.outsidereaction.value
GUESTBOT_LOCK = lock_map.LocksMap.guestbot.value


async def start_reaction_update_poller(client):
    offset = None
    LOGGER.info("Starting Bot API reaction/guest update poller.")
    while True:
        try:
            updates = await get_updates(
                offset=offset,
                allowed_updates=REACTION_ALLOWED_UPDATES,
                timeout=50,
            )
            if not updates:
                await asyncio.sleep(1)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                if "message_reaction" in update:
                    await _handle_message_reaction(client, update["message_reaction"])
                elif "guest_message" in update:
                    await _handle_guest_message(client, update["guest_message"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning("Reaction update poller error: %s", exc)
            await asyncio.sleep(3)


async def _is_approved(chat_id: int, user_id: int) -> bool:
    return (
        await _approved.find_one({"chat_id": chat_id, "user_id": user_id}) is not None
    )


async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    member = await get_chat_member_cached(client, chat_id, user_id)
    return bool(member and _status(member) in ("OWNER", "ADMINISTRATOR"))


async def _is_chat_member(client, chat_id: int, user_id: int) -> bool:
    member = await get_chat_member_cached(client, chat_id, user_id)
    return bool(member and _status(member) not in ("LEFT", "BANNED"))


async def _is_restricted_from_reactions(client, chat_id: int, user_id: int) -> bool:
    member = await get_chat_member_cached(client, chat_id, user_id)
    if not member or _status(member) != "RESTRICTED":
        return False

    can_react = _perm(member, "can_react_to_messages")
    if can_react is False:
        return True
    can_send = _perm(member, "can_send_messages")
    return can_send is False


async def _handle_message_reaction(client, reaction_update: dict):
    new_reaction = reaction_update.get("new_reaction") or []
    if not new_reaction:
        return

    chat_id = reaction_update["chat"]["id"]
    message_id = reaction_update["message_id"]
    user = reaction_update.get("user")
    actor_chat = reaction_update.get("actor_chat")
    user_id = user.get("id") if user else None
    actor_chat_id = actor_chat.get("id") if actor_chat else None

    locks = await get_locks(chat_id)
    should_delete = False

    if user_id is not None:
        fed_id = await get_chat_fed(chat_id)
        if fed_id:
            is_fbanned, _, _ = await get_fban_user(fed_id, user_id)
            if is_fbanned:
                try:
                    await client.ban_chat_member(chat_id, user_id)
                except Exception:
                    pass
                await delete_all_message_reactions(chat_id, user_id=user_id)
                return

        if REACTION_LOCK in locks:
            if not await _is_admin(client, chat_id, user_id) and not await _is_approved(
                chat_id, user_id
            ):
                should_delete = True

        if OUTSIDE_REACTION_LOCK in locks and not await _is_chat_member(
            client, chat_id, user_id
        ):
            should_delete = True

        if await _is_restricted_from_reactions(client, chat_id, user_id):
            should_delete = True

    elif actor_chat_id is not None:
        if REACTION_LOCK in locks or OUTSIDE_REACTION_LOCK in locks:
            allowlist = await get_allowlist(chat_id)
            if actor_chat_id not in allowlist:
                should_delete = True

    if should_delete:
        await delete_message_reaction(
            chat_id,
            message_id,
            user_id=user_id,
            actor_chat_id=actor_chat_id,
        )


async def _handle_guest_message(client, message: dict):
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    if not chat_id or not message_id:
        return

    locks = await get_locks(chat_id)
    if GUESTBOT_LOCK in locks:
        allowlist = await get_allowlist(chat_id)
        guest_bot = message.get("from") or {}
        guest_id = guest_bot.get("id")
        guest_username = guest_bot.get("username")
        allowed = guest_id in allowlist or (
            guest_username and f"@{guest_username}" in allowlist
        )
        if not allowed:
            await delete_message(chat_id, message_id)
            return

    text = message.get("text") or message.get("caption") or ""
    if not text:
        return

    blocklist_items = await get_blocklist(chat_id)
    for item in blocklist_items:
        trigger = item.get("blocklist_text")
        if not trigger or str(trigger).startswith("emojipack:"):
            continue
        pattern = r"(?: |^|[^\w])" + re.escape(trigger) + r"(?: |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            await delete_message(chat_id, message_id)
            return

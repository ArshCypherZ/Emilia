"""PYROGRAM privileges"""

from typing import List, Union

from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import PeerIdInvalid, UserNotParticipant
from pyrogram.types import Message

from Emilia import BOT_ID, DEV_USERS, LOGGER
from Emilia.utils.cache import admin_cache

BOT_PERMISSIONS_STRINGS = {
    "can_delete_messages": "Looks like I haven't got the right to delete messages; mind promoting me? Thanks!",
    "can_restrict_members": "could not set telegram chat privileges, so locks have all been unlocked: unable to setChatPermissions: Bad Request: not enough rights to change chat privileges",
    "can_promote_members": "I don't have permission to promote or demote someone in this chat!",
    "can_change_info": "I don't have permission to change the chat title, photo and other settings.",
    "can_pin_messages": "I don't have permission to pin messages in this chat.",
    "can_be_edited": "I don't have enough permission to edit administrator privileges of the user.",
}

USERS_PERMISSIONS_STRINGS = {
    "can_be_edited": "You don't have enough permission to edit adminstrator privileges of the user",
    "can_delete_messages": "You don't have enough permission to delete any messages in the chat.",
    "can_restrict_members": "You don't have enough permission to restrict, ban or unban chat members.",
    "can_promote_members": "You don't have enough permission to add new administrators with a subset of his own privileges or demote administrators that he has promoted, directly or indirectly (promoted by administrators that were appointed by the user).",
    "can_change_info": "You don't have enough permission to change the chat title, photo and other settings.",
    "can_invite_users": "You're not allowed to invite new users to the chat.",
    "can_pin_messages": "You're not allowed to pin messages.",
    "can_send_media_messages": "You're not allowed to send audios, documents, photos, videos, video notes and voice notes.",
    "can_send_stickers": "You're not allowed to send stickers, implies can_send_media_messages.",
    "can_send_animations": "You're not allowed to send animations (GIFs), implies can_send_media_messages.",
    "can_send_games": "You're not allowed to send games, implies can_send_media_messages.",
    "can_use_inline_bots": "You're not allowed to use inline bots, implies can_send_media_messages.",
    "can_add_web_page_previews": "You're not allowed to add web page previews to their messages.",
    "can_send_polls": "You're not allowed to send polls.",
}


def _verified_user_id(message):
    return getattr(message, "_emilia_verified_user_id", None) or getattr(
        message, "_emilia_bot2bot_reviewer_id", None
    )


def _status(member) -> str:
    """Status name for either a cached dict or a fresh ChatMember object."""
    if member is None:
        return ""
    if isinstance(member, dict):
        return member.get("status") or ""
    return member.status.name


def _priv(member, name: str) -> bool:
    """Privilege flag for either a cached dict or a fresh ChatMember object."""
    if member is None:
        return False
    if isinstance(member, dict):
        return bool((member.get("privileges") or {}).get(name, False))
    return bool(member.privileges and getattr(member.privileges, name, False))


def _perm(member, name: str):
    """Restricted-member permission flag (or None if unknown) for dict/object."""
    if member is None:
        return None
    if isinstance(member, dict):
        perms = member.get("permissions")
        return perms.get(name) if perms else None
    perms = getattr(member, "permissions", None)
    return getattr(perms, name, None) if perms else None


async def get_chat_member_cached(client, chat_id: int, user_id: int):
    """Fetches a ChatMember with caching.

    Returns a minimal JSON-serializable dict ({"status", "privileges"}) so the
    L2 (Redis/orjson) cache never has to serialize a live Pyrogram object.
    """
    cache_key = f"chat_member:{chat_id}:{user_id}"

    # L1 + L2 Cache
    cached_member = await admin_cache.get(cache_key)
    if cached_member is not None:
        return cached_member

    # L3 API Call
    try:
        member = await client.get_chat_member(chat_id=chat_id, user_id=user_id)
    except UserNotParticipant:
        # Expected/frequent - the user simply isn't in the chat, not an error.
        return None
    except PeerIdInvalid:
        LOGGER.debug(f"get_chat_member_cached({chat_id},{user_id}): peer not cached yet")
        return None
    except Exception as exc:
        LOGGER.warning(f"get_chat_member_cached({chat_id},{user_id}) failed: {exc}")
        return None

    payload = {
        "status": member.status.name,
        "privileges": (
            {k: v for k, v in vars(member.privileges).items() if isinstance(v, bool)}
            if member.privileges
            else None
        ),
        "permissions": (
            {k: v for k, v in vars(member.permissions).items() if isinstance(v, bool)}
            if getattr(member, "permissions", None)
            else None
        ),
    }
    await admin_cache.set(cache_key, payload, ttl=300)
    return payload


async def isBotAdmin(message: Message, chat_id=None, silent=False) -> bool:
    """This function returns the bot admin status in the chat.

    Args:
        message (Message): Message
        chat_id ([type], optional): pass chat_id: message.chat.id  Defaults to None.
        silent (bool, optional): if True bot will be silent when isBotAdmin returned False. Defaults to False.

    Returns:
        bool: True when bot has chat status is admin
    """
    if chat_id is None:
        chat_id = message.chat.id

    member = await get_chat_member_cached(message._client, chat_id, BOT_ID)

    if not member or _status(member) not in ("OWNER", "ADMINISTRATOR"):
        if not silent:
            await message.reply("I'm not admin here to do that.")
        return False
    else:
        return True


async def isUserAdmin(
    message: Message,
    pm_mode: bool = False,
    user_id: int = None,
    chat_id: int = None,
    silent: bool = False,
) -> bool:
    """This function returns users chat status in the chat.

    Args:
        message (Message): Message
        chat_id (int, optional): chat_id: message.chat.id . Defaults to None.
        silent (bool, optional): if True bot will be silent when its isUserAdmin = returned False. Defaults to False.

    Returns:
        bool: True when user has chat status is admin | creator of the chat.
    """

    if user_id is None:
        verified_user_id = _verified_user_id(message)
        if verified_user_id is not None:
            user_id = verified_user_id
        elif message.sender_chat:
            user_id = message.sender_chat.id
            chat_id = message.chat.id
            if user_id == chat_id:
                return True
        else:
            user_id = message.from_user.id

    if chat_id is not None:
        chat_id = chat_id

    else:
        chat_id = message.chat.id

    if not pm_mode:
        if message.chat.type == ChatType.PRIVATE:
            return True

    member = await get_chat_member_cached(message._client, chat_id, user_id)

    if member and _status(member) in ("OWNER", "ADMINISTRATOR"):
        return True
    else:
        if not silent:
            await message.reply("Only admins can execute this command!")
        return False


async def anon_admin_checker(
    chat_id: int, user_id: int, client, owner_only: bool = False
) -> bool:
    """This function returns user_id chat status

    Returns:
        bool: True when user_id has chat status is admin | creator of chat.
    """
    member = await get_chat_member_cached(client, chat_id, user_id)
    if owner_only:
        return bool(member and _status(member) == "OWNER")
    if not member or _status(member) not in ("OWNER", "ADMINISTRATOR"):
        return False
    else:
        return True


async def can_restrict_member(
    message: Message, user_id: int, chat_id: int = None
) -> bool:
    """This function returns can bot restrict member in the given chat.

    Returns:
        Bool: True is bot can restrict the member.
    """
    if chat_id is None:
        chat_id = message.chat.id

    member = await get_chat_member_cached(message._client, chat_id, user_id)
    if not member:
        return True

    if (_status(member) in ("OWNER", "ADMINISTRATOR")) or user_id in DEV_USERS:
        return False
    else:
        return True


async def isUserCreator(
    message: Message, chat_id: int = None, user_id: int = None
) -> bool:
    """This function returns the creator status of the given chat.

    Returns:
        bool: True when user's chat status is creator.
    """
    if user_id is None:
        verified_user_id = _verified_user_id(message)
        if verified_user_id is not None:
            user_id = verified_user_id
        elif message.sender_chat:
            user_id = message.sender_chat.id
            chat_id = message.chat.id
            if user_id == chat_id:
                return True
        else:
            user_id = message.from_user.id

    if chat_id is not None:
        chat_id = chat_id

    else:
        chat_id = message.chat.id
        if message.chat.type == ChatType.PRIVATE:
            return True

    member = await get_chat_member_cached(message._client, chat_id, user_id)

    if member and _status(member) == "OWNER":
        return True
    else:
        return False


async def isBotCan(
    message: Message,
    chat_id: int = None,
    privileges: str = "can_change_info",
    silent: bool = False,
) -> bool:
    """This function returns privileges of the bot in the  given chat.

    Args:
        message (Message): Message
        chat_id (int, optional): pass chat_id: message.chat.id . Defaults to None.
        privileges (str, optional): Pass permission . Defaults to can_change_info.
        silent (bool, optional): if True bot will be silent if isBotCan returned False. Defaults to False.

    Returns:
        bool: True when Bot has permission of given permission in the chat.
    """
    if chat_id is None:
        chat_id = message.chat.id

    member = await get_chat_member_cached(message._client, chat_id, BOT_ID)

    if member and _priv(member, privileges):
        return True

    # Also check if OWNER (owners can do everything usually, but checking
    # privileges is safer for bots)
    if member and _status(member) == "OWNER":
        return True

    if not silent:
        await message.reply(
            BOT_PERMISSIONS_STRINGS.get(privileges, "I don't have enough rights.")
        )
    return False


async def isUserCan(
    message,
    user_id: int = None,
    chat_id: int = None,
    privileges: str = None,
    silent: bool = False,
) -> bool:
    """This function returns privileges of the user in the chat.

    Returns:
        bool: True when user has permission of given permission in the chat.
    """
    if user_id is None:
        verified_user_id = _verified_user_id(message)
        if verified_user_id is not None:
            user_id = verified_user_id
        elif message.sender_chat:
            user_id = message.sender_chat.id
            chat_id = message.chat.id
            if user_id == chat_id:
                return True
        else:
            user_id = message.from_user.id

    if chat_id is not None:
        chat_id = chat_id

    else:
        chat_id = message.chat.id

    member = await get_chat_member_cached(message._client, chat_id, user_id)

    if user_id in DEV_USERS:
        return True

    if member:
        if _status(member) == "OWNER":
            return True

        # Check privileges
        if _priv(member, privileges):
            return True

    if not silent:
        await message.reply(
            USERS_PERMISSIONS_STRINGS.get(privileges, "You need more rights.")
        )
    return False


async def CheckAllAdminsStuffs(
    message: Message,
    privileges: Union[str, List[str]] = "can_change_info",
    silent=False,
    chat_id=None,
) -> bool:
    """This function checks both bot & user privileges and chat status is the chat.

    Args:
        message (Message): Message
        privileges (Union[str, List[str]], optional): pass permission list or str. Defaults to 'can_change_info'.
        silent (bool, optional): if True bot will be silent in chat. Defaults to False.

    Returns:
        bool: True when user and bot both has chat status is admin.
    """
    if not chat_id:
        chat_id = message.chat.id
    verified_user_id = _verified_user_id(message)
    if message.sender_chat and verified_user_id is None:
        user_id = message.sender_chat.id
        if user_id == chat_id:
            return True
        else:
            return False

    if message.chat.type == ChatType.PRIVATE and not str(chat_id).startswith("-100"):
        await message.reply(
            "This command is made to be used in group chats, not in pm!"
        )
        return False

    if not await isBotAdmin(message, chat_id=chat_id, silent=silent):
        return False

    if not await isUserAdmin(message, chat_id=chat_id, silent=silent):
        return False

    if isinstance(privileges, list):
        for permission in privileges:
            if not await isBotCan(
                message, chat_id=chat_id, privileges=permission, silent=silent
            ):
                return False

            if not await isUserCan(
                message, chat_id=chat_id, privileges=permission, silent=silent
            ):
                return False

    elif isinstance(privileges, str):
        if not await isBotCan(
            message, chat_id=chat_id, privileges=privileges, silent=silent
        ):
            return False

        if not await isUserCan(
            message, chat_id=chat_id, privileges=privileges, silent=silent
        ):
            return False
    return True


async def CheckAdmins(message: Message, silent: bool = False) -> bool:
    """This function checks both bot & user chat status in the chat.

    Args:
        message (Message): Message

    Returns:
        bool: True when both are admins.
    """
    verified_user_id = _verified_user_id(message)
    if message.sender_chat and verified_user_id is None:
        user_id = message.sender_chat.id
        chat_id = message.chat.id

        if user_id == chat_id:
            return True
        else:
            return False

    chat_id = message.chat.id
    if message.chat.type == ChatType.PRIVATE:
        await message.reply(
            "This command is made to be used in group chats, not in pm!"
        )
        return

    if not await isBotAdmin(message, chat_id=chat_id, silent=silent):
        return False

    if not await isUserAdmin(message, chat_id=chat_id, silent=silent):
        return False

    return True


async def isUserBanned(chat_id: int, user_id: int, client) -> bool:
    """This function check is user is banned in this given chat or not.

    Args:
        chat_id (int): chat_id: message.chat.id
        user_id (int): pass the user_id

    Returns:
        bool: True when user is banned in the given chat.
    """
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return bool(member and member.status == ChatMemberStatus.BANNED)


async def check_user(
    message: Message,
    privileges: Union[str, List[str]] = "can_change_info",
    silent: bool = False,
    pm_mode: bool = False,
    chat_id: int = None,
) -> bool:
    """This function check user's chat status as well as user's privileges in the chat.

    Returns:
        bool: True when user's chat status is admin or creator and user has privileges in the chat.
    """
    if not await isUserAdmin(
        message, silent=silent, pm_mode=pm_mode, chat_id=chat_id
    ):
        return False

    if isinstance(privileges, list):
        for permission in privileges:
            if not await isUserCan(
                message, privileges=permission, silent=silent, chat_id=chat_id
            ):
                return False

    elif isinstance(privileges, str):
        if not await isUserCan(
            message, privileges=privileges, silent=silent, chat_id=chat_id
        ):
            return False

    return True


async def check_bot(
    message: Message,
    privileges: Union[str, List[str]] = "can_change_info",
    silent: bool = False,
    chat_id: int = None,
) -> bool:
    """This function check bot's chat status as well as user's privileges in the chat.

    Returns:
        bool: True when bot's chat status is admin and bot has privileges in the chat.
    """
    if not await isBotAdmin(message, silent=silent, chat_id=chat_id):
        return False

    if isinstance(privileges, list):
        for permission in privileges:
            if not await isBotCan(
                message, privileges=permission, silent=silent, chat_id=chat_id
            ):
                return False
    else:
        if not await isBotCan(
            message, privileges=privileges, silent=silent, chat_id=chat_id
        ):
            return False

    return True

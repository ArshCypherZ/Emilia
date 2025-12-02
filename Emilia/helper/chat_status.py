"""PYROGRAM privileges"""

from typing import List, Union

from pyrogram import enums
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import BadRequest
from pyrogram.types import Message

from Emilia import BOT_ID, DEV_USERS

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

    GetData = await message._client.get_chat_member(chat_id=chat_id, user_id=BOT_ID)

    if GetData.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
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
        if message.sender_chat:
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

    global GetData
    try:
        GetData = await message._client.get_chat_member(chat_id=chat_id, user_id=user_id)
    except BadRequest:
        return

    if GetData.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return True
    else:
        if not silent:
            await message.reply("Only admins can execute this command!")
        return False


async def anon_admin_checker(chat_id: int, user_id: int, client) -> bool:
    """This function returns user_id chat status

    Returns:
        bool: True when user_id has chat status is admin | creator of chat.
    """
    GetData = await client.get_chat_member(chat_id=chat_id, user_id=user_id)
    if GetData.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
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

    try:
        GetData = await message._client.get_chat_member(chat_id=chat_id, user_id=user_id)
    except BaseException:
        return True

    if (
        GetData.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    ) or user_id in DEV_USERS:
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
        if message.sender_chat:
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

    GetData = await message._client.get_chat_member(chat_id=chat_id, user_id=user_id)

    if GetData.status == ChatMemberStatus.OWNER:
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

    GetData = await message._client.get_chat_member(chat_id=chat_id, user_id=BOT_ID)
    if GetData.privileges:
        return True
    else:
        if not silent:
            await message.reply(BOT_PERMISSIONS_STRINGS[privileges])
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
        if message.sender_chat:
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

    global GetData
    try:
        GetData = await message._client.get_chat_member(chat_id=chat_id, user_id=user_id)
    except BadRequest:
        return

    if GetData.privileges or user_id in DEV_USERS:
        return True
    else:
        if not silent:
            await message.reply(USERS_PERMISSIONS_STRINGS[privileges])
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
    if message.sender_chat:
        user_id = message.sender_chat.id
        if user_id == chat_id:
            return True
        else:
            return False

    user_id = message.from_user.id

    if message.chat.type == ChatType.PRIVATE and not str(chat_id).startswith('-100'):
        await message.reply(
            "This command is made to be used in group chats, not in pm!", quote=True
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
    if message.sender_chat:
        user_id = message.sender_chat.id
        chat_id = message.chat.id

        if user_id == chat_id:
            return True
        else:
            return False

    user_id = message.from_user.id
    chat_id = message.chat.id
    if message.chat.type == ChatType.PRIVATE:
        await message.reply(
            "This command is made to be used in group chats, not in pm!", quote=True
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
    data_list = client.get_chat_members(
        chat_id=chat_id, filter=enums.ChatMembersFilter.BANNED
    )
    async for user in data_list:
        if user is not None:
            try:
                if user_id == user.user_id:
                    return True
            except AttributeError:
                pass


async def check_user(
    message: Message,
    privileges: Union[str, List[str]] = "can_change_info",
    silent: bool = False,
    pm_mode: bool = False,
) -> bool:
    """This function check user's chat status as well as user's privileges in the chat.

    Returns:
        bool: True when user's chat status is admin or creator and user has privileges in the chat.
    """
    if not await isUserAdmin(message, silent=silent, pm_mode=pm_mode):
        return False

    if isinstance(privileges, list):
        for permission in privileges:
            if not await isUserCan(message, privileges=permission, silent=silent):
                return False

    elif isinstance(privileges, str):
        if not await isUserCan(message, privileges=privileges, silent=silent):
            return False

    return True


async def check_bot(
    message: Message,
    privileges: Union[str, List[str]] = "can_change_info",
    silent: bool = False,
) -> bool:
    """This function check bot's chat status as well as user's privileges in the chat.

    Returns:
        bool: True when bot's chat status is admin and bot has privileges in the chat.
    """
    if not await isBotAdmin(message, silent=silent):
        return False

    if isinstance(privileges, list):
        for permission in privileges:
            if not await isBotCan(message, privileges=permission, silent=silent):
                return False
    else:
        if not await isBotCan(message, privileges=privileges, silent=silent):
            return False

    return True

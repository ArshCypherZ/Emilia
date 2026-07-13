import asyncio
import os
import time

from pyrogram.enums import ChatMembersFilter, ChatMemberStatus, ChatType, ParseMode, UserStatus
from pyrogram.errors import (
    ChatAdminRequired,
    FloodWait,
    MessageDeleteForbidden,
    UserAdminInvalid,
)
from pyrogram.raw import functions as raw_functions
from pyrogram.raw import types as raw_types
from pyrogram.types import ChatPrivileges, InlineKeyboardButton, InlineKeyboardMarkup

import Emilia.strings as strings
from Emilia import DEV_USERS, LOGGER
from Emilia import pgram as meow
from Emilia.custom_filter import callbackquery as inline
from Emilia.custom_filter import register
from Emilia.helper.admins import *
from Emilia.helper.get_data import GetChat
from Emilia.modules.commands.bans import ban, kick, unban
from Emilia.modules.plugins.connection.connection import connection
from Emilia.utils.cache import SimpleCache

# check() re-invokes the original ban/kick/mute handlers after an anonymous
# admin is verified; those handlers live in their own modules, not here.
from Emilia.modules.plugins.mute.mute import mute
from Emilia.modules.plugins.mute.unmute import ban as unmute
from Emilia.utils.decorators import *
from Emilia.utils.decorators import _invalidate_admin_caches

# Resolve the target chat to operate on. In PM, use connected chat if
# available.


async def _target_chat_id(message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        return chat_id
    return message.chat.id


def _is_group(message):
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def _sender_id(message):
    return message.from_user.id if message.from_user else None


# Telegram enforces a 16-char max on custom admin titles.
ADMIN_TITLE_MAX = 16


def _clamp_title(title):
    if title and len(title) > ADMIN_TITLE_MAX:
        return title[:ADMIN_TITLE_MAX]
    return title


# ChatPrivileges with every flag False, used for demotes.
DEMOTE_RIGHTS = ChatPrivileges(
    can_manage_chat=False,
    can_delete_messages=False,
    can_manage_video_chats=False,
    can_restrict_members=False,
    can_promote_members=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    is_anonymous=False,
)


@register(pattern="promote")
@exception
@log_to_channel
async def promote(client, promt):
    chat_id = await _target_chat_id(promt)
    if promt.chat.type == ChatType.PRIVATE and chat_id is None:
        return await promt.reply_text(strings.is_pvt)
    if not promt.from_user:
        admins = await get_anonymous_admins(promt, "promote")
        if not admins:
            return await promt.reply_text(
                "I can't find any anonymous admin with required rights."
            )
        await promt.reply_text(
            "This is an anonymous command. Please select which admin you are from the list below to use this command.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"{i.first_name}",
                            callback_data=f"check_{promt.chat.id}_{i.id}_promote",
                        )
                        for i in admins
                    ]
                ]
            ),
        )
        return
    users, title = await get_user_reason(promt)
    if not users:
        return await promt.reply_text(strings.nouser)
    elif await is_admin(promt, users.id, chat_id=chat_id):
        return await promt.reply_text(strings.ON_ADMIN)
    elif not await can_add_admins(promt, _sender_id(promt), chat_id=chat_id):
        return
    new_rights = ChatPrivileges(
        can_invite_users=True,
        can_change_info=True,
        can_restrict_members=False,
        can_delete_messages=True,
        can_pin_messages=True,
    )

    await meow.promote_chat_member(chat_id, users.id, privileges=new_rights)
    await meow.set_administrator_title(chat_id, users.id, _clamp_title(title) if title else "Admin")
    await _invalidate_admin_caches(chat_id, users.id)
    await _adminlist_cache.delete(f"list:{chat_id}")
    await update_admin_cache(chat_id, users.id, True)
    await promt.reply_text(f"Promoted {users.first_name} Successfully!")
    return "PROMOTE", users.id, users.first_name


@register(pattern="fullpromote")
@exception
@log_to_channel
async def fpromote(client, promt):
    chat_id = await _target_chat_id(promt)
    if promt.chat.type == ChatType.PRIVATE and chat_id is None:
        return await promt.reply_text(strings.is_pvt)
    if not promt.from_user:
        admins = await get_anonymous_admins(promt, "superpromote")
        if not admins:
            return await promt.reply_text(
                "I can't find any anonymous admin with required rights."
            )
        await promt.reply_text(
            "This is an anonymous command. Please select which admin you are from the list below to use this command.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"{i.first_name}",
                            callback_data=f"check_{promt.chat.id}_{i.id}_superpromote",
                        )
                        for i in admins
                    ]
                ]
            ),
        )
        return
    users, title = await get_user_reason(promt)
    if not users:
        return await promt.reply_text(strings.nouser)
    elif await is_admin(promt, users.id, chat_id=chat_id):
        return await promt.reply_text(strings.ON_ADMIN)
    elif not await can_add_admins(promt, _sender_id(promt), chat_id=chat_id):
        return
    new_rights = ChatPrivileges(
        can_promote_members=True,
        can_invite_users=True,
        can_change_info=True,
        can_restrict_members=True,
        can_delete_messages=True,
        can_pin_messages=True,
        can_manage_video_chats=True,
    )
    await meow.promote_chat_member(chat_id, users.id, privileges=new_rights)
    await meow.set_administrator_title(chat_id, users.id, _clamp_title(title) if title else "Admin")
    await _invalidate_admin_caches(chat_id, users.id)
    await _adminlist_cache.delete(f"list:{chat_id}")
    await update_admin_cache(chat_id, users.id, True)
    await promt.reply_text(
        f"Promoted {users.first_name} with full rights successfully!"
    )
    return "FULL_PROMOTE", users.id, users.first_name


@register(pattern="admincache")
async def admincach(client, event):
    if event.chat.type == ChatType.PRIVATE:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply_text(strings.is_pvt)
    else:
        chat_id = event.chat.id

    # Invalidate the Redis chat-member cache for anyone previously cached as
    # admin in this chat, so demotions done outside the bot (e.g. directly in
    # Telegram) don't keep serving stale ADMINISTRATOR status.
    try:
        async for stale in cache_collection.find(
            {"chat_id": chat_id, "is_admin": True}
        ):
            await _invalidate_admin_caches(chat_id, stale["user_id"])
    except Exception:
        LOGGER.warning("admincache stale-entry invalidation failed", exc_info=True)

    # Clear existing cache for this chat to avoid stale entries
    try:
        await cache_collection.delete_many({"chat_id": chat_id})
    except Exception:
        # Best-effort; continue even if delete fails
        LOGGER.warning("admincache delete_many failed", exc_info=True)

    # Fetch current admins and repopulate cache with accurate True flags
    async for i in meow.get_chat_members(
        chat_id, filter=ChatMembersFilter.ADMINISTRATORS
    ):
        await _invalidate_admin_caches(chat_id, i.user.id)
        await update_admin_cache(chat_id, i.user.id, True)
    await _adminlist_cache.delete(f"list:{chat_id}")
    await event.reply_text("Admin cache refreshed!")


@register(pattern="demote")
@exception
@log_to_channel
async def demote(client, dmod):
    chat_id = await _target_chat_id(dmod)
    if dmod.chat.type == ChatType.PRIVATE and chat_id is None:
        return await dmod.reply_text(strings.is_pvt)
    if not dmod.from_user:
        admins = await get_anonymous_admins(dmod, "demote")
        if not admins:
            return await dmod.reply_text(
                "I can't find any anonymous admin with required rights."
            )
        await dmod.reply_text(
            "This is an anonymous command. Please select which admin you are from the list below to use this command.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"{i.first_name}",
                            callback_data=f"check_{dmod.chat.id}_{i.id}_demote",
                        )
                        for i in admins
                    ]
                ]
            ),
        )
        return
    users, _ = await get_user_reason(dmod)
    if not users:
        return await dmod.reply_text(strings.nouser)
    elif not await is_admin(dmod, users.id, chat_id=chat_id):
        return await dmod.reply_text(strings.OFF_ADMIN)
    elif not await can_add_admins(dmod, _sender_id(dmod), chat_id=chat_id):
        return

    # Only group owner (or dev users) can demote an admin with
    # can_promote_members; regular admins shouldn't demote each other.
    target_member = await meow.get_chat_member(chat_id, users.id)
    if target_member.status == ChatMemberStatus.ADMINISTRATOR and target_member.privileges.can_promote_members:
        caller_member = await meow.get_chat_member(chat_id, _sender_id(dmod))
        if caller_member.status != ChatMemberStatus.OWNER and _sender_id(dmod) not in DEV_USERS:
            return await dmod.reply_text(
                "Only the group owner can demote a full admin."
            )

    await meow.promote_chat_member(chat_id, users.id, privileges=DEMOTE_RIGHTS)
    await _invalidate_admin_caches(chat_id, users.id)
    await _adminlist_cache.delete(f"list:{chat_id}")
    await update_admin_cache(chat_id, users.id, False)
    await dmod.reply_text(f"Demoted {users.first_name} Successfully!")
    return "DEMOTE", users.id, users.first_name


_adminlist_cache = SimpleCache(default_ttl=120, namespace="adminlist")


@register(pattern="admins|adminlist")
@exception
async def get_admin(client, show):
    if show.chat.type == ChatType.PRIVATE:
        chat_id = await connection(show)
        if chat_id is None:
            return await show.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = show.chat.id
        title = show.chat.title

    cache_key = f"list:{chat_id}"
    mentions = await _adminlist_cache.get(cache_key)
    if mentions is None:
        admins = []
        bots = []
        async for admin in meow.get_chat_members(
            chat_id, filter=ChatMembersFilter.ADMINISTRATORS
        ):
            admins.append(admin.user)
            if admin.user.is_bot:
                bots.append(admin.user)

        mentions = f"<b>Admins in {title}:</b>\n"
        mentions += "\n".join(
            f"<a href='tg://user?id={admin.id}'>{admin.first_name}</a> - <code>{admin.id}</code>"
            for admin in admins
        )
        mentions += f"\n\n<b>Total Admins</b>: <code>{len(admins)}</code>"
        mentions += f"\n<b>Total Bots</b>: <code>{len(bots)}</code>"
        await _adminlist_cache.set(cache_key, mentions, ttl=120)

    await show.reply_text(mentions, parse_mode=ParseMode.HTML)


async def get_anonymous_admins(event, type):
    if type == "ban":
        right = "can_restrict_members"
    elif type == "unban":
        right = "can_restrict_members"
    elif type == "kick":
        right = "can_restrict_members"
    elif type == "mute":
        right = "can_restrict_members"
    elif type == "unmute":
        right = "can_restrict_members"
    elif type == "promote":
        right = "can_promote_members"
    elif type == "superpromote":
        right = "can_promote_members"
    elif type == "demote":
        right = "can_promote_members"
    else:
        return
    to_return = []
    async for admin in meow.get_chat_members(
        event.chat.id, filter=ChatMembersFilter.ADMINISTRATORS
    ):
        privileges = admin.privileges
        if privileges and privileges.is_anonymous:
            if getattr(privileges, right):
                to_return.append(admin.user)
    return to_return


@inline(pattern=r"check_")
async def check(client, event):
    # parse the callback data directly (str in pyrogram)
    data = event.data.split("_")
    chat_id = int(data[1])
    user_id = int(data[2])
    type = data[3]
    if event.from_user.id != user_id:
        return await event.answer("You are not the admin who initiated this command.")
    message = await client.get_messages(chat_id, event.message.id)
    # fake the sender so the re-invoked handler sees the verified admin
    message.from_user = await client.get_users(user_id)
    if type == "ban":
        await ban(client, message)
    elif type == "unban":
        await unban(client, message)
    elif type == "kick":
        await kick(client, message)
    elif type == "mute":
        await mute(client, message)
    elif type == "unmute":
        await unmute(client, message)
    elif type == "promote":
        await promote(client, message)
    elif type == "superpromote":
        await fpromote(client, message)
    elif type == "demote":
        await demote(client, message)
    await event.message.delete()


@register(pattern="setgpic")
@exception
@log_to_channel
async def set_group_photo(client, gpic):
    replymsg = gpic.reply_to_message
    photo = None
    chat_id = await _target_chat_id(gpic)
    if gpic.chat.type == ChatType.PRIVATE and chat_id is None:
        return await gpic.reply_text(strings.is_pvt)
    if not await can_change_info(gpic, _sender_id(gpic), chat_id=chat_id):
        return
    elif not replymsg:
        return await gpic.reply_text(strings.media)
    if replymsg and replymsg.media:
        if replymsg.photo:
            photo = await replymsg.download()
        elif replymsg.document and "image" in replymsg.document.mime_type.split("/"):
            photo = await replymsg.download()
        else:
            await gpic.reply_text(strings.imedia)
    if photo:
        await meow.set_chat_photo(chat_id, photo=photo)
        os.remove(photo)
        await gpic.reply_text("Successfully changed group profile photo.")
        return "NEW_GPIC", None, None


@register(pattern="title")
@exception
@log_to_channel
async def settitle(client, promt):
    user, title_admin = await get_user_reason(promt)
    chat_id = await _target_chat_id(promt)
    if promt.chat.type == ChatType.PRIVATE and chat_id is None:
        return await promt.reply_text(strings.is_pvt)
    elif not await can_add_admins(promt, _sender_id(promt), chat_id=chat_id):
        return
    elif not user:
        return await promt.reply_text("Reply to a user to set his title.")
    elif not title_admin:
        return await promt.reply_text("Give a title to set.")
    elif not await is_admin(promt, user.id, chat_id=chat_id):
        return await promt.reply_text(strings.OFF_ADMIN)
    title_admin = _clamp_title(title_admin)
    # set_administrator_title keeps the existing admin rights
    await meow.set_administrator_title(chat_id, user.id, title_admin)
    await promt.reply_text(
        f"Title for {user.first_name} set successfully to {title_admin}!"
    )
    return "NEW_TITLE", user.id, user.first_name


@register(pattern="zombies")
@exception
@log_to_channel
async def rm_deletedacc(client, show):
    con = show.pattern_match.group(1).lower()
    del_u = 0
    del_status = "No deleted accounts found, Group is clean."
    if not _is_group(show):
        return await show.reply_text(strings.is_pvt)
    if not await can_ban_users(show, _sender_id(show)):
        return
    if con != "clean":
        await show.reply_text("`Searching for zombie accounts...`")
        async for member in meow.get_chat_members(show.chat.id):
            if member.user.is_deleted:
                del_u += 1
        if del_u > 0:
            del_status = f"Found **{del_u}** deleted account(s) in this group,\
            \nclean them by using `/zombies clean`"
        return await show.reply_text(del_status)
    await show.reply_text("Banning deleted accounts...")
    del_u = 0
    del_a = 0
    async for member in meow.get_chat_members(show.chat.id):
        # pace mass iteration under Telegram's ceiling
        await asyncio.sleep(0.05)
        if member.user.is_deleted:
            try:
                await meow.ban_chat_member(show.chat.id, member.user.id)
            except ChatAdminRequired:
                return await show.reply_text(strings.botban)
            except UserAdminInvalid:
                del_u -= 1
                del_a += 1
            except FloodWait as ex:
                await asyncio.sleep(ex.value)
                continue
            await meow.unban_chat_member(show.chat.id, member.user.id)
            del_u += 1
    if del_u > 0:
        del_status = f"Cleaned **{del_u}** deleted account(s)"

    if del_a > 0:
        del_status = f"Cleaned **{del_u}** deleted account(s) \
        \n**{del_a}** deleted admin accounts are not removed"
    await show.reply_text(del_status)
    return "CLEANED_ZOMBIES", None, None


@register(pattern="kickdead")
@log_to_channel
@exception
async def _(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not await can_ban_users(event, _sender_id(event)):
        return
    c = 0
    cnt = 0
    done = await event.reply_text("Searching for Dead accounts...")
    async for i in meow.get_chat_members(event.chat.id):
        # pace mass iteration under Telegram's ceiling
        await asyncio.sleep(0.05)
        try:
            if i.user.status == UserStatus.LAST_MONTH:
                status = await meow.ban_chat_member(event.chat.id, i.user.id)
                await meow.unban_chat_member(event.chat.id, i.user.id)
                if not status:
                    return
                c = c + 1
            if i.user.status == UserStatus.LAST_WEEK:
                status = await meow.ban_chat_member(event.chat.id, i.user.id)
                await meow.unban_chat_member(event.chat.id, i.user.id)
                if not status:
                    return
                c = c + 1
        except UserAdminInvalid:
            cnt += 1
            continue
        except FloodWait as ex:
            await asyncio.sleep(ex.value)
            continue
    if c == 0:
        return await done.edit_text("Got no one to kick")
    required_string = "Successfully Kicked **{}** users who were inactive for a month or more. {} admins were not kicked."
    await done.edit_text(required_string.format(c, cnt))
    return "KICKED_DEAD", None, None


@register(pattern="unbanall")
@log_to_channel
@exception
async def _(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not await can_ban_users(event, _sender_id(event)):
        return
    done = await event.reply_text("Searching for Banned Accounts...")
    p = 0
    async for i in meow.get_chat_members(
        event.chat.id, filter=ChatMembersFilter.BANNED
    ):
        # pace mass iteration under Telegram's ceiling
        await asyncio.sleep(0.05)
        try:
            await meow.unban_chat_member(event.chat.id, i.user.id)
        except FloodWait as ex:
            LOGGER.warning("sleeping for {} seconds".format(ex.value))
            await asyncio.sleep(ex.value)
        except Exception as ex:
            LOGGER.warning(f"unbanall: failed to unban {i.user.id} in {event.chat.id}: {ex}")
        else:
            p += 1
    if p == 0:
        await done.edit_text("No one is banned in this chat")
        return
    required_string = "Successfully unbanned **{}** users"
    await done.edit_text(required_string.format(p))
    return "UNBANNED_ALL", None, None


@register(pattern="unmuteall")
@log_to_channel
@exception
async def _(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not await can_ban_users(event, _sender_id(event)):
        return
    done = await event.reply_text("Searching for Muted Accounts...")
    p = 0
    default_permissions = (await meow.get_chat(event.chat.id)).permissions
    async for i in meow.get_chat_members(
        event.chat.id, filter=ChatMembersFilter.RESTRICTED
    ):
        # pace mass iteration under Telegram's ceiling
        await asyncio.sleep(0.05)
        try:
            await meow.restrict_chat_member(
                event.chat.id, i.user.id, default_permissions
            )
        except FloodWait as ex:
            LOGGER.warning("sleeping for {} seconds".format(ex.value))
            await asyncio.sleep(ex.value)
        except Exception as ex:
            LOGGER.warning(f"unmuteall: failed to unmute {i.user.id} in {event.chat.id}: {ex}")
        else:
            p += 1
    if p == 0:
        await done.edit_text("No one is muted in this chat")
        return
    required_string = "Successfully unmuted **{}** users"
    await done.edit_text(required_string.format(p))
    return "UNMUTED_ALL", None, None


@register(pattern="setgtitle")
@log_to_channel
async def set_group_title(client, gpic):
    input_str = gpic.pattern_match.group(1)
    chat_id = await _target_chat_id(gpic)
    if gpic.chat.type == ChatType.PRIVATE and chat_id is None:
        return await gpic.reply_text(strings.is_pvt)
    if not input_str:
        return await gpic.reply_text("Please give me a title to set.")
    if len(input_str) > 255:
        return await gpic.reply_text("Title is too long.")
    elif not await can_change_info(gpic, _sender_id(gpic), chat_id=chat_id):
        return
    try:
        await meow.set_chat_title(chat_id, input_str)
        await gpic.reply_text(f"Group name updated successfully to {input_str}.")
    except ChatAdminRequired:
        await gpic.reply_text(strings.botinfo)
    return "NEW_GTITLE", None, None


@register(pattern="setdesc")
@log_to_channel
@exception
async def set_group_des(client, gpic):
    input_str = gpic.pattern_match.group(1)
    chat_id = await _target_chat_id(gpic)
    if gpic.chat.type == ChatType.PRIVATE and chat_id is None:
        return await gpic.reply_text(strings.is_pvt)
    if not input_str:
        return await gpic.reply_text("Please give me a description to set.")
    elif not await can_change_info(gpic, _sender_id(gpic), chat_id=chat_id):
        return
    await meow.set_chat_description(chat_id, input_str)
    await gpic.reply_text("Successfully set new group description.")
    return "NEW_GDESC", None, None


@register(pattern="setsticker")
@log_to_channel
@exception
async def set_group_sticker(client, gpic):
    if not _is_group(gpic):
        return await gpic.reply_text(strings.is_pvt)
    if not await can_change_info(gpic, _sender_id(gpic)):
        return
    rep_msg = gpic.reply_to_message
    if not rep_msg or not rep_msg.sticker:
        return await gpic.reply_text("Reply to a sticker to set it as group sticker.")
    if not rep_msg.sticker.set_name:
        return await gpic.reply_text("This sticker is not part of any pack.")
    # no high-level method for group sticker set; use raw API
    await meow.invoke(
        raw_functions.channels.SetStickers(
            channel=await meow.resolve_peer(gpic.chat.id),
            stickerset=raw_types.InputStickerSetShortName(
                short_name=rep_msg.sticker.set_name
            ),
        )
    )
    await gpic.reply_text("Successfully set group sticker.")
    return "NEW_GSTICKER", None, None


PURGE = {}


MAX_PURGE_MESSAGES = 5000


async def _delete_batch(client, chat_id, msgs):
    """Delete a batch of message ids, retrying once on FloodWait.

    Telegram fails the whole batch with MESSAGE_DELETE_FORBIDDEN if even one id
    is a service message or not deletable, so fall back to per-message deletes
    and skip the ones we're not allowed to remove.
    """
    try:
        await client.delete_messages(chat_id, msgs)
    except FloodWait as ex:
        await asyncio.sleep(ex.value)
        await _delete_batch(client, chat_id, msgs)
    except MessageDeleteForbidden:
        if len(msgs) == 1:
            return
        for m_id in msgs:
            try:
                await client.delete_messages(chat_id, m_id)
            except FloodWait as ex:
                await asyncio.sleep(ex.value)
                try:
                    await client.delete_messages(chat_id, m_id)
                except MessageDeleteForbidden:
                    pass
            except MessageDeleteForbidden:
                pass


@register(pattern="purgefrom")
async def purge_from(client, event):
    msg = event.reply_to_message
    if not msg:
        return await event.reply_text("Reply to a message to purge.")
    if not await can_delete_msg(event, _sender_id(event)) and _is_group(event):
        return
    PURGE[event.chat.id] = event.reply_to_message_id
    await event.reply_text("Purge from {}.".format(event.reply_to_message_id))


@register(pattern="purgeto")
async def purge_to(client, event):
    msg = event.reply_to_message
    if not msg:
        return await event.reply_text("Reply to a message to purge")
    if not await can_delete_msg(event, _sender_id(event)) and _is_group(event):
        return
    try:
        purge_from = PURGE[event.chat.id]
    except KeyError:
        return await event.reply_text("Purge from not found.")
    reply = event.reply_to_message
    if not reply:
        return await event.reply_text("Reply to a message to purge.")
    purge_to = reply.id
    total = purge_to - purge_from + 1
    if total > MAX_PURGE_MESSAGES:
        PURGE.pop(event.chat.id, None)
        return await event.reply_text(
            f"That range covers {total} messages, which is over the {MAX_PURGE_MESSAGES} "
            "limit. Pick a closer starting point."
        )
    messages = []
    try:
        await _delete_batch(client, event.chat.id, [event.id])
        for message in range(purge_to, purge_from - 1, -1):
            messages.append(message)
            if len(messages) == 100:
                await _delete_batch(client, event.chat.id, messages)
                messages = []

        if messages:
            await _delete_batch(client, event.chat.id, messages)
        m = await client.send_message(event.chat.id, "**Purged Completed!**")
        await m.delete()

    except Exception as e:
        error_message = strings.error_messages.get(type(e), str(e))
        await client.send_message(event.chat.id, error_message)
    finally:
        PURGE.pop(event.chat.id, None)


@register(pattern="purge")
@exception
async def purge(client, event):
    chat = event.chat.id
    start = time.perf_counter()
    msgs = []
    msg = event.reply_to_message
    if not msg:
        return await event.reply_text("Reply to a message to purge")
    if not await can_delete_msg(event, _sender_id(event)) and _is_group(event):
        return

    msg_id = msg.id
    to_delete = event.id - 1
    total = to_delete - msg_id + 2  # inclusive range + the command message
    if total > MAX_PURGE_MESSAGES:
        return await event.reply_text(
            f"That range covers ~{total} messages, which is over the {MAX_PURGE_MESSAGES} "
            "limit. Reply to a closer message instead."
        )

    count = 0
    await _delete_batch(client, chat, [event.id])
    for m_id in range(to_delete, msg_id - 1, -1):
        msgs.append(m_id)
        count += 1
        if len(msgs) == 100:
            await _delete_batch(client, chat, msgs)
            msgs = []

    if msgs:
        await _delete_batch(client, chat, msgs)
    time_ = time.perf_counter() - start
    m = await client.send_message(
        chat, f"Purged {count} Messages In {time_:0.2f} Secs."
    )
    await m.delete()


@register(pattern="spurge")
@exception
async def spurge(client, event):
    chat = event.chat.id
    msgs = []
    msg = event.reply_to_message
    if not msg:
        return await event.reply_text("Reply to a message to purge.")
    if not await can_delete_msg(event, _sender_id(event)) and _is_group(event):
        return

    msg_id = msg.id
    to_delete = event.id - 1
    total = to_delete - msg_id + 2
    if total > MAX_PURGE_MESSAGES:
        return await event.reply_text(
            f"That range covers ~{total} messages, which is over the {MAX_PURGE_MESSAGES} "
            "limit. Reply to a closer message instead."
        )

    await _delete_batch(client, chat, [event.id])
    for m_id in range(to_delete, msg_id - 1, -1):
        msgs.append(m_id)
        if len(msgs) == 100:
            await _delete_batch(client, chat, msgs)
            msgs = []
    if msgs:
        await _delete_batch(client, chat, msgs)


@register(pattern="del")
async def delete_messages(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    message = event.reply_to_message
    if not message:
        return await event.reply_text("Reply to a message to delete it.")
    if not await can_delete_msg(event, _sender_id(event)):
        return
    await client.delete_messages(event.chat.id, [message.id, event.id])



VALID_SLOWMODE_SECONDS = {0, 5, 10, 30, 60, 300, 900, 3600}


@usage("/slowmode [seconds]")
@example("/slowmode 60")
@description(
    "Set slow mode for the chat. Valid values: 0 (off), 5, 10, 30, 60, 300, 900, 3600. "
    "Omit the value to check the current setting."
)
@register(pattern="slowmode")
@log_to_channel
@exception
async def slow_mode(client, message):
    if not _is_group(message):
        return await message.reply_text(strings.is_pvt)
    if not await can_change_info(message, _sender_id(message)):
        return

    arg = message.text.split()[1:]
    if not arg:
        chat = await meow.get_chat(message.chat.id)
        current = getattr(chat, "slow_mode_delay", None) or 0
        return await message.reply_text(
            f"Current slow mode: **{current}s**" if current else "Slow mode is currently **off**."
        )

    try:
        seconds = int(arg[0])
    except ValueError:
        return await message.reply_text(
            "Give a number of seconds. Valid values: "
            + ", ".join(str(v) for v in sorted(VALID_SLOWMODE_SECONDS))
        )

    if seconds not in VALID_SLOWMODE_SECONDS:
        return await message.reply_text(
            "Invalid value. Valid values: "
            + ", ".join(str(v) for v in sorted(VALID_SLOWMODE_SECONDS))
        )

    await meow.set_slow_mode(message.chat.id, seconds if seconds else None)
    if seconds:
        await message.reply_text(f"Slow mode set to **{seconds}s**.")
    else:
        await message.reply_text("Slow mode turned **off**.")
    return "SLOWMODE", None, None

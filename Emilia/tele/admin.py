import asyncio
import os

from telethon import Button
from telethon.errors import *
from telethon.tl.functions.channels import (
    EditAdminRequest,
    EditBannedRequest,
    EditPhotoRequest,
    EditTitleRequest,
    GetParticipantRequest,
    SetStickersRequest,
)
from telethon.tl.functions.messages import EditChatAboutRequest, EditChatTitleRequest
from telethon.tl.types import (
    Channel,
    ChannelParticipantsAdmins,
    ChannelParticipantsBanned,
    ChannelParticipantsKicked,
    ChatAdminRights,
    ChatBannedRights,
    DocumentAttributeSticker,
    InputStickerSetID,
    MessageMediaPhoto,
    UserStatusLastMonth,
    UserStatusLastWeek,
)

import Emilia.strings as strings
from Emilia import LOGGER
from Emilia import telethn as meow
from Emilia.custom_filter import callbackquery as inline
from Emilia.custom_filter import register
from Emilia.functions.admins import *
from Emilia.helper.get_data import GetChat
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *

# Resolve the target chat to operate on. In PM, use connected chat if available.
async def _target_chat_id(event):
    if getattr(event, "is_private", False):
        chat_id = await connection(event)
        return chat_id
    return event.chat_id

BANNED_RIGHTS = ChatBannedRights(
    until_date=None,
    view_messages=True,
    send_messages=True,
    send_media=True,
    send_stickers=True,
    send_gifs=True,
    send_games=True,
    send_inline=True,
    embed_links=True,
)

UNBAN_RIGHTS = ChatBannedRights(
    until_date=None,
    send_messages=None,
    send_media=None,
    send_stickers=None,
    send_gifs=None,
    send_games=None,
    send_inline=None,
    embed_links=None,
)


KICK_RIGHTS = ChatBannedRights(until_date=None, view_messages=True)


@register(pattern="promote")
@exception
@logging
async def promote(promt):
    chat_id = await _target_chat_id(promt)
    if promt.is_private and chat_id is None:
        return await promt.reply(strings.is_pvt)
    if not promt.from_id:
        admins = await get_anonymous_admins(promt, "promote")
        if not admins:
            return await promt.reply(
                "I can't find any anonymous admin with required rights."
            )
        await promt.reply(
            "This is an anonymous command. Please select which admin you are from the list below to use this command.",
            buttons=[
                Button.inline(
                    f"{i.first_name}",
                    data=f"check_{promt.chat_id}_{i.id}_promote",
                )
                for i in admins
            ],
        )
        return
    users, title = await get_user_reason(promt)
    if not users:
        return await promt.reply(strings.nouser)
    elif await is_admin(promt, users.id, chat_id=chat_id):
        return await promt.reply(strings.ON_ADMIN)
    elif not await can_add_admins(promt, promt.sender_id, chat_id=chat_id):
        return
    new_rights = ChatAdminRights(
        invite_users=True,
        change_info=True,
        ban_users=False,
        delete_messages=True,
        pin_messages=True,
    )

    (
        await meow(EditAdminRequest(chat_id, users.id, new_rights, "Admin"))
        if not title
        else await meow(EditAdminRequest(chat_id, users.id, new_rights, title))
    )
    await update_admin_cache(chat_id, users.id, True)
    await promt.reply(f"Promoted {users.first_name} Successfully!")
    return "PROMOTE", users.id, users.first_name


@register(pattern="fullpromote")
@exception
@logging
async def fpromote(promt):
    chat_id = await _target_chat_id(promt)
    if promt.is_private and chat_id is None:
        return await promt.reply(strings.is_pvt)
    if not promt.from_id:
        admins = await get_anonymous_admins(promt, "superpromote")
        if not admins:
            return await promt.reply(
                "I can't find any anonymous admin with required rights."
            )
        await promt.reply(
            "This is an anonymous command. Please select which admin you are from the list below to use this command.",
            buttons=[
                Button.inline(
                    f"{i.first_name}",
                    data=f"check_{promt.chat_id}_{i.id}_superpromote",
                )
                for i in admins
            ],
        )
        return
    users, title = await get_user_reason(promt)
    if not users:
        return await promt.reply(strings.nouser)
    elif await is_admin(promt, users.id, chat_id=chat_id):
        return await promt.reply(strings.ON_ADMIN)
    elif not await can_add_admins(promt, promt.sender_id, chat_id=chat_id):
        return
    new_rights = ChatAdminRights(
        add_admins=True,
        invite_users=True,
        change_info=True,
        ban_users=True,
        delete_messages=True,
        pin_messages=True,
        manage_call=True,
    )
    (
        await meow(EditAdminRequest(chat_id, users.id, new_rights, "Admin"))
        if not title
        else await meow(EditAdminRequest(chat_id, users.id, new_rights, title))
    )
    await update_admin_cache(chat_id, users.id, True)
    await promt.reply(f"Promoted {users.first_name} with full rights successfully!")
    return "FULL_PROMOTE", users.id, users.first_name


@register(pattern="admincache")
async def admincach(event):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
    else:
        chat_id = event.chat_id

    # Clear existing cache for this chat to avoid stale entries
    try:
        await cache_collection.delete_many({"chat_id": chat_id})
    except Exception:
        pass

    # Fetch current admins and repopulate cache with accurate True flags
    m = await meow.get_participants(chat_id, filter=ChannelParticipantsAdmins)
    for i in m:
        await update_admin_cache(chat_id, i.id, True)
    await event.reply("Admin cache refreshed!")


@register(pattern="demote")
@exception
@logging
async def demote(dmod):
    chat_id = await _target_chat_id(dmod)
    if dmod.is_private and chat_id is None:
        return await dmod.reply(strings.is_pvt)
    if not dmod.from_id:
        admins = await get_anonymous_admins(dmod, "demote")
        if not admins:
            return await dmod.reply(
                "I can't find any anonymous admin with required rights."
            )
        await dmod.reply(
            "This is an anonymous command. Please select which admin you are from the list below to use this command.",
            buttons=[
                Button.inline(
                    f"{i.first_name}",
                    data=f"check_{dmod.chat_id}_{i.id}_demote",
                )
                for i in admins
            ],
        )
        return
    users, _ = await get_user_reason(dmod)
    if not users:
        return await dmod.reply(strings.nouser)
    elif not await is_admin(dmod, users.id, chat_id=chat_id):
        return await dmod.reply(strings.OFF_ADMIN)
    elif not await can_add_admins(dmod, dmod.sender_id, chat_id=chat_id):
        return
    newrights = ChatAdminRights(
        add_admins=None,
        invite_users=None,
        change_info=None,
        ban_users=None,
        delete_messages=None,
        pin_messages=None,
    )
    await meow(EditAdminRequest(chat_id, users.id, newrights, "Admin"))
    await update_admin_cache(chat_id, users.id, False)
    await dmod.reply(f"Demoted {users.first_name} Successfully!")
    return "DEMOTE", users.id, users.first_name


@register(pattern="admins|adminlist")
@exception
async def get_admin(show):
    if show.is_private:
        chat_id = await connection(show)
        if chat_id is None:
            return await show.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = show.chat_id
        title = show.chat.title

    admins = []
    bots = []
    async for admin in meow.iter_participants(
        chat_id, filter=ChannelParticipantsAdmins
    ):
        admins.append(admin)
        if admin.bot:
            bots.append(admin)

    mentions = f"<b>Admins in {title}:</b>\n"
    mentions += "\n".join(
        f"<a href='tg://user?id={admin.id}'>{admin.first_name}</a> - <code>{admin.id}</code>"
        for admin in admins
    )
    mentions += f"\n\n<b>Total Admins</b>: <code>{len(admins)}</code>"
    mentions += f"\n<b>Total Bots</b>: <code>{len(bots)}</code>"

    await show.reply(mentions, parse_mode="html")


async def get_anonymous_admins(event, type):
    if type == "ban":
        right = "ban_users"
    elif type == "unban":
        right = "ban_users"
    elif type == "kick":
        right = "ban_users"
    elif type == "mute":
        right = "ban_users"
    elif type == "unmute":
        right = "ban_users"
    elif type == "promote":
        right = "add_admins"
    elif type == "superpromote":
        right = "add_admins"
    elif type == "demote":
        right = "add_admins"
    else:
        return
    info = await meow.get_entity(event.chat_id)
    admins = await meow.get_participants(
        info, filter=ChannelParticipantsAdmins, aggressive=True
    )
    to_return = []
    for admin in admins:
        if admin.participant.is_anonymous:
            if getattr(admin.participant.admin_rights, right):
                to_return.append(admin)
    return to_return


@inline(pattern=r"check_")
async def check(event):
    chat_id = int(event.pattern_match.group(1).decode("UTF-8").split("_")[1])
    user_id = int(event.pattern_match.group(1).decode("UTF-8").split("_")[2])
    type = event.pattern_match.group(1).decode("UTF-8").split("_")[3]
    if event.sender_id != user_id:
        return await event.answer("You are not the admin who initiated this command.")
    message = await meow.get_messages(chat_id, ids=event.message_id)
    message.from_id = user_id
    if type == "ban":
        await ban(message)
    elif type == "unban":
        await unban(message)
    elif type == "kick":
        await kick(message)
    elif type == "mute":
        await mute(message)
    elif type == "unmute":
        await unmute(message)
    elif type == "promote":
        await promote(message)
    elif type == "superpromote":
        await fpromote(message)
    elif type == "demote":
        await demote(message)
    await event.delete()


@register(pattern="setgpic")
@exception
@logging
async def set_group_photo(gpic):
    replymsg = await gpic.get_reply_message()
    photo = None
    chat_id = await _target_chat_id(gpic)
    if gpic.is_private and chat_id is None:
        return await gpic.reply(strings.is_pvt)
    if not await can_change_info(gpic, gpic.sender_id, chat_id=chat_id):
        return
    elif not replymsg:
        return await gpic.reply(strings.media)
    if replymsg and replymsg.media:
        if isinstance(replymsg.media, MessageMediaPhoto):
            photo = await meow.download_media(message=replymsg.photo)
        elif "image" in replymsg.media.document.mime_type.split("/"):
            photo = await meow.download_file(replymsg.media.document)
        else:
            await gpic.reply(strings.imedia)
    if photo:
        await meow(EditPhotoRequest(chat_id, await meow.upload_file(photo)))
        os.remove(photo)
        await gpic.reply("Successfully changed group profile photo.")
        return "NEW_GPIC", None, None


@register(pattern="title")
@exception
@logging
async def settitle(promt):
    user, title_admin = await get_user_reason(promt)
    chat_id = await _target_chat_id(promt)
    if promt.is_private and chat_id is None:
        return await promt.reply(strings.is_pvt)
    elif not await can_add_admins(promt, promt.sender_id, chat_id=chat_id):
        return
    elif not user:
        return await promt.reply("Reply to a user to set his title.")
    elif not title_admin:
        return await promt.reply("Give a title to set.")
    elif not await is_admin(promt, user.id, chat_id=chat_id):
        return await promt.reply(strings.OFF_ADMIN)
    result = await meow(
        GetParticipantRequest(
            channel=chat_id,
            participant=user.id,
        )
    )
    p = result.participant

    await meow(
        EditAdminRequest(
            chat_id,
            user_id=user.id,
            admin_rights=p.admin_rights,
            rank=title_admin,
        )
    )
    await promt.reply(f"Title for {user.first_name} set successfully to {title_admin}!")
    return "NEW_TITLE", user.id, user.first_name


@register(pattern="zombies")
@exception
@logging
async def rm_deletedacc(show):
    con = show.pattern_match.group(1).lower()
    del_u = 0
    del_status = "No deleted accounts found, Group is clean."
    if not show.is_group:
        return await show.reply(strings.is_pvt)
    if not await can_ban_users(show, show.sender_id):
        return
    if con != "clean":
        await show.reply("`Searching for zombie accounts...`")
        async for users in meow.iter_participants(show.chat_id):
            if users.deleted:
                del_u += 1
        if del_u > 0:
            del_status = f"Found **{del_u}** deleted account(s) in this group,\
            \nclean them by using `/zombies clean`"
        return await show.reply(del_status)
    await show.reply("Banning deleted accounts...")
    del_u = 0
    del_a = 0
    async for users in meow.iter_participants(show.chat_id):
        if users.deleted:
            try:
                await meow(EditBannedRequest(show.chat_id, users.id, BANNED_RIGHTS))
            except ChatAdminRequiredError:
                return await show.reply(strings.botban)
            except UserAdminInvalidError:
                del_u -= 1
                del_a += 1
            await meow(EditBannedRequest(show.chat_id, users.id, UNBAN_RIGHTS))
            del_u += 1
    if del_u > 0:
        del_status = f"Cleaned **{del_u}** deleted account(s)"

    if del_a > 0:
        del_status = f"Cleaned **{del_u}** deleted account(s) \
        \n**{del_a}** deleted admin accounts are not removed"
    await show.reply(del_status)
    return "CLEANED_ZOMBIES", None, None


@register(pattern="kickdead")
@logging
@exception
async def _(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not await can_ban_users(event, event.sender_id):
        return
    c = 0
    cnt = 0
    done = await event.reply("Searching for Dead accounts...")
    async for i in meow.iter_participants(event.chat_id):
        try:
            if isinstance(i.status, UserStatusLastMonth):
                status = await meow(EditBannedRequest(event.chat_id, i, KICK_RIGHTS))
                await meow(EditBannedRequest(event.chat_id, i, UNBAN_RIGHTS))
                if not status:
                    return
                c = c + 1
            if isinstance(i.status, UserStatusLastWeek):
                status = await meow(EditBannedRequest(event.chat_id, i, KICK_RIGHTS))
                await meow(EditBannedRequest(event.chat_id, i, UNBAN_RIGHTS))
                if not status:
                    return
                c = c + 1
        except UserAdminInvalidError:
            cnt += 1
            continue
    if c == 0:
        return await done.edit("Got no one to kick")
    required_string = "Successfully Kicked **{}** users who were inactive for a month or more. {} admins were not kicked."
    await done.edit(required_string.format(c, cnt))
    return "KICKED_DEAD", None, None


@register(pattern="unbanall")
@logging
@exception
async def _(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not await can_ban_users(event, event.sender_id):
        return
    done = await event.reply("Searching for Banned Accounts...")
    p = 0
    async for i in meow.iter_participants(
        event.chat_id, filter=ChannelParticipantsKicked, aggressive=True
    ):
        rights = ChatBannedRights(until_date=0, view_messages=False)
        try:
            await meow(EditBannedRequest(event.chat_id, i, rights))
        except FloodWaitError as ex:
            LOGGER.warn("sleeping for {} seconds".format(ex.seconds))
            await asyncio.sleep(ex.seconds)
        except Exception as ex:
            await event.reply(str(ex))
        else:
            p += 1
    if p == 0:
        await done.edit("No one is banned in this chat")
        return
    required_string = "Successfully unbanned **{}** users"
    await done.edit(required_string.format(p))
    return "UNBANNED_ALL", None, None


@register(pattern="unmuteall")
@logging
@exception
async def _(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not await can_ban_users(event, event.sender_id):
        return
    done = await event.reply("Searching for Muted Accounts...")
    p = 0
    async for i in meow.iter_participants(
        event.chat_id, filter=ChannelParticipantsBanned, aggressive=True
    ):
        rights = ChatBannedRights(
            until_date=0,
            send_messages=False,
        )
        try:
            await meow(EditBannedRequest(event.chat_id, i, rights))
        except FloodWaitError as ex:
            LOGGER.warn("sleeping for {} seconds".format(ex.seconds))
            await asyncio.sleep(ex.seconds)
        except Exception as ex:
            await event.reply(str(ex))
        else:
            p += 1
    if p == 0:
        await done.edit("No one is muted in this chat")
        return
    required_string = "Successfully unmuted **{}** users"
    await done.edit(required_string.format(p))
    return "UNMUTED_ALL", None, None


@register(pattern="setgtitle")
@logging
async def set_group_title(gpic):
    input_str = gpic.pattern_match.group(1)
    chat_id = await _target_chat_id(gpic)
    if gpic.is_private and chat_id is None:
        return await gpic.reply(strings.is_pvt)
    if not input_str:
        return await gpic.reply("Please give me a title to set.")
    if len(input_str) > 255:
        return await gpic.reply("Title is too long.")
    elif not await can_change_info(gpic, gpic.sender_id, chat_id=chat_id):
        return
    try:
        await meow(EditChatTitleRequest(chat_id=chat_id, title=input_str))
        await gpic.reply(f"Group name updated successfully to {input_str}.")
    except ChatAdminRequiredError:
        await gpic.reply(strings.botinfo)
    except BaseException:
        await meow(EditTitleRequest(channel=chat_id, title=input_str))
        await gpic.reply(f"Group name updated successfully to {input_str}.")
    return "NEW_GTITLE", None, None


@register(pattern="setdesc")
@logging
@exception
async def set_group_des(gpic):
    input_str = gpic.pattern_match.group(1)
    chat_id = await _target_chat_id(gpic)
    if gpic.is_private and chat_id is None:
        return await gpic.reply(strings.is_pvt)
    if not input_str:
        return await gpic.reply("Please give me a description to set.")
    elif not await can_change_info(gpic, gpic.sender_id, chat_id=chat_id):
        return
    await meow(EditChatAboutRequest(peer=chat_id, about=input_str))
    await gpic.reply("Successfully set new group description.")
    return "NEW_GDESC", None, None


@register(pattern="setsticker")
@logging
@exception
async def set_group_sticker(gpic):
    if not gpic.is_group:
        return await gpic.reply(strings.is_pvt)
    if not await can_change_info(gpic, gpic.sender_id):
        return
    rep_msg = await gpic.get_reply_message()
    if not rep_msg.document:
        return await gpic.reply("Reply to a sticker to set it as group sticker.")
    stickerset_attr_s = rep_msg.document.attributes
    stickerset_attr = await find_instance(stickerset_attr_s, DocumentAttributeSticker)
    if not stickerset_attr.stickerset:
        return await gpic.reply("This sticker is not part of any pack.")
    id = stickerset_attr.stickerset.id
    access_hash = stickerset_attr.stickerset.access_hash
    await meow(
        SetStickersRequest(
            channel=gpic.chat_id,
            stickerset=InputStickerSetID(id=id, access_hash=access_hash),
        )
    )
    await gpic.reply("Successfully set group sticker.")
    return "NEW_GSTICKER", None, None


PURGE = {}


@register(pattern="purgefrom")
async def purge_from(event):
    msg = await event.get_reply_message()
    if not msg:
        return await event.reply("Reply to a message to purge.")
    if not await can_delete_msg(event, event.sender_id) and event.is_group:
        return
    PURGE[event.chat_id] = event.reply_to_msg_id
    await event.reply("Purge from {}.".format(event.reply_to_msg_id))


@register(pattern="purgeto")
async def purge_to(event):
    msg = await event.get_reply_message()
    if not msg:
        return await event.reply("Reply to a message to purge")
    if not await can_delete_msg(event, event.sender_id) and event.is_group:
        return
    try:
        purge_from = PURGE[event.chat_id]
    except KeyError:
        return await event.reply("Purge from not found.")
    reply = await event.get_reply_message()
    if not reply:
        return await event.reply("Reply to a message to purge.")
    messages = []
    purge_to = reply.id
    try:
        await event.client.delete_messages(event.chat_id, event.message.id)
        messages.append(event.reply_to_msg_id)
        for message in range(purge_to, purge_from - 1, -1):
            messages.append(message)
            if len(messages) == 100:
                await event.client.delete_messages(event.chat_id, messages)
                messages = []

        if messages:
            await event.client.delete_messages(event.chat_id, messages)
        m = await event.respond("**Purged Completed!**")
        await m.delete()

    except Exception as e:
        PURGE.pop(event.chat_id)
        error_message = strings.error_messages.get(type(e), str(e))
        await event.reply(error_message)


@register(pattern="purge")
@exception
async def purge(event):
    chat = event.chat_id
    start = time.perf_counter()
    msgs = []
    msg = await event.get_reply_message()
    if not msg:
        return await event.reply("Reply to a message to purge")
    if not await can_delete_msg(event, event.sender_id) and event.is_group:
        return

    msg_id = msg.id
    count = 0
    to_delete = event.message.id - 1
    await event.client.delete_messages(chat, event.message.id)
    msgs.append(event.reply_to_msg_id)
    for m_id in range(to_delete, msg_id - 1, -1):
        msgs.append(m_id)
        count += 1
        if len(msgs) == 100:
            await event.client.delete_messages(chat, msgs)
            msgs = []

    await event.client.delete_messages(chat, msgs)
    time_ = time.perf_counter() - start
    m = await event.respond(f"Purged {count} Messages In {time_:0.2f} Secs.")
    await m.delete()


@register(pattern="spurge")
@exception
async def spurge(event):
    chat = event.chat_id
    msgs = []
    msg = await event.get_reply_message()
    if not msg:
        return await event.reply("Reply to a message to purge.")
    if not await can_delete_msg(event, event.sender_id) and event.is_group:
        return
    msg_id = msg.id
    count = 0
    to_delete = event.message.id - 1
    await event.client.delete_messages(chat, event.message.id)
    msgs.append(event.reply_to_msg_id)
    for m_id in range(to_delete, msg_id - 1, -1):
        msgs.append(m_id)
        count += 1
        if len(msgs) == 100:
            await event.client.delete_messages(chat, msgs)
            msgs = []
    await event.client.delete_messages(chat, msgs)


@register(pattern="del")
async def delete_messages(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    message = await event.get_reply_message()
    if not message:
        return await event.reply("Reply to a message to delete it.")
    if not await can_delete_msg(event, event.sender_id):
        return
    chat = await event.get_input_chat()
    del_message = [message, event.message]
    await event.client.delete_messages(chat, del_message)


"""Anonymous Admins"""

db = {}


async def anonymous(event, mode):
    user_id = None
    first_name = None
    e_t = None
    if event.reply_to:
        user = (await event.get_reply_message()).sender
        if isinstance(user, Channel):
            return
        user_id = user.id
        first_name = user.first_name
    elif event.pattern_match.group(1):
        u_obj = event.text.split(None, 2)[1]
        try:
            user = await meow.get_entity(u_obj)
            user_id = user.id
            first_name = user.first_name
        except BaseException:
            pass
    try:
        if event.reply_to:
            e_t = event.text.split(None, 1)[1]
        elif user_id:
            e_t = event.text.split(None, 2)[2]
    except IndexError:
        e_t = None
    db[event.id] = [e_t, user_id, first_name]
    cb_data = str(event.id) + "|" + str(mode)
    a_buttons = Button.inline(
        "Click to prove you are admin", data="bad_{}".format(cb_data)
    )
    await event.reply(
        "It looks like you're anonymous. Tap this button to confirm your identity.",
        buttons=a_buttons,
    )


@inline(pattern=r"bad(\_(.*))")
async def _(e):
    d_ata = ((e.pattern_match.group(1)).decode()).split("_", 1)[1]
    da_ta = d_ata.split("|", 1)
    event_id = int(da_ta[0])
    mode = da_ta[1]
    try:
        cb_data = db[event_id]
    except KeyError:
        return await e.edit("This requests has been expired, please resend it.")
    user_id = cb_data[1]
    first_name = cb_data[2]
    title = cb_data[0]

    if not await cb_can_add_admins(e, e.sender_id):
        return
    if mode == "promote":
        try:
            await e.client.edit_admin(
                e.chat_id,
                int(user_id),
                manage_call=False,
                add_admins=False,
                pin_messages=True,
                delete_messages=True,
                ban_users=True,
                change_info=True,
                invite_users=True,
                title=title if title else "Admin",
            )
            text = "Promoted <b><a href='tg://user?id={}'>{}</a> in <b>{}</b>.".format(
                user_id, first_name or "User", e.chat.title
            )
        except BaseException:
            text = strings.botpromote
    elif mode == "superpromote":
        try:
            await e.client.edit_admin(
                e.chat_id,
                int(user_id),
                manage_call=True,
                add_admins=True,
                pin_messages=True,
                delete_messages=True,
                ban_users=True,
                change_info=True,
                invite_users=True,
                title=title or "Admin",
            )
            text = "Promoted <b><a href='tg://user?id={}'>{}</a> in <b>{}</b> with full rights.".format(
                user_id, first_name or "User", e.chat.title
            )
        except BaseException:
            text = strings.botpromote
    elif mode == "demote":
        try:
            await e.client.edit_admin(
                e.chat_id,
                int(user_id),
                is_admin=False,
                manage_call=False,
                add_admins=False,
                pin_messages=False,
                delete_messages=False,
                ban_users=False,
                change_info=False,
                invite_users=False,
            )
            text = "Demoted <b><a href='tg://user?id={}'>{}</a> !".format(
                user_id, first_name or "User"
            )
        except BaseException:
            text = strings.botpromote
    await e.delete()
    await e.respond(text, parse_mode="html")

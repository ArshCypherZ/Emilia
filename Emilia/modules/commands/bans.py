# DONE: BANS

import time
from datetime import datetime

from pyrogram import filters as pyrofilters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import MessageDeleteForbidden
from pyrogram.types import (
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyParameters,
)

import Emilia.strings as strings
from Emilia import db as xdb
from Emilia import pgram
from Emilia.custom_filter import callbackquery, listen, register
from Emilia.helper.admins import (
    can_ban_users,
    cb_can_ban_users,
    extract_time,
    get_time,
    get_user_reason,
    is_admin,
)
from Emilia.utils.decorators import exception, log_to_channel

db = {}


def _is_group(message):
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def _linked_chat_id(chat_id):
    # replaces GetFullChannelRequest().full_chat.linked_chat_id
    linked = (await pgram.get_chat(chat_id)).linked_chat
    return linked.id if linked else None


@exception
@log_to_channel
async def excecute_operation(
    client,
    event,
    user_id,
    name,
    mode,
    reason="",
    tt=0,
    reply_to=None,
    cb=False,
    actor_id=777000,
    actor="Anonymous",
):
    if reply_to == event.id:
        reply_to = event.reply_to_message_id or event.id
    r = ""
    if reason:
        # Use expandable blockquote for the reason
        r = f"\n\n<blockquote expandable>{reason}</blockquote>"
    if name:
        name = ((name).replace("<", "&lt;")).replace(">", "&gt;")
        
    actor_html = f"<a href='tg://user?id={actor_id}'>{actor}</a>"
    target_html = f"<a href='tg://user?id={user_id}'>{name}</a>"
    
    # message.chat no longer carries the bot's admin rights; fetch them
    me = await pgram.get_chat_member(event.chat.id, "me")
    if me.privileges:
        if not me.privileges.can_restrict_members:
            return await event.reply_text(strings.botban)
            
    if mode in ["ban", "dban"]:
        await pgram.ban_chat_member(event.chat.id, int(user_id))

        if cb:
            await event.delete()
            reply_to = None
        await pgram.send_message(
            event.chat.id,
            f"Yep! {target_html} has been banned by {actor_html}!{r}",
            parse_mode=ParseMode.HTML,
            reply_parameters=ReplyParameters(message_id=reply_to) if reply_to else None,
        )
        return "BAN", user_id, name
        
    elif mode in ["kick", "dkick"]:
        await pgram.ban_chat_member(event.chat.id, int(user_id))
        await pgram.unban_chat_member(event.chat.id, int(user_id))

        if cb:
            await event.delete()
            reply_to = None
        await pgram.send_message(
            event.chat.id,
            f"Yep! {target_html} has been kicked by {actor_html}!{r}",
            parse_mode=ParseMode.HTML,
            reply_parameters=ReplyParameters(message_id=reply_to) if reply_to else None,
        )
        return "KICK", user_id, name
        
    elif mode == "tban":
        if cb:
            await event.delete()
            reply_to = None
        await pgram.ban_chat_member(
            event.chat.id,
            int(user_id),
            until_date=datetime.fromtimestamp(time.time() + int(tt)),
        )
        duration_text = await get_time(int(tt))
        await pgram.send_message(
            event.chat.id,
            f"Yep! {target_html} has been temporarily banned for {duration_text} by {actor_html}!{r}",
            parse_mode=ParseMode.HTML,
            reply_parameters=ReplyParameters(message_id=reply_to) if reply_to else None,
        )
        return "TEMP_BAN", user_id, name

    elif mode == "unban":
        if cb:
            await event.delete()
            reply_to = None
        await pgram.unban_chat_member(event.chat.id, int(user_id))

        await pgram.send_message(
            event.chat.id,
            f"Yep! {target_html} can join the group again! They were unbanned by {actor_html}.",
            reply_parameters=ReplyParameters(message_id=reply_to) if reply_to else None,
            parse_mode=ParseMode.HTML,
        )
        return "UNBAN", user_id, name

    elif mode == "sban":
        await pgram.ban_chat_member(event.chat.id, int(user_id))

    elif mode == "skick":
        await pgram.ban_chat_member(event.chat.id, int(user_id))
        await pgram.unban_chat_member(event.chat.id, int(user_id))


@register(pattern="dban")
@exception
async def dban(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not event.from_user:
        return await a_ban(event, "dban")
    if not await can_ban_users(event, event.from_user.id):
        return
    if event.reply_to_message_id:
        reply_msg = event.reply_to_message
        me = await client.get_chat_member(event.chat.id, "me")
        if me.privileges and me.privileges.can_delete_messages:
            try:
                await reply_msg.delete()
            except MessageDeleteForbidden:
                return await event.reply_text(
                    "I cannot delete one of the messages you tried to delete, most likely because it is a service message or it is too old."
                )
    else:
        return await event.reply_text(
            "You have to reply to a message to delete it and ban the user."
        )
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply_text(strings.nouser)

    if isinstance(user, Chat):
        if user.id == event.chat.id:
            return await event.reply_text(
                "Cannot ban anonymous admins but i deleted the message."
            )
        if await _linked_chat_id(event.chat.id) == user.id:
            return await event.reply_text(
                "Cannot ban linked channels but i deleted the message."
            )

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply_text(strings.ON_ADMIN)
    await excecute_operation(
        client,
        event,
        user.id,
        f,
        "dban",
        reason,
        0,
        event.id,
        False,
        event.from_user.id,
        event.from_user.first_name,
    )


@register(pattern="ban")
@exception
async def ban(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not event.from_user:
        return await a_ban(event, "ban")
    if not await can_ban_users(event, event.from_user.id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply_text(strings.nouser)

    if isinstance(user, Chat):
        if user.id == event.chat.id:
            return await event.reply_text(
                "Cannot perform this command on anonymous admins!"
            )
        if await _linked_chat_id(event.chat.id) == user.id:
            return await event.reply_text(
                "Cannot perform this command on linked channels!"
            )

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply_text(strings.ON_ADMIN)
    await excecute_operation(
        client,
        event,
        user.id,
        f,
        "ban",
        reason,
        0,
        event.id,
        False,
        event.from_user.id,
        event.from_user.first_name,
    )


@register(pattern="sban")
@exception
async def ban(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not event.from_user:
        return await a_ban(event, "sban")
    if not await can_ban_users(event, event.from_user.id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply_text(strings.nouser)

    if isinstance(user, Chat):
        if user.id == event.chat.id:
            return
        if await _linked_chat_id(event.chat.id) == user.id:
            return

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply_text(strings.ON_ADMIN)
    await excecute_operation(
        client,
        event,
        user.id,
        f,
        "sban",
        reason,
        0,
        event.id,
        False,
        event.from_user.id,
        event.from_user.first_name,
    )


@register(pattern="unban")
@exception
async def unban(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not event.from_user:
        return await a_ban(event, "unban")

    if not await can_ban_users(event, event.from_user.id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply_text(strings.nouser)

    if isinstance(user, Chat):
        if user.id == event.chat.id:
            return await event.reply_text(
                "Cannot perform this command on anonymous admins!"
            )
        if await _linked_chat_id(event.chat.id) == user.id:
            return await event.reply_text(
                "Cannot perform this command on linked channels!"
            )

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply_text(strings.ON_ADMIN)
    await excecute_operation(
        client,
        event,
        user.id,
        f,
        "unban",
        reason,
        0,
        event.id,
        False,
        event.from_user.id,
        event.from_user.first_name,
    )


@register(pattern="dkick")
@exception
async def dkick(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not event.from_user:
        return await a_ban(event, "kick")
    if not await can_ban_users(event, event.from_user.id):
        return
    if event.reply_to_message_id:
        reply_msg = event.reply_to_message
        me = await client.get_chat_member(event.chat.id, "me")
        if me.privileges and me.privileges.can_delete_messages:
            try:
                await reply_msg.delete()
            except MessageDeleteForbidden:
                return await event.reply_text(
                    "I cannot delete one of the messages you tried to delete, most likely because it is a service message or it is too old."
                )
    else:
        return await event.reply_text(
            "You have to reply to a message to delete it and kick the user."
        )
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply_text(strings.nouser)

    if isinstance(user, Chat):
        if user.id == event.chat.id:
            return await event.reply_text(
                "Cannot kick anonymous admins but i deleted the message."
            )
        if await _linked_chat_id(event.chat.id) == user.id:
            return await event.reply_text(
                "Cannot kick linked channels but i deleted the message."
            )

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply_text(strings.ON_ADMIN)
    await excecute_operation(
        client,
        event,
        user.id,
        f,
        "kick",
        reason,
        0,
        event.id,
        False,
        event.from_user.id,
        event.from_user.first_name,
    )


@register(pattern="kick")
@exception
async def kick(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not event.from_user:
        return await a_ban(event, "kick")
    if not await can_ban_users(event, event.from_user.id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply_text(strings.nouser)

    if isinstance(user, Chat):
        if user.id == event.chat.id:
            return await event.reply_text(
                "Cannot perform this command on anonymous admins!"
            )
        if await _linked_chat_id(event.chat.id) == user.id:
            return await event.reply_text(
                "Cannot perform this command on linked channels!"
            )

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply_text(strings.ON_ADMIN)
    await excecute_operation(
        client,
        event,
        user.id,
        f,
        "kick",
        reason,
        0,
        event.id,
        False,
        event.from_user.id,
        event.from_user.first_name,
    )


@register(pattern="skick")
@exception
async def skick(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not event.from_user:
        return await a_ban(event, "skick")
    if not await can_ban_users(event, event.from_user.id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply_text(strings.nouser)

    if isinstance(user, Chat):
        if user.id == event.chat.id:
            return
        if await _linked_chat_id(event.chat.id) == user.id:
            return

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply_text(strings.ON_ADMIN)
    await excecute_operation(
        client,
        event,
        user.id,
        f,
        "skick",
        reason,
        0,
        event.id,
        False,
        event.from_user.id,
        event.from_user.first_name,
    )


@register(pattern="tban")
@exception
async def tban(client, event):
    if not _is_group(event):
        return await event.reply_text(strings.is_pvt)
    if not event.from_user:
        return await a_ban(event, "tban")
    if not await can_ban_users(event, event.from_user.id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply_text(strings.nouser)

    if isinstance(user, Chat):
        if user.id == event.chat.id:
            return await event.reply_text(
                "Cannot perform this command on anonymous admins!"
            )
        if await _linked_chat_id(event.chat.id) == user.id:
            return await event.reply_text(
                "Cannot perform this command on linked channels!"
            )

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply_text(strings.ON_ADMIN)
    if not reason:
        return await event.reply_text(
            "You haven't specified a time to ban this user for!"
        )
    if not reason[0].isdigit():
        return await event.reply_text(
            f"Give me the time in numbers to ban this user for!\n{reason} is not a valid number.\n\n **Usage**: /tban @user 3h"
        )
    if len(reason) == 1:
        return await event.reply_text(
            f"""Failed to get specified time!\n'{reason}' does not follow the expected time patterns.\n\nExample time values: 4m = 4 minutes, 3h = 3 hours, 6d = 6 days, 5w = 5 weeks."""
        )
    ban_time = int(await extract_time(event, reason))
    await excecute_operation(
        client,
        event,
        user.id,
        f,
        "tban",
        reason,
        ban_time,
        event.id,
        False,
        event.from_user.id,
        event.from_user.first_name,
    )


# -------Anonymous_Admins--------


async def a_ban(event, mode):
    user_id = None
    first_name = None
    e_t = None
    user_id = None
    first_name = None
    e_t = None

    # Use get_user_reason to extract user reliably
    try:
        user_obj, extra = await get_user_reason(event)
        if user_obj:
            user_id = user_obj.id
            first_name = user_obj.first_name
            e_t = extra
    except TypeError:
        pass

    if not user_id and event.pattern_match.group(1):
        # Logic if get_user_reason fails?
        # get_user_reason handles pattern match/reply.
        pass

    db[event.id] = [e_t, user_id, first_name]
    cb_data = str(event.id) + "|" + str(mode)
    a_buttons = InlineKeyboardButton(
        "Click to prove you are admin", callback_data="banon_{}".format(cb_data)
    )
    await event.reply_text(
        "It looks like you're anonymous. Tap this button to confirm your identity.",
        reply_markup=InlineKeyboardMarkup([[a_buttons]]),
    )


@callbackquery(pattern=r"banon(\_(.*))")
async def rules_anon(client, e):
    if not await cb_can_ban_users(e, e.from_user.id):
        return
    d_ata = (e.pattern_match.group(1)).split("_", 1)[1]
    da_ta = d_ata.split("|", 1)
    event_id = int(da_ta[0])
    mode = da_ta[1]
    try:
        cb_data = db[event_id]
    except KeyError:
        return await e.edit_message_text("This request has been expired. Try again!")
    user_id = cb_data[1]
    fname = cb_data[2]
    reason = cb_data[0]
    mute_time = 0
    if not reason:
        reason = ""
    if not user_id:
        return await e.edit_message_text(strings.nouser)
    if await is_admin(e.message, user_id):
        return await e.edit_message_text(strings.ON_ADMIN)
    if mode in ["tban"]:
        if not reason:
            meow = mode.replace("t", "")
            return await e.edit_message_text(
                f"You haven't specified a time to {meow} this user for!"
            )
        if not reason[0].isdigit():
            return await e.edit_message_text(
                f"Give me the time in numbers!\n{reason} is not a valid number.\n\n **Usage**: /{mode} @user 3h"
            )
        if len(reason) == 1:
            return await e.edit_message_text(
                f"""Failed to get specified time\n'{reason}' does not follow the expected time patterns.\n\nExample time values: 4m = 4 minutes, 3h = 3 hours, 6d = 6 days, 5w = 5 weeks."""
            )
        mute_time = await extract_time(e.message, reason)
    # pass the callback's message as the event; cb=True deletes it
    await excecute_operation(
        client,
        e.message,
        user_id,
        fname,
        mode,
        reason,
        mute_time,
        None,
        True,
    )


@register(pattern="dnd")
@exception
@log_to_channel
async def dnd(client, e):
    try:
        q = e.text.split(maxsplit=1)[1]
    except IndexError:
        q = None
    x = await xdb.dnd.find_one({"chat_id": e.chat.id})
    x = x["mode"] if x else False
    if not q:
        if not x:
            await e.reply_text("**DND** mode is currently off, group is not protected!")
        else:
            await e.reply_text(
                "**DND** mode is currently on, Emilia will autokick newly joined users without usernames."
            )
    elif q in ["on", "yes", "true"]:
        await xdb.dnd.update_one(
            {"chat_id": e.chat.id}, {"$set": {"mode": True}}, upsert=True
        )
        await e.reply_text("DND mode has been turned on!")
        return "DND_ACTIVE", None, None
    elif q in ["off", "no", "false"]:
        await e.reply_text("DND mode has been disabled.")
        await xdb.dnd.update_one(
            {"chat_id": e.chat.id}, {"$set": {"mode": False}}, upsert=True
        )
        return "DND_INACTIVE", None, None
    else:
        await e.reply_text("Expected true/false, got {}".format(q))


@listen(filters=pyrofilters.new_chat_members)
async def dndtr(client, message):
    x = await xdb.dnd.find_one({"chat_id": message.chat.id})
    x = x["mode"] if x else None
    if not x:
        return
    for user in message.new_chat_members:
        # Guard against None user (deleted accounts, system, etc.)
        if not user or not getattr(user, "username", None):
            continue
        try:
            await client.ban_chat_member(message.chat.id, user.id)
            await client.unban_chat_member(message.chat.id, user.id)
        except BaseException:
            pass

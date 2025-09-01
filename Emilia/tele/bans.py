# DONE: BANS

import time

from telethon import Button, errors, events, functions
from telethon.tl.types import Channel

import Emilia.strings as strings
from Emilia import db as xdb
from Emilia import telethn
from Emilia.custom_filter import callbackquery, register
from Emilia.functions.admins import (
    can_ban_users,
    cb_can_ban_users,
    extract_time,
    get_time,
    get_user_reason,
    is_admin,
)
from Emilia.utils.decorators import exception, logging

db = {}


@exception
@logging
async def excecute_operation(
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
        reply_to = event.reply_to_msg_id or event.id
    r = ""
    if reason:
        r = f"\n<b>Reason</b>: <code>{reason}</code>"
    if name:
        name = ((name).replace("<", "&lt;")).replace(">", "&gt;")
    if event.chat.admin_rights:
        if not event.chat.admin_rights.ban_users:
            return await event.reply(strings.botban)
    if mode == "ban":
        await telethn.edit_permissions(
            event.chat_id, int(user_id), until_date=None, view_messages=False
        )

        if cb:
            await event.delete()
            reply_to = None
        await event.respond(
            f'<b>Banned</b> <a href="tg://user?id={user_id}">{name}</a></b>.{r}',
            parse_mode="html",
            reply_to=reply_to,
        )
        return "BAN", user_id, name
    elif mode == "kick":
        await telethn.kick_participant(event.chat_id, int(user_id))

        if cb:
            await event.delete()
            reply_to = None
        await event.respond(
            f'<b>Kicked</b> <a href="tg://user?id={user_id}">{name}</a></b>.{r}',
            parse_mode="html",
            reply_to=reply_to,
        )
        return "KICK", user_id, name
    elif mode == "tban":
        if cb:
            await event.delete()
            reply_to = None
        await telethn.edit_permissions(
            event.chat_id,
            int(user_id),
            until_date=time.time() + int(tt),
            view_messages=False,
        )
        await event.respond(
            f'<b>Banned</b> <a href="tg://user?id={user_id}">{name}</a> for {(await get_time(int(tt)))}!{r}',
            parse_mode="html",
            reply_to=reply_to,
        )
        return "TEMP_BAN", user_id, name

    elif mode == "unban":
        if cb:
            await event.delete()
            reply_to = None
        await telethn.edit_permissions(
            event.chat_id, int(user_id), until_date=None, view_messages=True
        )

        await event.respond(
            "Yep! <b><a href='tg://user?id={}'>{}</a></b> can join again!\n<b>Unbanned by:</b> <a href='tg://user?id={}'>{}</a>".format(
                user_id, name, actor_id, actor
            ),
            reply_to=reply_to,
            parse_mode="html",
        )
        return "UNBAN", user_id, name

    elif mode == "sban":
        await telethn.edit_permissions(
            event.chat_id, int(user_id), until_date=None, view_messages=False
        )

    elif mode == "skick":
        await telethn.kick_participant(event.chat_id, int(user_id))


@register(pattern="dban")
@exception
async def dban(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not event.from_id:
        return await a_ban(event, "dban")
    if not await can_ban_users(event, event.sender_id):
        return
    if event.reply_to_msg_id:
        reply_msg = await event.get_reply_message()
        if event.chat.admin_rights.delete_messages:
            try:
                await reply_msg.delete()
            except errors.MessageDeleteForbiddenError:
                return await event.reply(
                    "I cannot delete one of the messages you tried to delete, most likely because it is a service message or it is too old."
                )
    else:
        return await event.reply(
            "You have to reply to a message to delete it and ban the user."
        )
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply(strings.nouser)

    if isinstance(user, Channel):
        if user.id == event.chat_id:
            return await event.reply(
                "Cannot ban anonymous admins but i deleted the message."
            )
        if (
            await telethn(functions.channels.GetFullChannelRequest(event.chat_id))
        ).full_chat.linked_chat_id == user.id:
            return await event.reply(
                "Cannot ban linked channels but i deleted the message."
            )

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply(strings.ON_ADMIN)
    await excecute_operation(
        event,
        user.id,
        f,
        "dban",
        reason,
        0,
        event.id,
        False,
        event.sender_id,
        event.sender.first_name,
    )


@register(pattern="ban")
@exception
async def ban(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not event.from_id:
        return await a_ban(event, "ban")
    if not await can_ban_users(event, event.sender_id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply(strings.nouser)

    if isinstance(user, Channel):
        if user.id == event.chat_id:
            return await event.reply("Cannot perform this command on anonymous admins!")
        if (
            await telethn(functions.channels.GetFullChannelRequest(event.chat_id))
        ).full_chat.linked_chat_id == user.id:
            return await event.reply("Cannot perform this command on linked channels!")

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply(strings.ON_ADMIN)
    await excecute_operation(
        event,
        user.id,
        f,
        "ban",
        reason,
        0,
        event.id,
        False,
        event.sender_id,
        event.sender.first_name,
    )


@register(pattern="sban")
@exception
async def ban(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not event.from_id:
        return await a_ban(event, "sban")
    if not await can_ban_users(event, event.sender_id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply(strings.nouser)

    if isinstance(user, Channel):
        if user.id == event.chat_id:
            return
        if (
            await telethn(functions.channels.GetFullChannelRequest(event.chat_id))
        ).full_chat.linked_chat_id == user.id:
            return

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply(strings.ON_ADMIN)
    await excecute_operation(
        event,
        user.id,
        f,
        "sban",
        reason,
        0,
        event.id,
        False,
        event.sender_id,
        event.sender.first_name,
    )


@register(pattern="unban")
@exception
async def unban(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not event.from_id:
        return await a_ban(event, "unban")

    if not await can_ban_users(event, event.sender_id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply(strings.nouser)

    if isinstance(user, Channel):
        if user.id == event.chat_id:
            return await event.reply("Cannot perform this command on anonymous admins!")
        if (
            await telethn(functions.channels.GetFullChannelRequest(event.chat_id))
        ).full_chat.linked_chat_id == user.id:
            return await event.reply("Cannot perform this command on linked channels!")

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply(strings.ON_ADMIN)
    await excecute_operation(
        event,
        user.id,
        f,
        "unban",
        reason,
        0,
        event.id,
        False,
        event.sender_id,
        event.sender.first_name,
    )


@register(pattern="dkick")
@exception
async def dkick(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not event.from_id:
        return await a_ban(event, "kick")
    if not await can_ban_users(event, event.sender_id):
        return
    if event.reply_to_msg_id:
        reply_msg = await event.get_reply_message()
        if event.chat.admin_rights.delete_messages:
            try:
                await reply_msg.delete()
            except errors.MessageDeleteForbiddenError:
                return await event.reply(
                    "I cannot delete one of the messages you tried to delete, most likely because it is a service message or it is too old."
                )
    else:
        return await event.reply(
            "You have to reply to a message to delete it and kick the user."
        )
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply(strings.nouser)

    if isinstance(user, Channel):
        if user.id == event.chat_id:
            return await event.reply(
                "Cannot kick anonymous admins but i deleted the message."
            )
        if (
            await telethn(functions.channels.GetFullChannelRequest(event.chat_id))
        ).full_chat.linked_chat_id == user.id:
            return await event.reply(
                "Cannot kick linked channels but i deleted the message."
            )

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply(strings.ON_ADMIN)
    await excecute_operation(
        event,
        user.id,
        f,
        "kick",
        reason,
        0,
        event.id,
        False,
        event.sender_id,
        event.sender.first_name,
    )


@register(pattern="kick")
@exception
async def kick(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not event.from_id:
        return await a_ban(event, "kick")
    if not await can_ban_users(event, event.sender_id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply(strings.nouser)

    if isinstance(user, Channel):
        if user.id == event.chat_id:
            return await event.reply("Cannot perform this command on anonymous admins!")
        if (
            await telethn(functions.channels.GetFullChannelRequest(event.chat_id))
        ).full_chat.linked_chat_id == user.id:
            return await event.reply("Cannot perform this command on linked channels!")

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply(strings.ON_ADMIN)
    await excecute_operation(
        event,
        user.id,
        f,
        "kick",
        reason,
        0,
        event.id,
        False,
        event.sender_id,
        event.sender.first_name,
    )


@register(pattern="skick")
@exception
async def skick(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not event.from_id:
        return await a_ban(event, "skick")
    if not await can_ban_users(event, event.sender_id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply(strings.nouser)

    if isinstance(user, Channel):
        if user.id == event.chat_id:
            return
        if (
            await telethn(functions.channels.GetFullChannelRequest(event.chat_id))
        ).full_chat.linked_chat_id == user.id:
            return

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply(strings.ON_ADMIN)
    await excecute_operation(
        event,
        user.id,
        f,
        "skick",
        reason,
        0,
        event.id,
        False,
        event.sender_id,
        event.sender.first_name,
    )


@register(pattern="tban")
@exception
async def tban(event):
    if not event.is_group:
        return await event.reply(strings.is_pvt)
    if not event.from_id:
        return await a_ban(event, "tban")
    if not await can_ban_users(event, event.sender_id):
        return
    reason = ""
    user = None
    try:
        user, reason = await get_user_reason(event)
    except TypeError:
        pass
    if not user:
        return await event.reply(strings.nouser)

    if isinstance(user, Channel):
        if user.id == event.chat_id:
            return await event.reply("Cannot perform this command on anonymous admins!")
        if (
            await telethn(functions.channels.GetFullChannelRequest(event.chat_id))
        ).full_chat.linked_chat_id == user.id:
            return await event.reply("Cannot perform this command on linked channels!")

        f = user.title

    else:
        f = user.first_name

    if await is_admin(event, user.id):
        return await event.reply(strings.ON_ADMIN)
    if not reason:
        return await event.reply("You haven't specified a time to ban this user for!")
    if not reason[0].isdigit():
        return await event.reply(
            f"Give me the time in numbers to ban this user for!\n{reason} is not a valid number.\n\n **Usage**: /tban @user 3h"
        )
    if len(reason) == 1:
        return await event.reply(
            f"""Failed to get specified time!\n'{reason}' does not follow the expected time patterns.\n\nExample time values: 4m = 4 minutes, 3h = 3 hours, 6d = 6 days, 5w = 5 weeks."""
        )
    ban_time = int(await extract_time(event, reason))
    await excecute_operation(
        event,
        user.id,
        f,
        "tban",
        reason,
        ban_time,
        event.id,
        False,
        event.sender_id,
        event.sender.first_name,
    )


# -------Anonymous_Admins--------


async def a_ban(event, mode):
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
            user = await telethn.get_entity(u_obj)
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
        "Click to prove you are admin", data="banon_{}".format(cb_data)
    )
    await event.reply(
        "It looks like you're anonymous. Tap this button to confirm your identity.",
        buttons=a_buttons,
    )


@callbackquery(pattern=r"banon(\_(.*))")
async def rules_anon(e):
    if not await cb_can_ban_users(e, e.sender_id):
        return
    d_ata = ((e.pattern_match.group(1)).decode()).split("_", 1)[1]
    da_ta = d_ata.split("|", 1)
    event_id = int(da_ta[0])
    mode = da_ta[1]
    try:
        cb_data = db[event_id]
    except KeyError:
        return await e.edit("This request has been expired. Try again!")
    user_id = cb_data[1]
    fname = cb_data[2]
    reason = cb_data[0]
    mute_time = 0
    if not reason:
        reason = ""
    if not user_id:
        return await e.edit(strings.nouser)
    if await is_admin(e, user_id):
        return await e.edit(strings.ON_ADMIN)
    if mode in ["tban"]:
        if not reason:
            meow = mode.replace("t", "")
            return await e.edit(
                f"You haven't specified a time to {meow} this user for!"
            )
        if not reason[0].isdigit():
            return await e.edit(
                f"Give me the time in numbers!\n{reason} is not a valid number.\n\n **Usage**: /{mode} @user 3h"
            )
        if len(reason) == 1:
            return await e.edit(
                f"""Failed to get specified time\n'{reason}' does not follow the expected time patterns.\n\nExample time values: 4m = 4 minutes, 3h = 3 hours, 6d = 6 days, 5w = 5 weeks."""
            )
        mute_time = await extract_time(e, reason)
    await excecute_operation(
        e,
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
@logging
async def dnd(e):
    try:
        q = e.text.split(maxsplit=1)[1]
    except IndexError:
        q = None
    x = await xdb.dnd.find_one({"chat_id": e.chat_id})
    x = x["mode"] if x else False
    if not q:
        if not x:
            await e.reply("**DND** mode is currently off, group is not protected!")
        else:
            await e.reply(
                "**DND** mode is currently on, Emilia will autokick newly joined users without usernames."
            )
    elif q in ["on", "yes", "true"]:
        await xdb.dnd.update_one(
            {"chat_id": e.chat_id}, {"$set": {"mode": True}}, upsert=True
        )
        await e.reply("DND mode has been turned on!")
        return "DND_ACTIVE", None, None
    elif q in ["off", "no", "false"]:
        await e.reply("DND mode has been disabled.")
        await xdb.dnd.update_one(
            {"chat_id": e.chat_id}, {"$set": {"mode": False}}, upsert=True
        )
        return "DND_INACTIVE", None, None
    else:
        await e.reply("Expected true/false, got {}".format(q))


@telethn.on(events.ChatAction(func=lambda e: e.user_joined))
async def dndtr(e):
    # Guard against None user (deleted accounts, system, etc.)
    if not getattr(e, "user", None) or not getattr(e.user, "username", None):
        return
    x = await xdb.dnd.find_one({"chat_id": e.chat_id})
    x = x["mode"] if x else None
    if not x:
        return
    try:
        await e.client.kick_participant(e.chat_id, e.user_id)
    except BaseException:
        pass

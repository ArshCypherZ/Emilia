# DONE: Approval

from telethon import Button
from telethon.tl.types import Channel

import Emilia.strings as strings
from Emilia import db
from Emilia.custom_filter import callbackquery as inline
from Emilia.custom_filter import register
from Emilia.functions.admins import (
    can_ban_users,
    cb_can_change_info,
    get_user_reason,
    is_admin,
    is_owner,
)
from Emilia.helper.get_data import GetChat
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *

approve_d = db.approve_d


@register(pattern="approve")
@logging
async def appr(event):
    if event.is_private:
        chat_id = await connection(event)
        title = await GetChat(chat_id)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
    else:
        chat_id = event.chat_id
        title = event.chat.title

    if isinstance(event.sender, Channel):
        await a_approval(event, "approve")
    else:
        if not await can_ban_users(event, event.sender_id):
            return
        user, reason = await get_user_reason(event)
        if not user:
            return await event.reply(strings.nouser)
        if await is_admin(event, user.id, pm_mode=True):
            return await event.reply(strings.ON_ADMIN)
        # Idempotent approve: upsert on (chat_id,user_id)
        await approve_d.update_one(
            {"user_id": int(user.id), "chat_id": chat_id},
            {"$set": {"name": user.first_name}},
            upsert=True,
        )
        a_str = "<a href='tg://user?id={}'>{}</a> has been approved in {}! They will now be ignored by automated admin actions like locks, blocklists, and antiflood."
        await event.respond(
            a_str.format(user.id, user.first_name, title),
            reply_to=event.reply_to_msg_id or event.id,
            parse_mode="html",
        )
        return "APPROVE", user.id, user.first_name


@register(pattern="unapprove")
@logging
async def dissapprove(event):
    if event.is_private:
        chat_id = await connection(event)
        title = await GetChat(chat_id)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    if isinstance(event.sender, Channel):
        await a_approval(event, "disapprove")
    else:
        if not await can_ban_users(event, event.sender_id):
            return

        user, reason = await get_user_reason(event)
        if not user:
            return await event.reply(strings.nouser)
        if await is_admin(event, user.id, pm_mode=True):
            return await event.reply(strings.ON_ADMIN)
        if await approve_d.find_one({"user_id": int(user.id), "chat_id": chat_id}):
            await approve_d.delete_one({"user_id": int(user.id), "chat_id": chat_id})
            await event.reply(f"{user.first_name} is no longer approved in {title}.")
            return "DISAPPROVE", user.id, user.first_name
        await event.reply(f"{user.first_name} isn't approved yet!")


@register(pattern="approved")
async def approved(event):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    app_rove_d = approve_d.find({"chat_id": chat_id})
    out_str = f"No users are approved in {title}"
    async for app in app_rove_d:
        out_str = "The following users are approved:"
        out_str += "\n- `{}`: {}".format(app["user_id"], app["name"])
    await event.reply(out_str)


@register(pattern="approval")
async def check_approval(event):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title

    if not event.reply_to and not event.pattern_match.group(1):
        if isinstance(event.sender, Channel):
            return await event.reply(
                "You are an anonymous user or a sender chat as channel, please revert back to a normal user to perform this task!"
            )
        user = event.sender
    else:
        user, xtra = await get_user_reason(event)
        if not user:
            return

    if await approve_d.find_one({"user_id": int(user.id), "chat_id": chat_id}):
        await event.reply(
            f"{user.first_name} is an approved user in {title}. Locks, antiflood, and blocklists won't apply to them."
        )
    else:
        await event.reply(
            f"{user.first_name} is not an approved user in {title}. They are affected by normal commands."
        )


@register(pattern="unapproveall")
async def unapprove_all(event, do=False):
    if event.is_private:
        chat_id = await connection(event)
        title = await GetChat(chat_id)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
    else:
        chat_id = event.chat_id
        title = event.chat.title

    if do:
        return chat_id
    if isinstance(event.sender, Channel):
        await a_approval(event, "unapproveall")
    else:
        if not await is_owner(event, event.sender_id):
            return
        c_text = f"Are you sure you would like to unapprove **ALL** users in {title}? This action cannot be undone."
        buttons = [
            [Button.inline("Unapprove all users", data="un_ap")],
            [Button.inline("Cancel", data="c_un_ap")],
        ]
        await event.reply(c_text, buttons=buttons)


@inline(pattern="un_ap")
async def un_app(event):
    chat_id = await unapprove_all(event, do=True)
    if not await is_owner(event, event.sender_id, chat_id=chat_id):
        return
    await approve_d.delete_many({"chat_id": chat_id})
    await event.edit(
        "Unapproved all users in chat. All users will now be affected by locks, blocklists, and antiflood."
    )


@inline(pattern="c_un_ap")
async def c_un_ap(event):
    chat_id = await unapprove_all(event, do=True)
    if not await is_owner(event, event.sender_id, chat_id=chat_id):
        return
    await event.edit("Unapproval of all approved users has been cancelled")


# Anonymous Admins
async def a_approval(event, mode):
    if mode in ["approve", "disapprove"]:
        user, reason = await get_user_reason(event)
        if not user:
            return await event.reply(strings.nouser)
        cb_data = str(user.id) + "|" + mode + "|" + str(user.first_name[:15])
    elif mode == "unapproveall":
        cb_data = str(6) + "|" + "unapproveall" + "|" + "noise"
    a_text = "It looks like you're anonymous. Tap this button to confirm your identity."
    a_button = Button.inline(
        "Click to prove you are admin", data="anap_{}".format(cb_data)
    )
    await event.reply(a_text, buttons=a_button)


@inline(pattern=r"anap(\_(.*))")
async def _(event):
    input = ((event.pattern_match.group(1)).decode()).split("_", 1)[1]
    user, mode, name = input.split("|")
    user = int(user.strip())
    mode = mode.strip()
    name = name.strip()
    if mode == "unapproveall":
        if not await is_owner(event, event.sender_id):
            return
    else:
        if not await cb_can_change_info(event, event.sender_id):
            return
    if mode == "disapprove":
        if await is_admin(event, user):
            return await event.edit(strings.ON_ADMIN)
        if await approve_d.find_one({"user_id": int(user), "chat_id": event.chat_id}):
            await approve_d.delete_one({"user_id": int(user), "chat_id": event.chat_id})
            await event.edit(f"{name} is no longer approved in {event.chat.title}.")
            return
        await event.edit(f"{name} isn't approved yet!")
    elif mode == "approve":
        if await is_admin(event, user):
            return await event.edit(strings.ON_ADMIN)
        a_str = "<a href='tg://user?id={}'>{}</a> has been approved in {}! They will now be ignored by automated admin actions like locks, blocklists, and antiflood."
        await event.edit(
            a_str.format(user, name, event.chat.title),
            parse_mode="html",
        )
        # Idempotent approve via upsert
        await approve_d.update_one(
            {"user_id": int(user), "chat_id": event.chat_id},
            {"$set": {"name": name}},
            upsert=True,
        )
    elif mode == "unapproveall":
        c_text = f"Are you sure you would like to unapprove **ALL** users in {event.chat.title}? This action cannot be undone."
        buttons = [
            [Button.inline("Unapprove all users", data="un_ap")],
            [Button.inline("Cancel", data="c_un_ap")],
        ]
        await event.edit(c_text, buttons=buttons)

# DONE: Approval

from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters

import Emilia.strings as strings
from Emilia import db
from Emilia.custom_filter import callbackquery as inline
from Emilia.custom_filter import register
from Emilia.helper.admins import (
    can_ban_users,
    cb_can_change_info,
    get_user_reason,
    is_admin,
    is_owner,
)
from Emilia.helper.get_data import GetChat
from Emilia.modules.plugins.connection.connection import connection
from Emilia.utils.decorators import *

approve_d = db.approve_d


@register(pattern="approve")
@log_to_channel
async def appr(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        title = await GetChat(chat_id)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
    else:
        chat_id = message.chat.id
        title = message.chat.title

    if message.sender_chat:
        await a_approval(message, "approve")
    else:
        sender_id = message.from_user.id if message.from_user else None
        if not await can_ban_users(message, sender_id):
            return
        user, reason = await get_user_reason(message)
        if not user:
            return await message.reply_text(strings.nouser)
        if await is_admin(message, user.id, pm_mode=True):
            return await message.reply_text(strings.ON_ADMIN)
        # Idempotent approve: upsert on (chat_id,user_id)
        await approve_d.update_one(
            {"user_id": int(user.id), "chat_id": chat_id},
            {"$set": {"name": user.first_name}},
            upsert=True,
        )
        a_str = "<a href='tg://user?id={}'>{}</a> has been approved in {}! They will now be ignored by automated admin actions like locks, blocklists, and antiflood."
        await message.reply_text(
            a_str.format(user.id, user.first_name, title),
            reply_parameters=ReplyParameters(
                message_id=message.reply_to_message_id or message.id
            ),
            parse_mode=ParseMode.HTML,
        )
        return "APPROVE", user.id, user.first_name


@register(pattern="unapprove")
@log_to_channel
async def dissapprove(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        title = await GetChat(chat_id)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
    else:
        chat_id = message.chat.id
        title = message.chat.title
    if message.sender_chat:
        await a_approval(message, "disapprove")
    else:
        sender_id = message.from_user.id if message.from_user else None
        if not await can_ban_users(message, sender_id):
            return

        user, reason = await get_user_reason(message)
        if not user:
            return await message.reply_text(strings.nouser)
        if await is_admin(message, user.id, pm_mode=True):
            return await message.reply_text(strings.ON_ADMIN)
        if await approve_d.find_one({"user_id": int(user.id), "chat_id": chat_id}):
            await approve_d.delete_one({"user_id": int(user.id), "chat_id": chat_id})
            await message.reply_text(
                f"{user.first_name} is no longer approved in {title}."
            )
            return "DISAPPROVE", user.id, user.first_name
        await message.reply_text(f"{user.first_name} isn't approved yet!")


@register(pattern="approved")
async def approved(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title
    app_rove_d = approve_d.find({"chat_id": chat_id})
    out_str = f"No users are approved in {title}"
    async for app in app_rove_d:
        out_str = "The following users are approved:"
        out_str += "\n- `{}`: {}".format(app["user_id"], app["name"])
    await message.reply_text(out_str)


@register(pattern="approval")
async def check_approval(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title

    if not message.reply_to_message and not message.pattern_match.group(1):
        if message.sender_chat:
            return await message.reply_text(
                "You are an anonymous user or a sender chat as channel, please revert back to a normal user to perform this task!"
            )
        user = message.from_user
    else:
        user, xtra = await get_user_reason(message)
        if not user:
            return

    if await approve_d.find_one({"user_id": int(user.id), "chat_id": chat_id}):
        await message.reply_text(
            f"{user.first_name} is an approved user in {title}. Locks, antiflood, and blocklists won't apply to them."
        )
    else:
        await message.reply_text(
            f"{user.first_name} is not an approved user in {title}. They are affected by normal commands."
        )


@register(pattern="unapproveall")
async def unapprove_all(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        title = await GetChat(chat_id)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
    else:
        chat_id = message.chat.id
        title = message.chat.title

    if message.sender_chat:
        await a_approval(message, "unapproveall")
    else:
        sender_id = message.from_user.id if message.from_user else None
        if not await is_owner(message, sender_id):
            return
        c_text = f"Are you sure you would like to unapprove **ALL** users in {title}? This action cannot be undone."
        buttons = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Unapprove all users", callback_data="un_ap")],
                [InlineKeyboardButton("Cancel", callback_data="c_un_ap")],
            ]
        )
        await message.reply_text(c_text, reply_markup=buttons)


async def _cb_chat_id(query):
    # replaces unapprove_all(event, do=True); resolves connected chat in PM
    msg = query.message
    if msg.chat.type == ChatType.PRIVATE:
        msg.from_user = query.from_user
        return await connection(msg)
    return msg.chat.id


@inline(pattern="un_ap")
async def un_app(client, query):
    chat_id = await _cb_chat_id(query)
    if not await is_owner(query.message, query.from_user.id, chat_id=chat_id):
        return
    await approve_d.delete_many({"chat_id": chat_id})
    await query.edit_message_text(
        "Unapproved all users in chat. All users will now be affected by locks, blocklists, and antiflood."
    )


@inline(pattern="c_un_ap")
async def c_un_ap(client, query):
    chat_id = await _cb_chat_id(query)
    if not await is_owner(query.message, query.from_user.id, chat_id=chat_id):
        return
    await query.edit_message_text("Unapproval of all approved users has been cancelled")


# Anonymous Admins
async def a_approval(message, mode):
    if mode in ["approve", "disapprove"]:
        user, reason = await get_user_reason(message)
        if not user:
            return await message.reply_text(strings.nouser)
        cb_data = str(user.id) + "|" + mode + "|" + str(user.first_name[:15])
    elif mode == "unapproveall":
        cb_data = str(6) + "|" + "unapproveall" + "|" + "noise"
    a_text = "It looks like you're anonymous. Tap this button to confirm your identity."
    a_button = InlineKeyboardButton(
        "Click to prove you are admin", callback_data="anap_{}".format(cb_data)
    )
    await message.reply_text(a_text, reply_markup=InlineKeyboardMarkup([[a_button]]))


@inline(pattern=r"anap(\_(.*))")
async def _(client, query):
    input = (query.pattern_match.group(1)).split("_", 1)[1]
    user, mode, name = input.split("|")
    user = int(user.strip())
    mode = mode.strip()
    name = name.strip()
    if mode == "unapproveall":
        if not await is_owner(query.message, query.from_user.id):
            return
    else:
        if not await cb_can_change_info(query, query.from_user.id):
            return
    chat_id = query.message.chat.id
    title = query.message.chat.title
    if mode == "disapprove":
        if await is_admin(query.message, user):
            return await query.edit_message_text(strings.ON_ADMIN)
        if await approve_d.find_one({"user_id": int(user), "chat_id": chat_id}):
            await approve_d.delete_one({"user_id": int(user), "chat_id": chat_id})
            await query.edit_message_text(f"{name} is no longer approved in {title}.")
            return
        await query.edit_message_text(f"{name} isn't approved yet!")
    elif mode == "approve":
        if await is_admin(query.message, user):
            return await query.edit_message_text(strings.ON_ADMIN)
        a_str = "<a href='tg://user?id={}'>{}</a> has been approved in {}! They will now be ignored by automated admin actions like locks, blocklists, and antiflood."
        await query.edit_message_text(
            a_str.format(user, name, title),
            parse_mode=ParseMode.HTML,
        )
        # Idempotent approve via upsert
        await approve_d.update_one(
            {"user_id": int(user), "chat_id": chat_id},
            {"$set": {"name": name}},
            upsert=True,
        )
    elif mode == "unapproveall":
        c_text = f"Are you sure you would like to unapprove **ALL** users in {title}? This action cannot be undone."
        buttons = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Unapprove all users", callback_data="un_ap")],
                [InlineKeyboardButton("Cancel", callback_data="c_un_ap")],
            ]
        )
        await query.edit_message_text(c_text, reply_markup=buttons)

import asyncio
import csv
import os
import uuid
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, tostring

import orjson
from pyrogram.enums import ButtonStyle, ChatMemberStatus, ChatType, ParseMode
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import Emilia.strings as strings
from Emilia import BOT_ID, DEV_USERS, LOGGER, OWNER_ID, pgram
from Emilia.custom_filter import callbackquery as inline
from Emilia.custom_filter import listen, register
from Emilia.helper.admins import *
from Emilia.helper.admins import get_user_reason as get_user
from Emilia.helper.get_data import GetChat
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo import feds_db as db
from Emilia.utils.tg_safe import flood_safe

# im_bannable
ADMINS = list(DEV_USERS) + [BOT_ID, OWNER_ID]
export = {}
anon_db = {}


async def is_user_fed_admin(fed_id, user_id):
    fed_admins = await db.get_all_fed_admins(fed_id) or []
    if int(user_id) in fed_admins or int(user_id) == OWNER_ID:
        return True
    else:
        return False


@register(pattern="newfed")
async def newfed(client, message):
    if not message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "Create your federation in my PM - not in a group."
        )

    if len(message.text.split(" ", 1)) == 2:
        name = message.text.split(" ", 1)[1]
    else:
        return await message.reply_text(
            "You need to give your federation a name! Federation names can be up to 64 characters long."
        )

    f_owner = await db.get_user_owner_fed_full(message.from_user.id)
    if f_owner:
        fed_name = f_owner[1]
        return await message.reply_text(
            f"You already have a federation called `{fed_name}` ; you can't create another. If you would like to rename it, use `/renamefed`."
        )
    if len(name) > 64:
        return await message.reply_text(
            "Federation names can only be upto 64 charactors long."
        )
    fed_id = str(uuid.uuid4())
    await db.new_fed(message.from_user.id, fed_id, name)
    await message.reply_text(
        f"Created new federation with FedID: `{fed_id}`.\nUse this ID to join the federation! eg:\n`/joinfed {fed_id}`"
    )


@register(pattern="delfed")
async def del_fed(client, message):
    if not message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "Delete your federation in my PM - not in a group."
        )
    fedowner = await db.get_user_owner_fed_full(message.from_user.id)
    if not fedowner:
        return await message.reply_text(
            "It doesn't look like you have a federation yet!"
        )
    name = fedowner[1]
    fed_id = fedowner[0]
    await message.reply_text(
        "Are you sure you want to delete your federation? This action cannot be undone - you will lose your entire ban list, and '{}' will be permanently gone.".format(
            name
        ),
        reply_parameters=None,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Delete Federation", callback_data="rmfed_{}".format(fed_id),
                        style=ButtonStyle.DANGER,
                    )
                ],
                [InlineKeyboardButton("Cancel", callback_data="cancel_delete", style=ButtonStyle.DEFAULT)],
            ]
        ),
    )


@inline(pattern=r"rmfed(\_(.*))")
async def delete_fed(client, query):
    data = query.pattern_match.group(1)
    fed_id = data.split("_", 1)[1]
    await db.del_fed(fed_id)
    await query.edit_message_text(
        "You have deleted your federation! All chats linked to it are now federation-less."
    )


@inline(pattern=r"cancel_delete")
async def delete_fed(client, query):
    await query.edit_message_text("Federation deletion cancelled.")


@register(pattern="renamefed")
async def rename(client, message):
    if not message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("You can only rename your fed in PM.")
    fedowner = await db.get_user_owner_fed_full(message.from_user.id)
    if not fedowner:
        return await message.reply_text(
            "It doesn't look like you have a federation yet!"
        )
    if not message.pattern_match.group(1):
        return await message.reply_text(
            "You need to give your federation a new name! Federation names can be up to 64 characters long."
        )
    elif len(message.pattern_match.group(1)) > 64:
        return await message.reply_text(
            "Federation names cannot be over 64 characters long."
        )
    name = fedowner[1]
    fed_id = fedowner[0]
    new_name = message.text.split(None, 1)[1]
    await db.rename_fed(fed_id, new_name)
    final_text = f"Tada! I've renamed your federation from '{name}' to '{new_name}'. (FedID: `{fed_id}`)."
    await message.reply_text(final_text)
    log_c = await db.get_fed_log(fed_id)
    if log_c and log_c != message.chat.id:
        await pgram.send_message(
            log_c,
            f"Federation {name} ({fed_id}) has been renamed to {new_name} by {message.from_user.first_name} ({message.from_user.id})",
        )


async def botfban(chat_id, user_id):
    try:
        p = await pgram.get_chat_member(chat_id, user_id)
    except UserNotParticipant:
        return False
    # ChannelParticipant/ChannelParticipantAdmin isinstance checks
    # mapped to pyrogram ChatMemberStatus + privileges.
    if p.status == ChatMemberStatus.MEMBER:
        return False
    elif p.status == ChatMemberStatus.ADMINISTRATOR:
        if not (p.privileges and p.privileges.can_restrict_members):
            return False
        return True


@register(pattern="joinfed")
async def jfed(client, message, sender_id: int = None, anon: bool = False):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title

    if not anon:
        if not message.from_user:
            return await anon_fed(message, "joinfed")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    if message.chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.PRIVATE,
    ):
        return

    if not await is_owner(message, sender_id):
        return
    if not await botfban(chat_id, BOT_ID):
        return await message.reply_text(
            "You need to give me ban rights in order to join a federation!"
        )
    args = message.pattern_match.group(1)
    if not args:
        return await message.reply_text(
            "You need to specify which federation you're asking about by giving me a FedID!"
        )
    if len(args) < 10:
        return await message.reply_text(strings.INVALID_FEDID)
    getfed = await db.search_fed_by_id(args)
    if not getfed:
        return await message.reply_text(strings.NO_SUCH_FED)
    name = getfed["fedname"]
    fed_id = await db.get_chat_fed(chat_id)
    if fed_id:
        await db.chat_leave_fed(fed_id, chat_id)
    await db.chat_join_fed(args, chat_id)
    await message.reply_text(
        f'Successfully joined the "{name}" federation! All new federation bans will now also remove the members from {title}.'
    )
    log_c = await db.get_fed_log(fed_id)
    if log_c and log_c != chat_id:
        await pgram.send_message(
            log_c,
            f"Chat {title} [{chat_id}] has joined the federation {name} ({fed_id})!",
        )


@register(pattern="leavefed")
async def lfed(client, message, sender_id: int = None, anon: bool = False):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "leavefed")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None

    if not await is_owner(message, sender_id):
        return
    fed_id = await db.get_chat_fed(chat_id)
    if fed_id:
        fed = await db.search_fed_by_id(fed_id)
        fname = fed.get("fedname", fed_id) if fed else fed_id
        await db.chat_leave_fed(fed_id, chat_id)
        await message.reply_text(
            'Chat {} has left the "{}" federation.'.format(title, fname)
        )
    else:
        await message.reply_text("This chat isn't currently in any federations!")


@register(pattern="fpromote")
async def fp(client, message, sender_id: int = None, anon: bool = False):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is made to be used in group chats, not in pm!"
        )
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "fpromote")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    user = None
    try:
        user, extra = await get_user(message)
    except TypeError:
        pass
    if not user:
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(
            "Only federation creators can promote people, and you don't seem to have a federation to promote to!"
        )
    fname = fedowner[1]
    fed_id = fedowner[0]
    if user.id == sender_id:
        return await message.reply_text("Yeah well you are the fed owner!")
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if fban:
        if fbanreason:
            reason = f"\n\nReason: <code>{fbanreason}</code>"
        else:
            reason = ""
        txt = f"User <a href='tg://user?id={user.id}'>{user.first_name}</a> is fbanned in {fname}. You should unfban them before promoting.{reason}"
        return await message.reply_text(txt, parse_mode=ParseMode.HTML)
    getuser = await db.search_user_in_fed(fed_id, user.id)
    if getuser:
        return await message.reply_text(
            f"<a href='tg://user?id={user.id}'>{user.first_name}</a> is already an admin in {fname}!",
            parse_mode=ParseMode.HTML,
        )
    cb_data = str(sender_id) + "|" + str(user.id)
    ftxt = f"Please get <a href='tg://user?id={user.id}'>{user.first_name}</a> to confirm that they would like to be fed admin for {fname}"
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Accept", callback_data=f"fp_{cb_data}", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton("Decline", callback_data=f"nofp_{cb_data}", style=ButtonStyle.DANGER),
            ]
        ]
    )
    await message.reply_text(
        ftxt, reply_parameters=None, reply_markup=buttons, parse_mode=ParseMode.HTML
    )


@inline(pattern=r"fp(\_(.*))")
async def fp_cb(client, query):
    input = (query.pattern_match.group(1)).split("_", 1)[1]
    owner_id, user_id = input.split("|")
    owner_id = int(owner_id.strip())
    user_id = int(user_id.strip())
    fedowner = await db.get_user_owner_fed_full(owner_id)
    if not fedowner:
        return await query.answer("This federation no longer exists.", show_alert=True)
    fname = fedowner[1]
    fed_id = fedowner[0]
    if not query.from_user.id == user_id:
        return await query.answer(
            "You are not the user being fpromoted", show_alert=True
        )
    name = (await client.get_users(user_id)).first_name
    await db.user_join_fed(fed_id, user_id)
    res = f"User <a href='tg://user?id={user_id}'>{name}</a> is now an admin of {fname} (<code>{fed_id}</code>)"
    await query.edit_message_text(res, parse_mode=ParseMode.HTML)
    await db.add_fname(user_id, query.from_user.first_name)


@inline(pattern=r"nofp(\_(.*))")
async def nofp(client, query):
    pata = query.pattern_match.group(1)
    input = pata.split("_", 1)[1]
    owner_id, user_id = input.split("|")
    owner_id = int(owner_id.strip())
    user_id = int(user_id.strip())
    await db.get_user_owner_fed_full(owner_id)
    if query.from_user.id == owner_id:
        user = await client.get_users(owner_id)
        await query.edit_message_text(
            f"Fedadmin promotion cancelled by <a href='tg://user?id={user.id}'>{user.first_name}</a>",
            parse_mode=ParseMode.HTML,
        )
    elif query.from_user.id == user_id:
        user = await client.get_users(user_id)
        await query.edit_message_text(
            f"Fedadmin promotion has been refused by <a href='tg://user?id={user.id}'>{user.first_name}</a>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await query.answer("You are not the user being fpromoted")


@register(pattern="fdemote")
async def fd(client, message, sender_id: int = None, anon: bool = False):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is made to be used in group chats, not in pm!"
        )
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "fdemote")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    user = None
    try:
        user, extra = await get_user(message)
    except TypeError:
        pass
    if not user:
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(
            "Only federation creators can demote people, and you don't seem to have a federation to promote to!"
        )
    fname = fedowner[1]
    fed_id = fedowner[0]
    if not (await db.search_user_in_fed(fed_id, user.id)):
        return await message.reply_text(
            f"This person isn't a federation admin for '{fname}', how could I demote them?"
        )
    await db.user_demote_fed(fed_id, user.id)
    await message.reply_text(
        f"User <a href='tg://user?id={user.id}'>{user.first_name}</a> is no longer an admin of {fname} ({fed_id})",
        parse_mode=ParseMode.HTML,
    )


@register(pattern="(ftransfer|fedtransfer)")
async def ft(client, message, sender_id: int = None, anon: bool = False):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(
            "This command is made to be used in group chats, not in pm!"
        )
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "ftransfer")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    user_r = None
    if not await is_admin(message, sender_id):
        return await message.reply_text(strings.NOT_ADMIN)
    try:
        user_r, extra = await get_user(message)
    except TypeError:
        pass
    if not user_r:
        return
    if user_r.bot:
        return await message.reply_text("Bots can't own federations.")
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text("You don't have a fed to transfer!")
    fname = fedowner[1]
    fed_id = fedowner[0]
    if user_r.id == sender_id:
        return await message.reply_text("You can only transfer your fed to others!")
    ownerfed = await db.get_user_owner_fed_full(user_r.id)
    if ownerfed:
        return await message.reply_text(
            f"<a href='tg://user?id={user_r.id}'>{user_r.first_name}</a> already owns a federation - they can't own another.",
            parse_mode=ParseMode.HTML,
        )
    getuser = await db.search_user_in_fed(fed_id, user_r.id)
    if not getuser:
        return await message.reply_text(
            f"<a href='tg://user?id={user_r.id}'>{user_r.first_name}</a> isn't an admin in {fname} - you can only give your fed to other admins.",
            parse_mode=ParseMode.HTML,
        )
    cb_data = str(sender_id) + "|" + str(user_r.id)
    text = f"<a href='tg://user?id={user_r.id}'>{user_r.first_name}</a>, please confirm you would like to receive fed {fname} (<code>{fed_id}</code>) from <a href='tg://user?id={sender_id}'>{message.from_user.first_name}</a>"
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Accept", callback_data=f"ft_{cb_data}", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton("Decline", callback_data=f"noft_{cb_data}", style=ButtonStyle.DANGER),
            ]
        ]
    )
    await message.reply_text(
        text, reply_parameters=None, reply_markup=buttons, parse_mode=ParseMode.HTML
    )


@inline(pattern=r"ft(\_(.*))")
async def ft(client, query):
    input = (query.pattern_match.group(1)).split("_", 1)[1]
    input = input.split("|", 1)
    owner_id = int(input[0])
    user_id = int(input[1])
    if not query.from_user.id == user_id:
        return await query.answer(
            "This action is not intended for you.", show_alert=True
        )
    fedowner = await db.get_user_owner_fed_full(owner_id)
    if not fedowner:
        return await query.answer("This federation no longer exists.", show_alert=True)
    fed_id = fedowner[0]
    fname = fedowner[1]
    try:
        owner = await client.get_users(owner_id)
    except Exception:
        return
    e_text = f"<a href='tg://user?id={owner.id}'>{owner.first_name}</a>, please confirm that you wish to send fed {fname} (<code>{fed_id}</code>) to <a href='tg://user?id={query.from_user.id}'>{query.from_user.first_name}</a> this cannot be undone."
    cb_data = str(owner.id) + "|" + str(user_id)
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"ftc_{cb_data}", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton("Cancel", callback_data=f"ftnoc_{cb_data}", style=ButtonStyle.DEFAULT),
            ]
        ]
    )
    await query.edit_message_text(
        e_text, reply_markup=buttons, parse_mode=ParseMode.HTML
    )


@inline(pattern=r"noft(\_(.*))")
async def ft_decline(client, query):
    input = (query.pattern_match.group(1)).split("_", 1)[1]
    input = input.split("|", 1)
    owner_id = int(input[0])
    user_id = int(input[1])
    if query.from_user.id not in [user_id, owner_id]:
        return await query.answer(
            "This action is not intended for you.", show_alert=True
        )
    if query.from_user.id == owner_id:
        user_name = ((query.from_user.first_name).replace("<", "&lt;")).replace(
            ">", "&gt;"
        )
        o_text = (
            "<a href='tg://user?id={}'>{}</a> has cancelled the fed transfer.".format(
                owner_id, user_name
            )
        )
    elif query.from_user.id == user_id:
        user_name = ((query.from_user.first_name).replace("<", "&lt;")).replace(
            ">", "&gt;"
        )
        o_text = (
            "<a href='tg://user?id={}'>{}</a> has declined the fed transfer.".format(
                owner_id, user_name
            )
        )
    await query.edit_message_text(o_text, parse_mode=ParseMode.HTML, reply_markup=None)


ftransfer_log = """
<b>Fed Transfer</b>
<b>Fed:</b> {}
<b>New Fed Owner:</b> <a href='tg://user?id={}'>{}</a> - <code>{}</code>
<b>Old Fed Owner:</b> <a href='tg://user?id={}'>{}</a> - <code>{}</code>

<a href='tg://user?id={}'>{}</a> is now the fed owner. They can promote/demote admins as they like.
"""


@inline(pattern=r"ftc(\_(.*))")
async def ft_confirm(client, query):
    input = (query.pattern_match.group(1)).split("_", 1)[1]
    input = input.split("|", 1)
    owner_id = int(input[0])
    user_id = int(input[1])
    if not query.from_user.id == owner_id:
        return await query.answer(
            "This action is not intended for you.", show_alert=True
        )
    f_text = "Congratulations! Federation {} (<code>{}</code>) has successfully been transferred from <a href='tg://user?id={}'>{}</a> to <a href='tg://user?id={}'>{}</a>."
    o_name = ((query.from_user.first_name).replace("<", "&lt;")).replace(">", "&gt;")
    n_name = (
        ((await client.get_users(user_id)).first_name).replace("<", "&lt;")
    ).replace(">", "&gt;")
    fedowner = await db.get_user_owner_fed_full(owner_id)
    if not fedowner:
        return await query.answer("This federation no longer exists.", show_alert=True)
    fed_id = fedowner[0]
    fname = fedowner[1]
    await query.edit_message_text(
        f_text.format(fname, fed_id, owner_id, o_name, user_id, n_name),
        parse_mode=ParseMode.HTML,
    )
    await db.transfer_fed(query.from_user.id, user_id)
    await db.user_demote_fed(fed_id, user_id)
    await query.message.reply_text(
        ftransfer_log.format(
            fname, user_id, n_name, user_id, owner_id, o_name, owner_id, user_id, n_name
        ),
        reply_parameters=None,
        parse_mode=ParseMode.HTML,
    )


@inline(pattern=r"ftnoc(\_(.*))")
async def ft_cancel(client, query):
    input = (query.pattern_match.group(1)).split("_", 1)[1]
    input = input.split("|", 1)
    owner_id = int(input[0])
    if not query.from_user.id == owner_id:
        return await query.answer(
            "This action is not intended for you.", show_alert=True
        )
    await query.edit_message_text(
        f"Fed transfer has been cancelled by <a href='tg://user?id={owner_id}'>{query.from_user.first_name}</a>.",
        parse_mode=ParseMode.HTML,
    )


@register(pattern="fednotif")
async def fed_notif(client, message):
    if not message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("This command is made to be used in PM.")
    parts = message.text.split(None, 1)
    args = parts[1] if len(parts) > 1 else ""
    fedowner = await db.get_user_owner_fed_full(message.from_user.id)
    if not fedowner:
        return await message.reply_text(
            "You aren't the creator of any await feds to act in."
        )
    fname = fedowner[1]
    if not args:
        mode = await db.user_feds_report(message.from_user.id)
        if mode:
            f_txt = "The `{}` fed is currently sending notifications to it's creator when a fed action is performed."
        else:
            f_txt = "The `{}` fed is currently **NOT** sending notifications to it's creator when a fed action is performed."
        await message.reply_text(f_txt.format(fname))
    elif args in ["on", "yes"]:
        await message.reply_text(
            f"The fed silence setting for `{fname}` has been updated to: `true`"
        )
        await db.set_feds_setting(message.from_user.id, True)
    elif args in ["off", "no"]:
        await message.reply_text(
            f"The fed silence setting for `{fname}` has been updated to: `false`"
        )
        await db.set_feds_setting(message.from_user.id, False)
    else:
        await message.reply_text(strings.YES_NO_ON_OFF)


new_fban = """
<b>New FedBan</b>
<b>Fed:</b> {}
<b>FedAdmin:</b> <a href="tg://user?id={}">{}</a>
<b>User:</b> <a href="tg://user?id={}">{}</a>
<b>User ID:</b> <code>{}</code>
"""
update_fban = """
<b>FedBan Reason Update</b>
<b>Fed:</b> {}
<b>FedAdmin:</b> <a href='tg://user?id={}'>{}</a>
<b>User:</b> <a href='tg://user?id={}'>{}</a>
<b>User ID:</b> <code>{}</code>{}
<b>New Reason:</b> {}
"""
un_fban = """
<b>New un-FedBan</b>
<b>Fed:</b> {}
<b>FedAdmin:</b> <a href="tg://user?id={}">{}</a>
<b>User:</b> <a href="tg://user?id={}">{}</a>
<b>User ID:</b> <code>{}</code>
"""


@register(pattern="fedreason")
async def fed_reason(client, message):
    if not message.chat.type == ChatType.PRIVATE:
        return await message.reply_text("This command is made to be used in PM.")
    parts = message.text.split(None, 1)
    args = parts[1] if len(parts) > 1 else ""
    fedowner = await db.get_user_owner_fed_full(message.from_user.id)
    if not fedowner:
        return await message.reply_text(
            "You aren't the creator of any await feds to act in."
        )
    fname = fedowner[1]
    fed_id = fedowner[0]
    if not args:
        mode = await db.get_fed_reason(fed_id)
        if mode:
            f_txt = "The `{}` fed is currently requiring a reason for fedbans."
        else:
            f_txt = "The `{}` fed is currently **NOT** requiring a reason for fedbans."
        await message.reply_text(f_txt.format(fname))
    elif args in ["on", "yes"]:
        await message.reply_text(
            f"The fed reason setting for `{fname}` has been updated to: `true`"
        )
        await db.set_fed_reason(fed_id, True)
    elif args in ["off", "no"]:
        await message.reply_text(
            f"The fed reason setting for `{fname}` has been updated to: `false`"
        )
        await db.set_fed_reason(fed_id, False)
    else:
        await message.reply_text(strings.YES_NO_ON_OFF)


@register(pattern="fban")
async def fban(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "fban")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        fed_id = await db.get_chat_fed(message.chat.id)
        if not fed_id:
            return await message.reply_text(strings.NOT_IN_ANY_FED)
        mejik = await db.search_fed_by_id(fed_id)
        fname = mejik["fedname"]
        if not (await is_user_fed_admin(fed_id, sender_id)):
            return await message.reply_text(
                f"You aren't a federation admin for {fname}!"
            )
        owner_id = mejik["owner_id"]
    elif message.chat.type == ChatType.PRIVATE:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await message.reply_text(
                "You aren't the creator of any feds to act in."
            )
        fed_id = fedowner[0]
        fname = fedowner[1]
        owner_id = sender_id
    user = None
    reason = None
    try:
        user, reason = await get_user(message)
    except TypeError:
        pass
    if not user:
        return await message.reply_text(
            "I don't know who you're talking about, you're going to need to specify a user...!"
        )
    check_reason = await db.get_fed_reason(fed_id)
    if check_reason:
        if not reason:
            return await message.reply_text("Please provide a reason to fban a user!")
    if reason:
        if len(reason) > 1024:
            reason = (
                reason[:1024]
                + "\n\nNote: The fban reason was over 1024 characters, so has been truncated."
            )
    else:
        reason = "None"
    if user.id == BOT_ID:
        return await message.reply_text(
            "Oh you're a funny one aren't you! I am _not_ going to fedban myself."
        )
    elif user.id in ADMINS:
        return await message.reply_text("I am not banning my developers.")
    elif await is_user_fed_admin(fed_id, user.id):
        f_ad = f"I'm not banning a fed admin/owner from their own fed! ({fname})"
        return await message.reply_text(f_ad)
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if fban:
        if reason == "" and fbanreason == "":
            return await message.reply_text(
                "User <a href='tg://user?id={}'>{}</a> is already banned in {}. There is no reason set for their fedban yet, so feel free to set one.".format(
                    user.id, user.first_name, fname
                ),
                parse_mode=ParseMode.HTML,
            )
        elif reason == fbanreason:
            return await message.reply_text(
                "User <a href='tg://user?id={}'>{}</a> has already been fbanned, with the exact same reason.".format(
                    user.id, user.first_name
                ),
                parse_mode=ParseMode.HTML,
            )
        elif reason is None:
            if not fbanreason:
                return await message.reply_text(
                    "User <a href='tg://user?id={}'>{}</a> is already banned in {}.".format(
                        user.id, user.first_name, fname
                    ),
                    parse_mode=ParseMode.HTML,
                )
            else:
                return await message.reply_text(
                    "User <a href='tg://user?id={}'>{}</a> is already banned in {}, with reason:\n<code>{}</code>.".format(
                        user.id, user.first_name, fname, fbanreason
                    ),
                    parse_mode=ParseMode.HTML,
                )
        await db.fban_user(
            fed_id,
            user.id,
            user.first_name,
            user.last_name,
            reason,
            datetime.now(timezone.utc),
        )
        p_reason = ""
        if fbanreason:
            p_reason = f"\n<b>Previous Reason:</b> {fbanreason}"
        fban_global_text = update_fban.format(
            fname,
            sender_id,
            message.from_user.first_name,
            user.id,
            user.first_name,
            user.id,
            p_reason,
            reason,
        )
    else:
        await db.fban_user(
            fed_id,
            user.id,
            user.first_name,
            user.last_name,
            reason,
            datetime.now(timezone.utc),
        )
        fban_global_text = new_fban.format(
            fname,
            sender_id,
            message.from_user.first_name,
            user.id,
            user.first_name,
            user.id,
            reason,
        )
        if reason:
            fban_global_text = fban_global_text + f"<b>Reason:</b> {reason}"
    await message.reply_text(fban_global_text, reply_parameters=None, parse_mode=ParseMode.HTML)
    getfednotif = await db.user_feds_report(int(owner_id))
    if getfednotif and message.chat.id != int(owner_id):
        await pgram.send_message(
            int(owner_id), fban_global_text, parse_mode=ParseMode.HTML
        )
    log_c = await db.get_fed_log(fed_id)
    if log_c and message.chat.id != int(log_c):
        await pgram.send_message(
            int(log_c), fban_global_text, parse_mode=ParseMode.HTML
        )
    fed_chats = list(await db.get_all_fed_chats(fed_id))
    if len(fed_chats) != 0:
        total = len(fed_chats)
        status = None
        last_edit = 0.0
        if total > 10:
            try:
                status = await message.reply_text(
                    f"Propagating ban across {total} chats...", reply_parameters=None
                )
            except Exception:
                status = None
        for idx, c in enumerate(fed_chats, start=1):
            try:
                await flood_safe(lambda c=c: pgram.ban_chat_member(int(c), user.id, revoke_messages=True))
            except Exception as exc:
                LOGGER.warning(f"fban propagation failed for chat {c}: {exc}")
            # pace to stay under Telegram's global ceiling
            await asyncio.sleep(0.1)
            # Progress edit at most once per 2s (edit throttling).
            if (
                status
                and idx % 10 == 0
                and (asyncio.get_event_loop().time() - last_edit) > 2
            ):
                last_edit = asyncio.get_event_loop().time()
                try:
                    await status.edit_text(f"Propagating ban... {idx}/{total} chats")
                except Exception:
                    pass
        if status:
            try:
                await status.edit_text(f"Ban propagated to {total} chats.")
            except Exception:
                pass
    subs = list(await db.get_fed_subs(fed_id))
    if len(subs) != 0:
        for fed in subs:
            await db.fban_user(
                fed,
                user.id,
                user.first_name,
                user.last_name,
                reason,
                datetime.now(timezone.utc),
            )
            all_fedschat = await db.get_all_fed_chats(fed)
            for c in all_fedschat:
                try:
                    await flood_safe(lambda c=c: pgram.ban_chat_member(int(c), user.id, revoke_messages=True))
                except Exception as exc:
                    LOGGER.warning(f"fban propagation (sub-fed {fed}) failed for chat {c}: {exc}")
                await asyncio.sleep(0.1)


@register(pattern="unfban")
async def unfban(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "unfban")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        fed_id = await db.get_chat_fed(message.chat.id)
        if not fed_id:
            return await message.reply_text(strings.NOT_IN_ANY_FED)
        mejik = await db.search_fed_by_id(fed_id)
        fname = mejik["fedname"]
        if not (await is_user_fed_admin(fed_id, sender_id)):
            return await message.reply_text(
                f"You aren't a federation admin for {fname}!"
            )
        owner_id = mejik["owner_id"]
    elif message.chat.type == ChatType.PRIVATE:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await message.reply_text(
                "You aren't the creator of any await feds to act in."
            )
        fed_id = fedowner[0]
        fname = fedowner[1]
        owner_id = sender_id
    user = None
    reason = None
    try:
        user, reason = await get_user(message)
    except TypeError:
        pass
    if not user:
        return await message.reply_text(
            "I don't know who you're talking about, you're going to need to specify a user...!"
        )
    if reason:
        if len(reason) > 1024:
            reason = (
                reason[:1024]
                + "\n\nNote: The unfban reason was over 1024 characters, so has been truncated."
            )
    if user.id == BOT_ID:
        return await message.reply_text(
            "Oh you're a funny one aren't you! How do you think I would have fbanned myself hm?."
        )
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if not fban:
        g_string = (
            "This user isn't banned in the current federation, {}. (`{}`)".format(
                fname, fed_id
            )
        )
        return await message.reply_text(g_string)
    ufb_string = un_fban.format(
        fname,
        sender_id,
        message.from_user.first_name,
        user.id,
        user.first_name,
        user.id,
    )
    if reason:
        ufb_string = ufb_string + f"\n<b>Reason:</b> {reason}"
    await db.unfban_user(fed_id, user.id)
    await message.reply_text(ufb_string, reply_parameters=None, parse_mode=ParseMode.HTML)
    getfednotif = await db.user_feds_report(int(owner_id))
    if getfednotif and message.chat.id != int(owner_id):
        await pgram.send_message(int(owner_id), ufb_string, parse_mode=ParseMode.HTML)
    log_c = await db.get_fed_log(fed_id)
    if log_c and message.chat.id != int(log_c):
        await pgram.send_message(int(log_c), ufb_string, parse_mode=ParseMode.HTML)


@register(pattern="chatfed")
async def CF(client, c):
    if c.chat.type == ChatType.PRIVATE:
        chat_id = await connection(c)
        if chat_id is None:
            return await c.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = c.chat.id
        title = c.chat.title
    if not await is_admin(c, c.from_user.id if c.from_user else None, pm_mode=True):
        return await c.reply_text(strings.NOT_ADMIN)
    fed_id = await db.get_chat_fed(chat_id)
    if not fed_id:
        return await c.reply_text("This chat isn't part of any feds yet!")
    fname = (await db.search_fed_by_id(fed_id))["fedname"]
    c_f = "Chat {} is part of the following federation: {} (ID: `{}`)".format(
        title, fname, fed_id
    )
    await c.reply_text(c_f)


fed_info = """
Fed info:
FedID: <code>{}</code>
Name: {}
Creator: <a href="tg://user?id={}">this person</a> (<code>{}</code>)
Number of admins: <code>{}</code>
Number of bans: <code>{}</code>
Number of connected chats: <code>{}</code>
Number of subscribed await feds: <code>{}</code>
"""


@register(pattern="fedinfo")
async def finfo(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "fedinfo")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not await is_admin(message, sender_id):
            return await message.reply_text(strings.NOT_ADMIN)
    fedowner = await db.get_user_owner_fed_full(sender_id)
    parts = message.text.split(None, 1)
    input = parts[1] if len(parts) > 1 else ""
    if not input and not fedowner:
        return await message.reply_text(
            "You need to give me a FedID to check, or be a federation creator to use this command!"
        )
    elif input:
        if len(input) < 10:
            return await message.reply_text(strings.INVALID_FEDID)
        getfed = await db.search_fed_by_id(input)
        if not getfed:
            return await message.reply_text(strings.NO_SUCH_FED)
        fname = getfed["fedname"]
        fed_id = input
    elif fedowner:
        fed_id = fedowner[0]
        fname = fedowner[1]
    info = await db.search_fed_by_id(fed_id)
    fadmins = len(info["fedadmins"])
    fbans = await db.get_len_fbans(fed_id)
    fchats = len(info["chats"])
    subbed = len(await db.get_fed_subs(fed_id))
    fed_main = fed_info.format(
        fed_id,
        fname,
        int(info["owner_id"]),
        int(info["owner_id"]),
        fadmins,
        fbans,
        fchats,
        subbed,
    )
    x_sub = await db.get_my_subs(fed_id)
    if len(x_sub) == 0:
        fed_main = (
            fed_main + "\nThis federation is not subscribed to any other await feds."
        )
    else:
        out_str = "\nSubscribed to the following await feds:"
        for x in x_sub:
            fname = (await db.search_fed_by_id(x))["fedname"]
            out_str += f"\n- {fname} (<code>{x}</code>)"
        fed_main = fed_main + out_str
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Check Fed Admins", callback_data="check_fadmins_{}".format(fed_id)
                )
            ]
        ]
    )
    await message.reply_text(fed_main, parse_mode=ParseMode.HTML, reply_markup=buttons)


@inline(pattern=r"check_fadmins(\_(.*))")
async def check_fadmins(client, e):
    if e.message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not await cb_is_admin(e, e.from_user.id):
            return
    fed_id = (e.pattern_match.group(1)).split("_", 1)[1]
    x_admins = await db.get_all_fed_admins(fed_id) or []
    fname = (await db.search_fed_by_id(fed_id))["fedname"]
    out_str = f"Admins in federation {fname}:"
    for _x in x_admins:
        _x_name = await db.get_fname(_x) or (await client.get_users(int(_x))).first_name
        out_str += "\n- <a href='tg://user?id={}'>{}</a> (<code>{}</code>)".format(
            _x, _x_name, _x
        )
    await e.edit_message_reply_markup(reply_markup=None)
    await e.message.reply_text(out_str, reply_parameters=None, parse_mode=ParseMode.HTML)


@register(pattern="subfed")
async def s_fed(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "subfed")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(
            "Only federation creators can subscribe to a fed. But you don't have a federation!"
        )
    parts = message.text.split(None, 1)
    arg = parts[1] if len(parts) > 1 else ""
    if not arg:
        return await message.reply_text(
            "You need to specify which federation you're asking about by giving me a FedID!"
        )
    if len(arg) < 10:
        return await message.reply_text(strings.INVALID_FEDID)
    getfed = await db.search_fed_by_id(arg)
    if not getfed:
        return await message.reply_text(strings.NO_SUCH_FED)
    s_fname = getfed["fedname"]
    if arg == fedowner[0]:
        return await message.reply_text(
            "... What's the point in subscribing a fed to itself?"
        )
    if len(await db.get_my_subs(str(fedowner[0]))) > 5:
        return await message.reply_text(
            "You can subscribe to at most 5 federations. Please unsubscribe from other federations before adding more."
        )
    await message.reply_text(
        "Federation `{}` has now subscribed to `{}`. All fedbans in `{}` will now take effect in both await feds.".format(
            fedowner[1], s_fname, s_fname
        )
    )
    await db.sub_fed(arg, fedowner[0])


@register(pattern="unsubfed")
async def us_fed(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "unsubfed")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(
            "Only federation creators can unsubscribe to a fed. But you don't have a federation!"
        )
    parts = message.text.split(None, 1)
    arg = parts[1] if len(parts) > 1 else ""
    if not arg:
        return await message.reply_text(
            "You need to specify which federation you're asking about by giving me a FedID!"
        )
    if len(arg) < 10:
        return await message.reply_text(strings.INVALID_FEDID)
    getfed = await db.search_fed_by_id(arg)
    if not getfed:
        return await message.reply_text(strings.NO_SUCH_FED)
    await message.reply_text(
        "Federation `{}` is no longer subscribed to `{}`. Bans in `{}` will no longer be applied. Please note that any bans that happened because the user was banned from the subfed will need to be removed manually.".format(
            fedowner[1], getfed["fedname"], getfed["fedname"]
        )
    )
    await db.unsub_fed(arg, fedowner[0])


@register(pattern="(feddemoteme|fdemoteme)")
async def self_demote(client, e, sender_id: int = None, anon: bool = False):
    if not anon:
        if not e.from_user:
            return await anon_fed(e, "feddemoteme")
    if not sender_id:
        sender_id = e.from_user.id if e.from_user else None
    try:
        fed_id = e.text.split(None, 1)[1]
    except IndexError:
        return await e.reply_text(
            "You need to specify a federation ID to demote yourself from."
        )
    getfed = await db.search_fed_by_id(fed_id)
    if not getfed:
        return await e.reply_text(strings.NO_SUCH_FED)
    fedname = getfed["fedname"]
    if int(getfed["owner_id"]) == sender_id:
        return await e.reply_text(
            "You can't demote yourself from your own fed - who would be the owner?"
        )
    if not (await is_user_fed_admin(fed_id, sender_id)):
        return await e.reply_text(
            f"You aren't an admin in '{fedname}' - how would I demote you?"
        )
    await e.reply_text(f"You are no longer a fed admin in '{fedname}'")
    await db.user_demote_fed(fed_id, sender_id)


@register(pattern="myfeds")
async def my_feds(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "myfeds")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    fed_list = await db.get_all_fed_admin(
        message.from_user.id if message.from_user else sender_id
    )
    if not fed_list:
        return await message.reply_text("You aren't a member of any federations.")
    out_str = "You are an admin of the following federations:"
    for fed in fed_list:
        fed_name = await db.get_fed_name(fed)
        out_str += f"\n- {fed_name} (<code>{fed}</code>)"
    await message.reply_text(out_str)


@register(pattern="setfedlog")
async def set_fed_logs(client, e, sender_id: int = None, anon: bool = False):
    if e.chat.type == ChatType.PRIVATE:
        return await e.reply_text(
            "This command is made to be used in group chats or channels, not in PM!"
        )
    if not anon:
        if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and not e.from_user:
            return await anon_fed(e, "setfedlog")
    if not sender_id:
        sender_id = e.from_user.id if e.from_user else None
    if e.chat.type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    ) and not await can_change_info(e, sender_id):
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner and not e.pattern_match.group(1):
        return await e.reply_text(
            "Only fed creators can set a fed log - but you don't have a federation! If you have try doing /setfedlog <fedid>"
        )
    elif fedowner:
        fed_id = fedowner[0]
        fname = fedowner[1]
    elif e.pattern_match.group(1):
        fed_id = e.pattern_match.group(1)
        fed = await db.search_fed_by_id(fed_id)
        if not fed:
            return await e.reply_text("This isn't a valid FedID!")
        fname = fed["fedname"]
    await db.set_fed_log(fed_id, e.chat.id)
    await e.reply_text(
        f"This has been set as the fed log for {fname} - all fed related actions will be logged here."
    )


@register(pattern="unsetfedlog")
async def un_set_fed_log(client, e, sender_id: int = None, anon: bool = False):
    if e.chat.type == ChatType.PRIVATE:
        return await e.reply_text(
            "This command is made to be used in group chats or channels, not in PM!"
        )
    if not anon:
        if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and not e.from_user:
            return await anon_fed(e, "unsetfedlog")
    if not sender_id:
        sender_id = e.from_user.id if e.from_user else None
    if e.chat.type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    ) and not await can_change_info(e, sender_id):
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await e.reply_text(
            "Only fed creators can unset a fed log - but you don't have a federation!"
        )
    fed_id = fedowner[0]
    fname = fedowner[1]
    await db.set_fed_log(fed_id)
    await e.reply_text(f"The {fname} federation has had its log location unset.")


@register(pattern="fedadmins")
async def fedadmins_(client, e, sender_id: int = None, anon: bool = False):
    if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not anon:
            if not e.from_user:
                return await anon_fed(e, "fedadmins")
        if not sender_id:
            sender_id = e.from_user.id if e.from_user else None
        if not await is_admin(e, sender_id):
            return await e.reply_text(strings.NOT_ADMIN)
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner and not e.pattern_match.group(1):
        return await e.reply_text(
            "You need to give me a FedID to check, or be a federation creator to use this command!"
        )
    elif fedowner:
        fed_id = fedowner[0]
        fname = fedowner[1]
    elif len(e.text.split(" ", 1)) == 2:
        fed_id = e.text.split(" ", 1)[1]
        fed = await db.search_fed_by_id(fed_id)
        if not fed:
            return await e.reply_text("This isn't a valid FedID!")
        fname = fed["fedname"]
    else:
        fed_id = await db.get_chat_fed(e.chat.id)
        if not fed_id:
            return await e.reply_text(strings.NOT_IN_ANY_FED)
        fname = (await db.search_fed_by_id(fed_id))["fedname"]
    x_admins = await db.get_all_fed_admins(fed_id) or []
    out_str = f"Admins in federation '{fname}':"
    for _x in x_admins:
        _x_name = await db.get_fname(_x) or (await client.get_users(int(_x))).first_name
        out_str += "\n- <a href='tg://user?id={}'>{}</a> (<code>{}</code>)".format(
            _x, _x_name, _x
        )
    await e.reply_text(out_str, parse_mode=ParseMode.HTML)


@register(pattern="fedsubs")
async def fedsubs(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not message.from_user:
            return await anon_fed(message, "fedsubs")
    if not sender_id:
        sender_id = message.from_user.id if message.from_user else None
    fedowner = await db.get_user_owner_fed_full(sender_id)
    subfed = await db.get_all_subscribed_feds(fedowner[0])
    fname = fedowner[1]
    if not subfed:
        return await message.reply_text("You aren't subscribed to any other feds.")
    out_str = f"Your federation **{fname}** (`{fedowner[0]}`) is subscribed to the following feds:"
    for fed in subfed:
        fed_name = await db.get_fed_name(fed)
        out_str += f"\n- {fed_name} (`{fed}`)"
    await message.reply_text(out_str)


@register(pattern="fedstat")
async def fedstat(client, e, sender_id: int = None, anon: bool = False):
    if not anon:
        if not e.from_user:
            return await anon_fed(e, "fedstat")
    if not sender_id:
        sender_id = e.from_user.id if e.from_user else None
    if not e.pattern_match.group(1):
        return await e.reply_text(
            "You need to specify a federation ID to check your ban status."
        )
    getfed = await db.search_fed_by_id(e.pattern_match.group(1))
    if not getfed:
        return await e.reply_text(strings.NO_SUCH_FED)
    fban, fbanreason, fbantime = await db.get_fban_user(
        e.pattern_match.group(1), sender_id
    )
    if not fban:
        return await e.reply_text("You aren't banned in this federation.")
    out_str = f"You are banned in federation {getfed['fedname']} (`{e.pattern_match.group(1)}`)."
    if fbanreason:
        out_str += f"\nReason: {fbanreason}"
    out_str += f"\nTime: {fbantime}"
    await e.reply_text(out_str)


@register(pattern="(fexport|fedexport)")
async def fed_export___(client, e, sender_id: int = None, anon: bool = False):
    if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not anon:
            if not e.from_user:
                return await anon_fed(e, "fexport")
        if not sender_id:
            sender_id = e.from_user.id if e.from_user else None
        fed_id = await db.get_chat_fed(e.chat.id)
        if not fed_id:
            return await e.reply_text(strings.NOT_IN_ANY_FED)
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner or fedowner[0] != fed_id:
            return await e.reply_text("Only the fed creator can export the ban list.")
        fname = fedowner[1]
    elif e.chat.type == ChatType.PRIVATE:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await e.reply_text(
                "You aren't the creator of any await feds to act in."
            )
        fname = fedowner[1]
        fed_id = fedowner[0]
    fbans = await db.get_all_fbans(fedowner[0])
    if not fbans:
        return await e.reply_text("There are no banned users in {}".format(fname))
    if not len(e.text.split(" ", 1)) == 2:
        mode = "csv"
    elif len(e.text.split(" ", 1)) == 2:
        pc = e.text.split(" ", 1)[1].lower()
        if pc not in ["csv", "json", "xml"]:
            mode = "csv"
        else:
            mode = pc
    else:
        mode = "csv"
    # Unique-per-call filename so concurrent exports (different feds/users)
    # can't race/overwrite each other's file; cleaned up after sending.
    export_path = f"fbanned_users_{uuid.uuid4().hex}.{mode}"
    try:
        if mode == "csv":
            fban_list = []
            for fban in fbans:
                fb = fbans[fban]
                fban_list.append(
                    {"Name": fb[0], "User ID": fban, "Reason": fb[2], "Time": str(fb[3])}
                )
            csv_headers = ["Name", "User ID", "Reason", "Time"]

            def _write_csv():
                with open(export_path, "w") as csvfile:
                    w = csv.DictWriter(csvfile, fieldnames=csv_headers)
                    w.writeheader()
                    for fban in fban_list:
                        w.writerow(fban)

            await asyncio.to_thread(_write_csv)
            await e.reply_document(
                export_path, caption="Fbanned users in {}.".format(fname)
            )
        elif mode == "json":
            fban_list = ""
            for fban in fbans:
                fb = fbans[fban]
                json_p = {
                    "name": fb[0],
                    "user_id": fban,
                    "reason": fb[2],
                    "time": str(fb[3]),
                }
                fban_list += orjson.dumps(json_p).decode("utf-8") + "\n"
            await asyncio.to_thread(
                lambda: open(export_path, "w").write(fban_list)
            )
            await e.reply_document(
                export_path, caption="Fbanned users in {}.".format(fname)
            )
        elif mode == "xml":
            fban_list = []
            for fban in fbans:
                fb = fbans[fban]
                fban_list.append(
                    {"Name": fb[0], "User ID": fban, "Reason": fb[2], "Time": str(fb[3])}
                )
            xml_str = ""
            qp = 0
            for x in fban_list:
                el = Element("fban")
                qp += 1
                el.set("sn", str(qp))
                for c, v in x.items():
                    child = Element(str(c))
                    child.text = str(v)
                    el.append(child)
                xml_str += tostring(el, encoding="unicode") + "\n"
            await asyncio.to_thread(lambda: open(export_path, "w").write(xml_str))
            await e.reply_document(
                export_path, caption="Fbanned users in {}.".format(fname)
            )
    finally:
        try:
            os.remove(export_path)
        except OSError:
            pass


@register(pattern="(fimport|fedimport)")
async def fed_import___(client, e, sender_id: int = None, anon: bool = False):
    if not anon:
        if not e.from_user:
            return await anon_fed(e, "fimport")
    if not sender_id:
        sender_id = e.from_user.id if e.from_user else None
    if not e.reply_to_message_id:
        return await e.reply_text(
            "You need to reply to the document containing the banlist, as a .txt file."
        )
    r = e.reply_to_message
    # Telethon r.file.ext replaced with the document file name extension.
    r_ext = (
        os.path.splitext(r.document.file_name or "")[1].lower()
        if r and r.document
        else None
    )
    if not e.media and r_ext not in [".xml", ".json", ".csv"]:
        return await e.reply_text(
            "You need to reply to the document containing the banlist, as a .txt file."
        )
    if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        fed_id = await db.get_chat_fed(e.chat.id)
        if not fed_id:
            return await e.reply_text(strings.NOT_IN_ANY_FED)
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner or fedowner[0] != fed_id:
            return await e.reply_text("Only the fed creator can import a ban list.")
        mejik = await db.search_fed_by_id(fed_id)
        mejik["fedname"]
    elif e.chat.type == ChatType.PRIVATE:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await e.reply_text(
                "You aren't the creator of any await feds to act in."
            )
        fedowner[1]
        fed_id = fedowner[0]
    Ext = (r_ext or "").replace(".", "")
    f = await r.download(in_memory=False)
    if Ext == "csv":
        with open(f, "r") as f:
            fbans = list(csv.DictReader(f))
        for x in fbans:
            await db.fban_user(
                fed_id,
                x["User ID"],
                x["Name"],
                "",
                x["Reason"],
                datetime.now(timezone.utc),
            )
        await e.reply_text(
            "Files were imported successfully. {} people banned. {} Failed to import.".format(
                len(fbans), 0
            )
        )
    elif Ext == "json":
        fbans = []
        with open(f, "rb") as f:
            fp = f.readlines()
        for x in fp:
            fbans.append(orjson.loads(x))
        for x in fbans:
            await db.fban_user(
                fed_id,
                x["user_id"],
                x["name"],
                "",
                x["reason"],
                datetime.now(timezone.utc),
            )
        await e.reply_text(
            "Files were imported successfully. {} people banned. {} Failed to import.".format(
                len(fbans), 0
            )
        )
    elif Ext == "xml":
        await e.reply_text(
            "File is in XML format. {} people banned. {} Failed to import.".format(0, 0)
        )


async def anon_fed(e, mode):
    if e.chat.type == ChatType.PRIVATE:
        return
    # message.id is only unique per-chat; key by (chat_id, message_id) so
    # concurrent proofs from different chats can't collide/overwrite.
    anon_db[(e.chat.id, e.id)] = (e, mode)
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Click to prove Admin", callback_data="fedp_{}_{}".format(e.chat.id, e.id)
                )
            ]
        ]
    )
    await e.reply_text(
        "It looks like you're anonymous. Tap this button to confirm your identity.",
        reply_markup=buttons,
    )


@inline(pattern=r"fedp(\_(.*))")
async def fed_call__back___(client, e):
    chat_id_str, msg_id_str = (e.pattern_match.group(1)).split("_", 1)[1].split("_", 1)
    key = (int(chat_id_str), int(msg_id_str))
    try:
        r = anon_db.pop(key)
    except KeyError:
        return await e.edit_message_text("This message is too old to interact with.")
    event, mode = r
    if mode == "fimport":
        await fed_import___(client, event, e.from_user.id, anon=True)
    elif mode == "fexport":
        await fed_export___(client, event, e.from_user.id, anon=True)
    elif mode == "fedstat":
        await fedstat(client, event, e.from_user.id, anon=True)
    elif mode == "fedsubs":
        await fedsubs(client, event, e.from_user.id, anon=True)
    elif mode == "fedadmins":
        await fedadmins_(client, event, e.from_user.id, anon=True)
    elif mode == "unsetfedlog":
        await un_set_fed_log(client, event, e.from_user.id, anon=True)
    elif mode == "setfedlog":
        await set_fed_logs(client, event, e.from_user.id, anon=True)
    elif mode == "myfeds":
        await my_feds(client, event, e.from_user.id, anon=True)
    elif mode == "feddemoteme":
        await self_demote(client, event, e.from_user.id, anon=True)
    elif mode == "subfed":
        await s_fed(client, event, e.from_user.id, anon=True)
    elif mode == "unsubfed":
        await us_fed(client, event, e.from_user.id, anon=True)
    elif mode == "fedinfo":
        await finfo(client, event, e.from_user.id, anon=True)
    elif mode == "unfban":
        await unfban(client, event, e.from_user.id, anon=True)
    elif mode == "fban":
        await fban(client, event, e.from_user.id, anon=True)
    elif mode == "ftransfer":
        await ft(client, event, e.from_user.id, anon=True)
    elif mode == "fdemote":
        await fd(client, event, e.from_user.id, anon=True)
    elif mode == "fpromote":
        await fp(client, event, e.from_user.id, anon=True)
    elif mode == "leavefed":
        await lfed(client, event, e.from_user.id, anon=True)
    elif mode == "joinfed":
        await jfed(client, event, e.from_user.id, anon=True)


@register(pattern="quietfed")
@log_to_channel
async def qf(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat_id = await connection(message)
        if chat_id is None:
            return await message.reply_text(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        title = message.chat.title
    if not await is_admin(
        message, message.from_user.id if message.from_user else None, pm_mode=True
    ):
        return await message.reply_text(strings.NOT_ADMIN)

    data = await db.feds.find_one({"chat_id": chat_id})
    if data and data["quiet"]:
        # db is the feds_db module; quietfed() is the helper that upserts
        # feds.quiet
        await db.quietfed(chat_id, False)
        await message.reply_text(f"Quietfed has been disabled in {title}.")
        return "QUIETFED_DISABLE", None, None
    else:
        await db.quietfed(chat_id, True)
        await message.reply_text(f"Quietfed has been enabled in {title}.")
        return "QUIETFED_ENABLE", None, None


@listen()
async def fban_welcome(client, message):
    if not message.from_user or not (message.text or message.caption):
        return
    if message.chat.type == ChatType.PRIVATE:
        return
    if not await botfban(message.chat.id, BOT_ID):
        return
    fed_id = await db.get_chat_fed(message.chat.id)
    if not fed_id:
        return
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, message.from_user.id)
    quiet = await db.feds.find_one({"chat_id": message.chat.id})
    if fban and fbanreason:
        try:
            await client.ban_chat_member(message.chat.id, int(message.from_user.id))
            if not quiet or quiet.get("quiet") is False:
                return await message.reply_text(
                    f"The user {message.from_user.first_name} has been fbanned in the current federation due to the following reason:\n{fbanreason}\n\nHence banned from here as well.",
                    reply_parameters=None,
                )
            else:
                return
        except Exception as exc:
            LOGGER.warning(f"fban_welcome ban_chat_member failed in {message.chat.id}: {exc}")
    else:
        return

import csv
from datetime import datetime
import orjson
import uuid
from xml.etree.ElementTree import Element, tostring

from telethon import Button, events, types
from telethon.errors.rpcerrorlist import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest

import Emilia.strings as strings
from Emilia import BOT_ID, DEV_USERS, OWNER_ID
from Emilia import telethn as meow
from Emilia.custom_filter import callbackquery as inline
from Emilia.custom_filter import register
from Emilia.functions.admins import *
from Emilia.functions.admins import get_user_reason as get_user
from Emilia.helper.get_data import GetChat
from Emilia.mongo import feds_db as db
from Emilia.pyro.connection.connection import connection

# im_bannable
ADMINS = DEV_USERS
ADMINS.append(BOT_ID)
ADMINS.append(OWNER_ID)
export = {}
anon_db = {}


async def is_user_fed_admin(fed_id, user_id):
    fed_admins = await db.get_all_fed_admins(fed_id) or []
    if int(user_id) in fed_admins or int(user_id) == OWNER_ID:
        return True
    else:
        return False


@register(pattern="newfed")
async def newfed(event):
    if not event.is_private:
        return await event.reply("Create your federation in my PM - not in a group.")

    if len(event.text.split(" ", 1)) == 2:
        name = event.text.split(" ", 1)[1]
    else:
        return await event.reply(
            "You need to give your federation a name! Federation names can be up to 64 characters long."
        )

    f_owner = await db.get_user_owner_fed_full(event.sender_id)
    if f_owner:
        fed_name = f_owner[1]
        return await event.reply(
            f"You already have a federation called `{fed_name}` ; you can't create another. If you would like to rename it, use `/renamefed`."
        )
    if len(name) > 64:
        return await event.reply(
            "Federation names can only be upto 64 charactors long."
        )
    fed_id = str(uuid.uuid4())
    await db.new_fed(event.sender_id, fed_id, name)
    await event.reply(
        f"Created new federation with FedID: `{fed_id}`.\nUse this ID to join the federation! eg:\n`/joinfed {fed_id}`"
    )


@register(pattern="delfed")
async def del_fed(event):
    if not event.is_private:
        return await event.reply("Delete your federation in my PM - not in a group.")
    fedowner = await db.get_user_owner_fed_full(event.sender_id)
    if not fedowner:
        return await event.reply("It doesn't look like you have a federation yet!")
    name = fedowner[1]
    fed_id = fedowner[0]
    await event.respond(
        "Are you sure you want to delete your federation? This action cannot be undone - you will lose your entire ban list, and '{}' will be permanently gone.".format(
            name
        ),
        buttons=[
            [Button.inline("Delete Federation", data="rmfed_{}".format(fed_id))],
            [Button.inline("Cancel", data="cancel_delete")],
        ],
    )


@inline(pattern=r"rmfed(\_(.*))")
async def delete_fed(event):
    tata = event.pattern_match.group(1)
    data = tata.decode()
    fed_id = data.split("_", 1)[1]
    await db.del_fed(fed_id)
    await event.edit(
        "You have deleted your federation! All chats linked to it are now federation-less."
    )


@inline(pattern=r"cancel_delete")
async def delete_fed(event):
    await event.edit("Federation deletion cancelled.")


@register(pattern="renamefed")
async def rename(event):
    if not event.is_private:
        return await event.reply("You can only rename your fed in PM.")
    fedowner = await db.get_user_owner_fed_full(event.sender_id)
    if not fedowner:
        return await event.reply("It doesn't look like you have a federation yet!")
    if not event.pattern_match.group(1):
        return await event.reply(
            "You need to give your federation a new name! Federation names can be up to 64 characters long."
        )
    elif len(event.pattern_match.group(1)) > 64:
        return await event.reply("Federation names cannot be over 64 characters long.")
    name = fedowner[1]
    fed_id = fedowner[0]
    new_name = event.text.split(None, 1)[1]
    await db.rename_fed(fed_id, new_name)
    final_text = f"Tada! I've renamed your federation from '{name}' to '{new_name}'. (FedID: `{fed_id}`)."
    await event.reply(final_text)
    log_c = await db.get_fed_log(fed_id)
    if log_c and log_c != event.chat_id:
        await meow.send_message(
            log_c,
            f"Federation {name} ({fed_id}) has been renamed to {new_name} by {event.sender.first_name} ({event.sender_id})",
        )


async def botfban(chat_id, user_id):
    try:
        p = await meow(GetParticipantRequest(chat_id, user_id))
    except UserNotParticipantError:
        return False
    if isinstance(p.participant, types.ChannelParticipant):
        return False
    elif isinstance(p.participant, types.ChannelParticipantAdmin):
        if not p.participant.admin_rights.ban_users:
            return False
        return True


@register(pattern="joinfed")
async def jfed(event, sender_id: int = None, anon: bool = False):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title

    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "joinfed")
    if not sender_id:
        sender_id = event.sender_id
    if not (event.is_group or event.is_private):
        return

    if not await is_owner(event, sender_id):
        return
    if not await botfban(chat_id, BOT_ID):
        return await event.reply(
            "You need to give me ban rights in order to join a federation!"
        )
    args = event.pattern_match.group(1)
    if not args:
        return await event.reply(
            "You need to specify which federation you're asking about by giving me a FedID!"
        )
    if len(args) < 10:
        return await event.reply("This isn't a valid FedID format!")
    getfed = await db.search_fed_by_id(args)
    if not getfed:
        return await event.reply("This FedID does not refer to an existing federation.")
    name = getfed["fedname"]
    fed_id = await db.get_chat_fed(chat_id)
    if fed_id:
        await db.chat_leave_fed(fed_id, chat_id)
    await db.chat_join_fed(args, chat_id)
    await event.reply(
        f'Successfully joined the "{name}" federation! All new federation bans will now also remove the members from {title}.'
    )
    log_c = await db.get_fed_log(fed_id)
    if log_c and log_c != chat_id:
        await meow.send_message(
            log_c,
            f"Chat {title} [{chat_id}] has joined the federation {name} ({fed_id})!",
        )


@register(pattern="leavefed")
async def lfed(event, sender_id: int = None, anon: bool = False):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "leavefed")
    if not sender_id:
        sender_id = event.sender_id

    if not await is_owner(event, sender_id):
        return
    fed_id = await db.get_chat_fed(chat_id)
    if fed_id:
        fname = (await db.search_fed_by_id(fed_id))["fname"]
        await db.chat_leave_fed(fed_id, chat_id)
        await event.reply('Chat {} has left the "{}" federation.'.format(title, fname))
    else:
        await event.reply("This chat isn't currently in any federations!")


@register(pattern="fpromote")
async def fp(event, sender_id: int = None, anon: bool = False):
    if event.is_private:
        return await event.reply(
            "This command is made to be used in group chats, not in pm!"
        )
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "fpromote")
    if not sender_id:
        sender_id = event.sender_id
    user = None
    try:
        user, extra = await get_user(event)
    except TypeError:
        pass
    if not user:
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await event.reply(
            "Only federation creators can promote people, and you don't seem to have a federation to promote to!"
        )
    fname = fedowner[1]
    fed_id = fedowner[0]
    if user.id == sender_id:
        return await event.reply("Yeah well you are the fed owner!")
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if fban:
        if fbanreason:
            reason = f"\n\nReason: <code>{fbanreason}</code>"
        else:
            reason = ""
        txt = f"User <a href='tg://user?id={user.id}'>{user.first_name}</a> is fbanned in {fname}. You should unfban them before promoting.{reason}"
        return await event.reply(txt, parse_mode="html")
    getuser = await db.search_user_in_fed(fed_id, user.id)
    if getuser:
        return await event.reply(
            f"<a href='tg://user?id={user.id}'>{user.first_name}</a> is already an admin in {fname}!",
            parse_mode="html",
        )
    cb_data = str(event.sender_id) + "|" + str(user.id)
    ftxt = f"Please get <a href='tg://user?id={user.id}'>{user.first_name}</a> to confirm that they would like to be fed admin for {fname}"
    buttons = [
        Button.inline("Accept", data=f"fp_{cb_data}"),
        Button.inline("Decline", data=f"nofp_{cb_data}"),
    ]
    await event.respond(ftxt, buttons=buttons, parse_mode="html")


@inline(pattern=r"fp(\_(.*))")
async def fp_cb(event):
    input = ((event.pattern_match.group(1)).decode()).split("_", 1)[1]
    owner_id, user_id = input.split("|")
    owner_id = int(owner_id.strip())
    user_id = int(user_id.strip())
    fedowner = await db.get_user_owner_fed_full(owner_id)
    fname = fedowner[1]
    fed_id = fedowner[0]
    if not event.sender_id == user_id:
        return await event.answer("You are not the user being fpromoted", alert=True)
    name = (await meow.get_entity(user_id)).first_name
    await db.user_join_fed(fed_id, user_id)
    res = f"User <a href='tg://user?id={user_id}'>{name}</a> is now an admin of {fname} (<code>{fed_id}</code>)"
    await event.edit(res, parse_mode="html")
    await db.add_fname(user_id, event.sender.first_name)


@inline(pattern=r"nofp(\_(.*))")
async def nofp(event):
    tata = event.pattern_match.group(1)
    pata = tata.decode()
    input = pata.split("_", 1)[1]
    owner_id, user_id = input.split("|")
    owner_id = int(owner_id.strip())
    user_id = int(user_id.strip())
    await db.get_user_owner_fed_full(owner_id)
    if event.sender_id == owner_id:
        user = await meow.get_entity(owner_id)
        await event.edit(
            f"Fedadmin promotion cancelled by <a href='tg://user?id={user.id}'>{user.first_name}</a>",
            parse_mode="html",
        )
    elif event.sender_id == user_id:
        user = await meow.get_entity(user_id)
        await event.edit(
            f"Fedadmin promotion has been refused by <a href='tg://user?id={user.id}'>{user.first_name}</a>",
            parse_mode="html",
        )
    else:
        await event.answer("You are not the user being fpromoted")


@register(pattern="fdemote")
async def fd(event, sender_id: int = None, anon: bool = False):
    if event.is_private:
        return await event.reply(
            "This command is made to be used in group chats, not in pm!"
        )
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "fdemote")
    if not sender_id:
        sender_id = event.sender_id
    user = None
    try:
        user, extra = await get_user(event)
    except TypeError:
        pass
    if not user:
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await event.reply(
            "Only federation creators can demote people, and you don't seem to have a federation to promote to!"
        )
    fname = fedowner[1]
    fed_id = fedowner[0]
    if not (await db.search_user_in_fed(fed_id, user.id)):
        return await event.reply(
            f"This person isn't a federation admin for '{fname}', how could I demote them?"
        )
    await db.user_demote_fed(fed_id, user.id)
    await event.reply(
        f"User <a href='tg://user?id={user.id}'>{user.first_name}</a> is no longer an admin of {fname} ({fed_id})",
        parse_mode="html",
    )


@register(pattern="(ftransfer|fedtransfer)")
async def ft(event, sender_id: int = None, anon: bool = False):
    if event.is_private:
        return await event.reply(
            "This command is made to be used in group chats, not in pm!"
        )
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "ftransfer")
    if not sender_id:
        sender_id = event.sender_id
    user_r = None
    if not await is_admin(event, sender_id):
        return await event.reply(strings.NOT_ADMIN)
    try:
        user_r, extra = await get_user(event)
    except TypeError:
        pass
    if not user_r:
        return
    if user_r.bot:
        return await event.reply("Bots can't own federations.")
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await event.reply("You don't have a fed to transfer!")
    fname = fedowner[1]
    fed_id = fedowner[0]
    if user_r.id == sender_id:
        return await event.reply("You can only transfer your fed to others!")
    ownerfed = await db.get_user_owner_fed_full(user_r.id)
    if ownerfed:
        return await event.reply(
            f"<a href='tg://user?id={user_r.id}'>{user_r.first_name}</a> already owns a federation - they can't own another.",
            parse_mode="html",
        )
    getuser = await db.search_user_in_fed(fed_id, user_r.id)
    if not getuser:
        return await event.reply(
            f"<a href='tg://user?id={user_r.id}'>{user_r.first_name}</a> isn't an admin in {fname} - you can only give your fed to other admins.",
            parse_mode="html",
        )
    cb_data = str(sender_id) + "|" + str(user_r.id)
    text = f"<a href='tg://user?id={user_r.id}'>{user_r.first_name}</a>, please confirm you would like to receive fed {fname} (<code>{fed_id}</code>) from <a href='tg://user?id={sender_id}'>{event.sender.first_name}</a>"
    buttons = [
        Button.inline("Accept", data=f"ft_{cb_data}"),
        Button.inline("Decline", data=f"noft_{cb_data}"),
    ]
    await event.respond(text, buttons=buttons, parse_mode="html")


@inline(pattern=r"ft(\_(.*))")
async def ft(event):
    input = ((event.pattern_match.group(1)).decode()).split("_", 1)[1]
    input = input.split("|", 1)
    owner_id = int(input[0])
    user_id = int(input[1])
    if not event.sender_id == user_id:
        return await event.answer("This action is not intended for you.", alert=True)
    fedowner = await db.get_user_owner_fed_full(owner_id)
    fed_id = fedowner[1]
    fname = fedowner[0]
    try:
        owner = await meow.get_entity(owner_id)
    except BaseException:
        return
    e_text = f"<a href='tg://user?id={owner.id}'>{owner.first_name}</a>, please confirm that you wish to send fed {fname} (<code>{fed_id}</code>) to <a href='tg://user?id={event.sender_id}'>{event.sender.first_name}</a> this cannot be undone."
    cb_data = str(owner.id) + "|" + str(user_id)
    buttons = [
        Button.inline("Confirm", data=f"ftc_{cb_data}"),
        Button.inline("Cancel", data=f"ftnoc_{cb_data}"),
    ]
    await event.edit(e_text, buttons=buttons, parse_mode="html")


@inline(pattern=r"noft(\_(.*))")
async def noft(event):
    input = ((event.pattern_match.group(1)).decode()).split("_", 1)[1]
    input = input.split("|", 1)
    owner_id = int(input[0])
    user_id = int(input[1])
    if event.sender_id not in [user_id, owner_id]:
        return await event.answer("This action is not intended for you.", alert=True)
    if event.sender_id == owner_id:
        user_name = ((event.sender.first_name).replace("<", "&lt;")).replace(
            ">", "&gt;"
        )
        o_text = (
            "<a href='tg://user?id={}'>{}</a> has cancelled the fed transfer.".format(
                owner_id, user_name
            )
        )
    elif event.sender_id == user_id:
        user_name = ((event.sender.first_name).replace("<", "&lt;")).replace(
            ">", "&gt;"
        )
        o_text = (
            "<a href='tg://user?id={}'>{}</a> has declined the fed transfer.".format(
                owner_id, user_name
            )
        )
    await event.edit(o_text, parse_mode="html", buttons=None)


ftransfer_log = """
<b>Fed Transfer</b>
<b>Fed:</b> {}
<b>New Fed Owner:</b> <a href='tg://user?id={}'>{}</a> - <code>{}</code>
<b>Old Fed Owner:</b> <a href='tg://user?id={}'>{}</a> - <code>{}</code>

<a href='tg://user?id={}'>{}</a> is now the fed owner. They can promote/demote admins as they like.
"""


@inline(pattern=r"ftc(\_(.*))")
async def noft(event):
    input = ((event.pattern_match.group(1)).decode()).split("_", 1)[1]
    input = input.split("|", 1)
    owner_id = int(input[0])
    user_id = int(input[1])
    if not event.sender_id == owner_id:
        return await event.answer("This action is not intended for you.", alert=True)
    f_text = "Congratulations! Federation {} (<code>{}</code>) has successfully been transferred from <a href='tg://user?id={}'>{}</a> to <a href='tg://user?id={}'>{}</a>."
    o_name = ((event.sender.first_name).replace("<", "&lt;")).replace(">", "&gt;")
    n_name = (
        ((await meow.get_entity(user_id)).first_name).replace("<", "&lt;")
    ).replace(">", "&gt;")
    fedowner = await db.get_user_owner_fed_full(owner_id)
    fed_id = fedowner[0]
    fname = fedowner[1]
    await event.edit(
        f_text.format(fname, fed_id, owner_id, o_name, user_id, n_name),
        parse_mode="html",
    )
    await db.transfer_fed(event.sender_id, user_id)
    await db.user_demote_fed(fed_id, user_id)
    await event.respond(
        ftransfer_log.format(
            fname, user_id, n_name, user_id, owner_id, o_name, owner_id, user_id, n_name
        ),
        parse_mode="html",
    )


@inline(pattern=r"ftnoc(\_(.*))")
async def noft(event):
    input = ((event.pattern_match.group(1)).decode()).split("_", 1)[1]
    input = input.split("|", 1)
    owner_id = int(input[0])
    if not event.sender_id == owner_id:
        return await event.answer("This action is not intended for you.", alert=True)
    await event.edit(
        "Fed transfer has been cancelled by <a href='tg://user?id={owner_id}'>{event.sender.first_name}</a>.",
        parse_mode="html",
    )


@register(pattern="fednotif")
async def fed_notif(event):
    if not event.is_private:
        return await event.reply("This command is made to be used in PM.")
    args = event.text.split(None, 1)[1]
    fedowner = await db.get_user_owner_fed_full(event.sender_id)
    if not fedowner:
        return await event.reply("You aren't the creator of any await feds to act in.")
    fname = fedowner[1]
    if not args:
        mode = await db.user_feds_report(event.sender_id)
        if mode:
            f_txt = "The `{}` fed is currently sending notifications to it's creator when a fed action is performed."
        else:
            f_txt = "The `{}` fed is currently **NOT** sending notifications to it's creator when a fed action is performed."
        await event.reply(f_txt.format(fname))
    elif args in ["on", "yes"]:
        await event.reply(
            f"The fed silence setting for `{fname}` has been updated to: `true`"
        )
        await db.set_feds_setting(event.sender_id, True)
    elif args in ["off", "no"]:
        await event.reply(
            f"The fed silence setting for `{fname}` has been updated to: `false`"
        )
        await db.set_feds_setting(event.sender_id, False)
    else:
        await event.reply("Your input was not recognised as one of: yes/no/on/off")


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
async def fed_reason(event):
    if not event.is_private:
        return await event.reply("This command is made to be used in PM.")
    args = event.text.split(None, 1)[1]
    fedowner = await db.get_user_owner_fed_full(event.sender_id)
    if not fedowner:
        return await event.reply("You aren't the creator of any await feds to act in.")
    fname = fedowner[1]
    if not args:
        mode = await db.get_fed_reason(event.sender_id)
        if mode:
            f_txt = "The `{}` fed is currently requiring a reason for fedbans."
        else:
            f_txt = "The `{}` fed is currently **NOT** requiring a reason for fedbans."
        await event.reply(f_txt.format(fname))
    elif args in ["on", "yes"]:
        await event.reply(
            f"The fed reason setting for `{fname}` has been updated to: `true`"
        )
        await db.set_fed_reason(event.sender_id, True)
    elif args in ["off", "no"]:
        await event.reply(
            f"The fed reason setting for `{fname}` has been updated to: `false`"
        )
        await db.set_fed_reason(event.sender_id, False)
    else:
        await event.reply("Your input was not recognised as one of: yes/no/on/off")


@register(pattern="fban")
async def fban(event, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "fban")
    if not sender_id:
        sender_id = event.sender_id
    if event.is_group:
        fed_id = await db.get_chat_fed(event.chat_id)
        if not fed_id:
            return await event.reply("This chat isn't in any federations.")
        mejik = await db.search_fed_by_id(fed_id)
        fname = mejik["fedname"]
        if not (await is_user_fed_admin(fed_id, sender_id)):
            return await event.reply(f"You aren't a federation admin for {fname}!")
        owner_id = mejik["owner_id"]
    elif event.is_private:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await event.reply("You aren't the creator of any feds to act in.")
        fed_id = fedowner[0]
        fname = fedowner[1]
        owner_id = sender_id
    if event.reply_to:
        user = (await event.get_reply_message()).sender
        try:
            reason = event.text.split(None, 1)[1]
        except BaseException:
            reason = None
    elif event.pattern_match.group(1):
        u = event.text.split(None, 2)
        try:
            u_ent = u[1]
            if u[1].isnumeric():
                u_ent = int(u[1])
            user = await meow.get_entity(u_ent)
        except BaseException:
            return await event.reply(
                "I don't know who you're talking about, you're going to need to specify a user...!"
            )
        try:
            reason = u[2]
        except BaseException:
            reason = None
    else:
        return await event.reply(
            "I don't know who you're talking about, you're going to need to specify a user...!"
        )
    check_reason = await db.get_fed_reason(owner_id)
    if check_reason:
        if not reason:
            return await event.reply("Please provide a reason to fban a user!")
    if reason:
        if len(reason) > 1024:
            reason = (
                reason[:1024]
                + "\n\nNote: The fban reason was over 1024 characters, so has been truncated."
            )
    else:
        reason = "None"
    if user.id == BOT_ID:
        return await event.reply(
            "Oh you're a funny one aren't you! I am _not_ going to fedban myself."
        )
    elif user.id in ADMINS:
        return await event.reply("I am not banning my developers.")
    elif await is_user_fed_admin(fed_id, user.id):
        f_ad = f"I'm not banning a fed admin/owner from their own fed! ({fname})"
        return await event.reply(f_ad)
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if fban:
        if reason == "" and fbanreason == "":
            return await event.reply(
                "User <a href='tg://user?id={}'>{}</a> is already banned in {}. There is no reason set for their fedban yet, so feel free to set one.".format(
                    user.id, user.first_name, fname
                ),
                parse_mode="html",
            )
        elif reason == fbanreason:
            return await event.reply(
                "User <a href='tg://user?id={}'>{}</a> has already been fbanned, with the exact same reason.".format(
                    user.id, user.first_name
                ),
                parse_mode="html",
            )
        elif reason is None:
            if not fbanreason:
                return await event.reply(
                    "User <a href='tg://user?id={}'>{}</a> is already banned in {}.".format(
                        user.id, user.first_name, fname
                    ),
                    parse_mode="html",
                )
            else:
                return await event.reply(
                    "User <a href='tg://user?id={}'>{}</a> is already banned in {}, with reason:\n<code>{}</code>.".format(
                        user.id, user.first_name, fname, fbanreason
                    ),
                    parse_mode="html",
                )
        await db.fban_user(
            fed_id,
            user.id,
            user.first_name,
            user.last_name,
            reason,
            datetime.now(),
        )
        p_reason = ""
        if fbanreason:
            p_reason = f"\n<b>Previous Reason:</b> {fbanreason}"
        fban_global_text = update_fban.format(
            fname,
            sender_id,
            event.sender.first_name,
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
            datetime.now(),
        )
        fban_global_text = new_fban.format(
            fname,
            sender_id,
            event.sender.first_name,
            user.id,
            user.first_name,
            user.id,
            reason,
        )
        if reason:
            fban_global_text = fban_global_text + f"<b>Reason:</b> {reason}"
    await event.respond(fban_global_text, parse_mode="html")
    getfednotif = await db.user_feds_report(int(owner_id))
    if getfednotif and event.chat_id != int(owner_id):
        await meow.send_message(int(owner_id), fban_global_text, parse_mode="html")
    log_c = await db.get_fed_log(fed_id)
    if log_c and event.chat_id != int(log_c):
        await meow.send_message(int(log_c), fban_global_text, parse_mode="html")
    fed_chats = list(await db.get_all_fed_chats(fed_id))
    if len(fed_chats) != 0:
        for c in fed_chats:
            try:
                await meow.edit_permissions(int(c), view_messages=False)
            except BaseException:
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
                datetime.now(),
            )
            all_fedschat = await db.get_all_fed_chats(fed)
            for c in all_fedschat:
                try:
                    await meow.edit_permissions(int(c), view_messages=False)
                except BaseException:
                    pass


@register(pattern="unfban")
async def unfban(event, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "unfban")
    if not sender_id:
        sender_id = event.sender_id
    if event.is_group:
        fed_id = await db.get_chat_fed(event.chat_id)
        if not fed_id:
            return await event.reply("This chat isn't in any federations.")
        mejik = await db.search_fed_by_id(fed_id)
        fname = mejik["fedname"]
        if not (await is_user_fed_admin(fed_id, sender_id)):
            return await event.reply(f"You aren't a federation admin for {fname}!")
        owner_id = mejik["owner_id"]
    elif event.is_private:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await event.reply(
                "You aren't the creator of any await feds to act in."
            )
        fed_id = fedowner[0]
        fname = fedowner[1]
        owner_id = sender_id
    if event.reply_to:
        user = (await event.get_reply_message()).sender
        try:
            reason = event.text.split(None, 1)[1]
        except BaseException:
            reason = None
    elif event.pattern_match.group(1):
        u = event.text.split(None, 2)
        try:
            u_ent = u[1]
            if u[1].isnumeric():
                u_ent = int(u[1])
            user = await meow.get_entity(u_ent)
        except BaseException:
            return await event.reply(
                "I don't know who you're talking about, you're going to need to specify a user...!"
            )
        try:
            reason = u[2]
        except BaseException:
            reason = None
    else:
        return await event.reply(
            "I don't know who you're talking about, you're going to need to specify a user...!"
        )
    if reason:
        if len(reason) > 1024:
            reason = (
                reason[:1024]
                + "\n\nNote: The unfban reason was over 1024 characters, so has been truncated."
            )
    if user.id == BOT_ID:
        return await event.reply(
            "Oh you're a funny one aren't you! How do you think I would have fbanned myself hm?."
        )
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if not fban:
        g_string = (
            "This user isn't banned in the current federation, {}. (`{}`)".format(
                fname, fed_id
            )
        )
        return await event.reply(g_string)
    ufb_string = un_fban.format(
        fname,
        sender_id,
        event.sender.first_name,
        user.id,
        user.first_name,
        user.id,
    )
    if reason:
        ufb_string = ufb_string + f"\n<b>Reason:</b> {reason}"
    await db.unfban_user(fed_id, user.id)
    await event.respond(ufb_string, parse_mode="html")
    getfednotif = await db.user_feds_report(int(owner_id))
    if getfednotif and event.chat_id != int(owner_id):
        await meow.send_message(int(owner_id), ufb_string, parse_mode="html")
    log_c = await db.get_fed_log(fed_id)
    if log_c and event.chat_id != int(log_c):
        await meow.send_message(int(log_c), ufb_string, parse_mode="html")


@register(pattern="chatfed")
async def CF(c):
    if c.is_private:
        chat_id = await connection(c)
        if chat_id is None:
            return await c.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = c.chat_id
        title = c.chat.title
    if not await is_admin(c, c.sender_id, pm_mode=True):
        return await c.reply(strings.NOT_ADMIN)
    fed_id = await db.get_chat_fed(chat_id)
    if not fed_id:
        return await c.reply("This chat isn't part of any feds yet!")
    fname = (await db.search_fed_by_id(fed_id))["fedname"]
    c_f = "Chat {} is part of the following federation: {} (ID: `{}`)".format(
        title, fname, fed_id
    )
    await c.reply(c_f)


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
async def finfo(event, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "fedinfo")
    if not sender_id:
        sender_id = event.sender_id
    if event.is_group:
        if not await is_admin(event, sender_id):
            return await event.reply(strings.NOT_ADMIN)
    fedowner = await db.get_user_owner_fed_full(sender_id)
    input = event.text.split(None, 1)[1]
    if not input and not fedowner:
        return await event.reply(
            "You need to give me a FedID to check, or be a federation creator to use this command!"
        )
    elif input:
        if len(input) < 10:
            return await event.reply("This isn't a valid FedID format!")
        getfed = await db.search_fed_by_id(input)
        if not getfed:
            return await event.reply(
                "This FedID does not refer to an existing federation."
            )
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
    buttons = Button.inline("Check Fed Admins", data="check_fadmins_{}".format(fed_id))
    await event.reply(fed_main, parse_mode="html", buttons=buttons)


@inline(pattern=r"check_fadmins(\_(.*))")
async def check_fadmins(e):
    if e.is_group:
        if not await cb_is_admin(e, e.sender_id):
            return
    fed_id = ((e.pattern_match.group(1)).decode()).split("_", 1)[1]
    x_admins = await db.get_all_fed_admins(fed_id) or []
    fname = (await db.search_fed_by_id(fed_id))["fedname"]
    out_str = f"Admins in federation {fname}:"
    for _x in x_admins:
        _x_name = await db.get_fname(_x) or (await meow.get_entity(int(_x))).first_name
        out_str += "\n- <a href='tg://user?id={}'>{}</a> (<code>{}</code>)".format(
            _x, _x_name, _x
        )
    await e.edit(buttons=None)
    await e.respond(out_str, parse_mode="html")


@register(pattern="subfed")
async def s_fed(event, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "subfed")
    if not sender_id:
        sender_id = event.sender_id
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await event.reply(
            "Only federation creators can subscribe to a fed. But you don't have a federation!"
        )
    arg = event.text.split(None, 1)[1]
    if not arg:
        return await event.reply(
            "You need to specify which federation you're asking about by giving me a FedID!"
        )
    if len(arg) < 10:
        return await event.reply("This isn't a valid FedID format!")
    getfed = await db.search_fed_by_id(arg)
    if not getfed:
        return await event.reply("This FedID does not refer to an existing federation.")
    s_fname = getfed["fedname"]
    if arg == fedowner[0]:
        return await event.reply("... What's the point in subscribing a fed to itself?")
    if len(await db.get_my_subs(str(fedowner[0]))) > 5:
        return await event.reply(
            "You can subscribe to at most 5 federations. Please unsubscribe from other federations before adding more."
        )
    await event.reply(
        "Federation `{}` has now subscribed to `{}`. All fedbans in `{}` will now take effect in both await feds.".format(
            fedowner[1], s_fname, s_fname
        )
    )
    await db.sub_fed(arg, fedowner[0])


@register(pattern="unsubfed")
async def us_fed(event, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "unsubfed")
    if not sender_id:
        sender_id = event.sender_id
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await event.reply(
            "Only federation creators can unsubscribe to a fed. But you don't have a federation!"
        )
    arg = event.text.split(None, 1)[1]
    if not arg:
        return await event.reply(
            "You need to specify which federation you're asking about by giving me a FedID!"
        )
    if len(arg) < 10:
        return await event.reply("This isn't a valid FedID format!")
    getfed = await db.search_fed_by_id(arg)
    if not getfed:
        return await event.reply("This FedID does not refer to an existing federation.")
    await event.reply(
        "Federation `{}` is no longer subscribed to `{}`. Bans in `{}` will no longer be applied. Please note that any bans that happened because the user was banned from the subfed will need to be removed manually.".format(
            fedowner[1], getfed["fedname"], getfed["fedname"]
        )
    )
    await db.unsub_fed(arg, fedowner[0])


@register(pattern="(feddemoteme|fdemoteme)")
async def self_demote(e, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(e.sender, types.Channel):
            return await anon_fed(e, "feddemoteme")
    if not sender_id:
        sender_id = e.sender_id
    try:
        fed_id = e.text.split(None, 1)[1]
    except IndexError:
        return await e.reply(
            "You need to specify a federation ID to demote yourself from."
        )
    getfed = await db.search_fed_by_id(fed_id)
    if not getfed:
        return await e.reply("This FedID does not refer to an existing federation.")
    fedname = getfed["fedname"]
    if int(getfed["owner_id"]) == sender_id:
        return await e.reply(
            "You can't demote yourself from your own fed - who would be the owner?"
        )
    if not (await is_user_fed_admin(fed_id, sender_id)):
        return await e.reply(
            f"You aren't an admin in '{fedname}' - how would I demote you?"
        )
    await e.reply(f"You are no longer a fed admin in '{fedname}'")
    await db.user_demote_fed(fed_id, sender_id)


@register(pattern="myfeds")
async def my_feds(event, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "myfeds")
    if not sender_id:
        sender_id = event.sender_id
    fed_list = await db.get_all_fed_admin(event.sender_id)
    if not fed_list:
        return await event.reply("You aren't a member of any federations.")
    out_str = "You are an admin of the following federations:"
    for fed in fed_list:
        fed_name = await db.get_fed_name(fed)
        out_str += f"\n- {fed_name} (<code>{fed}</code>)"
    await event.reply(out_str)


@register(pattern="setfedlog")
async def set_fed_logs(e, sender_id: int = None, anon: bool = False):
    if e.is_private:
        return await e.reply(
            "This command is made to be used in group chats or channels, not in PM!"
        )
    if not anon:
        if e.is_group and isinstance(e.sender, types.Channel):
            return await anon_fed(e, "setfedlog")
    if not sender_id:
        sender_id = e.sender_id
    if e.is_group and not await can_change_info(e, sender_id):
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner and not e.pattern_match.group(1):
        return await e.reply(
            "Only fed creators can set a fed log - but you don't have a federation! If you have try doing /setfedlog <fedid>"
        )
    elif fedowner:
        fed_id = fedowner[0]
        fname = fedowner[1]
    elif e.pattern_match.group(1):
        fed_id = e.pattern_match.group(1)
        fed = await db.search_fed_by_id(fed_id)
        if not fed:
            return await e.reply("This isn't a valid FedID!")
        fname = fed["fedname"]
    await db.set_fed_log(fed_id, e.chat_id)
    await e.reply(
        f"This has been set as the fed log for {fname} - all fed related actions will be logged here."
    )


@register(pattern="unsetfedlog")
async def un_set_fed_log(e, sender_id: int = None, anon: bool = False):
    if e.is_private:
        return await e.reply(
            "This command is made to be used in group chats or channels, not in PM!"
        )
    if not anon:
        if e.is_group and isinstance(e.sender, types.Channel):
            return await anon_fed(e, "unsetfedlog")
    if not sender_id:
        sender_id = e.sender_id
    if e.is_group and not await can_change_info(e, sender_id):
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await e.reply(
            "Only fed creators can unset a fed log - but you don't have a federation!"
        )
    fed_id = fedowner[0]
    fname = fedowner[1]
    await db.set_fed_log(fed_id)
    await e.reply(f"The {fname} federation has had its log location unset.")


@register(pattern="fedadmins")
async def fedadmins_(e, sender_id: int = None, anon: bool = False):
    if e.is_group:
        if not anon:
            if isinstance(e.sender, types.Channel):
                return await anon_fed(e, "fedadmins")
        if not sender_id:
            sender_id = e.sender_id
        if not await is_admin(e, sender_id):
            return await e.reply(strings.NOT_ADMIN)
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner and not e.pattern_match.group(1):
        return await e.reply(
            "You need to give me a FedID to check, or be a federation creator to use this command!"
        )
    elif fedowner:
        fed_id = fedowner[0]
        fname = fedowner[1]
    elif len(e.text.split(" ", 1)) == 2:
        fed_id = e.text.split(" ", 1)[1]
        fed = await db.search_fed_by_id(fed_id)
        if not fed:
            return await e.reply("This isn't a valid FedID!")
        fname = fed["fedname"]
    else:
        fed_id = await db.get_chat_fed(e.chat_id)
        if not fed_id:
            return await e.reply("This chat isn't in any federations.")
        fname = await db.search_fed_by_id(fed_id)["fedname"]
    x_admins = await db.get_all_fed_admins(fed_id) or []
    out_str = f"Admins in federation '{fname}':"
    for _x in x_admins:
        _x_name = await db.get_fname(_x) or (await meow.get_entity(int(_x))).first_name
        out_str += "\n- <a href='tg://user?id={}'>{}</a> (<code>{}</code>)".format(
            _x, _x_name, _x
        )
    await e.reply(out_str, parse_mode="html")


@register(pattern="fedsubs")
async def fedsubs(event, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(event.sender, types.Channel):
            return await anon_fed(event, "fedsubs")
    if not sender_id:
        sender_id = event.sender_id
    fedowner = await db.get_user_owner_fed_full(sender_id)
    subfed = await db.get_all_subscribed_feds(fedowner[0])
    fname = fedowner[1]
    if not subfed:
        return await event.reply("You aren't subscribed to any other feds.")
    out_str = f"Your federation **{fname}** (`{fedowner[0]}`) is subscribed to the following feds:"
    for fed in subfed:
        fed_name = await db.get_fed_name(fed)
        out_str += f"\n- {fed_name} (`{fed}`)"


@register(pattern="fedstat")
async def fedstat(e, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(e.sender, types.Channel):
            return await anon_fed(e, "fedstat")
    if not sender_id:
        sender_id = e.sender_id
    if not e.pattern_match.group(1):
        return await e.reply(
            "You need to specify a federation ID to check your ban status."
        )
    getfed = await db.search_fed_by_id(e.pattern_match.group(1))
    if not getfed:
        return await e.reply("This FedID does not refer to an existing federation.")
    fban, fbanreason, fbantime = await db.get_fban_user(
        e.pattern_match.group(1), sender_id
    )
    if not fban:
        return await e.reply("You aren't banned in this federation.")
    out_str = f"You are banned in federation {getfed['fedname']} (`{e.pattern_match.group(1)}`)."
    if fbanreason:
        out_str += f"\nReason: {fbanreason}"
    out_str += f"\nTime: {fbantime}"
    await e.reply(out_str)


@register(pattern="(fexport|fedexport)")
async def fed_export___(e, sender_id: int = None, anon: bool = False):
    if e.is_group:
        if not anon:
            if isinstance(e.sender, types.Channel):
                return await anon_fed(e, "fexport")
        if not sender_id:
            sender_id = e.sender_id
        fed_id = await db.get_chat_fed(e.chat_id)
        if not fed_id:
            return await e.reply("This chat isn't in any federations.")
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner or fedowner[0] != fed_id:
            return await e.reply("Only the fed creator can export the ban list.")
        fname = fedowner[1]
    elif e.is_private:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await e.reply("You aren't the creator of any await feds to act in.")
        fname = fedowner[1]
        fed_id = fedowner[0]
    fbans = await db.get_all_fbans(fedowner[0])
    if not fbans:
        return await e.reply("There are no banned users in {}".format(fname))
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
    if mode == "csv":
        fban_list = []
        for fban in fbans:
            fb = fbans[fban]
            fban_list.append(
                {"Name": fb[0], "User ID": fban, "Reason": fb[2], "Time": str(fb[3])}
            )
        csv_headers = ["Name", "User ID", "Reason", "Time"]
        with open("fbanned_users.csv", "w") as csvfile:
            w = csv.DictWriter(csvfile, fieldnames=csv_headers)
            w.writeheader()
            for fban in fban_list:
                w.writerow(fban)
        await e.reply("Fbanned users in {}.".format(fname), file="fbanned_users.csv")
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
            fban_list += orjson.dumps(json_p).decode('utf-8') + "\n"
        with open("fbanned_users.json", "w") as f:
            f.write(fban_list)
        await e.reply("Fbanned users in {}.".format(fname), file="fbanned_users.json")
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
            xml_str += str(tostring(el)) + "\n"
        with open("fbanned_users.xml", "w") as f:
            f.write(xml_str)
        await e.reply("Fbanned users in {}.".format(fname), file="fbanned_users.xml")


@register(pattern="(fimport|fedimport)")
async def fed_import___(e, sender_id: int = None, anon: bool = False):
    if not anon:
        if isinstance(e.sender, types.Channel):
            return await anon_fed(e, "fimport")
    if not sender_id:
        sender_id = e.sender_id
    if not e.reply_to:
        return await e.reply(
            "You need to reply to the document containing the banlist, as a .txt file."
        )
    r = await e.get_reply_message()
    if not e.media and r.file.ext not in [".xml", ".json", ".csv"]:
        return await e.reply(
            "You need to reply to the document containing the banlist, as a .txt file."
        )
    if e.is_group:
        fed_id = await db.get_chat_fed(e.chat_id)
        if not fed_id:
            return await e.reply("This chat isn't in any federations.")
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner or fedowner[0] != fed_id:
            return await e.reply("Only the fed creator can import a ban list.")
        mejik = await db.search_fed_by_id(fed_id)
        mejik["fedname"]
    elif e.is_private:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await e.reply("You aren't the creator of any await feds to act in.")
        fedowner[1]
        fed_id = fedowner[0]
    Ext = r.file.ext.replace(".", "")
    f = await e.client.download_media(r)
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
                datetime.now(),
            )
        await e.reply(
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
                datetime.now(),
            )
        await e.reply(
            "Files were imported successfully. {} people banned. {} Failed to import.".format(
                len(fbans), 0
            )
        )
    elif Ext == "xml":
        await e.reply(
            "File is in XML format. {} people banned. {} Failed to import.".format(0, 0)
        )


async def anon_fed(e, mode):
    if e.is_private:
        return
    anon_db[e.id] = (e, mode)
    buttons = Button.inline("Click to prove Admin", data="fedp_{}".format(e.id))
    await e.reply(
        "It looks like you're anonymous. Tap this button to confirm your identity.",
        buttons=buttons,
    )


@inline(pattern=r"fedp(\_(.*))")
async def fed_call__back___(e):
    e_id = int(((e.pattern_match.group(1)).decode()).split("_", 1)[1])
    try:
        r = anon_db[e_id]
    except KeyError:
        return await e.edit("This message is too old to interact with.")
    event, mode = r
    if mode == "fimport":
        await fed_import___(event, e.sender_id, anon=True)
    elif mode == "fexport":
        await fed_export___(event, e.sender_id, anon=True)
    elif mode == "fedstat":
        await fedstat(event, e.sender_id, anon=True)
    elif mode == "fedsubs":
        await fedsubs(event, e.sender_id, anon=True)
    elif mode == "fedadmins":
        await fedadmins_(event, e.sender_id, anon=True)
    elif mode == "unsetfedlog":
        await un_set_fed_log(event, e.sender_id, anon=True)
    elif mode == "setfedlog":
        await set_fed_logs(event, e.sender_id, anon=True)
    elif mode == "myfeds":
        await my_feds(event, e.sender_id, anon=True)
    elif mode == "feddemoteme":
        await self_demote(event, e.sender_id, anon=True)
    elif mode == "subfed":
        await s_fed(event, e.sender_id, anon=True)
    elif mode == "unsubfed":
        await us_fed(event, e.sender_id, anon=True)
    elif mode == "fedinfo":
        await finfo(event, e.sender_id, anon=True)
    elif mode == "unfban":
        await unfban(event, e.sender_id, anon=True)
    elif mode == "fban":
        await fban(event, e.sender_id, anon=True)
    elif mode == "ftransfer":
        await ft(event, e.sender_id, anon=True)
    elif mode == "fdemote":
        await fd(event, e.sender_id, anon=True)
    elif mode == "fpromote":
        await fp(event, e.sender_id, anon=True)
    elif mode == "leavefed":
        await lfed(event, e.sender_id, anon=True)
    elif mode == "joinfed":
        await jfed(event, e.sender_id, anon=True)


@register(pattern="quietfed")
@logging
async def qf(event):
    if event.is_private:
        chat_id = await connection(event)
        if chat_id is None:
            return await event.reply(strings.is_pvt)
        title = await GetChat(chat_id)
    else:
        chat_id = event.chat_id
        title = event.chat.title
    if not await is_admin(event, event.sender_id, pm_mode=True):
        return await event.reply(strings.NOT_ADMIN)

    data = await db.feds.find_one({"chat_id": chat_id})
    if data and data["quiet"]:
        await db.quietfed({"chat_id": chat_id, "quiet": False})
        await event.reply(f"Quietfed has been disabled in {title}.")
        return "QUIETFED_DISABLE", None, None
    else:
        await db.quietfed({"chat_id": chat_id, "quiet": True})
        await event.reply(f"Quietfed has been enabled in {title}.")
        return "QUIETFED_ENABLE", None, None


@meow.on(events.NewMessage())
async def fban_welcome(e):
    if e.is_private:
        return
    if not await botfban(e.chat_id, BOT_ID):
        return
    fed_id = await db.get_chat_fed(e.chat_id)
    if not fed_id:
        return
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, e.sender_id)
    quiet = await db.feds.find_one({"chat_id": e.chat_id})
    if fban and fbanreason:
        try:
            await meow.edit_permissions(
                e.chat_id, int(e.sender_id), until_date=None, view_messages=False
            )
            if quiet and quiet["quiet"] is False:
                return await e.respond(
                    f"The user {e.sender.first_name} has been fbanned in the current federation due to the following reason:\n{fbanreason}\n\nHence banned from here as well."
                )
            else:
                return
        except BaseException:
            pass
    else:
        return
import re

from pyrogram import filters as pyrofilters
from pyrogram.types import LinkPreviewOptions
from vanitaspy import User

from Emilia import db
from Emilia.custom_filter import listen, register
from Emilia.helper.admins import can_ban_users
from Emilia.utils.decorators import *

vanitas_db = db.vanitas

us = User()


def banned(user):
    chk = us.get_info(user)
    if chk["blacklisted"]:
        return True
    if not chk["blacklisted"]:
        return False


# handlers
HLRS = re.compile("(?i)(on|off|enable|disable|yes|no)")
OFF = re.compile("(?i)(off|disable|no)")
ON = re.compile("(?i)(on|enable|yes)")


@usage("/antispam [enable/disable]")
@example("/antispam enable")
@description(
    "This will trigger whether to enable or disable Vanitas Antispam System which protects your group chat from potential threats."
)
@register(pattern="antispam")
@log_to_channel
@anonadmin_checker
async def vanitas_handerl(client, van):
    args = van.pattern_match.group(1)
    chat = van.chat.id
    vanitas = await vanitas_db.find_one({"chat_id": chat})
    if not args:
        return await usage_string(van, vanitas_handerl)
    elif not re.findall(HLRS, args):
        return await van.reply_text(
            "Provide a valid argument. Like enable/disable/on/off."
        )
    if not await can_ban_users(van, van.from_user.id if van.from_user else None):
        return
    elif re.findall(ON, args):
        if not vanitas:
            return await van.reply_text("Vanitas Antispam System is already enabled.")
        await vanitas_db.delete_one({"chat_id": chat})
        await van.reply_text(
            f"Enabled Vanitas Antispam System in **{van.chat.title}** by [{van.from_user.first_name}]({van.from_user.id})."
        )
        return "ENABLED_ANTISPAM", None, None
    elif re.findall(OFF, args):
        if vanitas:
            return await van.reply_text("Vanitas Antispam System is already disabled.")
        await vanitas_db.update_one(
            {"chat_id": chat},
            {"$setOnInsert": {"chat_id": chat}},
            upsert=True,
        )
        await van.reply_text(
            f"Disabled Vanitas Antispam System in **{van.chat.title}** by [{van.from_user.first_name}]({van.from_user.id})."
        )
        return "DISABLED_ANTISPAM", None, None


# ban on welcome
@listen(filters=pyrofilters.new_chat_members)
async def chk_(client, message):
    chat_id = message.chat.id
    not_vanitas = await vanitas_db.find_one({"chat_id": chat_id})
    if not_vanitas:
        return
    for new_member in message.new_chat_members:
        if banned(new_member.id):
            try:
                await client.ban_chat_member(chat_id, new_member.id)
                chec = us.get_info(new_member.id)
                txt = f"**This user has been blacklisted in Vanitas Antispam System**\n"
                txt += f"**Reason:** `{chec['reason']}`\n"
                txt += f"**Enforcer:** `{chec['enforcer']}`\n\n"
                txt += "Report for unban at @VanitasSupport"
                await message.reply_text(
                    txt, link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
            except Exception as er:
                await message.reply_text(str(er))

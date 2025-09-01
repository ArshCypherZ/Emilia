import re

from telethon import events
from vanitaspy import User

from Emilia import db, telethn
from Emilia.custom_filter import register
from Emilia.functions.admins import can_ban_users
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
@logging
@anonadmin_checker
async def vanitas_handerl(van):
    args = van.pattern_match.group(1)
    chat = van.chat_id
    vanitas = await vanitas_db.find_one({"chat_id": chat})
    if not args:
        return await usage_string(van, vanitas_handerl)
    elif not re.findall(HLRS, args):
        return await van.reply("Provide a valid argument. Like enable/disable/on/off.")
    if not await can_ban_users(van, van.sender_id):
        return
    elif re.findall(ON, args):
        if not vanitas:
            return await van.reply("Vanitas Antispam System is already enabled.")
        await vanitas_db.delete_one({"chat_id": chat})
        await van.reply(
            f"Enabled Vanitas Antispam System in **{van.chat.title}** by [{van.sender.first_name}]({van.sender_id})."
        )
        return "ENABLED_ANTISPAM", None, None
    elif re.findall(OFF, args):
        if vanitas:
            return await van.reply("Vanitas Antispam System is already disabled.")
        await vanitas_db.update_one(
            {"chat_id": chat},
            {"$setOnInsert": {"chat_id": chat}},
            upsert=True,
        )
        await van.reply(
            f"Disabled Vanitas Antispam System in **{van.chat.title}** by [{van.sender.first_name}]({van.sender_id})."
        )
        return "DISABLED_ANTISPAM", None, None


# ban on welcome
@telethn.on(events.ChatAction)
async def chk_(event):
    if event.user_joined or event.user_added:
        chat_id = event.chat_id
        not_vanitas = await vanitas_db.find_one({"chat_id": chat_id})
        if not_vanitas:
            return
        if banned(event.user_id):
            try:
                await telethn.edit_permissions(
                    event.chat_id, event.user_id, view_messages=False
                )
                chec = us.get_info(event.user_id)
                txt = f"**This user has been blacklisted in Vanitas Antispam System**\n"
                txt += f"**Reason:** `{chec['reason']}`\n"
                txt += f"**Enforcer:** `{chec['enforcer']}`\n\n"
                txt += "Report for unban at @VanitasSupport"
                await event.reply(txt, link_preview=False)
            except Exception as er:
                await event.reply(er)

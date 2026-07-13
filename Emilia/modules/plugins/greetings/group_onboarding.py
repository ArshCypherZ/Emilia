import asyncio
from typing import Dict, Iterable, Optional, Tuple

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

from Emilia import BOT_ID, BOT_NAME, BOT_USERNAME, SUPPORT_CHAT, UPDATE_CHANNEL, db
from Emilia.helper.get_data import GetChat
from Emilia.modules.commands.levels import _level_cache
from Emilia.modules.plugins.antichannel import antichannelmode_off, antichannelmode_on
from Emilia.modules.plugins.antiflood import DB as ANTIFLOOD_DB
from Emilia.modules.plugins.antiflood import (
    _flood_status_cache as antiflood_status_cache,
)
from Emilia.modules.plugins.antiflood import _settings_cache as antiflood_settings_cache
from Emilia.modules.plugins.warnings.set_warn_mode import WarnModeMap
from Emilia.mongo.connection_mongo import connectDB
from Emilia.mongo.filters_mongo import get_filters_list
from Emilia.mongo.locks_mongo import get_locks, lock_db, unlock_db
from Emilia.mongo.log_channels_mongo import get_set_channel
from Emilia.mongo.notes_mongo import NoteList
from Emilia.mongo.rules_mongo import get_private_note, get_rules
from Emilia.mongo.warnings_mongo import (
    get_warn_mode,
    set_warn_limit_db,
    set_warn_mode_db,
    warn_limit,
)
from Emilia.mongo.welcome_mongo import (
    GetWelcomemessageOnOff,
    SetCaptcha,
    SetWelcomeMessageOnOff,
    isGetCaptcha,
)

HIDE_LATER_SECONDS = 3600
_cleanup_tasks: Dict[Tuple[int, int], asyncio.Task] = {}

PRIVILEGE_LABELS = {
    "can_change_info": "change group settings",
    "can_delete_messages": "delete messages",
    "can_restrict_members": "restrict members",
    "can_pin_messages": "pin messages",
    "can_invite_users": "invite users",
}


def _bool_text(value: bool) -> str:
    return "On" if value else "Off"


def _warn_mode_text(mode_value: int) -> str:
    mapping = {
        WarnModeMap.Ban.value: "Ban",
        WarnModeMap.Kick.value: "Kick",
        WarnModeMap.Mute.value: "Mute",
        WarnModeMap.Tban.value: "Temp Ban",
        WarnModeMap.Tmute.value: "Temp Mute",
    }
    return mapping.get(mode_value, "Mute")


def _format_locks(locks: Iterable[str]) -> str:
    locks = list(locks)
    if not locks:
        return "Off"
    if len(locks) <= 3:
        return ", ".join(locks)
    return f"{len(locks)} active"


def _member_is_admin(member) -> bool:
    return bool(
        member
        and member.status in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR}
    )


def _member_has_priv(member, privilege: str) -> bool:
    if not member:
        return False
    if member.status == ChatMemberStatus.OWNER:
        return True
    privileges = getattr(member, "privileges", None)
    return bool(privileges and getattr(privileges, privilege, False))


async def _safe_edit(
    callback_query: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup
):
    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=reply_markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except MessageNotModified:
        pass


async def _chat_title(client: Client, chat_id: int) -> str:
    title = await GetChat(chat_id)
    if title:
        return title
    try:
        chat = await client.get_chat(chat_id)
        return chat.title or str(chat_id)
    except Exception:
        return str(chat_id)


async def _fetch_member(client: Client, chat_id: int, user_id: int):
    try:
        return await client.get_chat_member(chat_id, user_id), None
    except Exception as err:
        return None, err


async def _resolve_setup_access(
    client: Client,
    user_id: int,
    chat_id: int,
    required_privilege: Optional[str] = None,
):
    title = await _chat_title(client, chat_id)
    user_member, user_error = await _fetch_member(client, chat_id, user_id)
    if user_error is not None:
        return (
            False,
            (
                f"I couldn't verify your admin status in {title} yet. "
                "This can happen right after I'm added or promoted. Please try again in a few seconds or promote me to admin first."
            ),
            title,
            None,
            None,
        )

    if not _member_is_admin(user_member):
        return (
            False,
            f"You're not an admin in {title}, so I can't open the setup panel for that chat.",
            title,
            user_member,
            None,
        )

    if required_privilege and not _member_has_priv(user_member, required_privilege):
        friendly = PRIVILEGE_LABELS.get(required_privilege, required_privilege)
        return (
            False,
            f"You're an admin in {title}, but this step needs permission to {friendly}.",
            title,
            user_member,
            None,
        )

    bot_member, _ = await _fetch_member(client, chat_id, BOT_ID)
    return True, None, title, user_member, bot_member


def _bot_permission_error(title: str, privilege: str) -> str:
    friendly = PRIVILEGE_LABELS.get(privilege, privilege)
    return f"I still need permission to {friendly} in {title} before I can do that."


def _group_keyboard(chat_id: int, has_rules: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "Set Up Emilia",
                url=f"https://t.me/{BOT_USERNAME}?start=onboard_{chat_id}",
            ),
            InlineKeyboardButton(
                "Try Emilia",
                url=f"https://t.me/{BOT_USERNAME}?start=starter_{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton("Support", url=f"https://t.me/{SUPPORT_CHAT}"),
            InlineKeyboardButton("News", url=f"https://t.me/{UPDATE_CHANNEL}"),
        ],
    ]

    if has_rules:
        rows.append(
            [
                InlineKeyboardButton(
                    "Rules",
                    url=f"https://t.me/{BOT_USERNAME}?start=rules_{chat_id}",
                ),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton("Pin Guide", callback_data="grpguide:pin"),
            InlineKeyboardButton("Hide in 1h", callback_data="grpguide:hide"),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def _get_settings(chat_id: int) -> dict:
    (
        welcome_on,
        captcha_on,
        rules_text,
        private_rules,
        log_channel,
        warn_limit_value,
        warn_mode_data,
        locks,
        notes,
        filters_list,
        flood_doc,
        antispam_doc,
        antichannel_doc,
        chatbot_doc,
        level_doc,
    ) = await asyncio.gather(
        GetWelcomemessageOnOff(chat_id),
        isGetCaptcha(chat_id),
        get_rules(chat_id),
        get_private_note(chat_id),
        get_set_channel(chat_id),
        warn_limit(chat_id),
        get_warn_mode(chat_id),
        get_locks(chat_id),
        NoteList(chat_id),
        get_filters_list(chat_id),
        db.antiflood_chats.find_one({"chat_id": chat_id}),
        db.vanitas.find_one({"chat_id": chat_id}),
        db.antichannel.find_one({"chat_id": chat_id}),
        db.chatbotto.find_one({"chat_id": chat_id}),
        db.onofflevel.find_one({"chat_id": chat_id}),
    )

    flood_on = bool(flood_doc and flood_doc.get("status") != "off")
    flood_limit = int((flood_doc or {}).get("limit", 10))
    rankings_on = bool(level_doc and not level_doc.get("disabled", False))

    return {
        "welcome_on": welcome_on,
        "captcha_on": captcha_on,
        "rules_set": bool(rules_text),
        "rules_private": private_rules,
        "log_channel": log_channel,
        "warn_limit": warn_limit_value,
        "warn_mode": _warn_mode_text(warn_mode_data[0]),
        "locks": list(locks),
        "notes_count": len(notes),
        "filters_count": len(filters_list),
        "flood_on": flood_on,
        "flood_limit": flood_limit,
        "antispam_on": antispam_doc is None,
        "antichannel_on": bool(antichannel_doc),
        "chatbot_on": bool(chatbot_doc),
        "rankings_on": rankings_on,
    }


async def _set_antiflood(chat_id: int, enabled: bool, limit: Optional[int] = None):
    current = await ANTIFLOOD_DB.find_one({"chat_id": chat_id}) or {}
    if enabled:
        effective_limit = int(current.get("limit", 10) if limit is None else limit)
        await ANTIFLOOD_DB.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "status": "on",
                    "limit": effective_limit,
                    "action": current.get("action", "mute"),
                    "clear": current.get("clear", "yes"),
                    "timed_status": current.get("timed_status", "off"),
                    "timed_limit": int(current.get("timed_limit", 10)),
                    "timed_duration": int(current.get("timed_duration", 10)),
                    "time": current.get("time"),
                }
            },
            upsert=True,
        )
        await antiflood_status_cache.set(f"flood_on:{chat_id}", True, ttl=60)
    else:
        await ANTIFLOOD_DB.update_one(
            {"chat_id": chat_id},
            {"$set": {"status": "off"}},
            upsert=True,
        )
        await antiflood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)
    await antiflood_settings_cache.delete(f"antiflood_settings:{chat_id}")


async def _set_antispam(chat_id: int, enabled: bool):
    if enabled:
        await db.vanitas.delete_one({"chat_id": chat_id})
    else:
        await db.vanitas.update_one(
            {"chat_id": chat_id},
            {"$setOnInsert": {"chat_id": chat_id}},
            upsert=True,
        )


async def _set_antichannel(chat_id: int, enabled: bool):
    if enabled:
        await antichannelmode_on(chat_id)
    else:
        await antichannelmode_off(chat_id)


async def _set_chatbot(chat_id: int, enabled: bool):
    if enabled:
        await db.chatbotto.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id}},
            upsert=True,
        )
    else:
        await db.chatbotto.delete_one({"chat_id": chat_id})


async def _set_rankings(chat_id: int, enabled: bool):
    if enabled:
        await db.onofflevel.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id}, "$unset": {"disabled": ""}},
            upsert=True,
        )
    else:
        await db.onofflevel.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "disabled": True}},
            upsert=True,
        )
    await _level_cache.delete(f"lvl:{chat_id}")


async def _set_lock_bundle(chat_id: int, bundle: str):
    if bundle == "basic":
        targets = {"invitelink", "forward"}
    else:
        targets = {"invitelink", "forward", "url", "inline"}

    managed = {"invitelink", "forward", "url", "inline"}
    for lock_name in targets:
        await lock_db(chat_id, lock_name)
    for lock_name in managed - targets:
        await unlock_db(chat_id, lock_name)


async def _apply_preset(chat_id: int, preset: str):
    await SetWelcomeMessageOnOff(chat_id, True)
    await set_warn_mode_db(chat_id, WarnModeMap.Mute.value)

    if preset == "strict":
        await SetCaptcha(chat_id, True)
        await _set_antiflood(chat_id, True, limit=10)
        await set_warn_limit_db(chat_id, 3)
        await _set_lock_bundle(chat_id, "basic")
        await _set_antispam(chat_id, True)
        await _set_antichannel(chat_id, False)
        await _set_chatbot(chat_id, False)
        await _set_rankings(chat_id, False)
        return "Applied Strict Community."

    if preset == "chill":
        await SetCaptcha(chat_id, False)
        await _set_antiflood(chat_id, True, limit=15)
        await set_warn_limit_db(chat_id, 4)
        await _set_antichannel(chat_id, False)
        await _set_chatbot(chat_id, False)
        await _set_rankings(chat_id, False)
        return "Applied Chill Group."

    if preset == "media":
        await SetCaptcha(chat_id, False)
        await _set_antiflood(chat_id, True, limit=12)
        await set_warn_limit_db(chat_id, 4)
        await _set_lock_bundle(chat_id, "basic")
        await _set_antispam(chat_id, True)
        await _set_antichannel(chat_id, True)
        await _set_chatbot(chat_id, False)
        await _set_rankings(chat_id, False)
        return "Applied Media / Anime Group."

    await SetCaptcha(chat_id, False)
    await _set_antiflood(chat_id, True, limit=18)
    await set_warn_limit_db(chat_id, 5)
    await _set_antispam(chat_id, True)
    await _set_antichannel(chat_id, False)
    await _set_chatbot(chat_id, True)
    await _set_rankings(chat_id, True)
    return "Applied Fun Group."


def _toggle_label(prefix: str, enabled: bool) -> str:
    return f"{prefix} Off" if enabled else f"{prefix} On"


def _toggle_state(enabled: bool) -> str:
    return "off" if enabled else "on"


def _setup_home_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Permissions Check", callback_data=f"onbpm:permissions:{chat_id}"
                ),
                InlineKeyboardButton(
                    "Choose Preset", callback_data=f"onbpm:presets:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "Welcome & Rules", callback_data=f"onbpm:welcome:{chat_id}"
                ),
                InlineKeyboardButton(
                    "Protection", callback_data=f"onbpm:protection:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "Log Channel", callback_data=f"onbpm:logs:{chat_id}"
                ),
                InlineKeyboardButton(
                    "Optional Extras", callback_data=f"onbpm:extras:{chat_id}"
                ),
            ],
            [InlineKeyboardButton("Summary", callback_data=f"onbpm:summary:{chat_id}")],
        ]
    )


async def _render_setup_home(
    client: Client, chat_id: int
) -> Tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    text = (
        f"**Emilia Setup**\n\n"
        f"Connected to {title}.\n\n"
        "I'll keep this short. Recommended order:\n"
        "1. Permissions Check\n"
        "2. Choose a Preset\n"
        "3. Welcome, Rules, Captcha\n"
        "4. Protection\n"
        "5. Log Channel\n"
        "6. Optional Extras\n\n"
        "I also connected this chat to your PM, so Emilia's regular admin commands now work here too. "
        "Use `/disconnect` when you're done."
    )
    return text, _setup_home_keyboard(chat_id)


def _permission_lines(member, items: Iterable[Tuple[str, str]]) -> str:
    return "\n".join(
        f"- {label}: {'Yes' if _member_has_priv(member, privilege) else 'No'}"
        for label, privilege in items
    )


async def _render_permissions(
    client: Client, chat_id: int, user_id: int
) -> Tuple[str, InlineKeyboardMarkup]:
    _, _, title, user_member, bot_member = await _resolve_setup_access(
        client, user_id, chat_id
    )

    permission_items = [
        ("Delete messages", "can_delete_messages"),
        ("Restrict members", "can_restrict_members"),
        ("Pin messages", "can_pin_messages"),
        ("Invite users", "can_invite_users"),
    ]

    bot_status = (
        "I am not an admin there yet."
        if not _member_is_admin(bot_member)
        else _permission_lines(bot_member, permission_items)
    )
    your_status = (
        "You are verified as an admin."
        if _member_is_admin(user_member)
        else "Your current admin state will be checked again on button presses."
    )

    text = (
        "**Setup 1/6: Permissions Check**\n\n"
        f"Chat: {title}\n"
        f"{your_status}\n\n"
        "These are the main rights I need for moderation:\n"
        f"{bot_status}\n\n"
        "If something is missing, fix it in the group, then tap Refresh."
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Refresh", callback_data=f"onbpm:permissions:{chat_id}"
                ),
                InlineKeyboardButton(
                    "Choose Preset", callback_data=f"onbpm:presets:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "Back to Setup", callback_data=f"onbpm:home:{chat_id}"
                )
            ],
        ]
    )
    return text, keyboard


async def _render_presets(
    client: Client, chat_id: int
) -> Tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    text = (
        "**Setup 2/6: Choose a Preset**\n\n"
        f"Pick the closest starting point for {title}. You can fine-tune the rest after.\n\n"
        "- Strict Community: captcha, antiflood, warnings, stronger defaults\n"
        "- Chill Group: welcome first, lighter moderation\n"
        "- Media / Anime Group: anti-spam, anti-channel, anime-friendly surface\n"
        "- Fun Group: rankings, chatbot-ready, relaxed defaults"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Strict Community",
                    callback_data=f"onbpm:applypreset:strict:{chat_id}",
                ),
                InlineKeyboardButton(
                    "Chill Group", callback_data=f"onbpm:applypreset:chill:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "Media / Anime Group",
                    callback_data=f"onbpm:applypreset:media:{chat_id}",
                ),
                InlineKeyboardButton(
                    "Fun Group", callback_data=f"onbpm:applypreset:fun:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "Back to Setup", callback_data=f"onbpm:home:{chat_id}"
                )
            ],
        ]
    )
    return text, keyboard


async def _render_welcome_rules(
    client: Client, chat_id: int
) -> Tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    rows = [
        [
            InlineKeyboardButton(
                _toggle_label("Welcome", settings["welcome_on"]),
                callback_data=f"onbpm:setwelcome:{_toggle_state(settings['welcome_on'])}:{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                _toggle_label("Captcha", settings["captcha_on"]),
                callback_data=f"onbpm:setcaptcha:{_toggle_state(settings['captcha_on'])}:{chat_id}",
            ),
        ],
    ]

    if settings["rules_set"]:
        rows.append(
            [
                InlineKeyboardButton(
                    "Open Rules",
                    url=f"https://t.me/{BOT_USERNAME}?start=rules_{chat_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton("Back to Setup", callback_data=f"onbpm:home:{chat_id}")]
    )

    text = (
        "**Setup 3/6: Welcome, Rules, Captcha**\n\n"
        f"Chat: {title}\n\n"
        f"- Welcome: {_bool_text(settings['welcome_on'])}\n"
        f"- Rules: {'Set' if settings['rules_set'] else 'Not Set'}\n"
        f"- Captcha: {_bool_text(settings['captcha_on'])}\n\n"
        "Best first pass:\n"
        "- Keep welcome on for most groups\n"
        "- Set rules with `/setrules ...`\n"
        "- Use `/privaterules on` if you want a cleaner chat\n"
        "- Enable captcha in stricter or more public groups"
    )
    return text, InlineKeyboardMarkup(rows)


async def _render_protection(
    client: Client, chat_id: int
) -> Tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    text = (
        "**Setup 4/6: Protection**\n\n"
        f"Chat: {title}\n\n"
        f"- Antiflood: {_bool_text(settings['flood_on'])}"
        + (f" ({settings['flood_limit']} msgs)" if settings["flood_on"] else "")
        + "\n"
        f"- Warn Limit: {settings['warn_limit']}\n"
        f"- Warn Mode: {settings['warn_mode']}\n"
        f"- Locks: {_format_locks(settings['locks'])}\n"
        f"- Anti-Spam: {_bool_text(settings['antispam_on'])}\n"
        f"- Anti-Channel: {_bool_text(settings['antichannel_on'])}\n\n"
        "Good defaults:\n"
        "- Antiflood on\n"
        "- Warn limit 3 or 5\n"
        "- Basic locks for `invitelink` and `forward`\n"
        "- Strict locks add `url` and `inline`"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _toggle_label("Antiflood", settings["flood_on"]),
                    callback_data=f"onbpm:setaf:{_toggle_state(settings['flood_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Warn Limit 3", callback_data=f"onbpm:setwarn:3:{chat_id}"
                ),
                InlineKeyboardButton(
                    "Warn Limit 5", callback_data=f"onbpm:setwarn:5:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "Basic Locks", callback_data=f"onbpm:setlocks:basic:{chat_id}"
                ),
                InlineKeyboardButton(
                    "Strict Locks", callback_data=f"onbpm:setlocks:strict:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    _toggle_label("Anti-Spam", settings["antispam_on"]),
                    callback_data=f"onbpm:setspam:{_toggle_state(settings['antispam_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    _toggle_label("Anti-Channel", settings["antichannel_on"]),
                    callback_data=f"onbpm:setchannel:{_toggle_state(settings['antichannel_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Back to Setup", callback_data=f"onbpm:home:{chat_id}"
                )
            ],
        ]
    )
    return text, keyboard


async def _render_logs(
    client: Client, chat_id: int
) -> Tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    text = (
        "**Setup 5/6: Log Channel**\n\n"
        f"Chat: {title}\n"
        f"Current log channel: `{settings['log_channel'] or 'Not Set'}`\n\n"
        "This step checks the existing `/setlog` flow.\n\n"
        "To connect logs:\n"
        "1. Add me to a channel as admin\n"
        "2. Send `/setlog` in that channel\n"
        "3. Forward that `/setlog` message into your group\n\n"
        "Then tap Refresh here."
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Refresh", callback_data=f"onbpm:logs:{chat_id}")],
            [
                InlineKeyboardButton(
                    "Back to Setup", callback_data=f"onbpm:home:{chat_id}"
                )
            ],
        ]
    )
    return text, keyboard


async def _render_extras(
    client: Client, chat_id: int
) -> Tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    text = (
        "**Setup 6/6: Optional Extras**\n\n"
        f"Chat: {title}\n\n"
        f"- Chatbot: {_bool_text(settings['chatbot_on'])}\n"
        f"- Rankings: {_bool_text(settings['rankings_on'])}\n"
        f"- Notes: {settings['notes_count']} saved\n"
        f"- Filters: {settings['filters_count']} saved\n\n"
        "Useful next steps:\n"
        "- Chatbot lets members reply to my messages\n"
        "- Notes are great for repeat answers\n"
        "- Filters create tiny custom auto-replies\n"
        "- Rankings add lightweight progression"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _toggle_label("Chatbot", settings["chatbot_on"]),
                    callback_data=f"onbpm:setchatbot:{_toggle_state(settings['chatbot_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    _toggle_label("Rankings", settings["rankings_on"]),
                    callback_data=f"onbpm:setrank:{_toggle_state(settings['rankings_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Back to Setup", callback_data=f"onbpm:home:{chat_id}"
                )
            ],
        ]
    )
    return text, keyboard


async def _render_summary(
    client: Client, chat_id: int
) -> Tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    text = (
        "**Setup Summary**\n\n"
        f"Chat: {title}\n\n"
        f"- Welcome: {_bool_text(settings['welcome_on'])}\n"
        f"- Rules: {'Set' if settings['rules_set'] else 'Not Set'}\n"
        f"- Captcha: {_bool_text(settings['captcha_on'])}\n"
        f"- Antiflood: {_bool_text(settings['flood_on'])}\n"
        f"- Warn Limit: {settings['warn_limit']}\n"
        f"- Locks: {_format_locks(settings['locks'])}\n"
        f"- Logs: {settings['log_channel'] or 'Not Set'}\n"
        f"- Chatbot: {_bool_text(settings['chatbot_on'])}\n"
        f"- Rankings: {_bool_text(settings['rankings_on'])}\n\n"
        "That is the 1-minute setup pass. Back in the group, use `Pin Guide` or `Hide in 1h` when you're done."
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Back to Setup", callback_data=f"onbpm:home:{chat_id}"
                )
            ],
        ]
    )
    return text, keyboard


async def _render_setup_screen(client: Client, chat_id: int, screen: str, user_id: int):
    if screen == "permissions":
        return await _render_permissions(client, chat_id, user_id)
    if screen == "presets":
        return await _render_presets(client, chat_id)
    if screen == "welcome":
        return await _render_welcome_rules(client, chat_id)
    if screen == "protection":
        return await _render_protection(client, chat_id)
    if screen == "logs":
        return await _render_logs(client, chat_id)
    if screen == "extras":
        return await _render_extras(client, chat_id)
    if screen == "summary":
        return await _render_summary(client, chat_id)
    return await _render_setup_home(client, chat_id)


async def _render_starter_home(client: Client, chat_id: int):
    title = await _chat_title(client, chat_id)
    rules_text = await get_rules(chat_id)
    text = (
        "**Emilia Starter Guide**\n\n"
        f"You don't need the full help menu to get value in {title}. "
        "These are the few things worth trying first."
    )
    rows = [
        [
            InlineKeyboardButton("Fun", callback_data=f"starterpm:fun:{chat_id}"),
            InlineKeyboardButton("Anime", callback_data=f"starterpm:anime:{chat_id}"),
        ],
        [
            InlineKeyboardButton(
                "Utilities", callback_data=f"starterpm:utilities:{chat_id}"
            ),
            InlineKeyboardButton(
                "Chat With Emilia", callback_data=f"starterpm:chat:{chat_id}"
            ),
        ],
    ]
    if rules_text:
        rows.append(
            [
                InlineKeyboardButton(
                    "Rules",
                    url=f"https://t.me/{BOT_USERNAME}?start=rules_{chat_id}",
                )
            ]
        )
    return text, InlineKeyboardMarkup(rows)


def _starter_back(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Back", callback_data=f"starterpm:home:{chat_id}")]]
    )


async def _render_starter_fun(chat_id: int):
    text = (
        "**Fun**\n\n"
        "Try these:\n"
        "- `/joke`\n"
        "- `/gif cat`\n"
        "- `/truth`\n"
        "- `/dare`\n"
        "- `/q` by replying to a message\n"
        "- `/react`"
    )
    return text, _starter_back(chat_id)


async def _render_starter_anime(chat_id: int):
    text = (
        "**Anime**\n\n"
        "Try these:\n"
        "- `/anime frieren`\n"
        "- `/quote`\n"
        "- `/browse`\n"
        "- `/watch naruto`\n"
        "- `/schedule`"
    )
    return text, _starter_back(chat_id)


async def _render_starter_utilities(chat_id: int):
    text = (
        "**Utilities**\n\n"
        "Try these:\n"
        "- `/id`\n"
        "- `/wiki Emilia`\n"
        "- `/github torvalds`\n"
        "- `/tgm`\n"
        "- `/info`"
    )
    return text, _starter_back(chat_id)


async def _render_starter_chat(chat_id: int):
    enabled = bool(await db.chatbotto.find_one({"chat_id": chat_id}))
    if enabled:
        text = (
            "**Chat With Emilia**\n\n"
            "Reply to one of my messages and I will reply back.\n\n"
            "Admins can turn this off any time with `/chatbot disable`."
        )
    else:
        text = (
            "**Chat With Emilia**\n\n"
            "Reply to one of my messages after admins enable chatbot.\n\n"
            "Admin command:\n"
            "- `/chatbot enable`"
        )
    return text, _starter_back(chat_id)


async def _render_starter_screen(client: Client, chat_id: int, screen: str):
    if screen == "fun":
        return await _render_starter_fun(chat_id)
    if screen == "anime":
        return await _render_starter_anime(chat_id)
    if screen == "utilities":
        return await _render_starter_utilities(chat_id)
    if screen == "chat":
        return await _render_starter_chat(chat_id)
    return await _render_starter_home(client, chat_id)


async def _delete_later(client: Client, chat_id: int, message_id: int, delay: int):
    key = (chat_id, message_id)
    try:
        await asyncio.sleep(delay)
        await client.delete_messages(chat_id, message_id)
    except Exception:
        pass
    finally:
        _cleanup_tasks.pop(key, None)


async def send_group_onboarding(client: Client, chat_id: int):
    has_rules = bool(await get_rules(chat_id))
    text = (
        f"Hi, I'm {BOT_NAME}.\n\n"
        "Thanks for adding me. I'll keep this short: I can welcome new people, protect the group, "
        "keep logs, save notes, and still be fun to use.\n\n"
        "Admins: tap `Set Up Emilia` for a quick setup in PM.\n"
        "Everyone else: tap `Try Emilia` for a short starter guide."
    )
    return await client.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=_group_keyboard(chat_id, has_rules),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def onboarding_redirect(client: Client, message, chat_id: int):
    ok, reason, title, _, _ = await _resolve_setup_access(
        client, message.from_user.id, chat_id
    )
    if not ok:
        await message.reply_text(reason, link_preview_options=LinkPreviewOptions(is_disabled=True))
        return

    await connectDB(message.from_user.id, chat_id)
    text, keyboard = await _render_setup_home(client, chat_id)
    await message.reply_text(text, reply_markup=keyboard, link_preview_options=LinkPreviewOptions(is_disabled=True))


async def starter_redirect(client: Client, message, chat_id: int):
    text, keyboard = await _render_starter_home(client, chat_id)
    await message.reply_text(text, reply_markup=keyboard, link_preview_options=LinkPreviewOptions(is_disabled=True))


@Client.on_callback_query(filters.regex(r"^grpguide:"))
async def group_guide_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.message.chat.type == ChatType.PRIVATE:
        return

    ok, reason, title, _, bot_member = await _resolve_setup_access(
        client, callback_query.from_user.id, callback_query.message.chat.id
    )
    if not ok:
        await callback_query.answer(reason, show_alert=True)
        return

    action = (callback_query.data or "").split(":")[1]
    chat_id = callback_query.message.chat.id
    if action == "pin":
        if not _member_has_priv(bot_member, "can_pin_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_pin_messages"), show_alert=True
            )
            return
        try:
            await client.pin_chat_message(
                chat_id,
                callback_query.message.id,
                disable_notification=True,
            )
            await callback_query.answer("Guide pinned.")
        except Exception:
            await callback_query.answer(
                "I couldn't pin the guide just now. Please try again from the group.",
                show_alert=True,
            )
        return

    key = (chat_id, callback_query.message.id)
    old_task = _cleanup_tasks.get(key)
    if old_task and not old_task.done():
        old_task.cancel()
    _cleanup_tasks[key] = asyncio.create_task(
        _delete_later(client, chat_id, callback_query.message.id, HIDE_LATER_SECONDS)
    )
    await callback_query.answer("I will hide this guide in 1 hour.")


@Client.on_callback_query(filters.regex(r"^onbpm:"))
async def onboarding_pm_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.message.chat.type != ChatType.PRIVATE:
        return

    data = (callback_query.data or "").split(":")
    if len(data) < 3:
        return

    action = data[1]
    chat_id = int(data[-1])
    user_id = callback_query.from_user.id

    privilege = None
    if action in {"setwelcome", "setwarn", "setlocks", "setchannel"}:
        privilege = "can_change_info"
    elif action in {"setcaptcha", "setaf", "setspam"}:
        privilege = "can_restrict_members"

    ok, reason, title, _, bot_member = await _resolve_setup_access(
        client, user_id, chat_id, required_privilege=privilege
    )
    if not ok:
        await callback_query.answer(reason, show_alert=True)
        return

    if action == "applypreset":
        if not _member_has_priv(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        if not _member_has_priv(bot_member, "can_delete_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_delete_messages"), show_alert=True
            )
            return
        preset = data[2]
        result = await _apply_preset(chat_id, preset)
        await callback_query.answer(result)
        text, keyboard = await _render_welcome_rules(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setwelcome":
        enabled = data[2] == "on"
        await SetWelcomeMessageOnOff(chat_id, enabled)
        await callback_query.answer(f"Welcome {_bool_text(enabled)}.")
        text, keyboard = await _render_welcome_rules(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setcaptcha":
        if not _member_has_priv(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        enabled = data[2] == "on"
        await SetCaptcha(chat_id, enabled)
        await callback_query.answer(f"Captcha {_bool_text(enabled)}.")
        text, keyboard = await _render_welcome_rules(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setaf":
        if not _member_has_priv(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        if not _member_has_priv(bot_member, "can_delete_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_delete_messages"), show_alert=True
            )
            return
        enabled = data[2] == "on"
        await _set_antiflood(chat_id, enabled)
        await callback_query.answer(f"Antiflood {_bool_text(enabled)}.")
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setwarn":
        limit_value = int(data[2])
        await set_warn_limit_db(chat_id, limit_value)
        await callback_query.answer(f"Warn limit set to {limit_value}.")
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setlocks":
        if not _member_has_priv(bot_member, "can_delete_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_delete_messages"), show_alert=True
            )
            return
        bundle = data[2]
        await _set_lock_bundle(chat_id, bundle)
        await callback_query.answer(
            "Basic locks applied." if bundle == "basic" else "Strict locks applied."
        )
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setspam":
        if not _member_has_priv(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        enabled = data[2] == "on"
        await _set_antispam(chat_id, enabled)
        await callback_query.answer(f"Anti-Spam {_bool_text(enabled)}.")
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setchannel":
        if not _member_has_priv(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        if not _member_has_priv(bot_member, "can_delete_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_delete_messages"), show_alert=True
            )
            return
        enabled = data[2] == "on"
        await _set_antichannel(chat_id, enabled)
        await callback_query.answer(f"Anti-Channel {_bool_text(enabled)}.")
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setchatbot":
        enabled = data[2] == "on"
        await _set_chatbot(chat_id, enabled)
        await callback_query.answer(f"Chatbot {_bool_text(enabled)}.")
        text, keyboard = await _render_extras(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setrank":
        enabled = data[2] == "on"
        await _set_rankings(chat_id, enabled)
        await callback_query.answer(f"Rankings {_bool_text(enabled)}.")
        text, keyboard = await _render_extras(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    await callback_query.answer()
    text, keyboard = await _render_setup_screen(client, chat_id, action, user_id)
    await _safe_edit(callback_query, text, keyboard)


@Client.on_callback_query(filters.regex(r"^starterpm:"))
async def starter_pm_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.message.chat.type != ChatType.PRIVATE:
        return

    data = (callback_query.data or "").split(":")
    if len(data) < 3:
        return

    action = data[1]
    chat_id = int(data[2])

    await callback_query.answer()
    text, keyboard = await _render_starter_screen(client, chat_id, action)
    await _safe_edit(callback_query, text, keyboard)

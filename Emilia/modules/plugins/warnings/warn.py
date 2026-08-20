from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import BOT_ID
from Emilia.helper.chat_status import can_restrict_member
from Emilia.helper.get_user import get_user_id
from Emilia.modules.plugins.warnings.warn_checker import warn_checker
from Emilia.mongo.warnings_mongo import count_user_warn, warn_db, warn_limit


async def warn(client, message, reason, silent=False, warn_user=None):
    chat_id = message.chat.id

    if message.sender_chat:
        admin_id = message.sender_chat.id

    else:
        admin_id = message.from_user.id

    if warn_user is None:
        user_info = await get_user_id(message)
        user_id = user_info.id
        if user_id == BOT_ID:
            return await message.reply("Bold of you to think I'm gonna warn myself!")

        if not await can_restrict_member(message, user_id):
            return await message.reply(
                "Wish I could warn an admin but sadly enough that isn't technically possible!"
            )

    else:
        user_info = warn_user.from_user
        user_id = warn_user.from_user.id

    await warn_db(chat_id, admin_id, user_id, reason)
    warnchecker, log_msg = await warn_checker(client, message, user_id, silent)

    if (warnchecker is True) or (warnchecker is None):
        return False, log_msg, None

    countuser_warn = await count_user_warn(chat_id, user_id)
    warnlimit = await warn_limit(chat_id)

    import html
    actor_html = f"<a href='tg://user?id={admin_id}'>Admin</a>" if admin_id < 0 else f"<a href='tg://user?id={admin_id}'>{html.escape(message.from_user.first_name)}</a>"
    target_html = f"<a href='tg://user?id={user_id}'>{html.escape(user_info.first_name)}</a>"
    
    warn_text = f"Yep! {target_html} has been warned by {actor_html}!\n• <b>Count:</b> <code>{countuser_warn}/{warnlimit}</code>"
    if reason:
        warn_text += f"\n\n<blockquote expandable>{html.escape(reason)}</blockquote>"

    button = [
        [
            InlineKeyboardButton(
                text="Remove warn (admin only)",
                callback_data=f"warn_{user_id}_{countuser_warn}",
                style=ButtonStyle.DANGER,
            )
        ]
    ]

    if not silent:
        from pyrogram.enums import ParseMode
        await client.send_message(
            message.chat.id, text=warn_text, reply_markup=InlineKeyboardMarkup(button), parse_mode=ParseMode.HTML
        )
    return True, log_msg, user_info

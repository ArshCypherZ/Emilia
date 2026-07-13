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

    warn_text = f"User {user_info.mention} has {countuser_warn}/{warnlimit} warnings; gotta be careful from now on!\n"
    if reason:
        warn_text += f"**Reason:**\n{reason}"

    button = [
        [
            InlineKeyboardButton(
                text="Remove warn (admin only)",
                callback_data=f"warn_{user_id}_{countuser_warn}",
            )
        ]
    ]

    if not silent:
        await client.send_message(
            message.chat.id, text=warn_text, reply_markup=InlineKeyboardMarkup(button)
        )
    return True, log_msg, user_info

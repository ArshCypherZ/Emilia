from pyrogram import Client, filters
from pyrogram.types import CallbackQuery
import re

from Emilia import LOGGER
from Emilia.helper.chat_status import isUserAdmin
from Emilia.mongo.warnings_mongo import remove_warn


@Client.on_callback_query(filters.regex(r"^warn_(\d+)_(\d+)$"), group=1)
async def warn_remove_callback(client: Client, callback_query: CallbackQuery):
    try:
        await callback_query.answer("Processing...")
    except Exception:
        pass

    # Extract ids from callback data
    m = re.match(r"^warn_(\d+)_(\d+)$", callback_query.data or "")
    if not m:
        return
    user_id = int(m.group(1))
    warn_id = int(m.group(2))

    chat_id = callback_query.message.chat.id
    from_user = callback_query.from_user.id
    admin_mention = callback_query.from_user.mention

    if not await isUserAdmin(
        message=callback_query.message, user_id=from_user, chat_id=chat_id, silent=True
    ):
        return await callback_query.answer(text="You're not an admin.", show_alert=True)

    # Use the same client instance handling the update
    user_data = await client.get_users(user_ids=user_id)
    await remove_warn(chat_id, user_id, warn_id)

    await callback_query.message.reply(
        f"Admin {admin_mention} has removed {user_data.mention}'s warning."
    )
    await callback_query.message.delete()
    return

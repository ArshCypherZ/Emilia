from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.helper.get_user import get_user_id
from Emilia.mongo.warnings_mongo import count_user_warn, reset_user_warns


@Client.on_message(
    custom_filter.command(commands=["rmwarns", "resetwarn", "resetwarns"])
)
async def reset_warn(client, message):
    chat_id = message.chat.id

    if not await isUserAdmin(message):
        return

    user_info = await get_user_id(message)
    user_id = user_info.id
    warn_num = await count_user_warn(chat_id, user_id)

    if warn_num is None:
        return await message.reply(
            f"User {user_info.mention} has no warnings to delete! What are you trying to acheive?"
        )

    await message.reply(
        f"User {user_info.mention} has had all their previous warns removed."
    )
    await reset_user_warns(chat_id, user_id)

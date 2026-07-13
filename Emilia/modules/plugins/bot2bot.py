from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from Emilia import custom_filter
from Emilia.helper.bot2bot import execute_approved_bot_command
from Emilia.helper.chat_status import (
    CheckAllAdminsStuffs,
    _status,
    get_chat_member_cached,
)
from Emilia.mongo.bot2bot_mongo import (
    delete_pending_bot_command,
    get_bot2bot_settings,
    get_pending_bot_command,
    set_bot2bot_mode,
    set_bot2bot_skip_review,
)
from Emilia.utils.decorators import anonadmin_checker

BOT2BOT_MODES = {"off", "admin", "all"}
BOT2BOT_TRUE = {"on", "yes", "true"}
BOT2BOT_FALSE = {"off", "no", "false"}


@Client.on_message(custom_filter.command(commands="bot2bot"))
@anonadmin_checker
async def bot2bot(client, message):
    chat_id = message.chat.id
    if not await CheckAllAdminsStuffs(message, privileges="can_change_info"):
        return

    args = message.text.split()
    if len(args) == 1:
        settings = await get_bot2bot_settings(chat_id)
        await message.reply(
            (
                f"Bot-to-bot command mode is `{settings['mode']}`.\n"
                f"Skip review is `{'on' if settings['skip_review'] else 'off'}`."
            ),
            )
        return

    mode = args[1].lower()
    if mode not in BOT2BOT_MODES:
        await message.reply("Choose one of: off/admin/all")
        return

    await set_bot2bot_mode(chat_id, mode)
    await message.reply(f"Bot-to-bot command mode set to `{mode}`.")


@Client.on_message(custom_filter.command(commands="bot2botskipreview"))
@anonadmin_checker
async def bot2botskipreview(client, message):
    chat_id = message.chat.id
    if not await CheckAllAdminsStuffs(message, privileges="can_change_info"):
        return

    args = message.text.split()
    if len(args) == 1:
        settings = await get_bot2bot_settings(chat_id)
        await message.reply(
            f"Bot-to-bot skip review is `{'on' if settings['skip_review'] else 'off'}`.",
            )
        return

    value = args[1].lower()
    if value in BOT2BOT_TRUE:
        skip_review = True
    elif value in BOT2BOT_FALSE:
        skip_review = False
    else:
        await message.reply("Choose one of: on/off/yes/no")
        return

    await set_bot2bot_skip_review(chat_id, skip_review)
    await message.reply(
        f"Bot-to-bot skip review set to `{'on' if skip_review else 'off'}`.",
        )


@Client.on_callback_query(filters.regex(r"^b2b:(ok|no):"))
async def bot2bot_review(client: Client, callback_query: CallbackQuery):
    action, token = callback_query.data.split(":")[1:3]
    chat_id = callback_query.message.chat.id
    member = await get_chat_member_cached(client, chat_id, callback_query.from_user.id)
    if not member or _status(member) not in ("OWNER", "ADMINISTRATOR"):
        await callback_query.answer(
            "Only admins can review bot commands.", show_alert=True
        )
        return

    pending = await get_pending_bot_command(token)
    if not pending:
        await callback_query.answer("This review request has expired.", show_alert=True)
        return
    if pending["chat_id"] != chat_id:
        await callback_query.answer(
            "This review request belongs to another chat.", show_alert=True
        )
        return

    await delete_pending_bot_command(token)
    if action == "no":
        await callback_query.message.edit_text("Bot command rejected.")
        return

    # legacy client_type values are all dispatched through the
    # pyrogram path below; every handler now runs on pyrogram.
    original = await client.get_messages(
        pending["chat_id"],
        pending["message_id"],
    )
    if (
        not original
        or not original.from_user
        or original.from_user.id != pending["bot_id"]
    ):
        await callback_query.message.edit_text("Bot command could not be verified.")
        return

    executed = await execute_approved_bot_command(
        client,
        original,
        reviewer_id=callback_query.from_user.id,
    )
    await callback_query.message.edit_text(
        "Bot command approved and executed."
        if executed
        else "Bot command approved, but no handler accepted it."
    )

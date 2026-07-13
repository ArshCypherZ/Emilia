import inspect
import secrets

from pyrogram import ContinuePropagation, StopPropagation
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.handlers import MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import BOT_ID, LOGGER
from Emilia.helper.chat_status import _status, get_chat_member_cached
from Emilia.mongo.bot2bot_mongo import add_pending_bot_command, get_bot2bot_settings

BOT2BOT_COMMANDS = {"bot2bot", "bot2botskipreview"}


async def bot_command_allowed(message, command_name: str) -> bool:
    sender = getattr(message, "from_user", None)
    if not sender or not getattr(sender, "is_bot", False) or sender.id == BOT_ID:
        return True

    if getattr(message, "_emilia_bot2bot_approved", False):
        return True

    if command_name.lower() in BOT2BOT_COMMANDS:
        return False

    chat = getattr(message, "chat", None)
    if not chat or chat.type == ChatType.PRIVATE:
        return False

    settings = await get_bot2bot_settings(chat.id)
    mode = settings["mode"]
    if mode == "off":
        return False

    if mode == "admin":
        member = await get_chat_member_cached(message._client, chat.id, sender.id)
        if not member or _status(member) not in ("OWNER", "ADMINISTRATOR"):
            return False

    if settings["skip_review"]:
        message._emilia_bot2bot_approved = True
        return True

    token = secrets.token_urlsafe(6)
    await add_pending_bot_command(
        token,
        chat.id,
        message.id,
        sender.id,
        client_type="pyrogram",
        command_name=command_name,
    )
    await message.reply(
        (
            f"Bot command review required for `{command_name}` from "
            f"{sender.mention}."
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Approve",
                        callback_data=f"b2b:ok:{token}",
                        style=ButtonStyle.SUCCESS,
                    ),
                    InlineKeyboardButton(
                        "Reject",
                        callback_data=f"b2b:no:{token}",
                        style=ButtonStyle.DANGER,
                    ),
                ]
            ]
        ),
        )
    return False


async def execute_approved_bot_command(client, message, reviewer_id: int = None):
    message._emilia_bot2bot_approved = True
    if reviewer_id is not None:
        message._emilia_bot2bot_reviewer_id = reviewer_id
    dispatcher = getattr(client, "dispatcher", None)
    if dispatcher is None:
        return False

    for group in dispatcher.groups.values():
        for handler in group:
            if not isinstance(handler, MessageHandler):
                continue
            try:
                if not await handler.check(client, message):
                    continue
                if inspect.iscoroutinefunction(handler.callback):
                    await handler.callback(client, message)
                else:
                    await dispatcher.loop.run_in_executor(
                        client.executor,
                        handler.callback,
                        client,
                        message,
                    )
                return True
            except StopPropagation:
                # Handler explicitly ended propagation after handling the
                # message - this is success, not failure.
                return True
            except ContinuePropagation:
                # Handler wants the next matching handler to run instead.
                continue
            except Exception as exc:
                LOGGER.warning("Approved bot-to-bot command failed: %s", exc)
                return False
    return False

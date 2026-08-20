import io

import orjson
from bson import ObjectId
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import Emilia.strings as strings
from Emilia import LOGGER, db
from Emilia.custom_filter import callbackquery, register
from Emilia.helper.admins import is_owner
from Emilia.modules.plugins.connection.connection import connection
from Emilia.utils.decorators import RATE_LIMIT_SUPER_HEAVY, rate_limit

MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def default(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError


collections = {
    "blocklists": db["blocklists"],
    "disable": db["disable"],
    "filters": db["filters"],
    "locks": db["locks"],
    "notes": db["notes"],
    "rules": db["rules"],
    "warnings": db["warnings"],
    "welcome": db["welcome"],
}


async def _resolve_owner_chat(message, action: str):
    """Resolve the target chat_id for an export/import/reset action and
    verify the caller owns it. Returns chat_id, or None after replying with
    an error (caller should just `return` in that case)."""
    connected = await connection(message)
    chat_id = connected if connected else message.chat.id
    if message.chat.type == ChatType.PRIVATE and not str(chat_id).startswith("-100"):
        await message.reply_text(strings.is_pvt)
        return None

    if not await is_owner(message, message.from_user.id, chat_id):
        await message.reply_text(f"Only the chat owner can {action} settings.")
        return None

    return chat_id


@register(pattern="export")
@rate_limit(RATE_LIMIT_SUPER_HEAVY)
async def export_settings(client, message):
    chat_id = await _resolve_owner_chat(message, "export")
    if chat_id is None:
        return

    args = message.text.split()[1:]

    exported_data = {}
    keys = args if args else collections.keys()
    for key in keys:
        collection = collections.get(key)
        if collection is None:
            continue
        settings = await collection.find_one({"chat_id": chat_id})
        if settings:
            settings.pop("_id", None)
            settings.pop("chat_id", None)
            exported_data[key] = settings

    if not exported_data:
        await message.reply_text("No settings found.")
        return

    settings_json = orjson.dumps(
        exported_data, option=orjson.OPT_INDENT_2, default=default
    )
    buf = io.BytesIO(settings_json)
    buf.name = f"chat_settings_{chat_id}.json"

    await message.reply_document(
        buf,
        caption=f"Exported: {', '.join(exported_data.keys())} ({len(exported_data)} section(s)).",
    )


@register(pattern="import")
@rate_limit(RATE_LIMIT_SUPER_HEAVY)
async def import_settings(client, message):
    chat_id = await _resolve_owner_chat(message, "import")
    if chat_id is None:
        return

    if not message.reply_to_message:
        await message.reply_text("Reply to the JSON file containing settings.")
        return

    reply = message.reply_to_message
    if not reply.document or not (reply.document.file_name or "").endswith(".json"):
        await message.reply_text("Please reply to a valid JSON file.")
        return

    if (reply.document.file_size or 0) > MAX_IMPORT_FILE_SIZE:
        await message.reply_text(
            f"That file is too large to import (max {MAX_IMPORT_FILE_SIZE // (1024 * 1024)} MB)."
        )
        return

    file_obj = await reply.download(in_memory=True)

    try:
        settings = orjson.loads(file_obj.getvalue())
    except orjson.JSONDecodeError:
        await message.reply_text("That file isn't valid JSON.")
        return

    if not isinstance(settings, dict):
        await message.reply_text("Malformed settings file: expected a JSON object.")
        return

    applied = []
    try:
        for key, value in settings.items():
            collection = collections.get(key)
            if collection is None:
                continue
            if not isinstance(value, dict):
                continue
            value = dict(value)
            value.pop("_id", None)
            value["chat_id"] = chat_id
            await collection.update_one(
                {"chat_id": chat_id}, {"$set": value}, upsert=True
            )
            applied.append(key)
    except Exception as exc:
        LOGGER.error(f"import_settings failed for chat {chat_id}: {exc}")
        await message.reply_text("Import failed - the file may be malformed.")
        return

    if not applied:
        await message.reply_text("Nothing recognizable to import in that file.")
        return

    await message.reply_text(f"Settings imported: {', '.join(applied)}.")


@register(pattern="chatreset")
@rate_limit(RATE_LIMIT_SUPER_HEAVY)
async def reset_settings(client, message):
    chat_id = await _resolve_owner_chat(message, "reset")
    if chat_id is None:
        return

    await message.reply_text(
        "This will permanently delete blocklists, filters, locks, notes, rules, warnings and "
        "welcome settings for this chat. Consider running /export first.\n\nContinue?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Confirm reset",
                        callback_data=f"chatreset_yes:{chat_id}",
                        style=ButtonStyle.DANGER,
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Cancel",
                        callback_data="chatreset_no",
                        style=ButtonStyle.PRIMARY,
                    ),
                ],
            ]
        ),
    )


@callbackquery(pattern=r"chatreset_yes:(.*)")
async def _chatreset_confirm(client, query):
    chat_id = int(query.pattern_match.group(1))
    if not await is_owner(query.message, query.from_user.id, chat_id):
        return await query.answer(
            "Only the chat owner can reset settings.", show_alert=True
        )

    for collection in collections.values():
        await collection.delete_one({"chat_id": chat_id})

    await query.answer("Settings reset.")
    await query.message.edit_text("All chat settings have been reset.")


@callbackquery(pattern="chatreset_no")
async def _chatreset_cancel(client, query):
    await query.answer("Cancelled.")
    await query.message.edit_text("Reset cancelled - no changes made.")

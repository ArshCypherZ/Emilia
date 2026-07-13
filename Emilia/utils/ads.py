import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
HANABI_URL = os.getenv("EMILIA_AD_URL", "https://hanabi.works").strip()
ADS_ENABLED = os.getenv("EMILIA_ADS_ENABLED", "true").strip().lower()

AD_FOOTERS = (
    "p.s. building an anime fansite, bot dashboard, or cozy community page? "
    f"Hanabi makes clean little web magic: {HANABI_URL}",
    "tiny Emilia note: pretty projects deserve pretty homes. "
    f"Hanabi can help with websites, UI, and branding: {HANABI_URL}",
    "if your server ever needs a polished website or dashboard, "
    f"Hanabi is very good at making things feel simple and pretty: {HANABI_URL}",
    'for fan projects, startups, and "wait this should look nicer" moments, '
    f"Hanabi builds sweet digital homes: {HANABI_URL}",
    "Emilia's quiet pick for clean websites and product UI: " f"{HANABI_URL}",
    "need a landing page before your project arc gets dramatic? "
    f"Hanabi can make it look main-character ready: {HANABI_URL}",
    "little craft note: Hanabi turns messy ideas into simple, beautiful web things: "
    f"{HANABI_URL}",
)

TRANSIENT_PREFIXES = (
    "checking",
    "collecting",
    "cannot",
    "converting",
    "creating",
    "downloaded to",
    "downloading",
    "error",
    "failed",
    "fetching",
    "give me",
    "generating",
    "i can't",
    "input not found",
    "invalid",
    "logo in a process",
    "looking",
    "no results",
    "nothing given",
    "pinging",
    "please wait",
    "please reply",
    "processing",
    "provide",
    "reply to",
    "reverse searching",
    "restarting",
    "searching",
    "sending please wait",
    "starting",
    "unzipping",
    "uploading",
    "usage",
    "wait",
    "waito",
    "waitoo",
    "wrong",
    "you haven't",
    "you need",
)

TRANSIENT_CONTAINS = (
    "please wait",
    "in a process",
    "now, please wait",
)

_AD_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "emilia_ad_context",
    default=None,
)
_HOOKS_INSTALLED = False


def ads_enabled() -> bool:
    return ADS_ENABLED not in {"0", "false", "no", "off"}


def set_ad_context(chat_id: int | None, is_group: bool):
    return _AD_CONTEXT.set(
        {
            "chat_id": _normalize_chat_id(chat_id),
            "is_group": is_group,
            "used": False,
        }
    )


def reset_ad_context(token) -> None:
    _AD_CONTEXT.reset(token)


def mark_pyrogram_command_message(message, is_group: bool) -> None:
    setattr(message, "_emilia_ad_command", True)
    setattr(message, "_emilia_ad_group", is_group)


async def maybe_append_ad_footer(chat_id: int | str | None, text: str, limit: int):
    ctx = _AD_CONTEXT.get()
    if not _can_use_context(ctx, chat_id) or not _can_ad_text(text):
        return text, False

    day = _today_key()
    footer = _select_footer(ctx["chat_id"], day)
    final_text = f"{text}\n\n{footer}"
    if len(final_text) > limit:
        return text, False

    ctx["used"] = True
    if not await _claim_daily_footer(ctx["chat_id"], day, footer):
        return text, False
    return final_text, True


async def maybe_append_ad_footer_to_pyrogram_message(message, text: str, limit: int):
    if _AD_CONTEXT.get() is not None:
        return await maybe_append_ad_footer(message.chat.id, text, limit)

    if not getattr(message, "_emilia_ad_command", False):
        return text, False

    if getattr(message, "_emilia_ad_done", False):
        return text, False

    token = set_ad_context(
        message.chat.id,
        bool(getattr(message, "_emilia_ad_group", False)),
    )
    try:
        result = await maybe_append_ad_footer(message.chat.id, text, limit)
        if _can_ad_text(text):
            setattr(message, "_emilia_ad_done", True)
        return result
    finally:
        reset_ad_context(token)


def install_ad_hooks() -> None:
    global _HOOKS_INSTALLED

    if _HOOKS_INSTALLED:
        return

    _install_pyrogram_hooks()
    _HOOKS_INSTALLED = True


def _install_pyrogram_hooks() -> None:
    try:
        from pyrogram import Client
        from pyrogram.types import LinkPreviewOptions, Message
    except ImportError:
        return

    original_send_message = Client.send_message
    original_send_photo = Client.send_photo
    original_reply_text = Message.reply_text
    original_reply = Message.reply
    original_reply_photo = Message.reply_photo

    async def send_message(self, chat_id, text, *args, **kwargs):
        text, changed = await maybe_append_ad_footer(chat_id, text, TEXT_LIMIT)
        if changed:
            kwargs["link_preview_options"] = LinkPreviewOptions(is_disabled=True)
        return await original_send_message(self, chat_id, text, *args, **kwargs)

    async def send_photo(self, chat_id, photo, *args, **kwargs):
        caption = kwargs.get("caption")
        if caption is None and args:
            caption = args[0]
        caption, changed = await maybe_append_ad_footer(
            chat_id,
            caption,
            CAPTION_LIMIT,
        )
        if changed:
            if args:
                args = (caption, *args[1:])
            else:
                kwargs["caption"] = caption
        return await original_send_photo(self, chat_id, photo, *args, **kwargs)

    async def reply_text(self, text, *args, **kwargs):
        text, changed = await maybe_append_ad_footer_to_pyrogram_message(
            self,
            text,
            TEXT_LIMIT,
        )
        if changed:
            kwargs["link_preview_options"] = LinkPreviewOptions(is_disabled=True)
        return await original_reply_text(self, text, *args, **kwargs)

    async def reply(self, text, *args, **kwargs):
        text, changed = await maybe_append_ad_footer_to_pyrogram_message(
            self,
            text,
            TEXT_LIMIT,
        )
        if changed:
            kwargs["link_preview_options"] = LinkPreviewOptions(is_disabled=True)
        return await original_reply(self, text, *args, **kwargs)

    async def reply_photo(self, photo, *args, **kwargs):
        caption = kwargs.get("caption")
        caption, changed = await maybe_append_ad_footer_to_pyrogram_message(
            self,
            caption,
            CAPTION_LIMIT,
        )
        if changed:
            kwargs["caption"] = caption
        return await original_reply_photo(self, photo, *args, **kwargs)

    Client.send_message = send_message
    Client.send_photo = send_photo
    Message.reply_text = reply_text
    Message.reply = reply
    Message.reply_photo = reply_photo


# In-memory record of footers already claimed today, so once a chat's daily
# footer is settled we stop round-tripping Mongo on every eligible group send.
# Single-process deployment makes a local set sufficient; the Mongo doc stays
# the source of truth across restarts.
_claimed_today: set[str] = set()
_claimed_day: str | None = None


async def _claim_daily_footer(chat_id: int, day: str, footer: str) -> bool:
    from Emilia import db

    global _claimed_day
    if _claimed_day != day:
        _claimed_today.clear()
        _claimed_day = day

    key = f"{chat_id}:{day}"
    if key in _claimed_today:
        return False

    try:
        result = await db.ad_footers.update_one(
            {"_id": key},
            {
                "$setOnInsert": {
                    "chat_id": chat_id,
                    "day": day,
                    "footer": footer,
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        _claimed_today.add(key)
        return False
    # Remember the outcome either way: claimed by us or already present.
    _claimed_today.add(key)
    return result.upserted_id is not None


def _can_use_context(ctx: dict[str, Any] | None, chat_id: int | str | None) -> bool:
    if not ads_enabled() or not ctx or ctx.get("used") or not ctx.get("is_group"):
        return False

    context_chat_id = ctx.get("chat_id")
    return context_chat_id is not None and context_chat_id == _normalize_chat_id(
        chat_id
    )


def _can_ad_text(text: str | None) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False

    cleaned = _normalize_ad_candidate(text)
    if any(cleaned.startswith(prefix) for prefix in TRANSIENT_PREFIXES):
        return False
    return not any(pattern in cleaned for pattern in TRANSIENT_CONTAINS)


def _select_footer(chat_id: int, day: str) -> str:
    seed = sum(ord(char) for char in f"{chat_id}:{day}")
    return AD_FOOTERS[seed % len(AD_FOOTERS)]


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _normalize_chat_id(chat_id: int | str | None) -> int | None:
    if chat_id is None:
        return None
    try:
        return int(chat_id)
    except (TypeError, ValueError):
        return None


def _normalize_ad_candidate(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = cleaned.strip("`*_~[](){}<>|:;,.!?\"' \n\t\r")
    cleaned = re.sub(r"^[^a-z0-9]+", "", cleaned)
    return cleaned.strip()

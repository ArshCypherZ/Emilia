import html
import itertools
import re
import time
import traceback
from functools import wraps
from typing import List, Optional, Union

import pyrogram
from pyrogram.enums import ChatType
from pyrogram.filters import create
from pyrogram.handlers import CallbackQueryHandler

from Emilia import BOT_USERNAME, DEV_USERS, EVENT_LOGS, LOGGER, pgram
from Emilia.utils.ads import (
    mark_pyrogram_command_message,
    reset_ad_context,
    set_ad_context,
)
from Emilia.utils.metrics import track_command
from Emilia.utils.trace import TRACE_ID

DISABLE_COMMANDS = []

# listen() watchers are raw main-bot-only handlers, not smart-plugin
# discovered — each needs its own group so multiple watchers on the same
# message all get a chance to run (group-limited first-match doesn't block
# other groups, but would block other listen()s sharing a group). Start at
# 1000 to stay clear of the plugins/ tree (group 0 and nearby).
_GROUP_SEQ = itertools.count(1000)

# listen() defers actual pgram.add_handler() calls until flush_pending_handlers()
# runs (after the real event loop is pinned) — see the note near that function.
_PENDING_LISTENERS = []

# "/cmd@BotUsername args" -> command token, mentioned username, rest
_MENTION_RE = re.compile(r"^([/!]\w+)@(\w+)([\s\S]*)$")


def unified_wrapper(func, command_name: str):
    @wraps(func)
    async def wrapper(client, update, *args, **kwargs):
        user = getattr(update, "from_user", None)
        user_id = user.id if user else None

        if command_name in {"callback_query", "inline_query"}:
            message = getattr(update, "message", None)
        else:
            message = update
        chat = getattr(message, "chat", None)
        chat_id = chat.id if chat else None
        message_id = getattr(message, "id", None)

        start_time = time.time()

        trace = f"{chat_id}:{message_id}"
        trace_token = TRACE_ID.set(trace)

        ad_token = set_ad_context(
            chat_id,
            command_name not in {"callback_query", "inline_query"}
            and _is_group_message(message),
        )

        if command_name == "callback_query":
            # Mark so the expired-callback catch-all knows a real handler
            # matched.
            try:
                update._emilia_handled = True
            except Exception:
                pass

        try:
            result = await func(client, update, *args, **kwargs)
        except Exception as e:
            duration = time.time() - start_time
            LOGGER.error(
                "command_error",
                extra={
                    "emilia": {
                        "event": "command_error",
                        "command": command_name,
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "duration": duration,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "trace": trace,
                    }
                },
            )
            try:
                tb = html.escape(traceback.format_exc()[-3500:])
                await pgram.send_message(
                    chat_id=EVENT_LOGS,
                    text=(
                        f"#COMMAND_ERROR\ncommand: {command_name}\n"
                        f"user_id: {user_id}\nchat_id: {chat_id}\n"
                        f"trace: {trace}\n\n<pre>{tb}</pre>"
                    ),
                )
            except Exception:
                LOGGER.warning("command_error: failed to forward traceback to log channel")
            # Best-effort user feedback so the command doesn't just vanish.
            try:
                if command_name == "callback_query":
                    await update.answer("Something went wrong.", show_alert=False)
                elif command_name != "inline_query":
                    await update.reply_text(
                        "Something went wrong running that command — the error has been logged."
                    )
            except Exception:
                pass
            return
        finally:
            reset_ad_context(ad_token)
            TRACE_ID.reset(trace_token)
            await track_command(command_name)

        duration = time.time() - start_time
        # Per-command success is noise at scale: log at DEBUG, but surface slow
        # commands at INFO so latency stays visible.
        payload = {
            "emilia": {
                "event": "command_success",
                "command": command_name,
                "user_id": user_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "duration": duration,
                "trace": trace,
            }
        }
        if duration > 2.0:
            LOGGER.info("command_slow", extra=payload)
        else:
            LOGGER.debug("command_success", extra=payload)
        return result

    return wrapper


def _is_group_message(message) -> bool:
    chat = getattr(message, "chat", None)
    chat_type = getattr(chat, "type", None)
    return chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)


def command_lister(commands: Union[str, List[str]], disable: bool = False) -> None:
    if not disable:
        return
    if isinstance(commands, str):
        DISABLE_COMMANDS.append(commands)
    elif isinstance(commands, list):
        DISABLE_COMMANDS.extend(commands)


def commands_helper(commands: Union[str, List[str]]) -> List[str]:
    if isinstance(commands, str):
        return [commands, f"{commands}@{BOT_USERNAME}"]

    if isinstance(commands, list):
        username_command = []
        for command in commands:
            username_command.append(f"{command}@{BOT_USERNAME}")
            username_command.append(command)
        return username_command

    return []


def command(
    commands: Union[str, List[str]],
    prefixes: Union[str, List[str]] = ["/", "!"],
    case_sensitive: bool = False,
    disable: bool = False,
):
    command_lister(commands, disable)
    commands_list = commands_helper(commands)

    command_re = re.compile(r"([\"'])(.*?)(?<!\\)\1|(\S+)")

    async def func(flt, _, message):
        text = message.text or message.caption
        message.command = None

        if not text:
            return False

        pattern = r"^{}(?:\s|$)" if flt.case_sensitive else r"(?i)^{}(?:\s|$)"

        for prefix in flt.prefixes:
            if not text.startswith(prefix):
                continue

            without_prefix = text[len(prefix) :]

            for cmd in flt.commands:
                if not re.match(pattern.format(re.escape(cmd)), without_prefix):
                    continue

                message.command = [cmd] + [
                    re.sub(r"\\([\"'])", r"\1", m.group(2) or m.group(3) or "")
                    for m in command_re.finditer(without_prefix[len(cmd) :])
                ]
                from Emilia.helper.bot2bot import bot_command_allowed

                if not await bot_command_allowed(message, cmd):
                    return False
                mark_pyrogram_command_message(message, _is_group_message(message))
                return True
        return False

    commands_set = {c if case_sensitive else c.lower() for c in commands_list}

    prefixes = set(prefixes) if prefixes else {""}

    return create(
        func,
        "CommandFilter",
        commands=commands_set,
        prefixes=prefixes,
        case_sensitive=case_sensitive,
    )


def pattern_filter(pattern: str, check_bot2bot: bool = True):
    """Filter reproducing the old Telethon `pattern=` command semantics.

    Matches "/cmd" and "!cmd" (optionally suffixed with @<this bot's
    username>), attaches the regex match to ``message.pattern_match`` so
    handlers can read their arguments from capture groups.
    """
    compiled = re.compile(r"(?i)^(?:/|!)(?:{})\s?(?:\s|$)([\s\S]*)$".format(pattern))
    command_name = str(pattern)

    async def func(flt, client, message):
        text = message.text or message.caption
        if not text:
            return False

        mention = _MENTION_RE.match(text)
        if mention:
            me = getattr(client, "me", None)
            username = (getattr(me, "username", None) or BOT_USERNAME or "").lower()
            if mention.group(2).lower() != username:
                return False
            text = mention.group(1) + mention.group(3)

        match = flt.compiled.match(text)
        if not match:
            return False

        message.pattern_match = match
        if flt.check_bot2bot:
            from Emilia.helper.bot2bot import bot_command_allowed

            if not await bot_command_allowed(message, flt.command_name):
                return False
        mark_pyrogram_command_message(message, _is_group_message(message))
        return True

    return create(
        func,
        "PatternCommand",
        compiled=compiled,
        command_name=command_name,
        check_bot2bot=check_bot2bot,
    )


def callback_pattern_filter(pattern: str):
    """Regex filter over callback_data, attaching ``pattern_match``."""
    compiled = re.compile(pattern)

    async def func(flt, _, query):
        data = query.data
        if data is None:
            return False
        if isinstance(data, bytes):
            data = data.decode("utf-8", "replace")
        match = flt.compiled.match(data)
        if not match:
            return False
        query.pattern_match = match
        return True

    return create(func, "CallbackPattern", compiled=compiled)


def inline_pattern_filter(pattern: str):
    compiled = re.compile(pattern)

    async def func(flt, _, query):
        match = flt.compiled.match(query.query or "")
        if not match:
            return False
        query.pattern_match = match
        return True

    return create(func, "InlinePattern", compiled=compiled)


def _dev_users_filter():
    async def func(_, __, update):
        user = getattr(update, "from_user", None)
        return bool(user and user.id in DEV_USERS)

    return create(func, "DevUsers")


def register(disable: bool = False, **args):
    """Register a command handler. Handlers receive ``(client, message)``.

    Attaches via pyrogram's native ``func.handlers`` mechanism (same as
    ``@Client.on_message(...)``) so smart-plugin discovery picks it up on
    both the main bot and every clone.
    """
    command_pattern = args.get("pattern")
    command_lister(command_pattern, disable)
    filters = pattern_filter(command_pattern)

    def decorator(func):
        wrapped_func = unified_wrapper(func, command_name=str(command_pattern))
        pyrogram.Client.on_message(filters, group=0)(wrapped_func)
        return wrapped_func

    return decorator


def callbackquery(**args):
    """Register a callback-query handler. Handlers receive ``(client, query)``."""
    pattern = args.get("pattern")
    if pattern is None and args.get("data") is not None:
        data = args["data"]
        if isinstance(data, bytes):
            data = data.decode()
        pattern = re.escape(data) + "$"
    filters = callback_pattern_filter(pattern) if pattern else None

    def decorator(func):
        wrapped_func = unified_wrapper(func, command_name="callback_query")
        pyrogram.Client.on_callback_query(filters, group=0)(wrapped_func)
        return wrapped_func

    return decorator


def auth(**args):
    """Register a DEV_USERS-only command handler (new + edited messages)."""
    command_pattern = args.get("pattern")
    filters = pattern_filter(command_pattern, check_bot2bot=False) & _dev_users_filter()

    def decorator(func):
        wrapped_func = unified_wrapper(func, command_name=str(command_pattern))
        pyrogram.Client.on_message(filters, group=0)(wrapped_func)
        pyrogram.Client.on_edited_message(filters, group=0)(wrapped_func)
        return wrapped_func

    return decorator


def InlineQuery(**args):
    pattern = args.get("pattern")
    filters = inline_pattern_filter(pattern) if pattern else None

    def decorator(func):
        wrapped_func = unified_wrapper(func, command_name="inline_query")
        pyrogram.Client.on_inline_query(filters, group=0)(wrapped_func)
        return wrapped_func

    return decorator


def listen(filters=None, name: Optional[str] = None):
    """Register a plain message listener on the main bot only (not clones).

    Kept on the direct add_handler path (not func.handlers/smart-plugin
    discovery) so it never gets picked up when clones scan modules/commands.
    """

    def decorator(func):
        wrapped_func = unified_wrapper(func, command_name=name or func.__name__)
        _PENDING_LISTENERS.append(
            (
                pyrogram.handlers.MessageHandler(wrapped_func, filters),
                next(_GROUP_SEQ),
            )
        )
        return wrapped_func

    return decorator


_EXPIRED_CB_GROUP = 999999


async def _expired_callback_catchall(client, query):
    # Runs after every real callback handler (highest dispatch group). If a real
    # handler already matched this query, it set _emilia_handled; otherwise the
    # button is stale/expired and would otherwise spin forever.
    if getattr(query, "_emilia_handled", False):
        return
    try:
        await query.answer("This button has expired.", cache_time=5)
    except Exception:
        pass


def register_expired_callback_catchall(client):
    client.add_handler(
        CallbackQueryHandler(_expired_callback_catchall, None), group=_EXPIRED_CB_GROUP
    )


# NOTE: do NOT call pgram.add_handler(...) here at import time. Modules under
# Emilia/modules/commands import this file (directly or transitively) during
# plain `import` statements at process start, long before uvloop.run(main())
# creates the real event loop. pgram.loop is a lazy property (see
# pyrogram.Client.loop) that caches whatever asyncio.get_event_loop() returns
# on first access — touching pgram.add_handler() this early pins pgram._loop
# to a throwaway loop that never runs, silently dropping every handler
# registered this way (this is exactly what happened to listen()-based
# watchers, see below). Registration is deferred to flush_pending_handlers(),
# called from __main__.start_pgram() right after pgram.loop is pinned to the
# real running loop.
flush_pending_handlers_called = False


def flush_pending_handlers():
    """Actually register listen()-watchers + the expired-callback catchall.

    Must run after `pgram.loop` has been pinned to the real running loop
    (see start_pgram() in __main__.py) — calling pgram.add_handler() before
    that pins pgram._loop to a dead loop and the handler is silently lost.
    """
    global flush_pending_handlers_called
    if flush_pending_handlers_called:
        return
    flush_pending_handlers_called = True

    for handler, group in _PENDING_LISTENERS:
        pgram.add_handler(handler, group)
    _PENDING_LISTENERS.clear()

    register_expired_callback_catchall(pgram)

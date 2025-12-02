import re
import time
import json
import traceback
from typing import List, Union
from functools import wraps

from pyrogram.filters import create
from telethon import events

from Emilia import BOT_USERNAME, DEV_USERS, telethn, LOGGER

DISABLE_COMMANDS = []
HANDLERS_REGISTRY = [] # List of (handler_func, event_type, args)

def unified_wrapper(func, command_name: str):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Determine client, message/event, user_id for logging
        client = None
        message = None
        user_id = None
        chat_id = None

        try:
            if args:
                if hasattr(args[0], "sender_id"): # Telethon Event
                    client = telethn
                    message = args[0]
                    user_id = message.sender_id
                    chat_id = message.chat_id
                elif hasattr(args[0], "send_message"): # Pyrogram Client
                    client = args[0]
                    if len(args) > 1:
                        message = args[1]
                        user_id = message.from_user.id if message.from_user else None
                        chat_id = message.chat.id
        except Exception:
            pass

        # Logging Start
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
        except Exception as e:
            # Error Handling & Logging
            duration = time.time() - start_time
            log_data = {
                "event": "command_error",
                "command": command_name,
                "user_id": user_id,
                "chat_id": chat_id,
                "duration": duration,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            # Log the error as JSON
            LOGGER.error(json.dumps(log_data))
            return

        # Success Logging
        duration = time.time() - start_time
        log_data = {
            "event": "command_success",
            "command": command_name,
            "user_id": user_id,
            "chat_id": chat_id,
            "duration": duration
        }
        LOGGER.info(json.dumps(log_data))
        return result

    return wrapper


def command_lister(commands: Union[str, List[str]], disable: bool = False) -> list:
    if isinstance(commands, str):
        if disable:
            DISABLE_COMMANDS.append(commands)

    if isinstance(commands, list):
        if disable:
            DISABLE_COMMANDS.extend(commands)


def commands_helper(commands: Union[str, List[str]]) -> List[str]:
    if isinstance(commands, str):
        username_command = f"{commands}@{BOT_USERNAME}"
        return [commands, username_command]

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


def register(disable: bool = False, **args):
    """Registers a new message."""
    command_pattern = args.get("pattern")
    command_lister(command_pattern, disable)

    args["pattern"] = r"(?i)^(?:/|!)(?:{})\s?(?:@Elf_Robot)?(?:\s|$)([\s\S]*)$".format(
        command_pattern
    )

    def decorator(func):
        # Wrap the function with unified logging
        wrapped_func = unified_wrapper(func, command_name=str(command_pattern))
        telethn.add_event_handler(wrapped_func, events.NewMessage(**args))
        HANDLERS_REGISTRY.append((wrapped_func, events.NewMessage, args))
        return wrapped_func

    return decorator


def callbackquery(**args):
    """Registers inline query."""

    def decorator(func):
        # Wrap the function
        wrapped_func = unified_wrapper(func, command_name="callback_query")
        telethn.add_event_handler(wrapped_func, events.CallbackQuery(**args))
        HANDLERS_REGISTRY.append((wrapped_func, events.CallbackQuery, args))
        return wrapped_func

    return decorator


def auth(**args):
    command_pattern = args.get("pattern")
    args["pattern"] = r"(?i)^(?:/|!)(?:{})\s?(?:@Elf_Robot)?(?:\s|$)([\s\S]*)$".format(
        command_pattern
    )
    args["from_users"] = DEV_USERS

    def decorator(func):
        wrapped_func = unified_wrapper(func, command_name=str(command_pattern))
        telethn.add_event_handler(wrapped_func, events.NewMessage(**args))
        telethn.add_event_handler(wrapped_func, events.MessageEdited(**args))
        HANDLERS_REGISTRY.append((wrapped_func, events.NewMessage, args))
        HANDLERS_REGISTRY.append((wrapped_func, events.MessageEdited, args))
        return wrapped_func

    return decorator


def InlineQuery(**args):
    def decorator(func):
        wrapped_func = unified_wrapper(func, command_name="inline_query")
        telethn.add_event_handler(wrapped_func, events.InlineQuery(**args))
        HANDLERS_REGISTRY.append((wrapped_func, events.InlineQuery, args))
        return wrapped_func

    return decorator

def apply_handlers(client):
    """Applies all registered handlers to a new client instance."""
    for func, event_type, args in HANDLERS_REGISTRY:
        client.add_event_handler(func, event_type(**args))
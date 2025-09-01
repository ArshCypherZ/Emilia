import re
from typing import List, Union

from pyrogram.filters import create
from telethon import events

from Emilia import BOT_USERNAME, DEV_USERS, telethn

DISABLE_COMMANDS = []


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
    commands = commands_helper(commands)

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

    commands = commands if isinstance(commands, list) else [commands]
    commands = {c if case_sensitive else c.lower() for c in commands}

    prefixes = set(prefixes) if prefixes else {""}

    return create(
        func,
        "CommandFilter",
        commands=commands,
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
        telethn.add_event_handler(func, events.NewMessage(**args))
        return func

    return decorator


def callbackquery(**args):
    """Registers inline query."""

    def decorator(func):
        telethn.add_event_handler(func, events.CallbackQuery(**args))
        return func

    return decorator


def auth(**args):
    command_pattern = args.get("pattern")
    args["pattern"] = r"(?i)^(?:/|!)(?:{})\s?(?:@Elf_Robot)?(?:\s|$)([\s\S]*)$".format(
        command_pattern
    )
    args["from_users"] = DEV_USERS

    def decorator(func):
        telethn.add_event_handler(func, events.NewMessage(**args))
        telethn.add_event_handler(func, events.MessageEdited(**args))
        return func

    return decorator


def InlineQuery(**args):
    def decorator(func):
        telethn.add_event_handler(func, events.InlineQuery(**args))
        return func

    return decorator

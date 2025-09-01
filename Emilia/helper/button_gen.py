import re

from pyrogram.types import InlineKeyboardButton

BTN_URL_REGEX = re.compile(r"(\[([^\[]+?)\]\(buttonurl:(?:/{0,2})(.+?)(:same)?\))")


def button_markdown_parser(text):
    markdown_note = None
    markdown_note = text
    text_data = ""
    buttons = []
    if markdown_note is None:
        return text_data, buttons
    prev = 0
    for match in BTN_URL_REGEX.finditer(markdown_note):
        n_escapes = 0
        to_check = match.start(1) - 1
        while to_check > 0 and markdown_note[to_check] == "\\":
            n_escapes += 1
            to_check -= 1

        if n_escapes % 2 == 0:
            if bool(match.group(4)) and buttons:
                buttons[-1].append(
                    [InlineKeyboardButton(text=match.group(2), url=match.group(3))]
                )
            else:
                buttons.append(
                    [InlineKeyboardButton(text=match.group(2), url=match.group(3))]
                )
            text_data += markdown_note[prev : match.start(1)]
            prev = match.end(1)
        else:
            text_data += markdown_note[prev:to_check]
            prev = match.start(1) - 1
    else:
        text_data += markdown_note[prev:]

    return text_data, buttons

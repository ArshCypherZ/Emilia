import re

from pyrogram.types import InlineKeyboardButton

BUTTON_STYLES = {"primary", "danger", "success"}
BTN_URL_REGEX = re.compile(
    r"(\[([^\[]+?)\]\(buttonurl(?:#(primary|danger|success))?:(?:/{0,2})(.+?)(:same)?\))",
    flags=re.IGNORECASE,
)


class StyledInlineKeyboardButton(InlineKeyboardButton):
    def __init__(self, *args, style=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.style = style if style in BUTTON_STYLES else None


def _normalize_button_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if re.match(r"(?i)^(https?://|tg://)", url):
        return url
    return f"https://{url}"


def button_has_styles(buttons) -> bool:
    return any(getattr(button, "style", None) for row in buttons for button in row)


def buttons_to_bot_api_markup(buttons):
    inline_keyboard = []
    for row in buttons:
        inline_row = []
        for button in row:
            data = {"text": button.text}
            if getattr(button, "url", None):
                data["url"] = button.url
            if getattr(button, "callback_data", None):
                data["callback_data"] = button.callback_data
            if getattr(button, "style", None):
                data["style"] = button.style
            inline_row.append(data)
        inline_keyboard.append(inline_row)
    return {"inline_keyboard": inline_keyboard}


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
            style = (match.group(3) or "").lower() or None
            url = _normalize_button_url(match.group(4))
            button = StyledInlineKeyboardButton(
                text=match.group(2),
                url=url,
                style=style,
            )
            if bool(match.group(5)) and buttons:
                buttons[-1].append(button)
            else:
                buttons.append([button])
            text_data += markdown_note[prev : match.start(1)]
            prev = match.end(1)
        else:
            text_data += markdown_note[prev:to_check]
            prev = match.start(1) - 1
    else:
        text_data += markdown_note[prev:]

    return text_data, buttons

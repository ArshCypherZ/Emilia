from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.data import HIDDEN_MOD
from Emilia import LOGGER


class EqInlineKeyboardButton(InlineKeyboardButton):
    def __eq__(self, other):
        return self.text == other.text

    def __lt__(self, other):
        return self.text < other.text

    def __gt__(self, other):
        return self.text > other.text


def paginate_modules(_page_n, module_dict, prefix, chat=None):
    if not chat:
        modules = sorted(
            [
                EqInlineKeyboardButton(
                    x.__mod_name__,
                    callback_data="{}_module({})".format(
                        prefix, x.__mod_name__.lower()
                    ),
                )
                for x in module_dict.values()
            ]
        )
    else:
        modules = sorted(
            [
                EqInlineKeyboardButton(
                    x.__mod_name__,
                    callback_data="{}_module({},{})".format(
                        prefix, chat, x.__mod_name__.lower()
                    ),
                )
                for x in module_dict.values()
            ]
        )

    pairs = []
    pair = []

    for module in modules:
        if HIDDEN_MOD.get(module.text.lower()) is None:
            pair.append(module)
            if len(pair) == 3:
                pairs.append(pair)
                pair = []

    if pair:
        pairs.append(pair)

    return InlineKeyboardMarkup(pairs)


async def build_keyboard(buttons):
    keyb = []
    for btn in buttons:
        if btn.same_line and keyb:
            await keyb[-1].append([InlineKeyboardButton(btn.name, url=btn.url)])
        else:
            await keyb.append([InlineKeyboardButton(btn.name, url=btn.url)])

    return keyb


async def revert_buttons(buttons):
    res = ""
    for btn in buttons:
        if btn.same_line:
            res += "\n[{}](buttonurl://{}:same)".format(btn.name, btn.url)
        else:
            res += "\n[{}](buttonurl://{})".format(btn.name, btn.url)

    return res
